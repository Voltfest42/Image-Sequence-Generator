"""Image sequence generation logic (no GUI, no sys.exit)."""

import os
import shutil
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Optional

import cv2
import numpy as np

# --------------------------------------------------------------------------
# Option tables -- the GUI builds its drop-downs from these, so an option that
# is incompatible with the chosen file type is never offered.
# --------------------------------------------------------------------------

FORMATS = {
    "PNG":  {"ext": "png",  "depths": [8, 16], "channels": ["RGB", "RGBA", "BW"]},
    "JPEG": {"ext": "jpeg", "depths": [8],     "channels": ["RGB", "BW"]},
    "EXR":  {"ext": "exr",  "depths": [16, 32], "channels": ["RGB", "RGBA", "BW"]},
}
FILE_TYPES = list(FORMATS)
RESOLUTION_PRESETS = {"8k": 8192, "4k": 4096, "2k": 2048, "1k": 1024}
CUSTOM_RES = "Custom"
ASPECT_PRESETS = ["1:1", "2:1", "1:2", "4:1", "1:4", "4:3", "3:2", "16:9", "9:16", "21:9"]
DEFAULTS = {
    "type": "PNG", "depth": 8, "channels": "RGBA", "color": "#000000",
    "alpha": 100, "aspect": "1:1", "res": "4k",
}
MAX_DIMENSION = 65535
JPEG_QUALITY = 95
PNG_COMPRESSION = 6


def default_depth(file_type: str, current: Optional[int] = None) -> int:
    depths = FORMATS[file_type]["depths"]
    return current if current in depths else depths[0]


def default_channels(file_type: str, current: Optional[str] = None) -> str:
    channels = FORMATS[file_type]["channels"]
    if current in channels:
        return current
    return "RGBA" if "RGBA" in channels else channels[0]


# --------------------------------------------------------------------------
# Settings + parsing
# --------------------------------------------------------------------------

@dataclass
class Settings:
    frames: int
    name: str
    res: str                 # "8k"/"4k"/"2k"/"1k" or "Custom"
    custom_w: int = 0
    custom_h: int = 0
    aspect: str = "1:1"
    file_type: str = "PNG"
    depth: int = 8
    channels: str = "RGBA"
    color: str = "#000000"
    alpha: float = 100.0
    out_dir: str = "output"


def parse_hex(hex_str: str):
    """'#RRGGBB' -> (r, g, b) in 0..1. Raises ValueError."""
    s = hex_str.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        raise ValueError("Color must be a 6-digit hex code, e.g. #FF8800.")
    try:
        return tuple(int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        raise ValueError("Color must be a 6-digit hex code, e.g. #FF8800.") from None


def parse_aspect(text: str):
    try:
        w_s, h_s = text.strip().replace("/", ":").split(":")
        w, h = float(w_s), float(h_s)
    except ValueError:
        raise ValueError("Aspect ratio must look like W:H, e.g. 16:9.") from None
    if w <= 0 or h <= 0:
        raise ValueError("Aspect ratio values must be greater than zero.")
    return w, h


def resolution_label(s: Settings) -> str:
    """Resolution tag used in the file names."""
    return f"{s.custom_w}x{s.custom_h}" if s.res == CUSTOM_RES else s.res


def get_dimensions(s: Settings):
    if s.res == CUSTOM_RES:
        w, h = s.custom_w, s.custom_h
    else:
        base = RESOLUTION_PRESETS[s.res]
        asp_w, asp_h = parse_aspect(s.aspect)
        if asp_w >= asp_h:
            w, h = base, round(base * asp_h / asp_w)
        else:
            w, h = round(base * asp_w / asp_h), base
    if not (1 <= w <= MAX_DIMENSION and 1 <= h <= MAX_DIMENSION):
        raise ValueError(
            f"Resulting size {w}x{h} is out of range (each side must be 1-{MAX_DIMENSION} px)."
        )
    return w, h


def frame_filename(s: Settings, index: int, pad_len: int) -> str:
    ext = FORMATS[s.file_type]["ext"]
    return f"{s.name}_{resolution_label(s)}_{str(index).zfill(pad_len)}.{ext}"


def pad_length(frames: int) -> int:
    return len(str(frames))


_ILLEGAL_NAME_CHARS = set('<>:"/\\|?*')


def validate(s: Settings):
    """Return (width, height). Raises ValueError with a user-readable message."""
    if s.frames < 1:
        raise ValueError("Frames must be at least 1.")
    if not s.name.strip():
        raise ValueError("Name is required.")
    if _ILLEGAL_NAME_CHARS & set(s.name):
        raise ValueError('Name cannot contain any of these characters: < > : " / \\ | ? *')
    fmt = FORMATS.get(s.file_type)
    if fmt is None:
        raise ValueError(f"Unknown file type '{s.file_type}'.")
    if s.depth not in fmt["depths"]:
        raise ValueError(f"{s.file_type} does not support {s.depth}-bit.")
    if s.channels not in fmt["channels"]:
        raise ValueError(f"{s.file_type} does not support {s.channels}.")
    parse_hex(s.color)
    if s.res != CUSTOM_RES and s.res not in RESOLUTION_PRESETS:
        raise ValueError(f"Unknown resolution '{s.res}'.")
    if s.res == CUSTOM_RES and (s.custom_w < 1 or s.custom_h < 1):
        raise ValueError("Enter a custom width and height.")
    if not s.out_dir.strip():
        raise ValueError("Choose an output directory.")
    return get_dimensions(s)


def frame_buffer_bytes(s: Settings, width: int, height: int) -> int:
    """Approximate size of the in-memory image used for encoding."""
    n_ch = {"RGB": 3, "RGBA": 4, "BW": 1}[s.channels]
    bytes_per = {8: 1, 16: 2, 32: 4}[s.depth]
    return width * height * n_ch * bytes_per


# --------------------------------------------------------------------------
# Image creation / encoding
# --------------------------------------------------------------------------

def _pixel_values(s: Settings):
    r, g, b = parse_hex(s.color)
    a = max(0.0, min(100.0, float(s.alpha))) / 100.0
    if s.channels == "BW":
        return [0.299 * r + 0.587 * g + 0.114 * b]
    if s.file_type == "EXR":                      # RGB order
        return [r, g, b] if s.channels == "RGB" else [r, g, b, a]
    return [b, g, r] if s.channels == "RGB" else [b, g, r, a]   # OpenCV: BGR order


def _make_image(s: Settings, width: int, height: int) -> np.ndarray:
    vals = _pixel_values(s)
    if s.file_type == "EXR":
        dtype = np.float16 if s.depth == 16 else np.float32
        pixel = np.array(vals, dtype=dtype)
    elif s.depth == 8:
        dtype = np.uint8
        pixel = np.rint(np.array(vals) * 255).astype(dtype)
    else:
        dtype = np.uint16
        pixel = np.rint(np.array(vals) * 65535).astype(dtype)
    img = np.empty((height, width, len(vals)), dtype=dtype)
    img[:] = pixel
    return img


def _encode_exr(img: np.ndarray, out_dir: str) -> bytes:
    import OpenEXR  # imported lazily: only needed for EXR output

    header = {"compression": OpenEXR.ZIP_COMPRESSION, "type": OpenEXR.scanlineimage}
    n = img.shape[2]
    if n == 1:
        channels = {"Y": np.ascontiguousarray(img[:, :, 0])}
    else:
        channels = {"RGBA" if n == 4 else "RGB": img}
    fd, tmp_path = tempfile.mkstemp(suffix=".exr", dir=out_dir)
    os.close(fd)
    try:
        OpenEXR.File(header, channels).write(tmp_path)
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        os.remove(tmp_path)


def _encode(s: Settings, img: np.ndarray, out_dir: str) -> bytes:
    if s.file_type == "EXR":
        return _encode_exr(img, out_dir)
    if s.file_type == "PNG":
        ok, buf = cv2.imencode(".png", img, [cv2.IMWRITE_PNG_COMPRESSION, PNG_COMPRESSION])
    else:
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        raise RuntimeError("OpenCV failed to encode the image.")
    return buf.tobytes()


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------

def existing_files(s: Settings):
    """Names of frames that already exist in the output folder."""
    if not os.path.isdir(s.out_dir):
        return []
    pad = pad_length(s.frames)
    return [
        n for n in (frame_filename(s, i, pad) for i in range(1, s.frames + 1))
        if os.path.exists(os.path.join(s.out_dir, n))
    ]


def generate(
    s: Settings,
    progress: Callable[[int, int], None] = lambda done, total: None,
    status: Callable[[str], None] = lambda text: None,
    cancel: Optional[threading.Event] = None,
):
    """Write the sequence. Returns (frames_written, seconds, cancelled).

    Every frame is identical, so the image is encoded once and the resulting
    bytes are written out N times; disk speed is the only real limit.
    """
    cancel = cancel or threading.Event()
    width, height = validate(s)
    os.makedirs(s.out_dir, exist_ok=True)
    started = time.perf_counter()

    status(f"Encoding {width}x{height} {s.file_type} ({s.depth}-bit {s.channels})...")
    try:
        img = _make_image(s, width, height)
        data = _encode(s, img, s.out_dir)
    except MemoryError:
        raise RuntimeError(
            "Not enough memory for an image this large. Try a smaller resolution, "
            "a lower bit depth, or fewer channels."
        ) from None
    del img

    needed = len(data) * s.frames
    free = shutil.disk_usage(s.out_dir).free
    if needed > free:
        raise RuntimeError(
            f"Not enough disk space: need about {needed / 1e9:.2f} GB, "
            f"{free / 1e9:.2f} GB free."
        )

    pad = pad_length(s.frames)
    done = 0
    lock = threading.Lock()

    def write_frame(i: int):
        if cancel.is_set():
            return False
        path = os.path.join(s.out_dir, frame_filename(s, i, pad))
        with open(path, "wb") as f:
            f.write(data)
        return True

    status(f"Writing {s.frames} frames to '{s.out_dir}'...")
    progress(0, s.frames)
    workers = min(16, (os.cpu_count() or 4))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for ok in pool.map(write_frame, range(1, s.frames + 1)):
            if ok:
                with lock:
                    done += 1
                    progress(done, s.frames)
    return done, time.perf_counter() - started, cancel.is_set()

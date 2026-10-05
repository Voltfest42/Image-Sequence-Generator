"""Run with:  .venv\\Scripts\\python.exe -m unittest discover -s tests"""

import itertools
import os
import sys
import tempfile
import unittest

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core  # noqa: E402


def make(out_dir, **kw):
    base = dict(frames=3, name="t", res="Custom", custom_w=64, custom_h=32,
                file_type="PNG", depth=8, channels="RGBA", color="#FF8000",
                alpha=50, out_dir=out_dir)
    base.update(kw)
    return core.Settings(**base)


class Dimensions(unittest.TestCase):
    def test_presets_and_aspects(self):
        d = lambda res, asp: core.get_dimensions(core.Settings(1, "x", res, aspect=asp))
        self.assertEqual(d("8k", "1:1"), (8192, 8192))
        self.assertEqual(d("4k", "2:1"), (4096, 2048))
        self.assertEqual(d("2k", "1:4"), (512, 2048))
        self.assertEqual(d("1k", "16:9"), (1024, 576))

    def test_custom_ignores_aspect(self):
        s = core.Settings(1, "x", "Custom", 1280, 720, aspect="1:1")
        self.assertEqual(core.get_dimensions(s), (1280, 720))

    def test_bad_input(self):
        for asp in ("abc", "0:1", "1:0", "-1:2", "1:2:3"):
            with self.assertRaises(ValueError):
                core.get_dimensions(core.Settings(1, "x", "1k", aspect=asp))
        with self.assertRaises(ValueError):
            core.get_dimensions(core.Settings(1, "x", "1k", aspect="1:5000"))


class Options(unittest.TestCase):
    def test_incompatible_combos_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            for kw in (dict(file_type="JPEG", channels="RGBA"), dict(file_type="JPEG", depth=16),
                       dict(file_type="PNG", depth=32), dict(file_type="EXR", depth=8)):
                with self.assertRaises(ValueError, msg=kw):
                    core.validate(make(d, **kw))

    def test_every_listed_combo_validates(self):
        with tempfile.TemporaryDirectory() as d:
            for ft, info in core.FORMATS.items():
                for depth, ch in itertools.product(info["depths"], info["channels"]):
                    core.validate(make(d, file_type=ft, depth=depth, channels=ch))

    def test_defaults_follow_type(self):
        self.assertEqual(core.default_depth("JPEG", 16), 8)
        self.assertEqual(core.default_depth("EXR", 8), 16)
        self.assertEqual(core.default_channels("JPEG", "RGBA"), "RGB")
        self.assertEqual(core.default_channels("EXR", "BW"), "BW")

    def test_name_and_hex(self):
        with tempfile.TemporaryDirectory() as d:
            for kw in (dict(name=""), dict(name="a/b"), dict(color="#12"), dict(color="zzzzzz"),
                       dict(frames=0)):
                with self.assertRaises(ValueError, msg=kw):
                    core.validate(make(d, **kw))


class Output(unittest.TestCase):
    def run_combo(self, read, **kw):
        """Generate a sequence, check the file list, return read(first_file_path)."""
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "sub", "output")
            s = make(out, **kw)
            done, _, cancelled = core.generate(s)
            self.assertEqual((done, cancelled), (s.frames, False))
            names = sorted(os.listdir(out))
            ext = core.FORMATS[s.file_type]["ext"]
            self.assertEqual(names, [f"t_64x32_{i}.{ext}" for i in (1, 2, 3)])
            return read(os.path.join(out, names[0]))

    def test_png_and_jpeg(self):
        for ft in ("PNG", "JPEG"):
            for depth in core.FORMATS[ft]["depths"]:
                for ch in core.FORMATS[ft]["channels"]:
                    img = self.run_combo(lambda p: cv2.imread(p, cv2.IMREAD_UNCHANGED),
                                         file_type=ft, depth=depth, channels=ch)
                    self.assertEqual(img.shape[:2], (32, 64))
                    n = {"RGB": 3, "RGBA": 4, "BW": 1}[ch]
                    self.assertEqual(1 if img.ndim == 2 else img.shape[2], n, (ft, depth, ch))
                    self.assertEqual(img.dtype, np.uint16 if depth == 16 else np.uint8)

    def test_png_values(self):
        read = lambda p: cv2.imread(p, cv2.IMREAD_UNCHANGED)
        img = self.run_combo(read)
        self.assertEqual(tuple(img[0, 0]), (0, 128, 255, 128))   # BGRA, rounded not truncated
        img = self.run_combo(read, depth=16)
        self.assertEqual(tuple(img[0, 0]), (0, 32896, 65535, 32768))

    @staticmethod
    def _exr(path, key):
        import OpenEXR
        chans = OpenEXR.File(path).channels()
        assert list(chans) == [key], list(chans)
        return chans[key].pixels.copy()

    def test_exr_precision_and_channels(self):
        for depth, dt in ((16, np.float16), (32, np.float32)):
            for ch, key, n in (("RGBA", "RGBA", 4), ("RGB", "RGB", 3), ("BW", "Y", 1)):
                px = self.run_combo(lambda p: self._exr(p, key), file_type="EXR",
                                    depth=depth, channels=ch)
                self.assertEqual(px.dtype, dt, (depth, ch))
                self.assertEqual(px.shape[:2], (32, 64))
                if ch == "RGBA":
                    np.testing.assert_allclose(px[0, 0], [1.0, 128 / 255, 0.0, 0.5], atol=1e-3)

    def test_cancel(self):
        import threading
        ev = threading.Event()
        ev.set()
        with tempfile.TemporaryDirectory() as d:
            done, _, cancelled = core.generate(make(d, frames=50), cancel=ev)
            self.assertTrue(cancelled)
            self.assertEqual(done, 0)

    def test_overwrite_detection(self):
        with tempfile.TemporaryDirectory() as d:
            s = make(d, frames=100, padding=3)
            self.assertEqual(core.existing_files(s), [])
            core.generate(s)
            self.assertEqual(len(core.existing_files(s)), 100)
            self.assertIn("t_64x32_001.png", os.listdir(d))
            self.assertIn("t_64x32_100.png", os.listdir(d))


class Padding(unittest.TestCase):
    def name(self, index, **kw):
        return core.frame_filename(make("out", **kw), index)

    def test_explicit_padding(self):
        self.assertEqual([self.name(i, frames=200, padding=4) for i in (1, 23, 134)],
                         ["t_64x32_0001.png", "t_64x32_0023.png", "t_64x32_0134.png"])

    def test_no_padding(self):
        self.assertEqual([self.name(i, frames=100, padding=0) for i in (1, 10, 100)],
                         ["t_64x32_1.png", "t_64x32_10.png", "t_64x32_100.png"])

    def test_padding_never_narrower_than_frame_count(self):
        s = make("out", frames=100, padding=2)
        self.assertEqual(core.effective_padding(s), 3)
        self.assertEqual(core.frame_filename(s, 5), "t_64x32_005.png")

    def test_limits(self):
        with tempfile.TemporaryDirectory() as d:
            core.validate(make(d, padding=core.MAX_PADDING))
            core.validate(make(d, frames=core.MAX_FRAMES))
            for kw in (dict(padding=core.MAX_PADDING + 1), dict(padding=-1),
                       dict(frames=core.MAX_FRAMES + 1)):
                with self.assertRaises(ValueError, msg=kw):
                    core.validate(make(d, **kw))

    def test_unicode_path(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "TextÃºre Ã± æ—¥æœ¬")
            core.generate(make(out))
            self.assertEqual(len(os.listdir(out)), 3)


if __name__ == "__main__":
    unittest.main()


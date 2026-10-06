"""GUI smoke test (needs a display):  .venv\\Scripts\\python.exe tests\\gui_smoke.py"""

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app  # noqa: E402


def pump(a, seconds=0.3):
    end = time.time() + seconds
    while time.time() < end:
        a.update()
        time.sleep(0.01)


def menu_values(menu):
    return list(menu.cget("values"))


a = app.App()
pump(a)

# --- dependent drop-downs -------------------------------------------------
a.type_var.set("JPEG"); a._on_type_change("JPEG")
assert menu_values(a.depth_menu) == ["8-bit"], menu_values(a.depth_menu)
assert menu_values(a.channels_menu) == ["RGB", "BW"]
assert a.channels_var.get() == "RGB"          # RGBA was not valid -> fell back
assert a.alpha_slider.cget("state") == "disabled"

a.type_var.set("EXR"); a._on_type_change("EXR")
assert menu_values(a.depth_menu) == ["16-bit half float", "32-bit float"], menu_values(a.depth_menu)
assert a.depth_var.get() == "16-bit half float"

a.type_var.set("PNG"); a._on_type_change("PNG")
assert menu_values(a.depth_menu) == ["8-bit", "16-bit"]
assert a.channels_var.get() in ("RGB",)       # stays at RGB (was valid)
a.channels_var.set("RGBA"); a._refresh()
assert a.alpha_slider.cget("state") == "normal"

# --- format-specific row (JPEG quality / EXR compression) --------------------
a.type_var.set("PNG"); a._on_type_change("PNG")
assert a.extra_row.winfo_manager() == "" and a.extra_label.winfo_manager() == ""   # hidden for PNG
a.type_var.set("JPEG"); a._on_type_change("JPEG")
assert a.extra_row.winfo_manager() == "grid" and a.jpeg_frame.winfo_manager() == "pack"
assert a.exr_frame.winfo_manager() == "" and a.extra_label.cget("text") == "JPEG quality"
assert a.jpeg_label.cget("text") == "95"
a.jpeg_var.set(40); a._refresh()
assert a.jpeg_label.cget("text") == "40"
a.type_var.set("EXR"); a._on_type_change("EXR")
assert a.exr_frame.winfo_manager() == "pack" and a.jpeg_frame.winfo_manager() == ""
assert a.extra_label.cget("text") == "Compression"
assert menu_values(a.codec_menu) == ["ZIP", "PIZ", "DWAA", "DWAB", "HTJ2K", "ZIPS", "RLE", "PXR24", "None"]
assert a.codec_var.get() == "ZIP" and "Lossless" in a.codec_hint.cget("text")
a.codec_var.set("PXR24"); a.depth_var.set("32-bit float"); a._refresh()
assert "Lossy" in a.codec_hint.cget("text")
a.depth_var.set("16-bit half float"); a._refresh()
assert "Lossless" in a.codec_hint.cget("text")
a.codec_var.set("DWAA"); a._refresh()
assert "Lossy" in a.codec_hint.cget("text")
a.name_var.set("zz"); a.frames_var.set("2"); a.res_var.set("4k")
st = a._collect()
assert (st.exr_codec, st.jpeg_quality, st.file_type) == ("DWAA", 40, "EXR"), st
a.codec_var.set("ZIP"); a.jpeg_var.set(95)
a.name_var.set(""); a.frames_var.set("")
a.type_var.set("PNG"); a._on_type_change("PNG")

# --- numeric-only entries ---------------------------------------------------
def typed(entry, var, text):
    """Type text one character at a time, like a keyboard."""
    var.set("")
    for ch in text:
        entry.insert("end", ch)
    return var.get()

assert typed(a.frames_entry, a.frames_var, "1a2b3-4.5 ") == "12345"
assert typed(a.frames_entry, a.frames_var, "123456789") == "12345"       # length cap
a.frames_entry.delete(0, "end"); a.frames_entry.insert(0, "12ab")         # a paste is rejected whole
assert a.frames_var.get() == "", a.frames_var.get()
assert typed(a.pad_entry, a.pad_var, "0") == ""                           # 1..MAX_PADDING only
assert typed(a.pad_entry, a.pad_var, "9") == ""
assert typed(a.pad_entry, a.pad_var, "x") == ""
assert typed(a.pad_entry, a.pad_var, "12") == "1"                         # single digit only
assert typed(a.pad_entry, a.pad_var, "8") == "8"
a.pad_var.set("4")
a.res_var.set("Custom"); a._refresh()
assert typed(a.cw_entry, a.cw_var, "12ab8") == "128"
a.cw_var.set(""); a.res_var.set("4k"); a._refresh()
a.frames_var.set("")

# --- zero-padding checkbox ---------------------------------------------------
assert a.pad_on_var.get() and a.pad_entry.cget("state") == "normal"
a.pad_on_var.set(False); a._refresh()
assert a.pad_entry.cget("state") == "disabled"
a.pad_on_var.set(True); a._refresh()
a.pad_var.set(""); a.name_var.set("zz"); a.frames_var.set("5")
a._on_go()
assert "padding" in a.status_label.cget("text").lower(), a.status_label.cget("text")
a.pad_var.set("4"); a.name_var.set(""); a.frames_var.set("")

# --- validation messages ---------------------------------------------------
a._on_go(); pump(a, 0.1)
assert "Name is required" in a.status_label.cget("text"), a.status_label.cget("text")
a.name_var.set("mask"); a._on_go()
assert "Frames" in a.status_label.cget("text")
a.frames_var.set("5")
a.res_var.set("Custom"); a._refresh()
a._on_go()
assert "width" in a.status_label.cget("text")
assert a.aspect_box.cget("state") == "disabled"
a.cw_var.set("128"); a.ch_var.set("64")

# --- real run -----------------------------------------------------------
with tempfile.TemporaryDirectory() as d:
    out = os.path.join(d, "output")
    a.out_var.set(out)
    a.type_var.set("EXR"); a._on_type_change("EXR")
    a._on_go()
    assert a.running and a.go_btn.cget("text") == "Cancel"
    for _ in range(100):
        pump(a, 0.1)
        if not a.running:
            break
    print("status:", a.status_label.cget("text"))
    files = sorted(os.listdir(out))
    print(files)
    assert files == [f"mask_128x64_000{i}.exr" for i in range(1, 6)], files   # default: 4 digits
    assert "Done" in a.status_label.cget("text")

a.destroy()
print("GUI smoke test OK")

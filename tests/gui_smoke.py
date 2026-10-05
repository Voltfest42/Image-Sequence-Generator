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
    assert files == [f"mask_128x64_{i}.exr" for i in range(1, 6)], files
    assert "Done" in a.status_label.cget("text")

a.destroy()
print("GUI smoke test OK")

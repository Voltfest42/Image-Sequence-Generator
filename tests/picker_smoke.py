"""Color picker smoke test (needs a display):  .venv\\Scripts\\python.exe tests\\picker_smoke.py [screenshot.png]"""

import os
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app  # noqa: E402
import picker  # noqa: E402


def pump(a, seconds=0.2):
    end = time.time() + seconds
    while time.time() < end:
        a.update()
        time.sleep(0.01)


a = app.App()
pump(a)

# exact round trip: opening and pressing OK must not alter the color
for initial in ("#FF8000", "#000000", "#FFFFFF", "#123456", "#7F7F7F", "#010203"):
    dlg = picker.ColorPicker(a, initial); pump(a, 0.1)
    assert dlg.hex_var.get() == initial, (initial, dlg.hex_var.get())
    dlg._ok(); pump(a, 0.05)
    assert dlg.result == initial, (initial, dlg.result)

dlg = picker.ColorPicker(a, "#FF8000"); pump(a)
assert [v.get() for v in dlg.rgb_vars] == ["255", "128", "0"]

# hex typing updates RGB fields + swatch; short form works
dlg.hex_var.set("#123456"); pump(a, 0.05)
assert [v.get() for v in dlg.rgb_vars] == ["18", "52", "86"]
dlg.hex_var.set("f80"); pump(a, 0.05)
assert dlg.rgb == (255, 136, 0) and dlg.hex_var.get() == "f80"   # field not rewritten mid-typing

# invalid hex: red border, OK refuses to close
dlg.hex_var.set("#12"); pump(a, 0.05)
assert dlg.hex_entry.cget("border_color") == picker.ERROR_COLOR
dlg._ok(); pump(a, 0.05)
assert dlg.result is None and dlg.winfo_exists()

# RGB typing
dlg.hex_var.set("#000000"); pump(a, 0.05)
dlg.rgb_vars[0].set("255"); pump(a, 0.05)
assert dlg.hex_var.get() == "#FF0000", dlg.hex_var.get()
dlg.rgb_vars[1].set("300"); pump(a, 0.05)                         # clamps
assert dlg.rgb == (255, 255, 0)

# square: top-left white, bottom-right black, top-right = pure hue
n = dlg._size - 1
dlg.hex_var.set("#FF8000"); pump(a, 0.05)
hue = dlg.h
dlg._on_sv(SimpleNamespace(x=0, y=0)); assert dlg.rgb == (255, 255, 255)
dlg._on_sv(SimpleNamespace(x=n, y=n)); assert dlg.rgb == (0, 0, 0)
dlg._on_sv(SimpleNamespace(x=n, y=0)); assert dlg.rgb == (255, 128, 0), dlg.rgb
dlg._on_sv(SimpleNamespace(x=-50, y=9999)); assert dlg.rgb == (0, 0, 0)   # drag outside is clamped
assert abs(dlg.h - hue) < 1e-9                                             # hue kept through black

# hue strip: left/right ends are red, middle is cyan
dlg._on_sv(SimpleNamespace(x=n, y=0))
dlg._on_hue(SimpleNamespace(x=0, y=0)); assert dlg.rgb == (255, 0, 0)
dlg._on_hue(SimpleNamespace(x=n // 2, y=0)); assert dlg.rgb[0] == 0 and dlg.rgb[1] > 250 and dlg.rgb[2] > 250

# grey keeps hue instead of snapping to red
dlg._on_hue(SimpleNamespace(x=n // 3, y=0)); h = dlg.h
dlg.hex_var.set("#808080"); pump(a, 0.05)
assert abs(dlg.h - h) < 1e-9

# cancel
dlg.destroy(); pump(a, 0.05)
assert dlg.result is None

# main-window wiring: swatch/Pick open the dialog and the result lands in the hex field
orig = picker.ask_color
picker.ask_color = lambda parent, initial: "#ABCDEF"
a._pick_color(); assert a.color_var.get() == "#ABCDEF"
picker.ask_color = lambda parent, initial: None
a._pick_color(); assert a.color_var.get() == "#ABCDEF"                     # cancel leaves it alone
picker.ask_color = orig

if len(sys.argv) > 1:       # optional screenshot of the dialog for eyeballing
    from PIL import ImageGrab
    dlg = picker.ColorPicker(a, "#E8793A"); pump(a, 0.6)
    ImageGrab.grab().save(sys.argv[1])
    dlg.destroy(); pump(a, 0.1)

a.destroy()
print("picker smoke test OK")

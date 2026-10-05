"""Modern color picker dialog for CustomTkinter: SV square, hue strip, hex + RGB fields."""

import colorsys
import re
import tkinter as tk
from typing import Optional

import customtkinter as ctk
import numpy as np
from PIL import Image, ImageTk

SQUARE = 240          # logical (unscaled) pixel sizes
STRIP_H = 20
MARKER_R = 8
_HEX_RE = re.compile(r"#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})")
ERROR_COLOR = "#e5484d"


def _to_hex(rgb) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def _parse_hex(text: str):
    m = _HEX_RE.fullmatch(text.strip())
    if not m:
        return None
    h = m.group(1)
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _sv_image(hue: float, size: int) -> Image.Image:
    """Saturation (x) / brightness (y) square for one hue."""
    base = np.array(colorsys.hsv_to_rgb(hue, 1.0, 1.0))
    s = np.linspace(0, 1, size)[None, :, None]
    v = np.linspace(1, 0, size)[:, None, None]
    rgb = v * ((1 - s) + s * base[None, None, :])
    return Image.fromarray(np.rint(rgb * 255).astype(np.uint8), "RGB")


def _hue_image(width: int, height: int) -> Image.Image:
    cols = [colorsys.hsv_to_rgb(x / max(width - 1, 1), 1.0, 1.0) for x in range(width)]
    row = np.rint(np.array(cols) * 255).astype(np.uint8)[None, :, :]
    return Image.fromarray(np.repeat(row, height, axis=0), "RGB")


class ColorPicker(ctk.CTkToplevel):
    def __init__(self, parent, initial: str = "#000000", title: str = "Choose color"):
        super().__init__(parent)
        self.result: Optional[str] = None
        self.title(title)
        self.resizable(False, False)
        self.withdraw()  # position before showing, to avoid a flash in the corner

        self._scale = self._get_window_scaling()
        self._size = int(SQUARE * self._scale)
        self._strip_h = int(STRIP_H * self._scale)
        self._updating = False
        self._original = _parse_hex(initial) or (0, 0, 0)

        self.rgb = self._original
        h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in self.rgb))
        self.h, self.s, self.v = h, s, v

        self._build()
        self._refresh(redraw_square=False)   # square was already drawn for the initial hue

        self.bind("<Return>", lambda _e: self._ok())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.transient(parent)
        self._center_on(parent)
        self.deiconify()
        self.after(50, self._grab)

    # ----------------------------------------------------------------- build

    def _grab(self):
        try:
            self.lift()
            self.grab_set()
            self.hex_entry.focus_set()
        except tk.TclError:
            pass

    def _center_on(self, parent):
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _build(self):
        bg = self._apply_appearance_mode(self.cget("fg_color"))
        pad = 20
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=0, column=0, padx=pad, pady=pad)

        # saturation / brightness square
        self._sv_photo = ImageTk.PhotoImage(_sv_image(self.h, self._size))
        self.sv_canvas = tk.Canvas(body, width=self._size, height=self._size, bg=bg,
                                   highlightthickness=0, cursor="crosshair")
        self.sv_canvas.grid(row=0, column=0, columnspan=2)
        self._sv_img_id = self.sv_canvas.create_image(0, 0, anchor="nw", image=self._sv_photo)
        self._sv_ring_out = self.sv_canvas.create_oval(0, 0, 0, 0, outline="#000000", width=2)
        self._sv_ring_in = self.sv_canvas.create_oval(0, 0, 0, 0, outline="#ffffff", width=2)
        for seq in ("<Button-1>", "<B1-Motion>"):
            self.sv_canvas.bind(seq, self._on_sv)

        # hue strip
        self._hue_photo = ImageTk.PhotoImage(_hue_image(self._size, self._strip_h))
        self.hue_canvas = tk.Canvas(body, width=self._size, height=self._strip_h + 4, bg=bg,
                                    highlightthickness=0, cursor="sb_h_double_arrow")
        self.hue_canvas.grid(row=1, column=0, columnspan=2, pady=(12, 0))
        self.hue_canvas.create_image(0, 2, anchor="nw", image=self._hue_photo)
        self._hue_out = self.hue_canvas.create_rectangle(0, 0, 0, 0, outline="#000000", width=2)
        self._hue_in = self.hue_canvas.create_rectangle(0, 0, 0, 0, outline="#ffffff", width=1)
        for seq in ("<Button-1>", "<B1-Motion>"):
            self.hue_canvas.bind(seq, self._on_hue)

        # preview (old | new) and hex
        info = ctk.CTkFrame(body, fg_color="transparent")
        info.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(16, 0))
        prev = ctk.CTkFrame(info, fg_color="transparent")
        prev.pack(side="left")
        self.old_swatch = ctk.CTkFrame(prev, width=44, height=44, corner_radius=8,
                                       fg_color=_to_hex(self._original))
        self.old_swatch.pack(side="left")
        self.new_swatch = ctk.CTkFrame(prev, width=44, height=44, corner_radius=8)
        self.new_swatch.pack(side="left", padx=(6, 0))
        self.old_swatch.pack_propagate(False)
        self.new_swatch.pack_propagate(False)
        ctk.CTkLabel(info, text="Hex", width=34, anchor="e").pack(side="left", padx=(14, 6))
        self.hex_var = tk.StringVar()
        self.hex_entry = ctk.CTkEntry(info, textvariable=self.hex_var, width=100)
        self.hex_entry.pack(side="left")
        self._default_border = self.hex_entry.cget("border_color")
        self.hex_var.trace_add("write", lambda *_: self._on_hex())

        # RGB fields
        rgb_row = ctk.CTkFrame(body, fg_color="transparent")
        rgb_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        self.rgb_vars, self.rgb_entries = [], []
        check = self.register(lambda p: re.fullmatch(r"\d{0,3}", p) is not None)
        for i, name in enumerate("RGB"):
            ctk.CTkLabel(rgb_row, text=name, width=16).pack(side="left", padx=(0 if i == 0 else 10, 4))
            var = tk.StringVar()
            e = ctk.CTkEntry(rgb_row, textvariable=var, width=56, justify="center",
                             validate="key", validatecommand=(check, "%P"))
            e.pack(side="left")
            var.trace_add("write", lambda *_: self._on_rgb())
            self.rgb_vars.append(var)
            self.rgb_entries.append(e)

        # buttons
        btns = ctk.CTkFrame(body, fg_color="transparent")
        btns.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(20, 0))
        btns.grid_columnconfigure((0, 1), weight=1, uniform="b")
        ctk.CTkButton(btns, text="Cancel", height=34, fg_color=("gray70", "gray30"),
                      hover_color=("gray60", "gray40"), command=self.destroy
                      ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(btns, text="OK", height=34, command=self._ok
                      ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

    # ----------------------------------------------------------------- state

    @staticmethod
    def _clamp(value, lo, hi):
        return max(lo, min(hi, value))

    def _set_hsv(self, h=None, s=None, v=None, redraw_square=True):
        self.h = self.h if h is None else h
        self.s = self.s if s is None else s
        self.v = self.v if v is None else v
        self.rgb = tuple(round(c * 255) for c in colorsys.hsv_to_rgb(self.h, self.s, self.v))
        self._refresh(redraw_square)

    def _set_rgb(self, rgb):
        self.rgb = rgb
        h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
        if s > 0 and v > 0:          # keep the hue for greys/black so it doesn't jump
            self.h = h
        self.s, self.v = s, v
        self._refresh(redraw_square=True)

    def _refresh(self, redraw_square: bool = True):
        """Bring every widget in line with the current color."""
        if redraw_square:
            self._sv_photo.paste(_sv_image(self.h, self._size))

        n = self._size - 1
        x, y = self.s * n, (1 - self.v) * n
        r = MARKER_R * self._scale
        self.sv_canvas.coords(self._sv_ring_out, x - r, y - r, x + r, y + r)
        self.sv_canvas.coords(self._sv_ring_in, x - r + 2, y - r + 2, x + r - 2, y + r - 2)
        hx = self.h * n
        self.hue_canvas.coords(self._hue_out, hx - 4, 1, hx + 4, self._strip_h + 3)
        self.hue_canvas.coords(self._hue_in, hx - 3, 2, hx + 3, self._strip_h + 2)
        self.new_swatch.configure(fg_color=_to_hex(self.rgb))

        # Only rewrite a text field if it doesn't already mean this color, so the
        # field being typed in ("#f80", "05") isn't reformatted under the cursor.
        self._updating = True
        try:
            if _parse_hex(self.hex_var.get()) != self.rgb:
                self.hex_var.set(_to_hex(self.rgb))
            self.hex_entry.configure(border_color=self._default_border)
            for var, c in zip(self.rgb_vars, self.rgb):
                text = var.get()
                if not (text.isdigit() and int(text) == c):
                    var.set(str(c))
        finally:
            self._updating = False

    def _on_sv(self, event):
        n = self._size - 1
        self._set_hsv(s=self._clamp(event.x / n, 0, 1),
                      v=1 - self._clamp(event.y / n, 0, 1), redraw_square=False)

    def _on_hue(self, event):
        self._set_hsv(h=self._clamp(event.x / (self._size - 1), 0, 1))

    def _on_hex(self):
        if self._updating:
            return
        rgb = _parse_hex(self.hex_var.get())
        if rgb is None:
            self.hex_entry.configure(border_color=ERROR_COLOR)
        else:
            self._set_rgb(rgb)

    def _on_rgb(self):
        if self._updating:
            return
        try:
            vals = [int(v.get()) for v in self.rgb_vars]
        except ValueError:
            return                      # a field is empty; wait for the user to finish typing
        self._set_rgb(tuple(self._clamp(v, 0, 255) for v in vals))

    def _ok(self):
        if _parse_hex(self.hex_var.get()) is None:
            return                      # hex field holds something invalid; keep the dialog open
        self.result = _to_hex(self.rgb)
        self.destroy()


def ask_color(parent, initial: str = "#000000") -> Optional[str]:
    """Show the picker modally; returns '#RRGGBB' or None if cancelled."""
    dlg = ColorPicker(parent, initial)
    parent.wait_window(dlg)
    return dlg.result

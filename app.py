"""Image Sequence Generator -- desktop GUI."""

import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox

import customtkinter as ctk

import core

APP_TITLE = "Image Sequence Generator"
ERROR_COLOR = "#e5484d"
OK_COLOR = "#30a46c"


def app_dir() -> str:
    """Folder next to the .exe when frozen, otherwise next to this script."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def depth_label(file_type: str, depth: int) -> str:
    if file_type == "EXR":
        return f"{depth}-bit " + ("half float" if depth == 16 else "float")
    return f"{depth}-bit"


def depth_from_label(label: str) -> int:
    return int(label.split("-")[0])


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")
        self.title(APP_TITLE)
        self.resizable(False, False)
        self._set_icon()

        self.msgs: "queue.Queue[tuple]" = queue.Queue()
        self.cancel_event = threading.Event()
        self.running = False
        self._default_border = None

        self._build_ui()
        self._on_type_change(core.DEFAULTS["type"])
        self._refresh()
        self.after(50, self._poll)

    # ------------------------------------------------------------------ UI

    def _set_icon(self):
        path = resource_path(os.path.join("assets", "icon.ico"))
        if os.path.exists(path):
            # CTk installs its own icon ~200 ms after start-up; override it afterwards.
            self.after(250, lambda: self.iconbitmap(path))

    def _build_ui(self):
        pad = {"padx": (0, 12), "pady": 5}
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=0, column=0, padx=22, pady=(18, 8), sticky="nsew")
        body.grid_columnconfigure(1, weight=1)
        self.body = body

        def label(row, text):
            ctk.CTkLabel(body, text=text, anchor="w").grid(row=row, column=0, sticky="w", **pad)

        # Name
        label(0, "Name *")
        self.name_var = tk.StringVar()
        self.name_entry = ctk.CTkEntry(body, textvariable=self.name_var, placeholder_text="e.g. mask")
        self.name_entry.grid(row=0, column=1, columnspan=2, sticky="ew", pady=5)
        self._default_border = self.name_entry.cget("border_color")

        # Frames
        label(1, "Frames *")
        self.frames_var = tk.StringVar()
        self.frames_entry = ctk.CTkEntry(body, textvariable=self.frames_var, width=110,
                                         placeholder_text="e.g. 100")
        self.frames_entry.grid(row=1, column=1, sticky="w", pady=5)

        # Resolution (+ custom W x H)
        label(2, "Resolution")
        res_row = ctk.CTkFrame(body, fg_color="transparent")
        res_row.grid(row=2, column=1, columnspan=2, sticky="w", pady=5)
        self.res_var = tk.StringVar(value=core.DEFAULTS["res"])
        self.res_menu = ctk.CTkOptionMenu(
            res_row, variable=self.res_var, width=110,
            values=list(core.RESOLUTION_PRESETS) + [core.CUSTOM_RES],
            command=lambda _v: self._refresh())
        self.res_menu.pack(side="left")
        self.custom_frame = ctk.CTkFrame(res_row, fg_color="transparent")
        self.cw_var, self.ch_var = tk.StringVar(), tk.StringVar()
        self.cw_entry = ctk.CTkEntry(self.custom_frame, textvariable=self.cw_var, width=70,
                                     placeholder_text="width")
        self.ch_entry = ctk.CTkEntry(self.custom_frame, textvariable=self.ch_var, width=70,
                                     placeholder_text="height")
        self.cw_entry.pack(side="left", padx=(12, 0))
        ctk.CTkLabel(self.custom_frame, text="×", width=18).pack(side="left")
        self.ch_entry.pack(side="left")
        ctk.CTkLabel(self.custom_frame, text="px", width=24).pack(side="left")

        # Aspect ratio
        label(3, "Aspect ratio")
        self.aspect_var = tk.StringVar(value=core.DEFAULTS["aspect"])
        self.aspect_box = ctk.CTkComboBox(body, variable=self.aspect_var, width=110,
                                          values=core.ASPECT_PRESETS,
                                          command=lambda _v: self._refresh())
        self.aspect_box.grid(row=3, column=1, sticky="w", pady=5)

        # File type / depth / channels
        label(4, "File type")
        self.type_var = tk.StringVar(value=core.DEFAULTS["type"])
        self.type_menu = ctk.CTkOptionMenu(body, variable=self.type_var, width=150,
                                           values=core.FILE_TYPES, command=self._on_type_change)
        self.type_menu.grid(row=4, column=1, sticky="w", pady=5)

        label(5, "Color depth")
        self.depth_var = tk.StringVar()
        self.depth_menu = ctk.CTkOptionMenu(body, variable=self.depth_var, width=150, values=[""],
                                            command=lambda _v: self._refresh())
        self.depth_menu.grid(row=5, column=1, sticky="w", pady=5)

        label(6, "Channels")
        self.channels_var = tk.StringVar()
        self.channels_menu = ctk.CTkOptionMenu(body, variable=self.channels_var, width=150,
                                               values=[""], command=lambda _v: self._refresh())
        self.channels_menu.grid(row=6, column=1, sticky="w", pady=5)

        # Color
        label(7, "Color")
        color_row = ctk.CTkFrame(body, fg_color="transparent")
        color_row.grid(row=7, column=1, columnspan=2, sticky="w", pady=5)
        self.color_var = tk.StringVar(value=core.DEFAULTS["color"])
        self.swatch = ctk.CTkButton(color_row, text="", width=44, height=28, border_width=1,
                                    border_color=("gray60", "gray40"),
                                    fg_color=core.DEFAULTS["color"],
                                    hover=False, command=self._pick_color)
        self.swatch.pack(side="left")
        self.hex_entry = ctk.CTkEntry(color_row, textvariable=self.color_var, width=100)
        self.hex_entry.pack(side="left", padx=10)
        ctk.CTkButton(color_row, text="Pick...", width=70, command=self._pick_color).pack(side="left")

        # Alpha
        label(8, "Alpha")
        alpha_row = ctk.CTkFrame(body, fg_color="transparent")
        alpha_row.grid(row=8, column=1, columnspan=2, sticky="ew", pady=5)
        self.alpha_var = tk.DoubleVar(value=core.DEFAULTS["alpha"])
        self.alpha_slider = ctk.CTkSlider(alpha_row, from_=0, to=100, number_of_steps=100,
                                          variable=self.alpha_var, width=230,
                                          command=lambda _v: self._refresh())
        self.alpha_slider.pack(side="left")
        self.alpha_label = ctk.CTkLabel(alpha_row, text="100", width=90, anchor="w")
        self.alpha_label.pack(side="left", padx=10)

        # Output directory
        label(9, "Output folder")
        out_row = ctk.CTkFrame(body, fg_color="transparent")
        out_row.grid(row=9, column=1, columnspan=2, sticky="ew", pady=5)
        out_row.grid_columnconfigure(0, weight=1)
        self.out_var = tk.StringVar(value=os.path.join(app_dir(), "output"))
        self.out_entry = ctk.CTkEntry(out_row, textvariable=self.out_var)
        self.out_entry.grid(row=0, column=0, sticky="ew")
        self.browse_btn = ctk.CTkButton(out_row, text="Browse...", width=80, command=self._browse)
        self.browse_btn.grid(row=0, column=1, padx=(8, 0))

        # Summary / action area
        self.info_label = ctk.CTkLabel(self, text="", anchor="w", justify="left", wraplength=520,
                                       text_color=("gray35", "gray65"))
        self.info_label.grid(row=1, column=0, padx=22, pady=(4, 0), sticky="ew")

        action = ctk.CTkFrame(self, fg_color="transparent")
        action.grid(row=2, column=0, padx=22, pady=(10, 4), sticky="ew")
        action.grid_columnconfigure(0, weight=1)
        self.go_btn = ctk.CTkButton(action, text="Generate", height=36, command=self._on_go)
        self.go_btn.grid(row=0, column=0, sticky="ew")
        self.open_btn = ctk.CTkButton(action, text="Open folder", height=36, width=110,
                                      fg_color=("gray70", "gray30"), hover_color=("gray60", "gray40"),
                                      command=self._open_folder)
        self.open_btn.grid(row=0, column=1, padx=(8, 0))

        self.progress = ctk.CTkProgressBar(self)
        self.progress.set(0)
        self.progress.grid(row=3, column=0, padx=22, pady=(8, 2), sticky="ew")
        self.status_label = ctk.CTkLabel(self, text="", anchor="w", justify="left", wraplength=520)
        self.status_label.grid(row=4, column=0, padx=22, pady=(2, 16), sticky="ew")
        self.grid_columnconfigure(0, weight=1)

        for var in (self.name_var, self.frames_var, self.cw_var, self.ch_var,
                    self.aspect_var, self.color_var, self.out_var):
            var.trace_add("write", lambda *_: self._refresh())

    # ------------------------------------------------------- dependent state

    def _on_type_change(self, file_type: str):
        """Rebuild depth/channel menus so only valid options are listed."""
        fmt = core.FORMATS[file_type]
        try:
            cur_depth = depth_from_label(self.depth_var.get())
        except ValueError:
            cur_depth = core.DEFAULTS["depth"]
        depth = core.default_depth(file_type, cur_depth)
        self.depth_menu.configure(values=[depth_label(file_type, d) for d in fmt["depths"]])
        self.depth_var.set(depth_label(file_type, depth))

        channels = core.default_channels(file_type, self.channels_var.get() or core.DEFAULTS["channels"])
        self.channels_menu.configure(values=fmt["channels"])
        self.channels_var.set(channels)
        self._refresh()

    def _refresh(self):
        """Re-evaluate enabled/visible widgets and the summary line."""
        custom = self.res_var.get() == core.CUSTOM_RES
        if custom:
            self.custom_frame.pack(side="left")
        else:
            self.custom_frame.pack_forget()

        is_rgba = self.channels_var.get() == "RGBA"
        busy = self.running
        normal = "disabled" if busy else "normal"

        self.aspect_box.configure(state="disabled" if (busy or custom) else "normal")
        self.alpha_slider.configure(state="normal" if (is_rgba and not busy) else "disabled")
        alpha = int(round(self.alpha_var.get()))
        self.alpha_label.configure(text=str(alpha) if is_rgba else "(RGBA only)")

        for w in (self.name_entry, self.frames_entry, self.cw_entry, self.ch_entry,
                  self.hex_entry, self.out_entry):
            w.configure(state=normal)
        for w in (self.res_menu, self.type_menu, self.depth_menu, self.channels_menu,
                  self.swatch, self.browse_btn):
            w.configure(state=normal)

        # swatch follows the hex field when it holds a valid color
        try:
            r, g, b = core.parse_hex(self.color_var.get())
            self.swatch.configure(fg_color="#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255)))
        except ValueError:
            pass

        for w in (self.name_entry, self.frames_entry, self.cw_entry, self.ch_entry,
                  self.hex_entry, self.out_entry):
            w.configure(border_color=self._default_border)

        self.open_btn.configure(state="normal" if os.path.isdir(self._resolve_out()) else "disabled")
        self._update_info()

    def _resolve_out(self) -> str:
        p = self.out_var.get().strip() or "output"
        return p if os.path.isabs(p) else os.path.join(app_dir(), p)

    def _update_info(self):
        try:
            s = self._collect(flag=False)
            w, h = core.validate(s)
            pad = core.pad_length(s.frames)
            first, last = core.frame_filename(s, 1, pad), core.frame_filename(s, s.frames, pad)
            names = first if s.frames == 1 else f"{first} … {last}"
            mem = core.frame_buffer_bytes(s, w, h) / (1024 ** 2)
            mem_txt = f"{mem / 1024:.1f} GB" if mem >= 1024 else f"{mem:.0f} MB"
            self.info_label.configure(
                text=f"{w} × {h} px · {s.frames} frame{'s' if s.frames != 1 else ''}\n"
                     f"{names}\nUses about {mem_txt} of memory while encoding.")
        except ValueError:
            self.info_label.configure(text="")

    # ---------------------------------------------------------------- inputs

    def _flag(self, widget):
        widget.configure(border_color=ERROR_COLOR)
        widget.focus_set()

    def _collect(self, flag: bool = True) -> core.Settings:
        """Read the form into Settings; raises ValueError (and highlights the bad field)."""
        def fail(widget, msg):
            if flag:
                self._flag(widget)
            raise ValueError(msg)

        name = self.name_var.get().strip()
        if not name:
            fail(self.name_entry, "Name is required.")

        frames_txt = self.frames_var.get().strip()
        if not frames_txt.isdigit() or int(frames_txt) < 1:
            fail(self.frames_entry, "Frames is required and must be a whole number of at least 1.")

        res = self.res_var.get()
        cw = ch = 0
        if res == core.CUSTOM_RES:
            if not self.cw_var.get().strip().isdigit():
                fail(self.cw_entry, "Custom width must be a whole number of pixels.")
            if not self.ch_var.get().strip().isdigit():
                fail(self.ch_entry, "Custom height must be a whole number of pixels.")
            cw, ch = int(self.cw_var.get()), int(self.ch_var.get())
        else:
            try:
                core.parse_aspect(self.aspect_var.get())
            except ValueError as e:
                fail(self.aspect_box, str(e))

        try:
            core.parse_hex(self.color_var.get())
        except ValueError as e:
            fail(self.hex_entry, str(e))

        file_type = self.type_var.get()
        return core.Settings(
            frames=int(frames_txt), name=name, res=res, custom_w=cw, custom_h=ch,
            aspect=self.aspect_var.get(), file_type=file_type,
            depth=depth_from_label(self.depth_var.get()), channels=self.channels_var.get(),
            color=self.color_var.get(), alpha=self.alpha_var.get(), out_dir=self._resolve_out(),
        )

    def _pick_color(self):
        try:
            initial = "#%02x%02x%02x" % tuple(round(c * 255) for c in core.parse_hex(self.color_var.get()))
        except ValueError:
            initial = core.DEFAULTS["color"]
        _rgb, hex_code = colorchooser.askcolor(color=initial, parent=self, title="Choose color")
        if hex_code:
            self.color_var.set(hex_code.upper())

    def _browse(self):
        start = self._resolve_out()
        while start and not os.path.isdir(start):
            start = os.path.dirname(start)
        chosen = filedialog.askdirectory(parent=self, initialdir=start or app_dir(),
                                         title="Choose output folder", mustexist=False)
        if chosen:
            self.out_var.set(os.path.normpath(chosen))

    def _open_folder(self):
        path = self._resolve_out()
        if os.path.isdir(path):
            os.startfile(path)

    # ------------------------------------------------------------ generation

    def _set_status(self, text: str, color=None):
        self.status_label.configure(text=text, text_color=color or ("gray10", "gray90"))

    def _on_go(self):
        if self.running:
            self.cancel_event.set()
            self.go_btn.configure(state="disabled", text="Cancelling...")
            return
        try:
            s = self._collect()
            core.validate(s)
        except ValueError as e:
            self._set_status(str(e), ERROR_COLOR)
            return

        clashes = core.existing_files(s)
        if clashes:
            if not messagebox.askyesno(
                APP_TITLE,
                f"{len(clashes)} file(s) in\n{s.out_dir}\nalready exist and will be overwritten.\n\nContinue?",
                parent=self,
            ):
                return

        self.cancel_event.clear()
        self.running = True
        self.progress.set(0)
        self._set_status("Starting...")
        self.go_btn.configure(text="Cancel")
        self._refresh()
        threading.Thread(target=self._worker, args=(s,), daemon=True).start()

    def _worker(self, s: core.Settings):
        try:
            done, secs, cancelled = core.generate(
                s,
                progress=lambda d, t: self.msgs.put(("progress", d, t)),
                status=lambda text: self.msgs.put(("status", text)),
                cancel=self.cancel_event,
            )
            self.msgs.put(("finished", done, s.frames, secs, cancelled))
        except Exception as e:  # shown to the user, never silently dropped
            self.msgs.put(("error", str(e) or e.__class__.__name__))

    def _poll(self):
        try:
            while True:
                msg = self.msgs.get_nowait()
                kind = msg[0]
                if kind == "progress":
                    _, d, t = msg
                    self.progress.set(d / t if t else 0)
                    self._set_status(f"Saved {d} / {t} frames")
                elif kind == "status":
                    self._set_status(msg[1])
                elif kind == "finished":
                    _, done, total, secs, cancelled = msg
                    if cancelled:
                        self._set_status(f"Cancelled after {done} of {total} frames.", ERROR_COLOR)
                    else:
                        self.progress.set(1)
                        self._set_status(f"Done: {total} frames in {secs:.1f} s.", OK_COLOR)
                    self._finish_run()
                elif kind == "error":
                    self._set_status(f"Error: {msg[1]}", ERROR_COLOR)
                    self._finish_run()
        except queue.Empty:
            pass
        self.after(50, self._poll)

    def _finish_run(self):
        self.running = False
        self.go_btn.configure(state="normal", text="Generate")
        self._refresh()


def selftest(out_dir: str) -> int:
    """Write a tiny sequence in every format (used to verify the packaged exe)."""
    lines, failed = [], False
    for ft, info in core.FORMATS.items():
        for depth in info["depths"]:
            try:
                s = core.Settings(frames=2, name=f"selftest_{ft}_{depth}", res="Custom",
                                  custom_w=64, custom_h=32, file_type=ft, depth=depth,
                                  channels="RGBA" if "RGBA" in info["channels"] else "RGB",
                                  alpha=50, out_dir=out_dir)
                done = core.generate(s)[0]
                lines.append(f"OK   {ft} {depth}-bit: {done} frames")
            except Exception as e:
                failed = True
                lines.append(f"FAIL {ft} {depth}-bit: {e!r}")
    with open(os.path.join(out_dir, "selftest.log"), "w") as f:
        f.write("\n".join(lines))
    return 1 if failed else 0


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--selftest":
        sys.exit(selftest(sys.argv[2]))
    App().mainloop()


if __name__ == "__main__":
    main()

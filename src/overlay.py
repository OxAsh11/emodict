"""Always-on-top recording indicator: the only feedback a user gets while
dictating. Red dot + 'recording' while the key is held, amber 'transcribing'
while Whisper runs, gone after paste. Borderless, tiny, bottom-center."""
import tkinter as tk


class RecordingOverlay:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        try:
            self.win.attributes("-alpha", 0.88)
        except Exception:  # noqa: BLE001 - older Tk may lack alpha
            pass
        self.label = tk.Label(self.win, text="", font=("Segoe UI", 11, "bold"),
                              fg="white", padx=14, pady=6)
        self.label.pack()
        self.hide()

    def _place(self) -> None:
        self.win.update_idletasks()
        w = self.win.winfo_reqwidth()
        h = self.win.winfo_reqheight()
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        self.win.geometry(f"+{(sw - w) // 2}+{sh - h - 110}")

    def show(self, state: str = "recording") -> None:
        if state == "recording":
            self.label.configure(text="\N{BULLET} recording", bg="#c0392b")
        else:  # processing
            self.label.configure(text="\N{HORIZONTAL ELLIPSIS} transcribing",
                                 bg="#b9770e")
        self._place()
        self.win.deiconify()
        self.win.lift()
        # failsafe: never let a bug freeze the chip on screen
        try:
            self.win.after_cancel(self._auto_hide_id)
        except Exception:  # noqa: BLE001
            pass
        self._auto_hide_id = self.win.after(15000, self.hide)

    _auto_hide_id = None

    def hide(self) -> None:
        self.win.withdraw()

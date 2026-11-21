"""System tray icon: Settings / Pause / Quit. Runs detached in its own thread;
callbacks are marshalled to the tkinter main loop by the App."""
from PIL import Image, ImageDraw


def _make_icon_image(paused: bool = False) -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    color = (120, 120, 130) if paused else (0, 140, 220)
    d.ellipse((6, 6, 58, 58), fill=color)
    d.rounded_rectangle((26, 16, 38, 36), radius=5, fill="white")
    d.arc((20, 24, 44, 42), start=20, end=160, fill="white", width=3)
    d.line((32, 42, 32, 48), fill="white", width=3)
    return img


class Tray:
    """pystray wrapper. Menu: Settings, Pause/Resume, Quit."""

    def __init__(self, on_settings, on_toggle_pause, on_quit, on_update=None,
                 on_dashboard=None):
        import pystray
        from pystray import Menu, MenuItem

        self.paused = False
        self.on_settings = on_settings
        self.on_toggle_pause = on_toggle_pause
        self.on_quit = on_quit
        self.on_update = on_update

        def pause_label(item):
            return "Resume dictation" if self.paused else "Pause dictation"

        menu_items = [
            MenuItem("Settings", self._settings, default=True),
            MenuItem(pause_label, self._toggle_pause),
        ]
        if on_update is not None:
            menu_items.append(MenuItem("Check for updates", self._update))
        if on_dashboard is not None:
            menu_items.append(MenuItem("Performance dashboard", self._dashboard))
        menu_items.append(MenuItem("Quit", self._quit))

        self.icon = pystray.Icon(
            "EmoDict",
            icon=_make_icon_image(False),
            title="EmoDict - running",
            menu=Menu(*menu_items),
        )

    # pystray passes (icon, item); our callbacks take nothing
    def _settings(self, icon=None, item=None):
        self.on_settings()

    def _toggle_pause(self, icon=None, item=None):
        self.on_toggle_pause()

    def _update(self, icon=None, item=None):
        if self.on_update is not None:
            self.on_update()

    def _dashboard(self, icon=None, item=None):
        if self.on_dashboard is not None:
            self.on_dashboard()

    def _quit(self, icon=None, item=None):
        self.on_quit()

    # ---- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        import threading

        threading.Thread(target=self.icon.run, daemon=True).start()

    def set_paused(self, paused: bool) -> None:
        self.paused = paused
        self.icon.icon = _make_icon_image(paused)
        self.icon.title = "EmoDict - paused" if paused else "EmoDict - running"
        self.icon.update_menu()

    def stop(self) -> None:
        try:
            self.icon.stop()
        except Exception:  # noqa: BLE001 - best effort on shutdown
            pass

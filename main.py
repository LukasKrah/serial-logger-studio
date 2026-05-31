"""
Entry point for Serial Session Studio.

Initializes the backend logger, the frontend UI, and handles system-tray integration.

| ``Path``: /main.py
| ``Project``: serial-logger-studio
| ``Created``: 31.05.2026
| ``Authors``: LukasKrah
"""

import sys
from threading import Thread
import pystray
from PIL import Image, ImageDraw
from logger import SerialSessionLogger
from ui import SerialLoggerUI


def create_tray_image() -> Image.Image:
    """
    Generates a simple, dynamic icon for the system tray.

    Returns:
        Image.Image: A 64x64 PIL Image object.
    """
    img = Image.new('RGB', (64, 64), color=(43, 43, 43))
    d = ImageDraw.Draw(img)
    d.rectangle((16, 16, 48, 48), fill=(46, 204, 113))
    return img


def main() -> None:
    """
    Main application loop. Wires up event callbacks between the UI and Logger,
    and initializes system tray functionality.
    """
    logger = SerialSessionLogger()
    app = SerialLoggerUI()

    # Sync initial state
    logger.auto_connect = app.auto_connect_var.get()

    # Event bindings: Logger -> UI
    logger.on_port_status_change = app.update_port_status
    logger.on_log_event = app.process_log_event

    # Event bindings: UI -> Logger
    app.on_toggle_connection = logger.set_port_connection
    app.on_toggle_auto_connect = lambda state: setattr(logger, 'auto_connect', state)

    def show_window(icon: pystray.Icon, item: pystray.MenuItem) -> None:
        """Restores the application window from the tray."""
        icon.stop()
        app.after(0, app.deiconify)

    def quit_from_tray(icon: pystray.Icon, item: pystray.MenuItem) -> None:
        """Terminates the application entirely from the tray context menu."""
        icon.stop()
        on_closing()

    def minimize_to_tray() -> None:
        """Hides the main window and spawns the system tray icon."""
        app.withdraw()
        menu = pystray.Menu(
            pystray.MenuItem('Show App', show_window, default=True),
            pystray.MenuItem('Quit', quit_from_tray)
        )
        tray_icon = pystray.Icon("SerialLogger", create_tray_image(), "Serial Session Studio", menu)
        Thread(target=tray_icon.run, daemon=True).start()

    app.on_minimize_to_tray = minimize_to_tray

    def on_closing() -> None:
        """Handles graceful shutdown of threads and UI."""
        logger.stop()
        app.destroy()
        sys.exit(0)

    # Lifecycle hooks
    app.protocol("WM_DELETE_WINDOW", on_closing)
    logger.start()
    app.mainloop()


if __name__ == "__main__":
    main()

"""
Main application window configuration and event processing loop.

| ``Path``: ui/_window.py
| ``Project``: serial-logger-studio
| ``Created``: 31.05.2026
| ``Authors``: LukasKrah
"""

import os
import json
import queue
from typing import Callable, Optional, Dict, Any

import customtkinter as ctk
from ._components import CTkCollapsibleFrame, FilterWindow

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class SerialLoggerUI(ctk.CTk):
    """
    Primary UI construct. Utilizes an asynchronous queue processing system
    to ensure the Tkinter mainloop never hangs during excessive serial data bursts.
    """

    def __init__(self) -> None:
        super().__init__()
        self.title("Serial Session Studio")
        self.geometry("1300x800")

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0, minsize=350)
        self.grid_columnconfigure(1, weight=1)

        # Unfocus binding on root click
        self.bind("<Button-1>", lambda event: self.focus_set() if event.widget == self else None)

        # External hooks
        self.on_toggle_connection: Optional[Callable[[str, bool], None]] = None
        self.on_toggle_auto_connect: Optional[Callable[[bool], None]] = None
        self.on_minimize_to_tray: Optional[Callable[[], None]] = None

        # State management
        self.port_frames: Dict[str, Dict[str, Any]] = {}
        self.port_views: Dict[str, Dict[str, Any]] = {}
        self.active_port: Optional[str] = None

        # UI Event Pump (crucial for decoupling hardware reads from the renderer)
        self.event_queue: queue.Queue = queue.Queue()

        self.settings_file: str = "settings.json"
        self._load_settings()

        self.__build_left_panel()
        self.__build_right_panel()

        # Start the batch event processor (our internal "game loop" for the UI)
        self.after(100, self._process_event_queue)

    def _load_settings(self) -> None:
        """Loads layout and session preferences from disk."""
        self.settings = {
            "auto_connect": True,
            "scroll_mode": False,
            "filters_active": True,
            "view_mode": "Expand active sessions",
            "filters": [],
            "auto_scroll": True
        }
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, "r") as f:
                    self.settings.update(json.load(f))
            except (json.JSONDecodeError, IOError):
                pass

    def _save_settings(self) -> None:
        """Flushes preferences to disk."""
        try:
            with open(self.settings_file, "w") as f:
                json.dump(self.settings, f)
        except IOError:
            pass

    def __build_left_panel(self) -> None:
        """Constructs the sidebar containing COM port toggles."""
        left_container = ctk.CTkFrame(self, corner_radius=10)
        left_container.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        left_container.grid_rowconfigure(1, weight=1)
        left_container.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(left_container, fg_color="#3a3a3a", corner_radius=8)
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=10)

        title = ctk.CTkLabel(header, text="COM Ports", font=ctk.CTkFont(size=16, weight="bold"))
        title.pack(side="left", padx=10, pady=5)

        self.auto_connect_var = ctk.BooleanVar(value=self.settings["auto_connect"])
        ac_btn = ctk.CTkCheckBox(header, text="Auto-Connect", variable=self.auto_connect_var, command=self._save_ac)
        ac_btn.pack(side="right", padx=10)

        self.left_panel = ctk.CTkScrollableFrame(left_container, fg_color="transparent")
        self.left_panel.grid(row=1, column=0, sticky="nsew")

    def _save_ac(self) -> None:
        """Hook fired when auto-connect checkbox is toggled."""
        val = self.auto_connect_var.get()
        self.settings["auto_connect"] = val
        self._save_settings()
        if self.on_toggle_auto_connect:
            self.on_toggle_auto_connect(val)

    def __build_right_panel(self) -> None:
        """Constructs the main viewing area for logs and filters."""
        self.right_container = ctk.CTkFrame(self, corner_radius=10)
        self.right_container.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="nsew")
        self.right_container.grid_rowconfigure(1, weight=1)
        self.right_container.grid_columnconfigure(0, weight=1)

        control_bar = ctk.CTkFrame(self.right_container, fg_color="#3a3a3a", corner_radius=8, height=45)
        control_bar.grid(row=0, column=0, sticky="ew", padx=10, pady=10)

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *args: self._trigger_refresh())
        search_entry = ctk.CTkEntry(
            control_bar, placeholder_text="Search logs...",
            textvariable=self.search_var, width=150
        )
        search_entry.pack(side="left", padx=10, pady=5)

        self.filter_btn = ctk.CTkButton(control_bar, text="Filter Settings", width=60, command=self._open_filter_window)
        self.filter_btn.pack(side="left", padx=(0, 5))

        self.filter_active_var = ctk.BooleanVar(value=self.settings["filters_active"])
        filt_cb = ctk.CTkSwitch(
            control_bar, text="Filters On", variable=self.filter_active_var,
            command=self._toggle_filter_active
        )
        filt_cb.pack(side="left", padx=(5, 10))
        self._update_filter_btn_appearance()

        tray_btn = ctk.CTkButton(
            control_bar, text="Run in Background", fg_color="#8e44ad",
            hover_color="#9b59b6", command=self._minimize_action
        )
        tray_btn.pack(side="right", padx=(10, 10))

        self.auto_scroll_var = ctk.BooleanVar(value=self.settings["auto_scroll"])
        auto_scroll_cb = ctk.CTkCheckBox(
            control_bar, text="Auto-Scroll", variable=self.auto_scroll_var,
            command=self._save_layout_settings
        )
        auto_scroll_cb.pack(side="right", padx=10)

        self.scroll_var = ctk.BooleanVar(value=self.settings["scroll_mode"])
        scroll_cb = ctk.CTkCheckBox(
            control_bar, text="Scrollable Subboxes", variable=self.scroll_var,
            command=self._toggle_scroll
        )
        scroll_cb.pack(side="right", padx=10)

        opts = ["Expand all", "Collapse all", "Expand active sessions", "Expand all in current run"]
        self.view_var = ctk.StringVar(value=self.settings["view_mode"])
        self.view_action = ctk.CTkOptionMenu(
            control_bar, values=opts, variable=self.view_var,
            command=self._handle_view_action
        )
        self.view_action.pack(side="right", padx=10)

        self.right_panel = ctk.CTkFrame(self.right_container, fg_color="transparent")
        self.right_panel.grid(row=1, column=0, sticky="nsew")
        self.right_panel.grid_rowconfigure(0, weight=1)
        self.right_panel.grid_columnconfigure(0, weight=1)

        self.placeholder = ctk.CTkLabel(self.right_panel, text="Select a port to view logs", text_color="gray")
        self.placeholder.grid(row=0, column=0, sticky="nsew")

    def _minimize_action(self) -> None:
        """Triggers the app minimization sequence to the system tray."""
        if self.on_minimize_to_tray:
            self.on_minimize_to_tray()

    def _open_filter_window(self) -> None:
        """Spawns the dialog for editing string exclusion filters."""
        FilterWindow(self, self.settings["filters"], self._on_filters_saved)

    def _toggle_filter_active(self) -> None:
        """Enables/disables the runtime message masking logic."""
        self.settings["filters_active"] = self.filter_active_var.get()
        self._save_settings()
        self._trigger_refresh()

    def _on_filters_saved(self, new_filters: list) -> None:
        """Callback invoked when the filter dialog completes."""
        self.settings["filters"] = new_filters
        self._save_settings()
        self._update_filter_btn_appearance()
        self._trigger_refresh()

    def _update_filter_btn_appearance(self) -> None:
        """Color-codes the filter button if filters are active and populated."""
        if self.settings["filters"] and self.settings["filters_active"]:
            self.filter_btn.configure(fg_color="#E74C3C", hover_color="#c0392b")
        else:
            self.filter_btn.configure(fg_color="#3498db", hover_color="#2980b9")

    def _save_layout_settings(self) -> None:
        """Simple property flush."""
        self.settings["auto_scroll"] = self.auto_scroll_var.get()
        self._save_settings()

    def _toggle_scroll(self) -> None:
        """Re-evaluates the height constraints of text boxes."""
        self.settings["scroll_mode"] = self.scroll_var.get()
        self._save_settings()
        self._trigger_refresh()

    def _trigger_refresh(self) -> None:
        """Forces a re-render of all text boxes based on current filter/search states."""
        if not self.active_port or self.active_port not in self.port_views:
            return

        term = self.search_var.get().strip()
        filts = self.settings["filters"]
        f_active = self.settings["filters_active"]
        scroll = self.scroll_var.get()

        for run_frame in self.port_views[self.active_port]["runs"]:
            for sess_frame in run_frame._session_frames:
                sess_frame.refresh_messages(term, filts, f_active, scroll)
                sess_frame.check_visibility()
            run_frame.check_visibility()

    def _handle_view_action(self, action: str) -> None:
        """Evaluates tree expansion states globally."""
        self.settings["view_mode"] = action
        self._save_settings()

        if not self.active_port or self.active_port not in self.port_views:
            return

        view_data = self.port_views[self.active_port]

        for run_frame in view_data["runs"]:
            is_latest_run = (run_frame == view_data["current_run_frame"])

            if action == "Expand all":
                run_frame.toggle(force_state=True)
                for sf in run_frame._session_frames:
                    sf.toggle(force_state=True)
            elif action == "Collapse all":
                run_frame.toggle(force_state=False)
                for sf in run_frame._session_frames:
                    sf.toggle(force_state=False)
            elif action == "Expand active sessions":
                has_active = False
                for sf in run_frame._session_frames:
                    is_active = (sf == view_data["current_session_frame"] and sf.status_badge.cget("text") == "Active")
                    if is_active:
                        has_active = True
                    sf.toggle(force_state=is_active)
                run_frame.toggle(force_state=has_active)
            elif action == "Expand all in current run":
                if is_latest_run:
                    run_frame.toggle(force_state=True)
                    for sf in run_frame._session_frames:
                        sf.toggle(force_state=True)
                else:
                    run_frame.toggle(force_state=False)

    def _select_port(self, port_name: str) -> None:
        """Swaps the main context view to the specified COM port."""
        self.active_port = port_name
        self.placeholder.grid_remove()

        for name, data in self.port_frames.items():
            data["frame"].configure(fg_color="#1f538d" if name == port_name else "#2b2b2b")

        for name, data in self.port_views.items():
            if name == port_name:
                data["scroll_frame"].grid(row=0, column=0, sticky="nsew")
            else:
                data["scroll_frame"].grid_remove()

    def _toggle_port_btn(self, port_name: str) -> None:
        """Fires the connect/disconnect request for a specific port."""
        if not self.on_toggle_connection:
            return
        is_conn = self.port_frames[port_name]["is_connected"]
        self.on_toggle_connection(port_name, not is_conn)

    def update_port_status(self, port_name: str, status: str) -> None:
        """Thread-safe UI update for port hardware availability states."""

        def _update():
            if port_name not in self.port_frames:
                self._create_port_entry(port_name)

            fdata = self.port_frames[port_name]

            if status == "connected":
                fdata["status_lbl"].configure(text="Connected", text_color="#2ECC71")
                fdata["btn"].configure(text="Disconnect", fg_color="#E74C3C", hover_color="#c0392b", state="normal")
                fdata["is_connected"] = True
            elif status == "disconnected":
                fdata["status_lbl"].configure(text="Disconnected", text_color="#E74C3C")
                fdata["btn"].configure(text="Connect", fg_color="#2ECC71", hover_color="#27ae60", state="normal")
                fdata["is_connected"] = False
            elif status == "not_found":
                fdata["status_lbl"].configure(text="Not Found", text_color="#7f8c8d")
                fdata["btn"].configure(text="N/A", fg_color="#333333", state="disabled")
                fdata["is_connected"] = False
            elif status == "reconnecting":
                fdata["status_lbl"].configure(text="Reconnecting...", text_color="#F1C40F")
                fdata["btn"].configure(text="Disconnect", fg_color="#E74C3C", hover_color="#c0392b", state="normal")
                fdata["is_connected"] = True

        self.after(0, _update)

    def _create_port_entry(self, port_name: str) -> None:
        """Instantiates the sidebar row construct for a newly discovered port."""
        frame = ctk.CTkFrame(self.left_panel, corner_radius=8, fg_color="#2b2b2b")
        frame.pack(fill="x", pady=5, padx=5)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_columnconfigure(2, weight=0)

        name_lbl = ctk.CTkLabel(frame, text=port_name, font=ctk.CTkFont(weight="bold"))
        name_lbl.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="w")

        status_lbl = ctk.CTkLabel(frame, text="Found", text_color="gray", font=ctk.CTkFont(size=12))
        status_lbl.grid(row=0, column=1, padx=5, pady=10, sticky="w")

        btn = ctk.CTkButton(frame, text="Connect", width=80, command=lambda p=port_name: self._toggle_port_btn(p))
        btn.grid(row=0, column=2, padx=(5, 10), pady=10, sticky="e")

        for w in (frame, name_lbl, status_lbl):
            w.bind("<Button-1>", lambda e, p=port_name: self._select_port(p))

        self.port_frames[port_name] = {
            "frame": frame, "status_lbl": status_lbl,
            "btn": btn, "is_connected": False
        }

        sf = ctk.CTkScrollableFrame(self.right_panel, fg_color="transparent")
        self.port_views[port_name] = {
            "scroll_frame": sf, "runs": [], "current_run_frame": None,
            "current_session_frame": None
        }

    def process_log_event(self, port_name: str, event_type: str, data: dict) -> None:
        """
        Receives raw signals from the background logger.
        Instead of modifying Tkinter elements directly (which is thread-unsafe),
        we marshal the events through a standard Queue.
        """
        self.event_queue.put((port_name, event_type, data))

    def _user_scrolled(self, event: Any) -> None:
        """Overrides auto-scrolling if the user intentionally scrolls back up."""
        self.auto_scroll_var.set(False)
        self._save_layout_settings()

    def _process_event_queue(self) -> None:
        """
        Batch processes queued UI events. Operating via this pump ensures
        we aren't blocking the main thread when rendering heavy UI updates.
        """
        processed_ports = set()

        while not self.event_queue.empty():
            try:
                port_name, event_type, data = self.event_queue.get_nowait()
                if port_name not in self.port_views:
                    self._create_port_entry(port_name)

                view = self.port_views[port_name]
                mode = self.settings["view_mode"]

                if event_type == "run_start":
                    run_frame = CTkCollapsibleFrame(
                        view["scroll_frame"], "Program Run",
                        start_time=data.get('start_time', ''), is_run=True
                    )
                    run_frame.set_right_status(
                        "Active" if not data.get("is_history") else "Ended",
                        "#2ECC71" if not data.get("is_history") else "#95a5a6"
                    )
                    run_frame.pack(fill="x", pady=5)

                    view["runs"].append(run_frame)
                    view["current_run_frame"] = run_frame

                    if mode == "Collapse all" or data.get("is_history"):
                        run_frame.toggle(force_state=False)

                elif event_type == "run_end":
                    for r in view["runs"]:
                        if data.get("run_id") in r.title_lbl.cget("text"):
                            r.set_right_status("Ended", "#95a5a6")

                elif event_type == "session_start":
                    if not view["current_run_frame"]:
                        continue

                    if view["current_session_frame"] and mode == "Expand active sessions":
                        view["current_session_frame"].toggle(force_state=False)

                    sess_frame = CTkCollapsibleFrame(
                        view["current_run_frame"].content_frame, "Session Start",
                        start_time=data.get('start_time', '')
                    )
                    sess_frame.pack(fill="x", pady=2)

                    tb = ctk.CTkTextbox(
                        sess_frame.content_frame, wrap="word",
                        font=ctk.CTkFont(family="Consolas", size=12)
                    )
                    tb.pack(fill="both", expand=True)
                    tb.tag_config("history", foreground="#7f8c8d")
                    tb.tag_config("live", foreground="#ecf0f1")
                    tb.tag_config("time", foreground="#3498db")

                    # Bind mouse wheel to disable auto-scroll
                    tb.bind("<MouseWheel>", self._user_scrolled)

                    sess_frame.tb = tb
                    view["current_run_frame"]._session_frames.append(sess_frame)
                    view["current_session_frame"] = sess_frame

                    if not data.get("is_history"):
                        sess_frame.set_right_status("Active", "#2ECC71")
                        if mode in ["Expand all", "Expand active sessions", "Expand all in current run"]:
                            sess_frame.toggle(force_state=True)
                        elif mode == "Collapse all":
                            sess_frame.toggle(force_state=False)
                    else:
                        sess_frame.set_right_status("Ended", "#95a5a6")
                        if mode == "Expand all":
                            sess_frame.toggle(force_state=True)
                        else:
                            sess_frame.toggle(force_state=False)

                elif event_type == "message":
                    sf = view["current_session_frame"]
                    if sf:
                        sf.raw_messages.append(data)
                        processed_ports.add((port_name, sf))

                elif event_type == "session_end":
                    sf = view["current_session_frame"]
                    if sf:
                        sf.set_right_status(f"Ended: {data['end_time']}", "#95a5a6")
                        if mode == "Expand active sessions":
                            sf.toggle(force_state=False)

            except queue.Empty:
                break

        # Batch UI renders for modified textboxes
        if processed_ports:
            term = self.search_var.get().strip()
            filts = self.settings["filters"]
            f_active = self.settings["filters_active"]
            scroll = self.scroll_var.get()
            do_scroll = self.auto_scroll_var.get()

            for port_name, sf in processed_ports:
                sf.refresh_messages(term, filts, f_active, scroll)
                sf.check_visibility()
                if do_scroll:
                    sf.tb.yview_moveto(1.0)

        # Re-schedule loop iteration
        self.after(100, self._process_event_queue)

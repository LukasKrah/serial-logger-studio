"""
Reusable UI layout components and specialized windows.

| ``Path``: ui/_components.py
| ``Project``: serial-logger-studio
| ``Created``: 31.05.2026
| ``Authors``: LukasKrah
"""

import re
from typing import List, Callable, Optional, Any
import customtkinter as ctk


class CTkCollapsibleFrame(ctk.CTkFrame):
    """
    A dynamic container that can hide/show its contents, displaying
    metadata and status badges in its header.
    """

    def __init__(self, master: Any, title: str, start_time: str = "", is_run: bool = False, **kwargs) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self.is_expanded: bool = True
        self.is_run: bool = is_run

        # Main Border formatting
        self.border_frame = ctk.CTkFrame(
            self, fg_color="transparent", corner_radius=8,
            border_width=1 if is_run else 0, border_color="#333333"
        )
        self.border_frame.pack(fill="both", expand=True, pady=2)

        self.header_frame = ctk.CTkFrame(
            self.border_frame,
            fg_color="#3a3a3a" if is_run else "#2c2c2c",
            corner_radius=6
        )
        self.header_frame.pack(fill="x")
        self.header_frame.grid_columnconfigure(1, weight=1)

        left_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        left_frame.grid(row=0, column=0, sticky="w", padx=5)

        self.toggle_btn = ctk.CTkButton(
            left_frame, text="▼", width=30, fg_color="transparent",
            hover_color="#555555", command=self.toggle
        )
        self.toggle_btn.pack(side="left")

        title_text = f"{title}" + (f"  |  {start_time}" if start_time else "")
        self.title_lbl = ctk.CTkLabel(left_frame, text=title_text, font=ctk.CTkFont(weight="bold"))
        self.title_lbl.pack(side="left", padx=5)

        self.filter_lbl = ctk.CTkLabel(
            self.header_frame, text="", text_color="#E74C3C",
            font=ctk.CTkFont(size=11, weight="bold")
        )
        self.filter_lbl.grid(row=0, column=1, sticky="e", padx=10)

        right_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        right_frame.grid(row=0, column=2, sticky="e", padx=10)

        self.status_badge = ctk.CTkLabel(
            right_frame, text="", text_color="#2ECC71",
            font=ctk.CTkFont(size=11, weight="bold")
        )
        self.status_badge.pack(side="right")

        # Content formatting
        self.content_frame = ctk.CTkFrame(
            self.border_frame,
            fg_color="#181818" if is_run else "#242424",
            corner_radius=6
        )
        self.content_frame.pack(fill="both", expand=True, padx=5 if is_run else 0, pady=(2, 5))

        self._session_frames: List['CTkCollapsibleFrame'] = []
        self.raw_messages: List[dict] = []
        self.tb: Optional[ctk.CTkTextbox] = None
        self.has_relevant_content: bool = True

    def set_right_status(self, text: str, color: str = "#2ECC71") -> None:
        """Updates the status badge on the right side of the header."""
        self.status_badge.configure(text=text, text_color=color)

    def set_filter_status(self, text: str, color: str = "#E74C3C") -> None:
        """Updates the filter indicator string."""
        self.filter_lbl.configure(text=text, text_color=color)

    def toggle(self, force_state: Optional[bool] = None) -> None:
        """Toggles the visibility of the internal content frame."""
        if force_state is not None:
            self.is_expanded = not force_state

        if self.is_expanded:
            self.content_frame.pack_forget()
            self.toggle_btn.configure(text="▶")
            self.is_expanded = False
        else:
            self.content_frame.pack(fill="both", expand=True, padx=5 if self.is_run else 0, pady=(2, 5))
            self.toggle_btn.configure(text="▼")
            self.is_expanded = True

    def check_visibility(self) -> None:
        """Hides the entire frame if there's no matching content during search/filter."""
        if not self.has_relevant_content:
            self.pack_forget()
        else:
            self.pack(fill="x", pady=2)

        if self.is_run:
            any_child_visible = any(sf.has_relevant_content for sf in self._session_frames)
            if not any_child_visible and self._session_frames:
                self.pack_forget()
            else:
                self.pack(fill="x", pady=5)

    def refresh_messages(self, search_term: str, filters: List[str], filters_enabled: bool, scrollable: bool) -> None:
        """Regenerates the internal text block based on search queries and exclusion filters."""
        if not self.tb:
            return

        self.tb.configure(state="normal")
        self.tb.delete("1.0", "end")

        visible_count = 0
        filtered_count = 0

        # Build strict exact match filters for wildcard syntax
        compiled_filters = []
        if filters_enabled:
            for f in filters:
                if f:
                    regex_str = f"^{re.escape(f).replace(r'\\*', '.*')}$"
                    compiled_filters.append(re.compile(regex_str, re.IGNORECASE))

        compiled_search = None
        if search_term:
            compiled_search = re.compile(f".*{re.escape(search_term).replace(r'\\*', '.*')}.*", re.IGNORECASE)

        # Process messages
        for msg_data in self.raw_messages:
            msg_text = msg_data["message"]

            if any(f.match(msg_text) for f in compiled_filters):
                filtered_count += 1
                continue

            if compiled_search and not compiled_search.match(msg_text):
                continue

            visible_count += 1
            tag = "history" if msg_data.get("is_history") else "live"
            self.tb.insert("end", f"[{msg_data['time']}] ", "time")
            self.tb.insert("end", f"{msg_text}\n", tag)

        self.tb.configure(state="disabled")

        # Visibility update
        self.has_relevant_content = (visible_count > 0) or (len(self.raw_messages) == 0 and not search_term)

        if filters_enabled and filters:
            if visible_count == 0 and len(self.raw_messages) > 0:
                self.set_filter_status("No relevant messages", "#F39C12")
            else:
                self.set_filter_status(f"{visible_count} relevant, {filtered_count} filtered", "#E74C3C")
        else:
            self.set_filter_status("")

        # Dynamic Box Resizing Optimization
        if not scrollable:
            line_height = 18
            target_height = max(35, visible_count * line_height + 10)
            self.tb.configure(height=target_height)
        else:
            self.tb.configure(height=200)


class FilterWindow(ctk.CTkToplevel):
    """
    Dialog window for managing wildcard exclusion filters.
    """

    def __init__(self, master: Any, current_filters: List[str], on_save: Callable[[List[str]], None]) -> None:
        super().__init__(master)
        self.title("Manage Filters")
        self.geometry("400x300")
        self.on_save = on_save
        self.filters: List[str] = list(current_filters)

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        top_frame = ctk.CTkFrame(self, fg_color="transparent")
        top_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)

        self.entry = ctk.CTkEntry(top_frame, placeholder_text="e.g. ExactMatch*")
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 5))

        add_btn = ctk.CTkButton(top_frame, text="Add", width=60, command=self._add_filter)
        add_btn.pack(side="right")

        self.listbox_frame = ctk.CTkScrollableFrame(self)
        self.listbox_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

        self._render_list()

    def _render_list(self) -> None:
        """Draws the active filters inside the scrollable container."""
        for widget in self.listbox_frame.winfo_children():
            widget.destroy()

        for i, f in enumerate(self.filters):
            row = ctk.CTkFrame(self.listbox_frame, fg_color="#333333")
            row.pack(fill="x", pady=2)

            lbl = ctk.CTkLabel(row, text=f)
            lbl.pack(side="left", padx=10)

            btn = ctk.CTkButton(
                row, text="X", width=30, fg_color="#E74C3C", hover_color="#c0392b",
                command=lambda idx=i: self._remove_filter(idx)
            )
            btn.pack(side="right", padx=5, pady=5)

        self.on_save(self.filters)

    def _add_filter(self) -> None:
        """Captures input and appends to the filter pool."""
        val = self.entry.get().strip()
        if val and val not in self.filters:
            self.filters.append(val)
            self.entry.delete(0, "end")
            self._render_list()

    def _remove_filter(self, idx: int) -> None:
        """Removes a filter by index."""
        self.filters.pop(idx)
        self._render_list()

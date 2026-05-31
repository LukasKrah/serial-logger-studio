"""
Core logging logic for managing serial connections and persisting data.

| ``Path``: logger/_logger.py
| ``Project``: serial-logger-studio
| ``Created``: 31.05.2026
| ``Authors``: LukasKrah
"""

import os
import json
import glob
import serial
from datetime import datetime
from threading import Thread, Lock, Event
from time import sleep
from typing import Callable, Optional, Dict, List, Set, Any


class SerialSessionLogger:
    """
    Manages active serial port connections, reads data streams, and handles
    session persistence for historical playback.
    """

    def __init__(self, baud_rate: int = 115200, scan_interval: int = 2) -> None:
        self.__baud_rate: int = baud_rate
        self.__scan_interval: int = scan_interval

        self.__thread_event: Event = Event()
        self.__thread_lock: Lock = Lock()
        self.__is_dirty: bool = False

        self.auto_connect: bool = True
        self.run_id: str = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_start_time: str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.__sessions: Dict[str, List[Dict[str, Any]]] = {}
        self.__active_ports: Dict[str, Thread] = {}
        self.__port_stop_events: Dict[str, Event] = {}
        self.__manual_disconnects: Set[str] = set()
        self.__known_ports: Set[str] = set()

        # Callbacks
        self.on_port_status_change: Optional[Callable[[str, str], None]] = None
        self.on_log_event: Optional[Callable[[str, str, Dict[str, Any]], None]] = None

        # Directory setup
        self.sessions_dir: str = os.path.join("logs", "sessions")
        self.individual_dir: str = os.path.join("logs", "individual")
        os.makedirs(self.sessions_dir, exist_ok=True)
        os.makedirs(self.individual_dir, exist_ok=True)

        self.__output_file: str = os.path.join(self.sessions_dir, f"serial_session_{self.run_id}.json")
        self.__load_historical_data()

    def __load_historical_data(self) -> None:
        """Loads previous session payloads from disk to populate known ports and history."""
        history_files = sorted(glob.glob(os.path.join(self.sessions_dir, "*.json")))
        for file in history_files:
            try:
                run_tag = os.path.basename(file).replace("serial_session_", "").replace(".json", "")
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for port, sessions in data.items():
                        self.__known_ports.add(port)
                        if port not in self.__sessions:
                            self.__sessions[port] = []
                        for s in sessions:
                            s['_historic_run_id'] = run_tag
                        self.__sessions[port].extend(sessions)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load historical file {file} - {e}")

    def push_history_to_ui(self, port_name: str) -> None:
        """
        Dispatches loaded historical data to the UI for a specific port.

        Args:
            port_name (str): The COM port identifier.
        """
        if not self.on_log_event or port_name not in self.__sessions:
            return

        current_run = None
        for session in self.__sessions[port_name]:
            run_tag = session.get('_historic_run_id', 'Unknown_Run')

            if run_tag != current_run:
                current_run = run_tag
                try:
                    start_t = datetime.strptime(current_run, "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    start_t = current_run

                self.on_log_event(
                    port_name, "run_start",
                    {"run_id": current_run, "start_time": start_t, "is_history": True}
                )

            self.on_log_event(
                port_name, "session_start",
                {"start_time": session.get("start_time", ""), "is_history": True}
            )

            for msg in session.get("messages", []):
                self.on_log_event(
                    port_name, "message",
                    {"time": msg["time"], "message": msg["message"], "is_history": True}
                )

            self.on_log_event(
                port_name, "session_end",
                {"end_time": session.get("end_time", ""), "is_history": True}
            )

        if current_run:
            self.on_log_event(port_name, "run_end", {"run_id": current_run, "is_history": True})

    def set_port_connection(self, port_name: str, connect: bool) -> None:
        """
        Manually connects or disconnects a specified port.

        Args:
            port_name (str): The target COM port.
            connect (bool): True to connect, False to disconnect.
        """
        if connect:
            self.__manual_disconnects.discard(port_name)
            if port_name in self.__port_stop_events:
                self.__port_stop_events[port_name].clear()
            self.__notify_status(port_name, "reconnecting")
        else:
            self.__manual_disconnects.add(port_name)
            if port_name in self.__port_stop_events:
                self.__port_stop_events[port_name].set()
            self.__notify_status(port_name, "disconnected")

    def __notify_status(self, port_name: str, status: str) -> None:
        """Helper to invoke the status change callback safely."""
        if self.on_port_status_change:
            self.on_port_status_change(port_name, status)

    def __log_session(self, port_name: str) -> None:
        """
        Main worker thread function for an active serial connection.
        Handles reading streams and appending to the session store.
        """
        start_time_dt = datetime.now()
        start_time = start_time_dt.strftime("%Y-%m-%d %H:%M:%S")
        stop_event = Event()
        self.__port_stop_events[port_name] = stop_event

        session_data = {
            "start_time": start_time,
            "end_time": "",
            "port": port_name,
            "messages": [],
            "_historic_run_id": self.run_id
        }

        with self.__thread_lock:
            if port_name not in self.__sessions:
                self.__sessions[port_name] = []
            self.__sessions[port_name].append(session_data)
            self.__is_dirty = True

        self.__notify_status(port_name, "connected")
        if self.on_log_event:
            self.on_log_event(
                port_name, "session_start",
                {"start_time": start_time, "is_history": False}
            )

        try:
            with serial.Serial(port_name, self.__baud_rate, timeout=0.1) as ser:
                while not self.__thread_event.is_set() and not stop_event.is_set():
                    try:
                        if ser.in_waiting:
                            line = ser.readline().decode(errors="replace").strip()
                            if line:
                                msg_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                with self.__thread_lock:
                                    session_data["messages"].append({"time": msg_time, "message": line})
                                    self.__is_dirty = True
                                if self.on_log_event:
                                    self.on_log_event(
                                        port_name, "message",
                                        {"time": msg_time, "message": line, "is_history": False}
                                    )
                    except serial.SerialException:
                        break
        except serial.SerialException:
            pass  # Device likely disconnected

        with self.__thread_lock:
            end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            session_data["end_time"] = end_time
            self.__is_dirty = True
            if port_name in self.__active_ports:
                del self.__active_ports[port_name]

        if self.on_log_event:
            self.on_log_event(port_name, "session_end", {"end_time": end_time, "is_history": False})

        if not stop_event.is_set():
            self.__notify_status(port_name, "reconnecting")

        self.__save_individual_log(session_data, port_name, start_time_dt)

    def __save_individual_log(self, session_data: Dict[str, Any], port_name: str, start_time: datetime) -> None:
        """Dumps a completed session into a standalone text log file."""
        safe_desc = "".join(c if c.isalnum() else "_" for c in port_name)
        base_filename = os.path.join(self.individual_dir, f"{start_time.strftime('%Y%m%d_%H%M%S')}_{safe_desc}")

        counter = 1
        filename = f"{base_filename}.log"
        while os.path.exists(filename):
            filename = f"{base_filename}_{counter}.log"
            counter += 1

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"Device: {port_name}\n")
                f.write(f"Started: {session_data['start_time']}\n")
                f.write(f"Ended: {session_data['end_time']}\n")
                f.write("-" * 40 + "\n")
                for msg in session_data["messages"]:
                    f.write(f"[{msg['time']}] {msg['message']}\n")
        except IOError as e:
            print(f"Error saving individual log: {e}")

    def __save(self) -> None:
        """Serializes current memory state to the JSON session file."""
        with self.__thread_lock:
            try:
                clean_sessions = {}
                for port, sessions in self.__sessions.items():
                    clean_sessions[port] = [
                        {k: v for k, v in s.items() if k != '_historic_run_id'}
                        for s in sessions
                    ]
                with open(self.__output_file, 'w', encoding='utf-8') as f:
                    json.dump(clean_sessions, f, indent=4)
            except IOError as e:
                print(f"Error saving JSON session data: {e}")

    def __auto_save_loop(self) -> None:
        """Background loop ensuring disk persistence occurs efficiently."""
        while not self.__thread_event.is_set():
            if self.__is_dirty:
                self.__save()
                with self.__thread_lock:
                    self.__is_dirty = False
            sleep(2)  # Reduced frequency to save disk I/O

    def __port_scan_loop(self) -> None:
        """Background loop querying the OS for hardware connect/disconnect events."""
        from serial.tools.list_ports import comports

        # Initialize UI with all historically known ports as not found
        for port in self.__known_ports:
            self.__notify_status(port, "not_found")
            self.push_history_to_ui(port)

        while not self.__thread_event.is_set():
            current_ports = {p.device: p for p in comports()}

            # Update missing ports status
            for known in list(self.__known_ports):
                if known not in current_ports and known not in self.__active_ports:
                    self.__notify_status(known, "not_found")

            for port_name in current_ports.keys():
                if port_name not in self.__known_ports:
                    self.__known_ports.add(port_name)
                    if not self.auto_connect:
                        self.__manual_disconnects.add(port_name)
                    self.__notify_status(port_name, "disconnected")
                    self.push_history_to_ui(port_name)

                    if self.on_log_event:
                        self.on_log_event(
                            port_name, "run_start",
                            {"run_id": self.run_id, "start_time": self.run_start_time, "is_history": False}
                        )

                if port_name not in self.__active_ports and port_name not in self.__manual_disconnects:
                    t = Thread(target=self.__log_session, args=(port_name,), daemon=True)
                    self.__active_ports[port_name] = t
                    t.start()

            sleep(self.__scan_interval)

    def start(self) -> None:
        """Initiates the background scanning and autosave daemon threads."""
        Thread(target=self.__auto_save_loop, daemon=True).start()
        Thread(target=self.__port_scan_loop, daemon=True).start()

    def stop(self) -> None:
        """Safely halts all background operations and flushes pending data to disk."""
        self.__thread_event.set()
        if self.on_log_event:
            for port in self.__known_ports:
                self.on_log_event(port, "run_end", {"run_id": self.run_id, "is_history": False})

        for ev in self.__port_stop_events.values():
            ev.set()

        self.__save()

"""
Serial Logger Module

Handles all serial port communication, background scanning, and disk I/O.

| ``Path``: logger/__init__.py
| ``Project``: serial-logger-studio
| ``Created``: 31.05.2026
| ``Authors``: LukasKrah
"""
from ._logger import SerialSessionLogger

__all__ = ["SerialSessionLogger"]

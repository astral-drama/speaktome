"""
GUI Module for SpeakToMe Desktop Client

Provides a Tkinter-based graphical user interface for the desktop voice client,
maintaining the functional architecture while adding visual feedback and controls.
"""

from .main_window import MainWindow
from .settings_window import SettingsWindow  
from .history_window import HistoryWindow
from .gui_events import *

__all__ = [
    "MainWindow",
    "SettingsWindow", 
    "HistoryWindow",
    "GUIShowEvent",
    "GUIHideEvent", 
    "SettingsChangedEvent",
    "TranscriptionCopiedEvent"
]
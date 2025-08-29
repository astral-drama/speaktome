#!/usr/bin/env python3

"""
GUI-Specific Events

Event classes for GUI interactions and state changes.
Extends the shared event system with GUI-specific functionality.
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional

from shared.events import BaseEvent


@dataclass
class GUIShowEvent(BaseEvent):
    """Event fired when GUI window should be shown"""
    window_type: str = "main"  # main, settings, history
    
    @property
    def event_type(self) -> str:
        return "gui.show"


@dataclass  
class GUIHideEvent(BaseEvent):
    """Event fired when GUI window should be hidden"""
    window_type: str = "main"  # main, settings, history
    
    @property
    def event_type(self) -> str:
        return "gui.hide"


@dataclass
class SettingsChangedEvent(BaseEvent):
    """Event fired when settings are modified through GUI"""
    changed_settings: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.changed_settings is None:
            object.__setattr__(self, 'changed_settings', {})
    
    @property
    def event_type(self) -> str:
        return "settings.changed"


@dataclass
class TranscriptionCopiedEvent(BaseEvent):
    """Event fired when transcription text is copied to clipboard"""
    text: str = ""
    transcription_id: Optional[str] = None
    
    @property
    def event_type(self) -> str:
        return "transcription.copied"


@dataclass
class GUIStateChangedEvent(BaseEvent):
    """Event fired when GUI state changes"""
    component: str = ""  # window, button, status
    new_state: str = ""  # visible, hidden, enabled, disabled
    details: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.details is None:
            object.__setattr__(self, 'details', {})
    
    @property  
    def event_type(self) -> str:
        return "gui.state_changed"
#!/usr/bin/env python3

"""
Settings Configuration Window

GUI for configuring client settings including hotkeys, audio devices,
server connection, and transcription options.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import logging
from typing import Dict, Any, Callable, Optional

from shared.functional import Result, Success, Failure
from shared.events import EventBus
from .gui_events import SettingsChangedEvent

logger = logging.getLogger(__name__)


class SettingsWindow:
    """
    Settings configuration window
    
    Features:
    - Hotkey customization
    - Audio device selection
    - Server URL configuration  
    - Model selection
    - Text processing options
    - Save/Cancel functionality
    """
    
    def __init__(self, event_bus: EventBus, config: Dict[str, Any], 
                 on_settings_changed: Optional[Callable[[Dict[str, Any]], None]] = None):
        self.event_bus = event_bus
        self.config = config.copy()  # Work with a copy
        self.on_settings_changed = on_settings_changed
        
        self.root: Optional[tk.Toplevel] = None
        self.parent_window: Optional[tk.Tk] = None
        
        # Form variables
        self.hotkey_var = tk.StringVar(value=config.get('hotkey', 'ctrl+shift+w'))
        self.server_url_var = tk.StringVar(value=config.get('server_url', 'ws://localhost:8000/ws/transcribe'))
        self.model_var = tk.StringVar(value=config.get('model', 'base'))
        
        logger.info("Settings window initialized")
    
    def show(self, parent_window: tk.Tk) -> Result[None, Exception]:
        """Show the settings window"""
        try:
            self.parent_window = parent_window
            
            if self.root is None:
                self._create_window()
            
            self.root.deiconify()
            self.root.lift()
            self.root.focus()
            
            logger.info("Settings window shown")
            return Success(None)
        except Exception as e:
            logger.error(f"Failed to show settings window: {e}")
            return Failure(e)
    
    def hide(self) -> Result[None, Exception]:
        """Hide the settings window"""
        try:
            if self.root:
                self.root.withdraw()
            logger.info("Settings window hidden")
            return Success(None)
        except Exception as e:
            logger.error(f"Failed to hide settings window: {e}")
            return Failure(e)
    
    def _create_window(self) -> None:
        """Create the settings window"""
        self.root = tk.Toplevel(self.parent_window)
        self.root.title("SpeakToMe Settings")
        self.root.geometry("500x400")
        self.root.resizable(False, False)
        
        # Make modal
        self.root.transient(self.parent_window)
        self.root.grab_set()
        
        # Center on parent
        self._center_window()
        
        self._create_widgets()
        self._setup_layout()
        
        logger.info("Settings window created")
    
    def _center_window(self) -> None:
        """Center the window on the parent"""
        if self.parent_window:
            self.root.update_idletasks()
            parent_x = self.parent_window.winfo_x()
            parent_y = self.parent_window.winfo_y()
            parent_width = self.parent_window.winfo_width()
            parent_height = self.parent_window.winfo_height()
            
            window_width = self.root.winfo_reqwidth()
            window_height = self.root.winfo_reqheight()
            
            x = parent_x + (parent_width // 2) - (window_width // 2)
            y = parent_y + (parent_height // 2) - (window_height // 2)
            
            self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
    
    def _create_widgets(self) -> None:
        """Create settings form widgets"""
        # Create notebook for tabs
        notebook = ttk.Notebook(self.root)
        
        # General tab
        general_frame = ttk.Frame(notebook)
        notebook.add(general_frame, text="General")
        
        # Hotkey setting
        ttk.Label(general_frame, text="Recording Hotkey:").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        hotkey_entry = ttk.Entry(general_frame, textvariable=self.hotkey_var, width=20)
        hotkey_entry.grid(row=0, column=1, padx=10, pady=5)
        
        # Server URL setting
        ttk.Label(general_frame, text="Server URL:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        server_entry = ttk.Entry(general_frame, textvariable=self.server_url_var, width=40)
        server_entry.grid(row=1, column=1, padx=10, pady=5)
        
        # Model selection
        ttk.Label(general_frame, text="Whisper Model:").grid(row=2, column=0, sticky="w", padx=10, pady=5)
        model_combo = ttk.Combobox(general_frame, textvariable=self.model_var, 
                                  values=['tiny', 'base', 'small', 'medium', 'large'],
                                  state="readonly", width=15)
        model_combo.grid(row=2, column=1, sticky="w", padx=10, pady=5)
        
        # Audio tab (placeholder)
        audio_frame = ttk.Frame(notebook)
        notebook.add(audio_frame, text="Audio")
        ttk.Label(audio_frame, text="Audio device selection coming soon...").pack(pady=20)
        
        # Advanced tab (placeholder)  
        advanced_frame = ttk.Frame(notebook)
        notebook.add(advanced_frame, text="Advanced")
        ttk.Label(advanced_frame, text="Advanced settings coming soon...").pack(pady=20)
        
        # Button frame
        button_frame = ttk.Frame(self.root)
        
        # Save button
        save_button = ttk.Button(button_frame, text="Save", command=self._save_settings)
        save_button.pack(side=tk.RIGHT, padx=5)
        
        # Cancel button  
        cancel_button = ttk.Button(button_frame, text="Cancel", command=self._cancel_settings)
        cancel_button.pack(side=tk.RIGHT, padx=5)
        
        # Store references
        self.notebook = notebook
        self.button_frame = button_frame
        self.save_button = save_button
        self.cancel_button = cancel_button
    
    def _setup_layout(self) -> None:
        """Setup widget layout"""
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.button_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
    
    def _save_settings(self) -> None:
        """Save settings and close window"""
        try:
            # Update config with form values
            new_settings = {
                'hotkey': self.hotkey_var.get(),
                'server_url': self.server_url_var.get(), 
                'model': self.model_var.get()
            }
            
            # Validate settings
            validation_result = self._validate_settings(new_settings)
            if validation_result.is_failure():
                messagebox.showerror("Invalid Settings", validation_result.error)
                return
            
            # Apply settings
            self.config.update(new_settings)
            
            # Notify of changes
            if self.on_settings_changed:
                self.on_settings_changed(new_settings)
            
            # Publish settings changed event
            event = SettingsChangedEvent(
                changed_settings=new_settings,
                source="settings_window"
            )
            import asyncio
            # Use call_soon_threadsafe to schedule the coroutine
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(lambda: asyncio.create_task(self.event_bus.publish(event)))
            
            # Close window
            self.hide()
            messagebox.showinfo("Settings Saved", "Settings have been saved successfully!")
            
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            messagebox.showerror("Error", f"Failed to save settings: {e}")
    
    def _cancel_settings(self) -> None:
        """Cancel settings changes and close window"""
        self.hide()
    
    def _validate_settings(self, settings: Dict[str, Any]) -> Result[Dict[str, Any], str]:
        """Validate settings values"""
        # Validate hotkey format
        hotkey = settings.get('hotkey', '').lower()
        if not hotkey or '+' not in hotkey:
            return Failure("Hotkey must be in format like 'ctrl+shift+w'")
        
        # Validate server URL
        server_url = settings.get('server_url', '')
        if not server_url.startswith(('ws://', 'wss://')):
            return Failure("Server URL must start with 'ws://' or 'wss://'")
        
        # Validate model
        model = settings.get('model', '')
        if model not in ['tiny', 'base', 'small', 'medium', 'large']:
            return Failure("Invalid model selection")
        
        return Success(settings)
    
    def destroy(self) -> None:
        """Destroy the settings window"""
        if self.root:
            self.root.destroy()
            self.root = None
        logger.info("Settings window destroyed")
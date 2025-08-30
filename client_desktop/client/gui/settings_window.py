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
from ..settings import get_settings_manager, AppSettings

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
                 on_settings_changed: Optional[Callable[[Dict[str, Any]], None]] = None,
                 config_file: Optional[str] = None):
        self.event_bus = event_bus
        self.on_settings_changed = on_settings_changed
        
        # Initialize settings manager
        self.settings_manager = get_settings_manager(config_file)
        
        # Load current settings
        settings_result = self.settings_manager.load_settings()
        if settings_result.is_success():
            self.current_settings = settings_result.value
        else:
            logger.warning(f"Failed to load settings: {settings_result.error}")
            self.current_settings = AppSettings()
        
        self.root: Optional[tk.Toplevel] = None
        self.parent_window: Optional[tk.Tk] = None
        
        # Form variables - initialize from loaded settings
        self.hotkey_var = tk.StringVar(value=self.current_settings.hotkey)
        self.server_url_var = tk.StringVar(value=self.current_settings.server_url)
        self.model_var = tk.StringVar(value=self.current_settings.model)
        
        # Additional form variables for more settings
        self.audio_sample_rate_var = tk.StringVar(value=str(self.current_settings.audio_sample_rate))
        self.audio_channels_var = tk.StringVar(value=str(self.current_settings.audio_channels))
        self.text_add_space_var = tk.BooleanVar(value=self.current_settings.text_add_space_after)
        self.text_capitalize_var = tk.BooleanVar(value=self.current_settings.text_capitalize_first)
        self.ui_notifications_var = tk.BooleanVar(value=self.current_settings.ui_show_notifications)
        
        logger.info("Settings window initialized")
    
    def show(self, parent_window: tk.Tk) -> Result[None, Exception]:
        """Show the settings window"""
        try:
            # Validate parent window
            if not parent_window or not isinstance(parent_window, tk.Tk):
                logger.error("Invalid parent window provided")
                return Failure(Exception("Invalid parent window"))
                
            # Check if parent window is still valid
            try:
                parent_window.winfo_exists()
            except tk.TclError:
                logger.error("Parent window no longer exists")
                return Failure(Exception("Parent window no longer exists"))
            
            self.parent_window = parent_window
            
            if self.root is None:
                self._create_window()
            else:
                # Check if existing window is still valid
                try:
                    self.root.winfo_exists()
                except tk.TclError:
                    logger.warning("Settings window was destroyed, recreating")
                    self.root = None
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
                try:
                    self.root.grab_release()  # Release modal grab
                    self.root.withdraw()
                except tk.TclError:
                    # Window might already be destroyed
                    pass
            logger.info("Settings window hidden")
            return Success(None)
        except Exception as e:
            logger.error(f"Failed to hide settings window: {e}")
            return Failure(e)
    
    def _create_window(self) -> None:
        """Create the settings window"""
        if not self.parent_window:
            raise Exception("Cannot create settings window: no parent window set")
            
        try:
            self.root = tk.Toplevel(self.parent_window)
            self.root.title("SpeakToMe Settings")
            self.root.geometry("600x500")
            self.root.resizable(True, True)
            self.root.minsize(550, 450)  # Set minimum size
            
            # Make modal
            self.root.transient(self.parent_window)
            self.root.grab_set()
            
            # Handle window close
            self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)
            
            # Center on parent
            self._center_window()
            
            self._create_widgets()
            self._setup_layout()
            
            logger.info("Settings window created")
        except Exception as e:
            logger.error(f"Failed to create settings window: {e}")
            raise
    
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
    
    # Pure UI builder functions (functional composition)
    def _create_notebook_structure(self) -> Dict[str, Any]:
        """Pure function to create main notebook structure"""
        notebook = ttk.Notebook(self.root)
        
        general_frame = ttk.Frame(notebook)
        notebook.add(general_frame, text="General")
        
        audio_frame = ttk.Frame(notebook)
        notebook.add(audio_frame, text="Audio")
        
        advanced_frame = ttk.Frame(notebook)
        notebook.add(advanced_frame, text="Advanced")
        
        return {
            'notebook': notebook,
            'general_frame': general_frame,
            'audio_frame': audio_frame,
            'advanced_frame': advanced_frame
        }
    
    def _create_general_tab_widgets(self, parent_frame) -> Dict[str, Any]:
        """Pure function to create general settings tab widgets"""
        widgets = {}
        
        # Hotkey section
        ttk.Label(parent_frame, text="Recording Hotkey:").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        hotkey_frame = ttk.Frame(parent_frame)
        hotkey_frame.grid(row=0, column=1, padx=10, pady=5, sticky="w")
        
        hotkey_entry = ttk.Entry(hotkey_frame, textvariable=self.hotkey_var, width=20)
        hotkey_entry.pack(side=tk.LEFT, padx=(0, 5))
        
        test_hotkey_btn = ttk.Button(hotkey_frame, text="Test", 
                                   command=self._test_hotkey, width=6)
        test_hotkey_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        suggestions_btn = ttk.Button(hotkey_frame, text="...", 
                                   command=self._show_hotkey_suggestions, width=3)
        suggestions_btn.pack(side=tk.LEFT)
        
        # Server URL section
        ttk.Label(parent_frame, text="Server URL:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        server_entry = ttk.Entry(parent_frame, textvariable=self.server_url_var, width=40)
        server_entry.grid(row=1, column=1, padx=10, pady=5, sticky="w")
        
        # Model selection
        ttk.Label(parent_frame, text="Whisper Model:").grid(row=2, column=0, sticky="w", padx=10, pady=5)
        model_combo = ttk.Combobox(parent_frame, textvariable=self.model_var, 
                                 values=['tiny', 'base', 'small', 'medium', 'large'],
                                 state="readonly", width=15)
        model_combo.grid(row=2, column=1, sticky="w", padx=10, pady=5)
        
        # Configure column weights
        parent_frame.columnconfigure(1, weight=1)
        
        widgets.update({
            'hotkey_frame': hotkey_frame,
            'hotkey_entry': hotkey_entry,
            'server_entry': server_entry,
            'model_combo': model_combo
        })
        
        return widgets
    
    def _create_text_processing_widgets(self, parent_frame) -> Dict[str, Any]:
        """Pure function to create text processing settings"""
        text_frame = ttk.LabelFrame(parent_frame, text="Text Processing", padding=10)
        text_frame.grid(row=3, column=0, columnspan=2, pady=(10, 5), padx=10, sticky="ew")
        
        space_check = ttk.Checkbutton(text_frame, text="Add space after transcription", 
                                    variable=self.text_add_space_var)
        space_check.grid(row=0, column=0, sticky="w", pady=2)
        
        capitalize_check = ttk.Checkbutton(text_frame, text="Capitalize first letter", 
                                         variable=self.text_capitalize_var)
        capitalize_check.grid(row=1, column=0, sticky="w", pady=2)
        
        return {
            'text_frame': text_frame,
            'space_check': space_check,
            'capitalize_check': capitalize_check
        }
    
    def _create_ui_settings_widgets(self, parent_frame) -> Dict[str, Any]:
        """Pure function to create UI settings"""
        ui_frame = ttk.LabelFrame(parent_frame, text="User Interface", padding=10)
        ui_frame.grid(row=4, column=0, columnspan=2, pady=(5, 10), padx=10, sticky="ew")
        
        notifications_check = ttk.Checkbutton(ui_frame, text="Show notifications", 
                                            variable=self.ui_notifications_var)
        notifications_check.grid(row=0, column=0, sticky="w", pady=2)
        
        return {
            'ui_frame': ui_frame,
            'notifications_check': notifications_check
        }
    
    def _create_audio_tab_widgets(self, parent_frame) -> Dict[str, Any]:
        """Pure function to create audio settings tab widgets"""
        # Sample rate
        ttk.Label(parent_frame, text="Sample Rate:").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        sample_rate_combo = ttk.Combobox(parent_frame, textvariable=self.audio_sample_rate_var,
                                       values=['8000', '16000', '22050', '44100', '48000'],
                                       state="readonly", width=10)
        sample_rate_combo.grid(row=0, column=1, sticky="w", padx=10, pady=5)
        
        # Channels
        ttk.Label(parent_frame, text="Channels:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        channels_combo = ttk.Combobox(parent_frame, textvariable=self.audio_channels_var,
                                    values=['1', '2'], state="readonly", width=10)
        channels_combo.grid(row=1, column=1, sticky="w", padx=10, pady=5)
        
        ttk.Label(parent_frame, text="Audio device selection coming soon...").grid(row=2, column=0, columnspan=2, pady=20)
        
        # Configure column weights
        parent_frame.columnconfigure(1, weight=1)
        
        return {
            'sample_rate_combo': sample_rate_combo,
            'channels_combo': channels_combo
        }
    
    def _create_advanced_tab_widgets(self, parent_frame) -> Dict[str, Any]:
        """Pure function to create advanced settings tab widgets"""
        placeholder_label = ttk.Label(parent_frame, text="Advanced settings coming soon...")
        placeholder_label.pack(pady=20)
        
        return {
            'placeholder_label': placeholder_label
        }
    
    def _create_button_widgets(self) -> Dict[str, Any]:
        """Pure function to create action buttons"""
        button_frame = ttk.Frame(self.root)
        
        save_button = ttk.Button(button_frame, text="Save", command=self._save_settings)
        save_button.pack(side=tk.RIGHT, padx=5)
        
        cancel_button = ttk.Button(button_frame, text="Cancel", command=self._cancel_settings)
        cancel_button.pack(side=tk.RIGHT, padx=5)
        
        return {
            'button_frame': button_frame,
            'save_button': save_button,
            'cancel_button': cancel_button
        }

    def _create_widgets(self) -> None:
        """Create settings form widgets using functional composition"""
        # Compose UI sections using pure functions
        notebook_widgets = self._create_notebook_structure()
        general_widgets = self._create_general_tab_widgets(notebook_widgets['general_frame'])
        text_widgets = self._create_text_processing_widgets(notebook_widgets['general_frame'])
        ui_widgets = self._create_ui_settings_widgets(notebook_widgets['general_frame'])
        audio_widgets = self._create_audio_tab_widgets(notebook_widgets['audio_frame'])
        advanced_widgets = self._create_advanced_tab_widgets(notebook_widgets['advanced_frame'])
        button_widgets = self._create_button_widgets()
        
        # Store widget references (preserving original interface)
        self.notebook = notebook_widgets['notebook']
        self.button_frame = button_widgets['button_frame']
        self.save_button = button_widgets['save_button']
        self.cancel_button = button_widgets['cancel_button']
    
    def _setup_layout(self) -> None:
        """Setup widget layout"""
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.button_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
    
    def _save_settings(self) -> None:
        """Save settings and close window"""
        try:
            # Create settings object with form values
            updates = {
                'hotkey': self.hotkey_var.get(),
                'server_url': self.server_url_var.get(),
                'model': self.model_var.get(),
                'audio_sample_rate': int(self.audio_sample_rate_var.get()),
                'audio_channels': int(self.audio_channels_var.get()),
                'text_add_space_after': self.text_add_space_var.get(),
                'text_capitalize_first': self.text_capitalize_var.get(),
                'ui_show_notifications': self.ui_notifications_var.get()
            }
            
            # Update settings using the settings manager
            update_result = self.settings_manager.update_settings(updates)
            if update_result.is_failure():
                messagebox.showerror("Invalid Settings", str(update_result.error))
                return
            
            # Get the updated settings
            self.current_settings = update_result.value
            
            # Notify of changes (for backwards compatibility)
            if self.on_settings_changed:
                self.on_settings_changed(updates)
            
            # Publish settings changed event
            event = SettingsChangedEvent(
                changed_settings=updates,
                source="settings_window"
            )
            import asyncio
            # Use call_soon_threadsafe to schedule the coroutine
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(lambda: asyncio.create_task(self.event_bus.publish(event)))
            
            # Close window
            self.hide()
            
        except ValueError as e:
            messagebox.showerror("Invalid Input", f"Please check your input values: {e}")
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            messagebox.showerror("Error", f"Failed to save settings: {e}")
    
    def _cancel_settings(self) -> None:
        """Cancel settings changes and close window"""
        # Reset form values to current settings
        self.hotkey_var.set(self.current_settings.hotkey)
        self.server_url_var.set(self.current_settings.server_url)
        self.model_var.set(self.current_settings.model)
        self.audio_sample_rate_var.set(str(self.current_settings.audio_sample_rate))
        self.audio_channels_var.set(str(self.current_settings.audio_channels))
        self.text_add_space_var.set(self.current_settings.text_add_space_after)
        self.text_capitalize_var.set(self.current_settings.text_capitalize_first)
        self.ui_notifications_var.set(self.current_settings.ui_show_notifications)
        
        self.hide()
    
    def _test_hotkey(self) -> None:
        """Test if the current hotkey is valid"""
        hotkey = self.hotkey_var.get()
        if self.settings_manager._validate_hotkey(hotkey):
            messagebox.showinfo("Hotkey Valid", f"✅ Hotkey '{hotkey}' is valid!")
        else:
            messagebox.showerror("Invalid Hotkey", 
                               f"❌ Hotkey '{hotkey}' is invalid.\n\n"
                               f"Format should be: modifier+key\n"
                               f"Example: ctrl+shift+w")
    
    def _show_hotkey_suggestions(self) -> None:
        """Show hotkey suggestions dialog"""
        suggestions = self.settings_manager.get_hotkey_suggestions()
        
        # Create suggestions dialog
        dialog = tk.Toplevel(self.root)
        dialog.title("Hotkey Suggestions")
        dialog.geometry("300x400")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center on settings window
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (dialog.winfo_reqwidth() // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (dialog.winfo_reqheight() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        ttk.Label(dialog, text="Select a hotkey combination:", 
                 font=('TkDefaultFont', 10, 'bold')).pack(pady=10)
        
        # Create listbox with suggestions
        listbox_frame = ttk.Frame(dialog)
        listbox_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        listbox = tk.Listbox(listbox_frame, font=('TkDefaultFont', 11))
        scrollbar = ttk.Scrollbar(listbox_frame, orient=tk.VERTICAL, command=listbox.yview)
        listbox.config(yscrollcommand=scrollbar.set)
        
        for suggestion in suggestions:
            listbox.insert(tk.END, suggestion)
        
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Button frame
        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=10)
        
        def select_hotkey():
            selection = listbox.curselection()
            if selection:
                selected_hotkey = listbox.get(selection[0])
                self.hotkey_var.set(selected_hotkey)
                dialog.destroy()
        
        def cancel():
            dialog.destroy()
        
        ttk.Button(button_frame, text="Select", command=select_hotkey).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=cancel).pack(side=tk.LEFT, padx=5)
        
        # Double-click to select
        listbox.bind('<Double-Button-1>', lambda e: select_hotkey())
    
    def _on_window_close(self) -> None:
        """Handle window close event"""
        try:
            if self.root:
                self.root.grab_release()
                self.root.destroy()
                self.root = None
            logger.info("Settings window closed and destroyed")
        except Exception as e:
            logger.error(f"Error closing settings window: {e}")
            self.root = None
    
    def destroy(self) -> None:
        """Destroy the settings window"""
        if self.root:
            try:
                self.root.grab_release()
                self.root.destroy()
            except tk.TclError:
                pass  # Window might already be destroyed
            self.root = None
        logger.info("Settings window destroyed")
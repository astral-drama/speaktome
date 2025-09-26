#!/usr/bin/env python3

"""
Main GUI Window for SpeakToMe Desktop Client

Provides a compact, always-on-top status window showing connection status,
recording state, and transcription results with copy functionality.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import asyncio
import logging
from typing import Optional, Callable, Dict, Any
from threading import Thread
import queue
import time

from shared.functional import Result, Success, Failure
from shared.events import (
    EventBus, ConnectionStatusEvent, TranscriptionReceivedEvent, 
    RecordingStartedEvent, RecordingStoppedEvent, ErrorEvent
)
from .gui_events import TranscriptionCopiedEvent, SettingsChangedEvent

logger = logging.getLogger(__name__)


class MainWindow:
    """
    Main GUI window for the desktop voice client
    
    Features:
    - Connection status indicator
    - Recording state display  
    - Manual start/stop recording buttons
    - Last transcription display with copy button
    - Settings button
    - Compact, always-on-top design
    """
    
    def __init__(self, event_bus: EventBus, config: Dict[str, Any], settings_manager=None):
        self.event_bus = event_bus
        self.config = config
        self.settings_manager = settings_manager
        self.root: Optional[tk.Tk] = None
        self.is_running = False
        
        # GUI update queue for thread safety
        self.gui_queue = queue.Queue()
        
        # State tracking
        self.connection_status = "disconnected"
        self.recording_state = "ready"  # ready, recording, processing
        self.last_transcription = ""
        self.transcription_history = []
        
        # GUI components
        self.status_label: Optional[tk.Label] = None
        self.connection_indicator: Optional[tk.Label] = None
        self.record_button: Optional[tk.Button] = None
        self.transcription_text: Optional[tk.Text] = None
        self.copy_button: Optional[tk.Button] = None
        
        logger.info("Main GUI window initialized")
    
    def initialize(self) -> Result[None, Exception]:
        """Initialize the GUI window and subscribe to events"""
        try:
            # Create the window immediately during initialization
            self._create_window()
            self._subscribe_to_events()
            return Success(None)
        except Exception as e:
            logger.error(f"Failed to initialize main window: {e}")
            return Failure(e)
    
    def _subscribe_to_events(self) -> None:
        """Subscribe to relevant events"""
        self.event_bus.subscribe("connection.status", self._handle_connection_status)
        self.event_bus.subscribe("transcription.received", self._handle_transcription_received)
        self.event_bus.subscribe("recording.started", self._handle_recording_started)
        self.event_bus.subscribe("recording.stopped", self._handle_recording_stopped)
        self.event_bus.subscribe("error", self._handle_error)
        
        logger.info("GUI event subscriptions configured")
    
    def _handle_connection_status(self, event: ConnectionStatusEvent) -> Result[None, Exception]:
        """Handle connection status changes"""
        self._queue_gui_update(lambda: self._update_connection_status(event.status))
        return Success(None)
    
    def _handle_transcription_received(self, event: TranscriptionReceivedEvent) -> Result[None, Exception]:
        """Handle new transcription results"""
        self._queue_gui_update(lambda: self._update_transcription(event.text))
        return Success(None)
    
    def _handle_recording_started(self, event: RecordingStartedEvent) -> Result[None, Exception]:
        """Handle recording started"""
        logger.debug(f"GUI received RecordingStartedEvent: {event}")
        self._queue_gui_update(lambda: self._update_recording_state("recording"))
        return Success(None)
    
    def _handle_recording_stopped(self, event: RecordingStoppedEvent) -> Result[None, Exception]:
        """Handle recording stopped"""  
        logger.debug(f"GUI received RecordingStoppedEvent: {event}")
        self._queue_gui_update(lambda: self._update_recording_state("processing"))
        return Success(None)
    
    def _handle_error(self, event: ErrorEvent) -> Result[None, Exception]:
        """Handle error events"""
        self._queue_gui_update(lambda: self._show_error(event.error_message))
        return Success(None)
    
    def _queue_gui_update(self, update_func: Callable) -> None:
        """Queue a GUI update for thread-safe execution"""
        logger.debug("Queuing GUI update")
        self.gui_queue.put(update_func)
    
    def show(self) -> Result[None, Exception]:
        """Show the main window"""
        try:
            if self.root is None:
                return Failure(Exception("Window not created - call initialize() first"))
            
            self.root.deiconify()
            self.root.lift()
            self.is_running = True
            
            # Start GUI update processing
            self._process_gui_updates()
            
            logger.info("Main window shown")
            return Success(None)
        except Exception as e:
            logger.error(f"Failed to show main window: {e}")
            return Failure(e)
    
    def hide(self) -> Result[None, Exception]:
        """Hide the main window"""
        try:
            if self.root:
                self.root.withdraw()
            self.is_running = False
            logger.info("Main window hidden")
            return Success(None)
        except Exception as e:
            logger.error(f"Failed to hide main window: {e}")
            return Failure(e)
    
    def _create_window(self) -> None:
        """Create the main GUI window"""
        self.root = tk.Tk()
        self.root.title("SpeakToMe Voice Client")
        # Adjusted height to ensure buttons aren't truncated: 3 lines * 15px + buttons ~35px + padding ~20px = ~105px
        self.root.geometry("600x105")
        self.root.resizable(True, True)  # Allow both horizontal and vertical resize
        self.root.minsize(550, 105)  # Set minimum size ensuring buttons are visible
        
        # Keep window on top (can be toggled)
        self.always_on_top = True
        self.root.attributes('-topmost', self.always_on_top)
        
        # Configure window close behavior
        self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)
        
        self._create_widgets()
        self._setup_layout()
        self._setup_gui_hotkeys()
        
        logger.info("Main GUI window created")
    
    def _create_widgets(self) -> None:
        """Create all GUI widgets using functional composition"""
        # Compose UI sections using pure functions
        transcription_widgets = self._create_transcription_widgets()
        bottom_control_widgets = self._create_bottom_control_widgets(transcription_widgets['transcription_frame'])

        # Store widget references
        self.transcription_frame = transcription_widgets['transcription_frame']
        self.history_listbox_frame = transcription_widgets['history_listbox_frame']
        self.history_listbox = transcription_widgets['history_listbox']
        self.history_scrollbar = transcription_widgets['history_scrollbar']

        self.bottom_control_frame = bottom_control_widgets['bottom_control_frame']
        self.record_button = bottom_control_widgets['record_button']
        self.copy_selected_button = bottom_control_widgets['copy_selected_button']
        self.menu_button = bottom_control_widgets['menu_button']
        self.connection_indicator = bottom_control_widgets['connection_indicator']
        self.status_label = bottom_control_widgets['status_label']
    
    def _setup_layout(self) -> None:
        """Setup widget layout"""
        # Transcription layout
        self.transcription_frame.pack(fill=tk.BOTH, expand=True, padx=3, pady=1)

        # History listbox with scrollbar
        self.history_listbox_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 2))
        self.history_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.history_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Bottom control panel with main buttons and menu
        self.bottom_control_frame.pack(fill=tk.X, pady=1)
        self.record_button.pack(side=tk.LEFT, padx=(0, 3))
        self.copy_selected_button.pack(side=tk.LEFT, padx=(0, 3))
        self.menu_button.pack(side=tk.LEFT, padx=3)
        self.status_label.pack(side=tk.RIGHT)
        self.connection_indicator.pack(side=tk.RIGHT, padx=(0, 3))
    
    def _process_gui_updates(self) -> None:
        """Process queued GUI updates"""
        processed = 0
        try:
            while True:
                update_func = self.gui_queue.get_nowait()
                update_func()
                processed += 1
        except queue.Empty:
            pass
        
        if processed > 0:
            logger.debug(f"Processed {processed} GUI updates")
        
        # Schedule next update check
        if self.is_running and self.root:
            self.root.after(100, self._process_gui_updates)
    
    def _update_connection_status(self, status: str) -> None:
        """Update connection status display"""
        self.connection_status = status
        
        if status == "connected":
            self.connection_indicator.config(foreground="green")
            self.status_label.config(text="Connected")
            self.record_button.config(state=tk.NORMAL)
        elif status == "connecting":
            self.connection_indicator.config(foreground="orange") 
            self.status_label.config(text="Connecting...")
            self.record_button.config(state=tk.DISABLED)
        else:
            self.connection_indicator.config(foreground="red")
            self.status_label.config(text="Disconnected")
            self.record_button.config(state=tk.DISABLED)
    
    def _update_recording_state(self, state: str) -> None:
        """Update recording state display"""
        logger.debug(f"Updating recording state: {self.recording_state} -> {state}")
        self.recording_state = state
        
        if state == "recording":
            self.record_button.config(text="🛑 Stop Recording", style="Accent.TButton")
            logger.debug("Button updated to 'Stop Recording'")
        elif state == "processing":
            self.record_button.config(text="⏳ Processing...", state=tk.DISABLED)
            logger.debug("Button updated to 'Processing...'")
        else:
            self.record_button.config(text="🎙️ Start Recording", state=tk.NORMAL)
            # Reset button style
            self.record_button.config(style="TButton")
            logger.debug("Button updated to 'Start Recording'")
    
    def _update_transcription(self, text: str) -> None:
        """Update transcription display"""
        self.last_transcription = text
        transcription_entry = {
            'text': text,
            'timestamp': time.time(),
            'datetime': time.strftime('%H:%M:%S', time.localtime())
        }
        self.transcription_history.append(transcription_entry)
        
        # Add to history listbox (newest at top) - show time prefix but copy pure text
        display_text = f"[{transcription_entry['datetime']}] {text[:80]}{'...' if len(text) > 80 else ''}"
        self.history_listbox.insert(0, display_text)
        
        # Enable copy button
        self.copy_selected_button.config(state=tk.NORMAL)
        
        # Add history window entry
        if hasattr(self, 'history_window') and self.history_window:
            self.history_window.add_transcription(text)
        
        # Reset recording state
        self._update_recording_state("ready")
    
    def _show_error(self, error_message: str) -> None:
        """Show error message"""
        messagebox.showerror("Voice Client Error", error_message)
        self._update_recording_state("ready")
    
    def _toggle_recording(self) -> None:
        """Toggle recording state using functional composition"""
        logger.info(f"GUI button clicked - current recording_state: {self.recording_state}")
        
        # Determine recording action based on current state
        hotkey = self.config.get('hotkey', 'ctrl+shift+w')
        
        if self.recording_state == "ready":
            is_recording_start = True
            action = "start"
        elif self.recording_state == "recording":
            is_recording_start = False  
            action = "stop"
        else:
            logger.warning(f"Cannot toggle recording from state: {self.recording_state}")
            return
        
        # Use functional composition to create and publish event
        result = (
            MainWindow._create_hotkey_event(hotkey, is_recording_start, "gui_button")
            .flat_map(lambda event: self._publish_event_async(event))
        )
        
        if result.is_failure():
            logger.error(f"Failed to {action} recording: {result.error}")
    
    # Pure UI builder functions (functional composition)
    def _create_bottom_control_widgets(self, transcription_frame) -> Dict[str, Any]:
        """Pure function to create bottom control panel with main buttons and menu"""
        bottom_control_frame = ttk.Frame(transcription_frame)

        record_button = ttk.Button(
            bottom_control_frame,
            text="🎙️ Start Recording",
            command=self._toggle_recording,
            width=20
        )

        copy_selected_button = ttk.Button(
            bottom_control_frame,
            text="📋 Copy Selected",
            command=self._copy_selected_transcription,
            state=tk.DISABLED
        )

        menu_button = ttk.Button(
            bottom_control_frame,
            text="☰ Menu",
            command=self._show_hamburger_menu,
            width=8
        )

        # Connection status indicators
        connection_indicator = ttk.Label(bottom_control_frame, text="●", foreground="red")
        status_label = ttk.Label(bottom_control_frame, text="Disconnected", font=('Arial', 9))

        return {
            'bottom_control_frame': bottom_control_frame,
            'record_button': record_button,
            'copy_selected_button': copy_selected_button,
            'menu_button': menu_button,
            'connection_indicator': connection_indicator,
            'status_label': status_label
        }
    
    def _create_transcription_widgets(self) -> Dict[str, Any]:
        """Pure function to create transcription history widgets"""
        transcription_frame = ttk.Frame(self.root, padding=2)
        history_listbox_frame = ttk.Frame(transcription_frame)
        
        history_listbox = tk.Listbox(
            history_listbox_frame,
            height=4,
            width=60,
            font=('Arial', 9),
            selectmode=tk.SINGLE,
            exportselection=False  # Prevent selection clearing
        )
        history_listbox.bind('<<ListboxSelect>>', self._on_history_select)
        
        history_scrollbar = ttk.Scrollbar(history_listbox_frame, orient="vertical", command=history_listbox.yview)
        history_listbox.configure(yscrollcommand=history_scrollbar.set)
        
        return {
            'transcription_frame': transcription_frame,
            'history_listbox_frame': history_listbox_frame,
            'history_listbox': history_listbox,
            'history_scrollbar': history_scrollbar
        }
    
    
    def _get_current_hotkey(self) -> str:
        """Pure function to get current hotkey"""
        if self.settings_manager:
            settings_result = self.settings_manager.load_settings()
            if settings_result.is_success():
                return settings_result.value.hotkey
        return self.config.get('hotkey', 'ctrl+r')
    
    @staticmethod
    def _format_hotkey_display(hotkey: str) -> str:
        """Pure function to format hotkey for display"""
        parts = []
        for part in hotkey.split('+'):
            if part.lower() in ['ctrl', 'shift', 'alt', 'cmd']:
                parts.append(part.capitalize())
            else:
                parts.append(part.lower())
        return '+'.join(parts)

    # Pure functions for recording operations (functional composition)
    @staticmethod
    def _create_hotkey_event(hotkey: str, is_recording_start: bool, source: str) -> Result[Any, str]:
        """Pure function to create hotkey pressed event"""
        try:
            from shared.events import HotkeyPressedEvent
            event = HotkeyPressedEvent(
                hotkey_combination=hotkey,
                is_recording_start=is_recording_start,
                source=source
            )
            return Success(event)
        except Exception as e:
            return Failure(f"Failed to create hotkey event: {e}")
    
    def _publish_event_async(self, event) -> Result[None, Exception]:
        """Publish event using thread-safe utility"""
        from client.voice_client_app import VoiceClientApplication
        publisher = VoiceClientApplication.create_thread_safe_publisher(self.event_bus)
        return publisher(event)

    # Pure functions for clipboard operations (functional composition)
    @staticmethod
    def _extract_selected_index(listbox_selection) -> Result[int, str]:
        """Pure function to extract selected index from listbox selection"""
        if not listbox_selection:
            return Failure("No selection made")
        return Success(listbox_selection[0])
    
    @staticmethod 
    def _calculate_history_index(selected_index: int, history_length: int) -> Result[int, str]:
        """Pure function to convert display index to history index"""
        if selected_index >= history_length:
            return Failure(f"Selected index {selected_index} exceeds history length {history_length}")
        
        history_index = history_length - 1 - selected_index
        if 0 <= history_index < history_length:
            return Success(history_index)
        return Failure(f"Invalid history index {history_index}")
    
    @staticmethod
    def _extract_text_from_history(history: list, history_index: int) -> Result[str, str]:
        """Pure function to extract text from transcription history"""
        if 0 <= history_index < len(history):
            return Success(history[history_index]['text'])
        return Failure(f"History index {history_index} out of bounds")
    
    def _copy_to_clipboard_and_primary(self, text: str) -> Result[None, Exception]:
        """Copy text to both clipboard and primary selection"""
        try:
            import pyperclip
            pyperclip.copy(text)
            
            # Set Tkinter clipboard and primary selection
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(text)
                self.root.selection_clear()
                self.root.selection_own()
                self.root.selection_handle(lambda offset, length: text)
                logger.debug("Set clipboard and primary selection")
            except Exception as e:
                logger.error(f"Error setting primary selection: {e}")
            
            # Also try xclip for primary selection
            try:
                import subprocess
                subprocess.run(['xclip', '-selection', 'primary'], 
                             input=text.encode(), check=False)
                logger.debug("Set primary selection via xclip")
            except Exception as e:
                logger.debug(f"xclip not available: {e}")
            
            return Success(None)
            
        except ImportError:
            # Fallback to Tkinter only
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update()
            return Success(None)
        except Exception as e:
            # Final fallback to Tkinter
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(text)
                self.root.update()
                return Success(None)
            except Exception as fallback_error:
                return Failure(fallback_error)
    
    def _publish_copy_event(self, text: str, history_index: int) -> Result[None, Exception]:
        """Publish transcription copied event"""
        try:
            from .gui_events import TranscriptionCopiedEvent
            event = TranscriptionCopiedEvent(
                text=text,
                transcription_id=str(history_index),
                source="gui_history_copy"
            )
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(lambda: asyncio.create_task(self.event_bus.publish(event)))
            return Success(None)
        except Exception as e:
            return Failure(e)
    
    def _show_copy_confirmation(self) -> None:
        """Show brief copy confirmation in UI"""
        original_text = self.copy_selected_button.cget("text")
        self.copy_selected_button.config(text="✅ Copied!")
        self.root.after(2000, lambda: self.copy_selected_button.config(text=original_text))

    def _copy_selected_transcription(self) -> None:
        """Copy selected transcription to clipboard using functional composition"""
        result = (
            MainWindow._extract_selected_index(self.history_listbox.curselection())
            .flat_map(lambda selected_index: 
                MainWindow._calculate_history_index(selected_index, len(self.transcription_history))
                .flat_map(lambda history_index:
                    MainWindow._extract_text_from_history(self.transcription_history, history_index)
                    .flat_map(lambda text:
                        self._copy_to_clipboard_and_primary(text)
                        .flat_map(lambda _:
                            self._publish_copy_event(text, history_index)
                            .map(lambda _: (text, history_index))
                        )
                    )
                )
            )
        )
        
        if result.is_success():
            self._show_copy_confirmation()
        else:
            error_msg = str(result.error)
            if "No selection" in error_msg:
                messagebox.showwarning("No Selection", "Please select a transcription to copy.")
            else:
                logger.error(f"Copy operation failed: {error_msg}")
    
    def _show_full_history(self) -> None:
        """Show full history window"""
        if hasattr(self, 'history_window') and self.history_window:
            # Clear any old data and populate with current history
            self.history_window.transcriptions = self.transcription_history.copy()
            self.history_window.show(self.root)
    
    def _clear_transcription_history(self) -> None:
        """Clear all transcription history"""
        if not self.transcription_history:
            messagebox.showinfo("No History", "History is already empty.")
            return
        
        # Confirm clear
        result = messagebox.askyesno(
            "Clear History", 
            "Are you sure you want to clear all transcription history? This cannot be undone."
        )
        
        if result:
            self.transcription_history.clear()
            self.history_listbox.delete(0, tk.END)
            self.copy_selected_button.config(state=tk.DISABLED)
            self.last_transcription = ""
    
    def _on_history_select(self, event) -> None:
        """Handle history listbox selection"""
        selection = self.history_listbox.curselection()
        if selection:
            self.copy_selected_button.config(state=tk.NORMAL)
        else:
            self.copy_selected_button.config(state=tk.DISABLED)
    
    def _show_settings(self) -> None:
        """Show settings window"""
        try:
            if hasattr(self, 'settings_window') and self.settings_window:
                # Show existing settings window
                result = self.settings_window.show(self.root)
                if result.is_failure():
                    logger.error(f"Failed to show settings window: {result.error}")
                    messagebox.showerror("Error", f"Failed to show settings: {result.error}")
            else:
                logger.warning("Settings window not available")
                messagebox.showinfo("Settings", "Settings window not available")
        except Exception as e:
            logger.error(f"Error showing settings: {e}")
            messagebox.showerror("Error", f"Failed to show settings: {e}")
    
    def _on_window_close(self) -> None:
        """Handle window close event"""
        # Stop the application when window is closed
        self.is_running = False
        if self.root:
            self.root.quit()  # Exit mainloop
    
    def run(self) -> None:
        """Run the GUI main loop (blocking) - should not be called in async context"""
        if self.root:
            self.root.mainloop()
    
    def _setup_gui_hotkeys(self) -> None:
        """Setup GUI-focused keyboard shortcuts as fallback for global hotkeys"""
        try:
            # Load current hotkey setting from settings manager (live) or config fallback
            if self.settings_manager:
                settings_result = self.settings_manager.load_settings()
                if settings_result.is_success():
                    hotkey = settings_result.value.hotkey
                else:
                    hotkey = self.config.get('hotkey', 'ctrl+r')
            elif hasattr(self, 'config') and 'hotkey' in self.config:
                hotkey = self.config['hotkey']
            else:
                hotkey = 'ctrl+r'  # default
                
            # Convert hotkey format for tkinter (ctrl+shift+r -> <Control-Shift-r>)
            tk_hotkey = self._convert_hotkey_to_tk_format(hotkey)
            
            logger.info(f"Converting hotkey '{hotkey}' to tkinter format: '{tk_hotkey}'")
            
            # Note: Disabling GUI hotkey binding to prevent double firing with global hotkeys
            # Global hotkeys work across all applications, so GUI binding is redundant
            # self.root.bind_all(tk_hotkey, self._on_gui_hotkey)
            
            logger.info(f"GUI hotkey disabled to prevent conflicts with global hotkey: {tk_hotkey}")
            
        except Exception as e:
            logger.error(f"Failed to setup GUI hotkeys: {e}")
    
    def _convert_hotkey_to_tk_format(self, hotkey: str) -> str:
        """Convert hotkey format from 'ctrl+shift+r' to '<Control-Shift-r>'"""
        parts = hotkey.lower().split('+')
        tk_parts = []
        
        for part in parts:
            if part == 'ctrl':
                tk_parts.append('Control')
            elif part == 'shift':
                tk_parts.append('Shift') 
            elif part == 'alt':
                tk_parts.append('Alt')
            elif part == 'cmd' or part == 'meta':
                tk_parts.append('Meta')
            else:
                # Last part is the key - keep lowercase for regular letters
                tk_parts.append(part.lower())
                
        return f"<{'-'.join(tk_parts)}>"
    
    def _on_gui_hotkey(self, event) -> None:
        """Handle GUI hotkey press (when window has focus)"""
        try:
            logger.info(f"GUI hotkey triggered (window focused) - event: {event}")
            logger.info(f"Event details - keysym: {event.keysym}, state: {event.state}, keycode: {event.keycode}")
            
            # Publish hotkey pressed event (same as global hotkey)
            # Get current hotkey from settings (live reload) or fallback to config  
            if self.settings_manager:
                settings_result = self.settings_manager.load_settings()
                if settings_result.is_success():
                    hotkey = settings_result.value.hotkey
                else:
                    hotkey = self.config.get('hotkey', 'ctrl+r')
            else:
                hotkey = self.config.get('hotkey', 'ctrl+r')
            is_recording_start = self.recording_state == "ready"
            
            import asyncio
            from shared.events import HotkeyPressedEvent
            
            # Create and publish event
            event_obj = HotkeyPressedEvent(
                hotkey_combination=hotkey,
                is_recording_start=is_recording_start,
                source="gui_hotkey"
            )
            
            # Use call_soon_threadsafe to schedule the event publishing
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(
                lambda: asyncio.create_task(self.event_bus.publish(event_obj))
            )
            
            logger.info("GUI hotkey event published")
            
        except Exception as e:
            logger.error(f"Failed to handle GUI hotkey: {e}")
    
    def _show_hamburger_menu(self) -> None:
        """Show hamburger menu with secondary options"""
        try:
            menu = tk.Menu(self.root, tearoff=0)

            # Settings option
            menu.add_command(label="⚙️ Settings", command=self._show_settings)

            # View All History option
            menu.add_command(label="📚 View All History", command=self._show_full_history)

            # Clear History option
            menu.add_command(label="🗑️ Clear History", command=self._clear_transcription_history)

            menu.add_separator()

            # Always on top toggle
            if self.always_on_top:
                menu.add_command(label="📌 Disable Always on Top", command=self._toggle_always_on_top)
            else:
                menu.add_command(label="📌 Enable Always on Top", command=self._toggle_always_on_top)

            # Show the menu at the button location
            try:
                x = self.menu_button.winfo_rootx()
                y = self.menu_button.winfo_rooty() + self.menu_button.winfo_height()
                menu.post(x, y)
            finally:
                menu.grab_release()

        except Exception as e:
            logger.error(f"Failed to show hamburger menu: {e}")

    def _toggle_always_on_top(self) -> None:
        """Toggle window always-on-top behavior"""
        try:
            self.always_on_top = not self.always_on_top
            self.root.attributes('-topmost', self.always_on_top)

            if self.always_on_top:
                logger.info("Window set to always on top")
            else:
                logger.info("Window set to normal behavior")

        except Exception as e:
            logger.error(f"Failed to toggle always on top: {e}")
    
    def refresh_settings_display(self) -> None:
        """Refresh GUI display when settings change"""
        try:
            # Get current hotkey from settings
            if self.settings_manager:
                settings_result = self.settings_manager.load_settings()
                if settings_result.is_success():
                    hotkey = settings_result.value.hotkey
                else:
                    hotkey = self.config.get('hotkey', 'ctrl+r')
            else:
                hotkey = self.config.get('hotkey', 'ctrl+r')
            
            # Format hotkey for display - capitalize modifiers but keep single chars lowercase
            parts = []
            for part in hotkey.split('+'):
                if part.lower() in ['ctrl', 'shift', 'alt', 'cmd']:
                    parts.append(part.capitalize())
                else:
                    # Keep single character keys lowercase
                    parts.append(part.lower())
            hotkey_display = '+'.join(parts)
            
            # Re-setup GUI hotkeys with new binding
            self._setup_gui_hotkeys()
            logger.info(f"GUI settings display refreshed for hotkey: {hotkey}")
            
        except Exception as e:
            logger.error(f"Failed to refresh settings display: {e}")
    
    def destroy(self) -> None:
        """Destroy the window and cleanup"""
        self.is_running = False
        if self.root:
            self.root.destroy()
            self.root = None
        logger.info("Main window destroyed")
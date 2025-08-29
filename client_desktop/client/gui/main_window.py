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
    
    def __init__(self, event_bus: EventBus, config: Dict[str, Any]):
        self.event_bus = event_bus
        self.config = config
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
        self._queue_gui_update(lambda: self._update_recording_state("recording"))
        return Success(None)
    
    def _handle_recording_stopped(self, event: RecordingStoppedEvent) -> Result[None, Exception]:
        """Handle recording stopped"""  
        self._queue_gui_update(lambda: self._update_recording_state("processing"))
        return Success(None)
    
    def _handle_error(self, event: ErrorEvent) -> Result[None, Exception]:
        """Handle error events"""
        self._queue_gui_update(lambda: self._show_error(event.error_message))
        return Success(None)
    
    def _queue_gui_update(self, update_func: Callable) -> None:
        """Queue a GUI update for thread-safe execution"""
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
        self.root.geometry("400x300")
        self.root.resizable(False, False)
        
        # Keep window on top
        self.root.attributes('-topmost', True)
        
        # Configure window close behavior
        self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)
        
        self._create_widgets()
        self._setup_layout()
        
        logger.info("Main GUI window created")
    
    def _create_widgets(self) -> None:
        """Create all GUI widgets"""
        # Header frame
        header_frame = ttk.Frame(self.root)
        
        # Title
        title_label = ttk.Label(header_frame, text="🎤 SpeakToMe", font=('Arial', 14, 'bold'))
        
        # Connection status
        self.connection_indicator = ttk.Label(header_frame, text="●", foreground="red")
        self.status_label = ttk.Label(header_frame, text="Disconnected", font=('Arial', 9))
        
        # Control frame  
        control_frame = ttk.Frame(self.root)
        
        # Record button
        self.record_button = ttk.Button(
            control_frame,
            text="🎙️ Start Recording", 
            command=self._toggle_recording,
            width=20
        )
        
        # Settings button
        settings_button = ttk.Button(
            control_frame,
            text="⚙️ Settings",
            command=self._show_settings,
            width=15
        )
        
        # Transcription frame
        transcription_frame = ttk.LabelFrame(self.root, text="Transcription History", padding=10)
        
        # History listbox with scrollbar
        history_listbox_frame = ttk.Frame(transcription_frame)
        
        self.history_listbox = tk.Listbox(
            history_listbox_frame,
            height=8,
            width=60,
            font=('Arial', 9),
            selectmode=tk.SINGLE
        )
        
        # Bind selection event
        self.history_listbox.bind('<<ListboxSelect>>', self._on_history_select)
        
        # Scrollbar for history listbox
        history_scrollbar = ttk.Scrollbar(history_listbox_frame, orient="vertical", command=self.history_listbox.yview)
        self.history_listbox.configure(yscrollcommand=history_scrollbar.set)
        
        # History control buttons
        history_button_frame = ttk.Frame(transcription_frame)
        
        # Copy selected button
        self.copy_selected_button = ttk.Button(
            history_button_frame,
            text="📋 Copy Selected",
            command=self._copy_selected_transcription,
            state=tk.DISABLED
        )
        
        # View all history button  
        self.view_all_button = ttk.Button(
            history_button_frame,
            text="📚 View All History",
            command=self._show_full_history
        )
        
        # Clear history button
        self.clear_history_button = ttk.Button(
            history_button_frame,
            text="🗑️ Clear History", 
            command=self._clear_transcription_history
        )
        
        # Store widget references
        self.header_frame = header_frame
        self.title_label = title_label
        self.control_frame = control_frame
        self.settings_button = settings_button
        self.transcription_frame = transcription_frame
        self.history_listbox_frame = history_listbox_frame
        self.history_scrollbar = history_scrollbar
        self.history_button_frame = history_button_frame
    
    def _setup_layout(self) -> None:
        """Setup widget layout"""
        # Header layout
        self.header_frame.pack(fill=tk.X, padx=10, pady=5)
        self.title_label.pack(side=tk.LEFT)
        self.status_label.pack(side=tk.RIGHT)
        self.connection_indicator.pack(side=tk.RIGHT, padx=(0, 5))
        
        # Control layout
        self.control_frame.pack(fill=tk.X, padx=10, pady=5)
        self.record_button.pack(side=tk.LEFT, padx=(0, 10))
        self.settings_button.pack(side=tk.LEFT)
        
        # Transcription layout
        self.transcription_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # History listbox with scrollbar
        self.history_listbox_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.history_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.history_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # History control buttons
        self.history_button_frame.pack(fill=tk.X)
        self.copy_selected_button.pack(side=tk.LEFT, padx=(0, 5))
        self.view_all_button.pack(side=tk.LEFT, padx=5)
        self.clear_history_button.pack(side=tk.LEFT, padx=5)
    
    def _process_gui_updates(self) -> None:
        """Process queued GUI updates"""
        try:
            while True:
                update_func = self.gui_queue.get_nowait()
                update_func()
        except queue.Empty:
            pass
        
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
        self.recording_state = state
        
        if state == "recording":
            self.record_button.config(text="🛑 Stop Recording", style="Accent.TButton")
        elif state == "processing":
            self.record_button.config(text="⏳ Processing...", state=tk.DISABLED)
        else:
            self.record_button.config(text="🎙️ Start Recording", state=tk.NORMAL)
            # Reset button style
            self.record_button.config(style="TButton")
    
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
        """Toggle recording state"""
        logger.info(f"GUI button clicked - current recording_state: {self.recording_state}")
        
        if self.recording_state == "ready":
            # Start recording - this would trigger hotkey press event
            from shared.events import HotkeyPressedEvent
            event = HotkeyPressedEvent(
                hotkey_combination=self.config.get('hotkey', 'ctrl+shift+w'),
                is_recording_start=True,
                source="gui_button"
            )
            logger.info(f"Publishing start recording event: {event}")
            
            # Use asyncio.create_task directly (similar to hotkey handler)
            try:
                asyncio.create_task(self.event_bus.publish(event))
                logger.info("Start recording event published successfully")
            except Exception as e:
                logger.error(f"Failed to publish start recording event: {e}")
        elif self.recording_state == "recording":
            # Stop recording
            from shared.events import HotkeyPressedEvent  
            event = HotkeyPressedEvent(
                hotkey_combination=self.config.get('hotkey', 'ctrl+shift+w'), 
                is_recording_start=False,
                source="gui_button"
            )
            logger.info(f"Publishing stop recording event: {event}")
            
            # Use asyncio.create_task directly (similar to hotkey handler)
            try:
                asyncio.create_task(self.event_bus.publish(event))
                logger.info("Stop recording event published successfully")
            except Exception as e:
                logger.error(f"Failed to publish stop recording event: {e}")
    
    def _copy_selected_transcription(self) -> None:
        """Copy selected transcription to clipboard"""
        selection = self.history_listbox.curselection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a transcription to copy.")
            return
        
        # Get the selected index (remembering newest is at top)
        selected_index = selection[0]
        logger.info(f"Selected listbox index: {selected_index}")
        logger.info(f"Total transcription_history entries: {len(self.transcription_history)}")
        
        # DEBUG: Show what the listbox actually contains at this index
        try:
            listbox_text = self.history_listbox.get(selected_index)
            logger.info(f"DEBUG: Listbox text at index {selected_index}: '{listbox_text}'")
        except Exception as e:
            logger.error(f"Could not get listbox text: {e}")
        
        if selected_index < len(self.transcription_history):
            # History is stored oldest-first, but displayed newest-first
            history_index = len(self.transcription_history) - 1 - selected_index
            logger.info(f"Calculated history_index: {history_index}")
            
            # Debug: show what's in the transcription_history at this index
            if 0 <= history_index < len(self.transcription_history):
                entry = self.transcription_history[history_index]
                logger.info(f"Transcription entry at history_index {history_index}: {entry}")
                selected_text = entry['text']
                logger.info(f"DEBUG: Original text from history: '{selected_text}'")
                logger.info(f"DEBUG: Does original text contain brackets? {('[' in selected_text or ']' in selected_text)}")
            else:
                logger.error(f"Invalid history_index {history_index} for history of length {len(self.transcription_history)}")
                return
            
            # Copy to clipboard using pyperclip to bypass external interference
            try:
                import pyperclip
                logger.info(f"DEBUG: Using pyperclip to set clipboard to: '{selected_text}'")
                pyperclip.copy(selected_text)
                
                # ALSO set the PRIMARY selection (for middle mouse button) using Tkinter
                try:
                    self.root.clipboard_clear()
                    self.root.clipboard_append(selected_text)
                    # Set PRIMARY selection by clearing listbox selection and forcing our text
                    self.root.selection_clear()
                    self.root.selection_own()
                    self.root.selection_handle(lambda offset, length: selected_text)
                    logger.info("DEBUG: Set both CLIPBOARD and PRIMARY selection")
                except Exception as e:
                    logger.error(f"DEBUG: Error setting PRIMARY selection: {e}")
                
                # Alternative: try using xclip if available
                try:
                    import subprocess
                    subprocess.run(['xclip', '-selection', 'primary'], 
                                 input=selected_text.encode(), check=False)
                    logger.info("DEBUG: Also set PRIMARY selection via xclip")
                except Exception as e:
                    logger.debug(f"DEBUG: xclip not available: {e}")
                
                # Verify with pyperclip immediately
                clipboard_content = pyperclip.paste()
                logger.info(f"DEBUG: pyperclip verification - contains: '{clipboard_content}'")
                logger.info(f"DEBUG: pyperclip matches original? {clipboard_content == selected_text}")
                
                # Add a delay and check again to see if something overwrites it
                import time
                time.sleep(0.1)
                clipboard_content_after_delay = pyperclip.paste()
                logger.info(f"DEBUG: pyperclip verification AFTER 100ms delay - contains: '{clipboard_content_after_delay}'")
                logger.info(f"DEBUG: Clipboard changed after delay? {clipboard_content != clipboard_content_after_delay}")
                
                if clipboard_content != selected_text:
                    logger.error(f"DEBUG: PYPERCLIP MISMATCH! Expected: '{selected_text}', Got: '{clipboard_content}'")
                    # Fallback to Tkinter method
                    logger.info("DEBUG: Falling back to Tkinter clipboard method")
                    self.root.clipboard_clear()
                    self.root.clipboard_append(selected_text)
                    self.root.update()
                else:
                    logger.info("DEBUG: pyperclip successfully set clipboard")
                    
            except ImportError:
                logger.info("DEBUG: pyperclip not available, using Tkinter clipboard")
                self.root.clipboard_clear()
                self.root.clipboard_append(selected_text)
                self.root.update()
                
                # Verify clipboard contents
                try:
                    clipboard_content = self.root.clipboard_get()
                    logger.info(f"DEBUG: Tkinter clipboard verification - contains: '{clipboard_content}'")
                    logger.info(f"DEBUG: Tkinter clipboard matches original? {clipboard_content == selected_text}")
                except Exception as e:
                    logger.error(f"Could not verify clipboard contents: {e}")
            except Exception as e:
                logger.error(f"Error with pyperclip: {e}")
                # Fallback to Tkinter
                self.root.clipboard_clear()
                self.root.clipboard_append(selected_text)
                self.root.update()
            
            # Publish copy event
            event = TranscriptionCopiedEvent(
                text=selected_text,
                transcription_id=str(history_index),
                source="gui_history_copy"
            )
            # Use call_soon_threadsafe to schedule the coroutine
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(lambda: asyncio.create_task(self.event_bus.publish(event)))
            
            # Show brief confirmation
            original_text = self.copy_selected_button.cget("text")
            self.copy_selected_button.config(text="✅ Copied!")
            self.root.after(2000, lambda: self.copy_selected_button.config(text=original_text))
    
    def _show_full_history(self) -> None:
        """Show full history window"""
        if hasattr(self, 'history_window') and self.history_window:
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
        # TODO: Implement settings window
        messagebox.showinfo("Settings", "Settings window coming soon!")
    
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
    
    def destroy(self) -> None:
        """Destroy the window and cleanup"""
        self.is_running = False
        if self.root:
            self.root.destroy()
            self.root = None
        logger.info("Main window destroyed")
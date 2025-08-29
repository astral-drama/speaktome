#!/usr/bin/env python3

"""
Transcription History Window

GUI for viewing, managing, and exporting transcription history.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import logging
import json
import time
from typing import List, Dict, Any, Optional
from datetime import datetime

from shared.functional import Result, Success, Failure
from shared.events import EventBus
from .gui_events import TranscriptionCopiedEvent

logger = logging.getLogger(__name__)


class HistoryWindow:
    """
    Transcription history viewer
    
    Features:
    - List of all transcriptions with timestamps
    - Copy individual transcriptions
    - Clear all history
    - Export history to file
    - Search/filter functionality
    """
    
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        
        self.root: Optional[tk.Toplevel] = None
        self.parent_window: Optional[tk.Tk] = None
        
        # History data
        self.transcriptions: List[Dict[str, Any]] = []
        
        # GUI components
        self.tree: Optional[ttk.Treeview] = None
        self.details_text: Optional[tk.Text] = None
        
        logger.info("History window initialized")
    
    def add_transcription(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Add a transcription to history"""
        transcription = {
            'text': text,
            'timestamp': time.time(),
            'datetime': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'metadata': metadata or {}
        }
        
        self.transcriptions.append(transcription)
        
        # Update tree view if window is open
        if self.tree:
            self._refresh_tree_view()
    
    def show(self, parent_window: tk.Tk) -> Result[None, Exception]:
        """Show the history window"""
        try:
            self.parent_window = parent_window
            
            if self.root is None:
                self._create_window()
            
            self.root.deiconify()
            self.root.lift()
            self.root.focus()
            
            self._refresh_tree_view()
            
            logger.info("History window shown")
            return Success(None)
        except Exception as e:
            logger.error(f"Failed to show history window: {e}")
            return Failure(e)
    
    def hide(self) -> Result[None, Exception]:
        """Hide the history window"""
        try:
            if self.root:
                self.root.withdraw()
            logger.info("History window hidden")
            return Success(None)
        except Exception as e:
            logger.error(f"Failed to hide history window: {e}")
            return Failure(e)
    
    def _create_window(self) -> None:
        """Create the history window"""
        self.root = tk.Toplevel(self.parent_window)
        self.root.title("Transcription History")
        self.root.geometry("700x500")
        
        # Make modal
        self.root.transient(self.parent_window)
        self.root.grab_set()
        
        self._create_widgets()
        self._setup_layout()
        
        logger.info("History window created")
    
    def _create_widgets(self) -> None:
        """Create history window widgets"""
        # Main paned window
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        
        # Left frame - history list
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)
        
        # History tree view
        tree_frame = ttk.Frame(left_frame)
        
        # Column headers
        columns = ('datetime', 'preview')
        self.tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=15)
        
        # Configure columns
        self.tree.heading('datetime', text='Date & Time')
        self.tree.heading('preview', text='Preview')
        self.tree.column('datetime', width=150, anchor='w')
        self.tree.column('preview', width=300, anchor='w')
        
        # Scrollbar for tree
        tree_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scrollbar.set)
        
        # Bind selection event
        self.tree.bind('<<TreeviewSelect>>', self._on_tree_select)
        
        # Right frame - details
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=1)
        
        # Details label
        details_label = ttk.Label(right_frame, text="Full Text:", font=('Arial', 10, 'bold'))
        
        # Details text area
        details_frame = ttk.Frame(right_frame)
        self.details_text = tk.Text(details_frame, wrap=tk.WORD, state=tk.DISABLED,
                                  font=('Arial', 10), height=20)
        details_scrollbar = ttk.Scrollbar(details_frame, orient=tk.VERTICAL,
                                        command=self.details_text.yview)
        self.details_text.configure(yscrollcommand=details_scrollbar.set)
        
        # Button frame
        button_frame = ttk.Frame(self.root)
        
        # Copy button
        copy_button = ttk.Button(button_frame, text="Copy Selected", 
                                command=self._copy_selected)
        
        # Export button
        export_button = ttk.Button(button_frame, text="Export All",
                                 command=self._export_history)
        
        # Clear button
        clear_button = ttk.Button(button_frame, text="Clear All",
                                command=self._clear_history)
        
        # Close button
        close_button = ttk.Button(button_frame, text="Close",
                                command=self.hide)
        
        # Store references
        self.paned = paned
        self.left_frame = left_frame
        self.right_frame = right_frame
        self.tree_frame = tree_frame
        self.tree_scrollbar = tree_scrollbar
        self.details_label = details_label
        self.details_frame = details_frame
        self.details_scrollbar = details_scrollbar
        self.button_frame = button_frame
        self.copy_button = copy_button
        self.export_button = export_button
        self.clear_button = clear_button
        self.close_button = close_button
    
    def _setup_layout(self) -> None:
        """Setup widget layout"""
        # Main paned window
        self.paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left frame layout
        self.tree_frame.pack(fill=tk.BOTH, expand=True)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Right frame layout
        self.details_label.pack(anchor='w', pady=(0, 5))
        self.details_frame.pack(fill=tk.BOTH, expand=True)
        self.details_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.details_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Button frame layout
        self.button_frame.pack(fill=tk.X, padx=10, pady=(5, 10))
        self.close_button.pack(side=tk.RIGHT, padx=(5, 0))
        self.clear_button.pack(side=tk.RIGHT, padx=5)
        self.export_button.pack(side=tk.RIGHT, padx=5) 
        self.copy_button.pack(side=tk.RIGHT, padx=5)
    
    def _refresh_tree_view(self) -> None:
        """Refresh the tree view with current transcriptions"""
        if not self.tree:
            return
        
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Add transcriptions in reverse order (newest first)
        for i, transcription in enumerate(reversed(self.transcriptions)):
            preview = transcription['text'][:50] + ('...' if len(transcription['text']) > 50 else '')
            
            self.tree.insert('', tk.END, iid=str(len(self.transcriptions) - 1 - i),
                           values=(transcription['datetime'], preview))
    
    def _on_tree_select(self, event) -> None:
        """Handle tree selection"""
        selection = self.tree.selection()
        if not selection:
            return
        
        # Get selected transcription
        item_id = selection[0]
        index = int(item_id)
        
        if 0 <= index < len(self.transcriptions):
            transcription = self.transcriptions[index]
            
            # Update details text
            self.details_text.config(state=tk.NORMAL)
            self.details_text.delete('1.0', tk.END)
            self.details_text.insert('1.0', transcription['text'])
            self.details_text.config(state=tk.DISABLED)
    
    def _copy_selected(self) -> None:
        """Copy selected transcription to clipboard"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a transcription to copy.")
            return
        
        # Get selected transcription
        item_id = selection[0]
        index = int(item_id)
        
        if 0 <= index < len(self.transcriptions):
            transcription = self.transcriptions[index]
            text = transcription['text']
            
            # Copy to clipboard
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            
            # Publish copy event
            event = TranscriptionCopiedEvent(
                text=text,
                transcription_id=str(index),
                source="history_window"
            )
            import asyncio
            # Use call_soon_threadsafe to schedule the coroutine
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(lambda: asyncio.create_task(self.event_bus.publish(event)))
            
            messagebox.showinfo("Copied", "Transcription copied to clipboard!")
    
    def _export_history(self) -> None:
        """Export all transcriptions to file"""
        if not self.transcriptions:
            messagebox.showwarning("No Data", "No transcriptions to export.")
            return
        
        # Get export file path
        file_path = filedialog.asksaveasfilename(
            title="Export Transcription History",
            defaultextension=".json",
            filetypes=[
                ("JSON files", "*.json"),
                ("Text files", "*.txt"),
                ("All files", "*.*")
            ]
        )
        
        if not file_path:
            return
        
        try:
            if file_path.endswith('.json'):
                # Export as JSON
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(self.transcriptions, f, indent=2, ensure_ascii=False)
            else:
                # Export as text
                with open(file_path, 'w', encoding='utf-8') as f:
                    for transcription in self.transcriptions:
                        f.write(f"[{transcription['datetime']}]\n")
                        f.write(f"{transcription['text']}\n\n")
            
            messagebox.showinfo("Export Complete", f"History exported to {file_path}")
            
        except Exception as e:
            logger.error(f"Failed to export history: {e}")
            messagebox.showerror("Export Failed", f"Failed to export history: {e}")
    
    def _clear_history(self) -> None:
        """Clear all transcription history"""
        if not self.transcriptions:
            messagebox.showinfo("No Data", "History is already empty.")
            return
        
        # Confirm clear
        result = messagebox.askyesno(
            "Clear History",
            "Are you sure you want to clear all transcription history? This cannot be undone."
        )
        
        if result:
            self.transcriptions.clear()
            self._refresh_tree_view()
            
            # Clear details text
            self.details_text.config(state=tk.NORMAL)
            self.details_text.delete('1.0', tk.END)
            self.details_text.config(state=tk.DISABLED)
            
            messagebox.showinfo("Cleared", "Transcription history cleared.")
    
    def get_history_count(self) -> int:
        """Get number of transcriptions in history"""
        return len(self.transcriptions)
    
    def destroy(self) -> None:
        """Destroy the history window"""
        if self.root:
            self.root.destroy()
            self.root = None
        logger.info("History window destroyed")
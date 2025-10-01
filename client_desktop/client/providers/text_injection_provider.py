#!/usr/bin/env python3

"""
Text Injection Provider

Cross-platform text injection provider using functional patterns.
"""

import asyncio
import logging
import time
import platform
from typing import Optional, Dict, Any
from abc import ABC, abstractmethod

import pyautogui

from shared.functional import Result, Success, Failure, from_callable
from shared.events import get_event_bus, TextInjectedEvent

logger = logging.getLogger(__name__)

# Disable PyAutoGUI failsafe for production use
pyautogui.FAILSAFE = False


class TextInjectionProvider(ABC):
    """Abstract text injection provider interface"""
    
    @abstractmethod
    async def initialize(self) -> Result[None, Exception]:
        """Initialize the text injection provider"""
        pass
    
    @abstractmethod
    async def inject_text(self, text: str, **options) -> Result[None, Exception]:
        """Inject text into the active window"""
        pass
    
    @abstractmethod
    async def cleanup(self) -> None:
        """Cleanup resources"""
        pass


class PyAutoGUIProvider(TextInjectionProvider):
    """
    PyAutoGUI-based text injection provider
    
    Cross-platform text injection using PyAutoGUI with functional error handling.
    """
    
    def __init__(self, 
                 typing_delay: float = 0.0,
                 add_space_after: bool = True,
                 capitalize_first: bool = False):
        self.typing_delay = typing_delay
        self.add_space_after = add_space_after
        self.capitalize_first = capitalize_first
        self.platform = platform.system()
        
        self.event_bus = get_event_bus()
        
        logger.info(f"PyAutoGUI provider initialized for {self.platform}")
    
    async def initialize(self) -> Result[None, Exception]:
        """Initialize PyAutoGUI settings"""
        def _initialize():
            # Platform-specific optimizations
            if self.platform == "Darwin":  # macOS
                # macOS requires accessibility permissions
                logger.info("macOS detected - ensure accessibility permissions are granted")
            elif self.platform == "Linux":
                # Linux may need X11 support
                logger.info("Linux detected - ensure X11 support is available")
            elif self.platform == "Windows":
                # Windows usually works out of the box
                logger.info("Windows detected")
            
            # Set PyAutoGUI defaults
            pyautogui.PAUSE = self.typing_delay
            pyautogui.FAILSAFE = False  # Disable for production
            
            logger.info("PyAutoGUI provider initialized successfully")
        
        return from_callable(_initialize).map(lambda _: None)
    
    async def inject_text(self, text: str, **options) -> Result[None, Exception]:
        """Inject text into the active window"""
        try:
            # Process text based on settings
            processed_text = self._process_text(text, options)

            # Small delay to ensure window focus
            injection_delay = options.get('delay', 0.1)
            if injection_delay > 0:
                await asyncio.sleep(injection_delay)

            # Inject text using PyAutoGUI
            def _type_text():
                pyautogui.typewrite(processed_text, interval=self.typing_delay)
                return len(processed_text)

            result = from_callable(_type_text)

            if result.is_success():
                chars_typed = result.value

                # Publish event
                await self.event_bus.publish(TextInjectedEvent(
                    text=processed_text,
                    target_window=options.get('target_window'),
                    injection_method="pyautogui",
                    source="text_injection_provider",
                    metadata={
                        'chars_typed': chars_typed,
                        'platform': self.platform,
                        'typing_delay': self.typing_delay
                    }
                ))

                logger.info(f"Text injected successfully: '{processed_text[:30]}...' ({chars_typed} chars)")
                return Success(None)
            else:
                logger.error(f"Failed to inject text: {result.error}")
                return result
        except Exception as e:
            logger.error(f"Exception in inject_text: {e}")
            return Failure(e)
    
    async def inject_text_with_formatting(self, text: str, **options) -> Result[None, Exception]:
        """Inject text with additional formatting options"""
        # Add newline if requested
        if options.get('add_newline', False):
            text += '\n'
        
        # Add specific key combinations
        if options.get('select_all_first', False):
            def _select_all():
                if self.platform == "Darwin":
                    pyautogui.hotkey('cmd', 'a')
                else:
                    pyautogui.hotkey('ctrl', 'a')
            
            result = from_callable(_select_all)
            if result.is_failure():
                return Failure(result.error)
            
            # Small delay after select all
            await asyncio.sleep(0.1)
        
        return await self.inject_text(text, **options)
    
    def _process_text(self, text: str, options: Dict[str, Any]) -> str:
        """Process text according to configuration"""
        processed = text.strip()
        
        # Capitalize first letter if configured
        capitalize = options.get('capitalize_first', self.capitalize_first)
        if capitalize and processed:
            processed = processed[0].upper() + processed[1:]
        
        # Add space after if configured
        add_space = options.get('add_space_after', self.add_space_after)
        if add_space:
            processed += ' '
        
        return processed
    
    async def get_active_window_info(self) -> Result[Dict[str, Any], Exception]:
        """Get information about the active window"""
        def _get_window_info():
            try:
                # Get current mouse position (approximation of active window)
                x, y = pyautogui.position()
                size = pyautogui.size()
                
                return {
                    'cursor_position': (x, y),
                    'screen_size': size,
                    'platform': self.platform,
                    'timestamp': time.time()
                }
            except Exception as e:
                raise Exception(f"Failed to get window info: {e}")
        
        return from_callable(_get_window_info)
    
    async def simulate_key_combination(self, *keys) -> Result[None, Exception]:
        """Simulate key combination (e.g., Ctrl+C)"""
        def _simulate_keys():
            pyautogui.hotkey(*keys)
        
        result = from_callable(_simulate_keys)
        
        if result.is_success():
            logger.debug(f"Key combination executed: {' + '.join(keys)}")
        
        return result.map(lambda _: None)
    
    async def cleanup(self) -> None:
        """Cleanup resources"""
        # PyAutoGUI doesn't require explicit cleanup
        logger.info("PyAutoGUI provider cleanup completed")


# Platform-specific providers could be added here
class ClipboardProvider(TextInjectionProvider):
    """
    Alternative text injection via clipboard
    
    Useful as fallback when direct typing doesn't work.
    """
    
    def __init__(self):
        self.platform = platform.system()
        self.event_bus = get_event_bus()
        
    async def initialize(self) -> Result[None, Exception]:
        """Initialize clipboard provider"""
        try:
            import pyperclip
            self.pyperclip = pyperclip
            return Success(None)
        except ImportError:
            return Failure(Exception("pyperclip not available for clipboard injection"))
    
    async def inject_text(self, text: str, **options) -> Result[None, Exception]:
        """Inject text via clipboard and paste"""
        def _clipboard_inject():
            # Copy to clipboard
            self.pyperclip.copy(text)
            
            # Wait a bit
            time.sleep(0.1)
            
            # Paste
            if self.platform == "Darwin":
                pyautogui.hotkey('cmd', 'v')
            else:
                pyautogui.hotkey('ctrl', 'v')
            
            return len(text)
        
        result = from_callable(_clipboard_inject)
        
        if result.is_success():
            await self.event_bus.publish(TextInjectedEvent(
                text=text,
                injection_method="clipboard",
                source="clipboard_provider"
            ))
            
            logger.info(f"Text injected via clipboard: '{text[:30]}...'")
        
        return result.map(lambda _: None)
    
    async def cleanup(self) -> None:
        """Cleanup clipboard provider"""
        # Clear clipboard for security
        if hasattr(self, 'pyperclip'):
            self.pyperclip.copy('')
        
        logger.info("Clipboard provider cleanup completed")
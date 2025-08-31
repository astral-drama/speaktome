#!/usr/bin/env python3

"""
Hotkey Input Handler

Global hotkey detection using functional patterns and event-driven architecture.
"""

import asyncio
import logging
import platform
import threading
from typing import List, Dict, Any, Optional, Callable
from abc import ABC, abstractmethod

from pynput import keyboard
from pynput.keyboard import Key, Listener, HotKey

from shared.functional import Result, Success, Failure, from_callable
from shared.events import get_event_bus, HotkeyPressedEvent

logger = logging.getLogger(__name__)


class HotkeyHandler(ABC):
    """Abstract hotkey handler interface"""
    
    @abstractmethod
    async def initialize(self) -> Result[None, Exception]:
        """Initialize the hotkey handler"""
        pass
    
    @abstractmethod
    async def register_hotkey(self, combination: str, callback: Callable[[], None]) -> Result[None, Exception]:
        """Register a global hotkey combination"""
        pass
    
    @abstractmethod
    async def unregister_hotkey(self, combination: str) -> Result[None, Exception]:
        """Unregister a hotkey combination"""
        pass
    
    @abstractmethod
    async def cleanup(self) -> None:
        """Cleanup hotkey resources"""
        pass
    
    @abstractmethod
    def is_active(self) -> bool:
        """Check if hotkey handler is active"""
        pass


class PynputHotkeyHandler(HotkeyHandler):
    """
    Pynput-based global hotkey handler
    
    Provides cross-platform global hotkey detection with functional error handling
    and event-driven architecture matching server patterns.
    """
    
    def __init__(self, main_loop=None):
        self.hotkeys: Dict[str, HotKey] = {}
        self.callbacks: Dict[str, Callable[[], None]] = {}
        self.listener: Optional[Listener] = None
        self._active = False
        self.main_loop = main_loop  # Reference to main asyncio event loop
        
        self.event_bus = get_event_bus()
        
        logger.info("Pynput hotkey handler initialized")
    
    async def initialize(self) -> Result[None, Exception]:
        """Initialize the global hotkey listener"""
        def _initialize():
            try:
                self.listener = Listener(
                    on_press=self._on_key_press,
                    on_release=self._on_key_release
                )
                
                self.listener.start()
                self._active = True
                
                logger.info("Global hotkey listener started successfully")
                logger.info(f"Listener daemon status: {self.listener.daemon}")
                logger.info(f"Listener running: {self.listener.running}")
                
                # Check for macOS accessibility permission warning
                if platform.system() == "Darwin":
                    # Give the listener a moment to initialize and potentially show warnings
                    import time
                    time.sleep(0.1)
                    if not self.listener.running:
                        logger.warning("⚠️  Hotkey listener not running - may need macOS Accessibility permission")
                
            except Exception as e:
                logger.error(f"Failed to start global hotkey listener: {e}")
                if platform.system() == "Darwin" and "accessibility" in str(e).lower():
                    logger.error("🍎 macOS: Grant Accessibility permission to enable global hotkeys")
                    logger.error("   System Preferences > Security & Privacy > Privacy > Accessibility")
                raise
        
        return from_callable(_initialize).map(lambda _: None)
    
    async def register_hotkey(self, combination: str, callback: Callable[[], None]) -> Result[None, Exception]:
        """Register a global hotkey combination"""
        def _register():
            # Parse hotkey combination
            key_combo = self._parse_hotkey_combination(combination)
            
            # Create wrapped callback that publishes events
            wrapped_callback = self._create_event_callback(combination, callback)
            
            # Create HotKey instance
            hotkey = HotKey(key_combo, wrapped_callback)
            
            # Store hotkey and callback
            self.hotkeys[combination] = hotkey
            self.callbacks[combination] = callback
            
            logger.info(f"Hotkey registered: {combination} with key_combo: {key_combo}")
        
        result = from_callable(_register)
        
        if result.is_failure():
            logger.error(f"Failed to register hotkey {combination}: {result.error}")
        
        return result.map(lambda _: None)
    
    async def unregister_hotkey(self, combination: str) -> Result[None, Exception]:
        """Unregister a hotkey combination"""
        def _unregister():
            if combination in self.hotkeys:
                del self.hotkeys[combination]
                del self.callbacks[combination]
                logger.info(f"Hotkey unregistered: {combination}")
            else:
                raise ValueError(f"Hotkey not found: {combination}")
        
        return from_callable(_unregister).map(lambda _: None)
    
    def _parse_hotkey_combination(self, combination: str) -> List[Key]:
        """Parse hotkey combination string into pynput Key objects"""
        keys = combination.lower().split('+')
        key_combo = []
        
        for key_str in keys:
            key_str = key_str.strip()
            
            if key_str == 'ctrl':
                # Use Key.ctrl which matches both left and right ctrl
                key_combo.append(Key.ctrl)
            elif key_str == 'shift':
                # Use Key.shift which matches both left and right shift  
                key_combo.append(Key.shift)
            elif key_str == 'alt':
                # Use Key.alt which matches both left and right alt
                key_combo.append(Key.alt)
            elif key_str == 'cmd':
                key_combo.append(Key.cmd)
            elif key_str == 'space':
                key_combo.append(Key.space)
            elif key_str == 'enter':
                key_combo.append(Key.enter)
            elif key_str == 'tab':
                key_combo.append(Key.tab)
            elif key_str == 'esc' or key_str == 'escape':
                key_combo.append(Key.esc)
            elif key_str.startswith('f') and len(key_str) > 1:
                # Function keys (f1, f2, etc.)
                try:
                    f_num = int(key_str[1:])
                    if 1 <= f_num <= 12:
                        key_combo.append(getattr(Key, key_str))
                    else:
                        raise ValueError(f"Invalid function key: {key_str}")
                except (ValueError, AttributeError):
                    raise ValueError(f"Invalid function key: {key_str}")
            elif len(key_str) == 1:
                # Single character keys
                key_combo.append(keyboard.KeyCode.from_char(key_str))
            else:
                raise ValueError(f"Unknown key: {key_str}")
        
        return key_combo
    
    def _create_event_callback(self, combination: str, original_callback: Callable[[], None]) -> Callable[[], None]:
        """Create a callback that publishes events and calls the original callback"""
        def event_callback():
            logger.debug(f"Hotkey triggered: {combination}")
            
            # Determine if this is a recording start or stop
            # This is a simple heuristic - in practice you might want more state tracking
            is_recording_start = True  # This would be determined by application state
            
            # Publish hotkey event (thread-safe)
            try:
                if self.main_loop and not self.main_loop.is_closed():
                    # Schedule the coroutine in the main thread using stored loop reference
                    self.main_loop.call_soon_threadsafe(
                        lambda: asyncio.create_task(
                            self.event_bus.publish(HotkeyPressedEvent(
                                hotkey_combination=combination,
                                is_recording_start=is_recording_start,
                                source="hotkey_handler"
                            ))
                        )
                    )
                else:
                    logger.warning("Main event loop not available - cannot publish hotkey event")
            except Exception as e:
                logger.warning(f"Failed to publish hotkey event: {e}")
            
            # Call the original callback
            try:
                original_callback()
            except Exception as e:
                logger.error(f"Hotkey callback failed for {combination}: {e}")
        
        return event_callback
    
    def _on_key_press(self, key):
        """Handle key press events"""
        logger.debug(f"Key pressed: {key} (type: {type(key)})")
        for hotkey in self.hotkeys.values():
            hotkey.press(key)
    
    def _on_key_release(self, key):
        """Handle key release events"""  
        logger.debug(f"Key released: {key} (type: {type(key)})")
        for hotkey in self.hotkeys.values():
            hotkey.release(key)
    
    def is_active(self) -> bool:
        """Check if hotkey handler is active"""
        return self._active and self.listener is not None
    
    async def cleanup(self) -> None:
        """Cleanup hotkey resources"""
        self._active = False
        
        if self.listener:
            self.listener.stop()
            self.listener = None
        
        self.hotkeys.clear()
        self.callbacks.clear()
        
        logger.info("Hotkey handler cleanup completed")


class HotkeyRegistry:
    """
    Registry for managing multiple hotkey handlers and combinations
    
    Provides centralized hotkey management with functional patterns.
    """
    
    def __init__(self, handler: HotkeyHandler):
        self.handler = handler
        self.registered_combinations: Dict[str, Dict[str, Any]] = {}
        
        logger.info("Hotkey registry initialized")
    
    async def register_voice_trigger(self, combination: str, voice_callback: Callable[[], None]) -> Result[None, Exception]:
        """Register hotkey for voice recording trigger"""
        registration_info = {
            'type': 'voice_trigger',
            'callback': voice_callback,
            'registered_at': asyncio.get_event_loop().time()
        }
        
        result = await self.handler.register_hotkey(combination, voice_callback)
        
        if result.is_success():
            self.registered_combinations[combination] = registration_info
            logger.info(f"Voice trigger registered: {combination}")
        else:
            logger.error(f"Failed to register voice trigger {combination}: {result.error}")
        
        return result
    
    async def register_command_hotkey(self, combination: str, command: str, callback: Callable[[], None]) -> Result[None, Exception]:
        """Register hotkey for specific commands"""
        registration_info = {
            'type': 'command',
            'command': command,
            'callback': callback,
            'registered_at': asyncio.get_event_loop().time()
        }
        
        result = await self.handler.register_hotkey(combination, callback)
        
        if result.is_success():
            self.registered_combinations[combination] = registration_info
            logger.info(f"Command hotkey registered: {combination} -> {command}")
        
        return result
    
    async def unregister_all(self) -> Result[None, Exception]:
        """Unregister all hotkey combinations"""
        errors = []
        
        for combination in list(self.registered_combinations.keys()):
            result = await self.handler.unregister_hotkey(combination)
            if result.is_failure():
                errors.append(f"{combination}: {result.error}")
            else:
                del self.registered_combinations[combination]
        
        if errors:
            error_msg = "; ".join(errors)
            return Failure(Exception(f"Failed to unregister some hotkeys: {error_msg}"))
        
        logger.info("All hotkeys unregistered")
        return Success(None)
    
    def get_registered_combinations(self) -> Dict[str, Dict[str, Any]]:
        """Get all registered hotkey combinations"""
        return self.registered_combinations.copy()
    
    async def cleanup(self) -> None:
        """Cleanup registry and handler"""
        await self.unregister_all()
        await self.handler.cleanup()
        
        logger.info("Hotkey registry cleanup completed")


def parse_hotkey_string(hotkey_str: str) -> Result[str, Exception]:
    """Parse and validate hotkey string format"""
    def _parse():
        # Normalize the hotkey string
        normalized = hotkey_str.lower().strip()
        
        # Split by + and validate each part
        parts = [part.strip() for part in normalized.split('+')]
        
        if len(parts) < 2:
            raise ValueError("Hotkey must have at least one modifier and one key")
        
        valid_modifiers = {'ctrl', 'shift', 'alt', 'cmd'}
        valid_keys = set('abcdefghijklmnopqrstuvwxyz0123456789')
        valid_keys.update({'space', 'enter', 'tab', 'esc', 'escape'})
        valid_keys.update([f'f{i}' for i in range(1, 13)])  # F1-F12
        
        modifiers = []
        key = None
        
        for part in parts:
            if part in valid_modifiers:
                modifiers.append(part)
            elif part in valid_keys or len(part) == 1:
                if key is None:
                    key = part
                else:
                    raise ValueError(f"Multiple non-modifier keys specified: {key}, {part}")
            else:
                raise ValueError(f"Invalid key: {part}")
        
        if key is None:
            raise ValueError("No main key specified")
        
        if not modifiers:
            raise ValueError("At least one modifier key required")
        
        # Return normalized format
        return '+'.join(sorted(modifiers) + [key])
    
    return from_callable(_parse)
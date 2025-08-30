#!/usr/bin/env python3

"""
Settings Management System

Handles loading, saving, and validation of application settings with
functional programming patterns and proper error handling.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict

from shared.functional import Result, Success, Failure, from_callable

logger = logging.getLogger(__name__)


@dataclass
class AppSettings:
    """Application settings with default values"""
    # Connection settings
    server_url: str = "ws://localhost:8000/ws/transcribe"
    model: str = "base"
    
    # Input settings
    hotkey: str = "ctrl+shift+w"
    
    # Audio settings
    audio_sample_rate: int = 16000
    audio_channels: int = 1
    audio_chunk_size: int = 1024
    audio_input_device: Optional[int] = None
    
    # Text processing settings
    text_add_space_after: bool = True
    text_capitalize_first: bool = True
    text_auto_punctuation: bool = False
    
    # UI settings
    ui_show_notifications: bool = True
    ui_recording_feedback: bool = True
    
    # Logging settings
    logging_level: str = "INFO"
    logging_file: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert settings to dictionary"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AppSettings':
        """Create settings from dictionary, using defaults for missing keys"""
        # Get default values
        defaults = cls()
        settings_dict = defaults.to_dict()
        
        # Update with provided data
        settings_dict.update(data)
        
        # Create instance with merged data
        return cls(**settings_dict)


class SettingsManager:
    """
    Settings management with persistence
    
    Provides functional interface for loading, saving, and validating
    application settings with JSON file persistence.
    """
    
    def __init__(self, config_file: str = "voice_client_config.json"):
        self.config_file = Path(config_file)
        self._settings: Optional[AppSettings] = None
        
        logger.info(f"Settings manager initialized with config file: {self.config_file}")
    
    def load_settings(self) -> Result[AppSettings, Exception]:
        """Load settings from file, creating defaults if file doesn't exist"""
        def _load():
            if not self.config_file.exists():
                logger.info("Config file doesn't exist, creating with defaults")
                settings = AppSettings()
                # Save defaults to file
                save_result = self.save_settings(settings)
                if save_result.is_failure():
                    logger.warning(f"Failed to save default settings: {save_result.error}")
                return settings
            
            with open(self.config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            settings = AppSettings.from_dict(data)
            logger.info("Settings loaded successfully")
            return settings
        
        result = from_callable(_load)
        if result.is_success():
            self._settings = result.value
        else:
            logger.error(f"Failed to load settings: {result.error}")
            # Fallback to defaults
            self._settings = AppSettings()
        
        return result
    
    def save_settings(self, settings: AppSettings) -> Result[None, Exception]:
        """Save settings to file"""
        def _save():
            # Create parent directory if it doesn't exist
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Validate settings before saving
            validation_result = self.validate_settings(settings)
            if validation_result.is_failure():
                raise Exception(f"Invalid settings: {validation_result.error}")
            
            # Save to file with pretty formatting
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(settings.to_dict(), f, indent=4, ensure_ascii=False)
            
            logger.info(f"Settings saved to {self.config_file}")
        
        result = from_callable(_save)
        if result.is_success():
            self._settings = settings
        
        return result
    
    def get_settings(self) -> AppSettings:
        """Get current settings, loading if not already loaded"""
        if self._settings is None:
            load_result = self.load_settings()
            if load_result.is_failure():
                logger.warning("Using default settings due to load failure")
                self._settings = AppSettings()
        
        return self._settings
    
    def update_settings(self, updates: Dict[str, Any]) -> Result[AppSettings, Exception]:
        """Update specific settings and save to file"""
        current_settings = self.get_settings()
        updated_dict = current_settings.to_dict()
        updated_dict.update(updates)
        
        try:
            new_settings = AppSettings.from_dict(updated_dict)
            save_result = self.save_settings(new_settings)
            
            if save_result.is_success():
                logger.info(f"Settings updated: {list(updates.keys())}")
                return Success(new_settings)
            else:
                return Failure(save_result.error)
                
        except Exception as e:
            logger.error(f"Failed to update settings: {e}")
            return Failure(e)
    
    def validate_settings(self, settings: AppSettings) -> Result[AppSettings, str]:
        """Validate settings values"""
        # Validate hotkey format
        if not self._validate_hotkey(settings.hotkey):
            return Failure(f"Invalid hotkey format: {settings.hotkey}")
        
        # Validate server URL
        if not settings.server_url.startswith(('ws://', 'wss://')):
            return Failure(f"Server URL must start with 'ws://' or 'wss://': {settings.server_url}")
        
        # Validate model
        valid_models = ['tiny', 'base', 'small', 'medium', 'large']
        if settings.model not in valid_models:
            return Failure(f"Invalid model '{settings.model}', must be one of: {valid_models}")
        
        # Validate audio settings
        if settings.audio_sample_rate <= 0:
            return Failure("Audio sample rate must be positive")
        
        if settings.audio_channels not in [1, 2]:
            return Failure("Audio channels must be 1 or 2")
        
        if settings.audio_chunk_size <= 0:
            return Failure("Audio chunk size must be positive")
        
        # Validate logging level
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if settings.logging_level not in valid_levels:
            return Failure(f"Invalid logging level '{settings.logging_level}', must be one of: {valid_levels}")
        
        return Success(settings)
    
    def _validate_hotkey(self, hotkey: str) -> bool:
        """Validate hotkey combination format"""
        if not hotkey or not isinstance(hotkey, str):
            return False
        
        # Convert to lowercase for validation
        hotkey = hotkey.lower().strip()
        
        if '+' not in hotkey:
            return False
        
        parts = [part.strip() for part in hotkey.split('+')]
        
        # Must have at least 2 parts (modifier + key)
        if len(parts) < 2:
            return False
        
        valid_modifiers = {'ctrl', 'shift', 'alt', 'cmd', 'meta'}
        valid_keys = set('abcdefghijklmnopqrstuvwxyz0123456789')
        valid_keys.update(['space', 'enter', 'tab', 'esc', 'escape'])
        valid_keys.update([f'f{i}' for i in range(1, 13)])  # F1-F12
        
        # Check that we have at least one modifier
        modifiers = [part for part in parts[:-1] if part in valid_modifiers]
        if not modifiers:
            return False
        
        # Check that the last part is a valid key
        key = parts[-1]
        if key not in valid_keys and len(key) != 1:
            return False
        
        return True
    
    def get_hotkey_suggestions(self) -> list[str]:
        """Get list of suggested hotkey combinations"""
        return [
            "ctrl+r",
            "ctrl+shift+w",
            "ctrl+shift+r", 
            "ctrl+alt+w",
            "ctrl+alt+r",
            "shift+alt+w",
            "shift+alt+r",
            "ctrl+shift+space",
            "ctrl+alt+space",
            "ctrl+shift+f1",
            "ctrl+shift+f2"
        ]


# Global settings manager instance
_settings_manager: Optional[SettingsManager] = None


def get_settings_manager(config_file: Optional[str] = None) -> SettingsManager:
    """Get global settings manager instance"""
    global _settings_manager
    
    if _settings_manager is None:
        config_file = config_file or "voice_client_config.json"
        _settings_manager = SettingsManager(config_file)
    
    return _settings_manager


def load_app_settings(config_file: Optional[str] = None) -> Result[AppSettings, Exception]:
    """Convenience function to load application settings"""
    manager = get_settings_manager(config_file)
    return manager.load_settings()


def save_app_settings(settings: AppSettings, config_file: Optional[str] = None) -> Result[None, Exception]:
    """Convenience function to save application settings"""
    manager = get_settings_manager(config_file)
    return manager.save_settings(settings)
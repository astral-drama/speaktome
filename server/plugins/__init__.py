"""
Plugin System Module

Provides extensible plugin architecture for the Whisper system.
"""

from .plugin_system import (
    Plugin,
    PluginMetadata,
    PluginType,
    PluginStatus,
    PluginRegistry,
    PluginRegistration,
    get_plugin_registry,
    plugin_metadata
)

from .example_plugins import (
    MetricsCollectorPlugin,
    WebSocketLoggerPlugin,
    AudioDurationCalculatorPlugin,
    NotificationSenderPlugin,
    StorageManagerPlugin,
    register_example_plugins
)

__all__ = [
    "Plugin",
    "PluginMetadata",
    "PluginType", 
    "PluginStatus",
    "PluginRegistry",
    "PluginRegistration",
    "get_plugin_registry",
    "plugin_metadata",
    "MetricsCollectorPlugin",
    "WebSocketLoggerPlugin",
    "AudioDurationCalculatorPlugin", 
    "NotificationSenderPlugin",
    "StorageManagerPlugin",
    "register_example_plugins"
]
#!/usr/bin/env python3

"""
Plugin System for Extensibility

Provides a functional plugin architecture with discovery, loading, and lifecycle management.
Uses Result monads for composable error handling and dependency injection for plugin configuration.
"""

import asyncio
import importlib.util
import inspect
import logging
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Type, TypeVar, Generic, Union

from ..functional.result_monad import Result, Success, Failure, traverse
from ..container import DependencyContainer, get_container
from ..events import EventBus, get_event_bus, DomainEvent, EventHandler, AsyncEventHandler

logger = logging.getLogger(__name__)

T = TypeVar('T')

class PluginStatus(Enum):
    """Plugin lifecycle status"""
    DISCOVERED = "discovered"
    LOADED = "loaded"
    CONFIGURED = "configured"
    STARTED = "started"
    STOPPED = "stopped"
    FAILED = "failed"
    UNLOADED = "unloaded"

class PluginType(Enum):
    """Plugin types for categorization"""
    TRANSCRIPTION_PROVIDER = "transcription_provider"
    AUDIO_PROCESSOR = "audio_processor"
    EVENT_HANDLER = "event_handler"
    MIDDLEWARE = "middleware"
    VALIDATOR = "validator"
    STORAGE_PROVIDER = "storage_provider"
    NOTIFICATION_PROVIDER = "notification_provider"
    METRICS_COLLECTOR = "metrics_collector"

@dataclass
class PluginMetadata:
    """Plugin metadata and configuration"""
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    plugin_type: PluginType = PluginType.EVENT_HANDLER
    dependencies: List[str] = field(default_factory=list)
    required_services: List[str] = field(default_factory=list)
    optional_services: List[str] = field(default_factory=list)
    configuration_schema: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    priority: int = 100  # Lower numbers = higher priority

class Plugin(ABC):
    """Abstract base class for all plugins"""
    
    def __init__(self):
        self._status = PluginStatus.DISCOVERED
        self._container: Optional[DependencyContainer] = None
        self._event_bus: Optional[EventBus] = None
        self._configuration: Dict[str, Any] = {}
    
    @property
    @abstractmethod
    def metadata(self) -> PluginMetadata:
        """Plugin metadata"""
        pass
    
    @property
    def status(self) -> PluginStatus:
        """Current plugin status"""
        return self._status
    
    @property
    def configuration(self) -> Dict[str, Any]:
        """Plugin configuration"""
        return self._configuration.copy()
    
    async def initialize(self, 
                        container: DependencyContainer, 
                        event_bus: EventBus,
                        configuration: Dict[str, Any] = None) -> Result[None, str]:
        """Initialize plugin with dependencies"""
        try:
            self._container = container
            self._event_bus = event_bus
            self._configuration = configuration or {}
            
            # Validate configuration if schema is provided
            if self.metadata.configuration_schema:
                validation_result = self._validate_configuration(self._configuration)
                if validation_result.is_failure():
                    return validation_result
            
            # Call plugin-specific initialization
            init_result = await self.on_initialize()
            if init_result.is_failure():
                self._status = PluginStatus.FAILED
                return init_result
            
            self._status = PluginStatus.CONFIGURED
            return Success(None)
            
        except Exception as e:
            self._status = PluginStatus.FAILED
            logger.error(f"Plugin {self.metadata.name} initialization failed: {e}")
            return Failure(f"Plugin initialization failed: {str(e)}")
    
    async def start(self) -> Result[None, str]:
        """Start the plugin"""
        try:
            if self._status != PluginStatus.CONFIGURED:
                return Failure(f"Plugin not configured (status: {self._status.value})")
            
            start_result = await self.on_start()
            if start_result.is_failure():
                self._status = PluginStatus.FAILED
                return start_result
            
            self._status = PluginStatus.STARTED
            logger.info(f"Plugin {self.metadata.name} started successfully")
            return Success(None)
            
        except Exception as e:
            self._status = PluginStatus.FAILED
            logger.error(f"Plugin {self.metadata.name} start failed: {e}")
            return Failure(f"Plugin start failed: {str(e)}")
    
    async def stop(self) -> Result[None, str]:
        """Stop the plugin"""
        try:
            if self._status not in [PluginStatus.STARTED, PluginStatus.FAILED]:
                return Success(None)  # Already stopped
            
            stop_result = await self.on_stop()
            if stop_result.is_failure():
                logger.error(f"Plugin {self.metadata.name} stop failed: {stop_result.get_error()}")
            
            self._status = PluginStatus.STOPPED
            logger.info(f"Plugin {self.metadata.name} stopped")
            return Success(None)
            
        except Exception as e:
            logger.error(f"Plugin {self.metadata.name} stop error: {e}")
            return Failure(f"Plugin stop failed: {str(e)}")
    
    async def reload(self, configuration: Dict[str, Any] = None) -> Result[None, str]:
        """Reload plugin with new configuration"""
        try:
            # Stop plugin
            stop_result = await self.stop()
            if stop_result.is_failure():
                return stop_result
            
            # Update configuration
            if configuration is not None:
                self._configuration.update(configuration)
            
            # Restart plugin
            return await self.start()
            
        except Exception as e:
            logger.error(f"Plugin {self.metadata.name} reload failed: {e}")
            return Failure(f"Plugin reload failed: {str(e)}")
    
    # Plugin lifecycle hooks (to be implemented by plugin subclasses)
    async def on_initialize(self) -> Result[None, str]:
        """Called during plugin initialization"""
        return Success(None)
    
    async def on_start(self) -> Result[None, str]:
        """Called when plugin starts"""
        return Success(None)
    
    async def on_stop(self) -> Result[None, str]:
        """Called when plugin stops"""
        return Success(None)
    
    # Helper methods
    def get_service(self, service_type: Type[T], name: Optional[str] = None) -> Result[T, str]:
        """Get service from dependency container"""
        if not self._container:
            return Failure("Plugin not initialized")
        
        return self._container.resolve(service_type, name)
    
    async def publish_event(self, event: DomainEvent) -> Result[None, str]:
        """Publish event to event bus"""
        if not self._event_bus:
            return Failure("Plugin not initialized")
        
        return await self._event_bus.publish(event)
    
    def subscribe_to_event(self, event_type: str, handler: Union[EventHandler, AsyncEventHandler]) -> None:
        """Subscribe to events"""
        if self._event_bus:
            self._event_bus.subscribe(event_type, handler)
    
    def _validate_configuration(self, configuration: Dict[str, Any]) -> Result[None, str]:
        """Validate configuration against schema (placeholder)"""
        # This would implement JSON Schema validation or similar
        # For now, just check required fields exist
        try:
            schema = self.metadata.configuration_schema
            required_fields = schema.get('required', [])
            
            for field in required_fields:
                if field not in configuration:
                    return Failure(f"Required configuration field missing: {field}")
            
            return Success(None)
            
        except Exception as e:
            return Failure(f"Configuration validation failed: {str(e)}")

@dataclass
class PluginRegistration:
    """Plugin registration information"""
    metadata: PluginMetadata
    plugin_class: Type[Plugin]
    instance: Optional[Plugin] = None
    file_path: Optional[str] = None
    load_error: Optional[str] = None

class PluginRegistry:
    """Registry for managing plugin discovery and lifecycle"""
    
    def __init__(self, container: DependencyContainer = None, event_bus: EventBus = None):
        self._plugins: Dict[str, PluginRegistration] = {}
        self._container = container or get_container()
        self._event_bus = event_bus or get_event_bus()
        self._plugin_directories: List[Path] = []
        
    def add_plugin_directory(self, directory: Union[str, Path]) -> Result[None, str]:
        """Add directory to search for plugins"""
        try:
            path = Path(directory)
            if not path.exists():
                return Failure(f"Plugin directory does not exist: {directory}")
            
            if not path.is_dir():
                return Failure(f"Plugin path is not a directory: {directory}")
            
            self._plugin_directories.append(path)
            logger.info(f"Added plugin directory: {directory}")
            return Success(None)
            
        except Exception as e:
            return Failure(f"Failed to add plugin directory: {str(e)}")
    
    async def discover_plugins(self) -> Result[List[str], str]:
        """Discover plugins in registered directories"""
        try:
            discovered_plugins = []
            
            for directory in self._plugin_directories:
                discovery_result = await self._discover_in_directory(directory)
                if discovery_result.is_success():
                    discovered_plugins.extend(discovery_result.get_value())
                else:
                    logger.error(f"Plugin discovery failed in {directory}: {discovery_result.get_error()}")
            
            logger.info(f"Discovered {len(discovered_plugins)} plugins")
            return Success(discovered_plugins)
            
        except Exception as e:
            logger.error(f"Plugin discovery failed: {e}")
            return Failure(f"Plugin discovery failed: {str(e)}")
    
    def register_plugin(self, plugin_class: Type[Plugin], file_path: str = None) -> Result[None, str]:
        """Manually register a plugin class"""
        try:
            # Create temporary instance to get metadata
            temp_instance = plugin_class()
            metadata = temp_instance.metadata
            
            if metadata.name in self._plugins:
                return Failure(f"Plugin already registered: {metadata.name}")
            
            registration = PluginRegistration(
                metadata=metadata,
                plugin_class=plugin_class,
                file_path=file_path
            )
            
            self._plugins[metadata.name] = registration
            logger.info(f"Registered plugin: {metadata.name}")
            return Success(None)
            
        except Exception as e:
            logger.error(f"Plugin registration failed: {e}")
            return Failure(f"Plugin registration failed: {str(e)}")
    
    async def load_plugin(self, plugin_name: str, configuration: Dict[str, Any] = None) -> Result[Plugin, str]:
        """Load and initialize a plugin"""
        try:
            if plugin_name not in self._plugins:
                return Failure(f"Plugin not found: {plugin_name}")
            
            registration = self._plugins[plugin_name]
            
            # Check if already loaded
            if registration.instance and registration.instance.status != PluginStatus.FAILED:
                return Success(registration.instance)
            
            # Create plugin instance
            plugin_instance = registration.plugin_class()
            
            # Initialize plugin
            init_result = await plugin_instance.initialize(
                self._container, 
                self._event_bus, 
                configuration
            )
            
            if init_result.is_failure():
                registration.load_error = init_result.get_error()
                return init_result
            
            registration.instance = plugin_instance
            registration.load_error = None
            
            logger.info(f"Loaded plugin: {plugin_name}")
            return Success(plugin_instance)
            
        except Exception as e:
            error_msg = f"Plugin loading failed: {str(e)}"
            logger.error(error_msg)
            
            if plugin_name in self._plugins:
                self._plugins[plugin_name].load_error = error_msg
            
            return Failure(error_msg)
    
    async def start_plugin(self, plugin_name: str) -> Result[None, str]:
        """Start a loaded plugin"""
        try:
            if plugin_name not in self._plugins:
                return Failure(f"Plugin not found: {plugin_name}")
            
            registration = self._plugins[plugin_name]
            
            if not registration.instance:
                return Failure(f"Plugin not loaded: {plugin_name}")
            
            return await registration.instance.start()
            
        except Exception as e:
            logger.error(f"Plugin start failed: {e}")
            return Failure(f"Plugin start failed: {str(e)}")
    
    async def stop_plugin(self, plugin_name: str) -> Result[None, str]:
        """Stop a running plugin"""
        try:
            if plugin_name not in self._plugins:
                return Failure(f"Plugin not found: {plugin_name}")
            
            registration = self._plugins[plugin_name]
            
            if not registration.instance:
                return Success(None)  # Not loaded, nothing to stop
            
            return await registration.instance.stop()
            
        except Exception as e:
            logger.error(f"Plugin stop failed: {e}")
            return Failure(f"Plugin stop failed: {str(e)}")
    
    async def load_and_start_all(self, configurations: Dict[str, Dict[str, Any]] = None) -> Result[Dict[str, bool], str]:
        """Load and start all registered plugins"""
        try:
            configurations = configurations or {}
            results = {}
            
            # Sort plugins by priority (lower number = higher priority)
            sorted_plugins = sorted(
                self._plugins.items(),
                key=lambda x: x[1].metadata.priority
            )
            
            for plugin_name, registration in sorted_plugins:
                if not registration.metadata.enabled:
                    logger.info(f"Skipping disabled plugin: {plugin_name}")
                    results[plugin_name] = True  # Consider disabled as "successful"
                    continue
                
                try:
                    # Load plugin
                    plugin_config = configurations.get(plugin_name, {})
                    load_result = await self.load_plugin(plugin_name, plugin_config)
                    
                    if load_result.is_failure():
                        logger.error(f"Failed to load plugin {plugin_name}: {load_result.get_error()}")
                        results[plugin_name] = False
                        continue
                    
                    # Start plugin
                    start_result = await self.start_plugin(plugin_name)
                    
                    if start_result.is_failure():
                        logger.error(f"Failed to start plugin {plugin_name}: {start_result.get_error()}")
                        results[plugin_name] = False
                    else:
                        logger.info(f"Successfully started plugin: {plugin_name}")
                        results[plugin_name] = True
                    
                except Exception as e:
                    logger.error(f"Exception with plugin {plugin_name}: {e}")
                    results[plugin_name] = False
            
            return Success(results)
            
        except Exception as e:
            logger.error(f"Failed to load and start plugins: {e}")
            return Failure(f"Plugin startup failed: {str(e)}")
    
    async def stop_all_plugins(self) -> Result[Dict[str, bool], str]:
        """Stop all running plugins"""
        try:
            results = {}
            
            # Stop in reverse priority order
            sorted_plugins = sorted(
                self._plugins.items(),
                key=lambda x: x[1].metadata.priority,
                reverse=True
            )
            
            for plugin_name, registration in sorted_plugins:
                if registration.instance:
                    stop_result = await self.stop_plugin(plugin_name)
                    results[plugin_name] = stop_result.is_success()
                else:
                    results[plugin_name] = True  # Not loaded, consider successful
            
            return Success(results)
            
        except Exception as e:
            logger.error(f"Failed to stop plugins: {e}")
            return Failure(f"Plugin shutdown failed: {str(e)}")
    
    def get_plugin_info(self, plugin_name: str) -> Optional[PluginRegistration]:
        """Get plugin registration information"""
        return self._plugins.get(plugin_name)
    
    def list_plugins(self) -> Dict[str, PluginRegistration]:
        """List all registered plugins"""
        return self._plugins.copy()
    
    def get_plugins_by_type(self, plugin_type: PluginType) -> List[PluginRegistration]:
        """Get plugins of a specific type"""
        return [
            registration for registration in self._plugins.values()
            if registration.metadata.plugin_type == plugin_type
        ]
    
    async def _discover_in_directory(self, directory: Path) -> Result[List[str], str]:
        """Discover plugins in a specific directory"""
        try:
            discovered = []
            
            # Look for Python files
            for py_file in directory.glob("*.py"):
                if py_file.name.startswith("_"):
                    continue  # Skip private files
                
                discovery_result = await self._discover_in_file(py_file)
                if discovery_result.is_success():
                    discovered.extend(discovery_result.get_value())
                else:
                    logger.warning(f"Plugin discovery failed for {py_file}: {discovery_result.get_error()}")
            
            return Success(discovered)
            
        except Exception as e:
            return Failure(f"Directory discovery failed: {str(e)}")
    
    async def _discover_in_file(self, file_path: Path) -> Result[List[str], str]:
        """Discover plugins in a specific file"""
        try:
            # Load module
            spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
            if not spec or not spec.loader:
                return Failure("Could not load module spec")
            
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            discovered = []
            
            # Look for Plugin subclasses
            for name in dir(module):
                obj = getattr(module, name)
                
                if (inspect.isclass(obj) and 
                    issubclass(obj, Plugin) and 
                    obj != Plugin):
                    
                    register_result = self.register_plugin(obj, str(file_path))
                    if register_result.is_success():
                        discovered.append(obj.metadata.name)
                    else:
                        logger.warning(f"Failed to register plugin {name}: {register_result.get_error()}")
            
            return Success(discovered)
            
        except Exception as e:
            return Failure(f"File discovery failed: {str(e)}")

# Global plugin registry
_global_plugin_registry = PluginRegistry()

def get_plugin_registry() -> PluginRegistry:
    """Get the global plugin registry"""
    return _global_plugin_registry

# Plugin decorators for easier plugin creation
def plugin_metadata(**kwargs) -> Callable[[Type[Plugin]], Type[Plugin]]:
    """Decorator to set plugin metadata"""
    def decorator(plugin_class: Type[Plugin]) -> Type[Plugin]:
        # Store metadata as class attribute
        plugin_class._plugin_metadata = PluginMetadata(**kwargs)
        return plugin_class
    
    return decorator
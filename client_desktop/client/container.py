#!/usr/bin/env python3

"""
Dependency Injection Container for Desktop Client

Provides consistent dependency management patterns matching the server architecture.
"""

import logging
from typing import Dict, Any, Optional, TypeVar, Type, Callable
from dataclasses import dataclass

from shared.functional import Result, Success, Failure

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class ClientConfig:
    """Client configuration matching server patterns"""
    server_url: str = "ws://localhost:8000/ws/transcribe"
    model: str = "base"
    hotkey: str = "ctrl+shift+w"
    
    # Audio configuration
    audio_sample_rate: int = 16000
    audio_channels: int = 1
    audio_chunk_size: int = 1024
    audio_input_device: Optional[int] = None
    
    # Text processing
    text_add_space_after: bool = True
    text_capitalize_first: bool = True
    text_auto_punctuation: bool = False
    
    # UI configuration
    ui_show_notifications: bool = True
    ui_recording_feedback: bool = True
    
    # Logging
    logging_level: str = "INFO"
    logging_file: Optional[str] = None


class ClientContainer:
    """
    Dependency injection container for client components
    
    Matches server container patterns for consistent development experience.
    """
    
    def __init__(self, config: ClientConfig):
        self.config = config
        self._services: Dict[str, Any] = {}
        self._factories: Dict[str, Callable[[], Any]] = {}
        self._singletons: Dict[str, Any] = {}
        
        logger.info("Client container initialized")
    
    def register_singleton(self, name: str, instance: T) -> None:
        """Register a singleton instance"""
        self._singletons[name] = instance
        logger.debug(f"Singleton registered: {name}")
    
    def register_factory(self, name: str, factory: Callable[[], T]) -> None:
        """Register a factory function"""
        self._factories[name] = factory
        logger.debug(f"Factory registered: {name}")
    
    def register_service(self, name: str, service: T) -> None:
        """Register a service instance"""
        self._services[name] = service
        logger.debug(f"Service registered: {name}")
    
    def get(self, name: str, service_type: Type[T] = None) -> Result[T, str]:
        """Get a service by name"""
        # Check singletons first
        if name in self._singletons:
            return Success(self._singletons[name])
        
        # Check services
        if name in self._services:
            return Success(self._services[name])
        
        # Check factories
        if name in self._factories:
            try:
                instance = self._factories[name]()
                return Success(instance)
            except Exception as e:
                return Failure(f"Factory failed for {name}: {e}")
        
        return Failure(f"Service not found: {name}")
    
    def get_or_create(self, name: str, factory: Callable[[], T]) -> Result[T, str]:
        """Get service or create with factory if not found"""
        result = self.get(name)
        if result.is_success():
            return result
        
        try:
            instance = factory()
            self.register_service(name, instance)
            return Success(instance)
        except Exception as e:
            return Failure(f"Failed to create {name}: {e}")
    
    async def initialize_services(self) -> Result[None, str]:
        """Initialize all registered services"""
        logger.info("Initializing client services...")
        
        # Initialize services that require async setup
        for name, service in self._services.items():
            if hasattr(service, 'initialize') and callable(service.initialize):
                try:
                    if asyncio.iscoroutinefunction(service.initialize):
                        await service.initialize()
                    else:
                        service.initialize()
                    logger.debug(f"Service initialized: {name}")
                except Exception as e:
                    logger.error(f"Failed to initialize {name}: {e}")
                    return Failure(f"Service initialization failed: {name}")
        
        logger.info("All services initialized successfully")
        return Success(None)
    
    async def cleanup_services(self) -> None:
        """Cleanup all services"""
        logger.info("Cleaning up client services...")
        
        for name, service in self._services.items():
            if hasattr(service, 'cleanup') and callable(service.cleanup):
                try:
                    if asyncio.iscoroutinefunction(service.cleanup):
                        await service.cleanup()
                    else:
                        service.cleanup()
                    logger.debug(f"Service cleaned up: {name}")
                except Exception as e:
                    logger.error(f"Failed to cleanup {name}: {e}")
        
        logger.info("Service cleanup completed")


# Global container instance
_container: Optional[ClientContainer] = None


def get_container() -> ClientContainer:
    """Get the global container instance"""
    global _container
    
    if _container is None:
        config = ClientConfig()
        _container = ClientContainer(config)
    
    return _container


def set_container(container: ClientContainer) -> None:
    """Set the global container instance"""
    global _container
    _container = container
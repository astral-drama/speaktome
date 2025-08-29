#!/usr/bin/env python3

"""
Shared Event System

Event-driven architecture components shared between server and client.
Provides consistent event handling patterns across both components.
"""

import asyncio
import logging
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar, Generic
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from enum import Enum

from .functional import Result, Success, Failure

logger = logging.getLogger(__name__)

# Event types
T = TypeVar('T')


class EventPriority(Enum):
    """Event processing priority levels"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class BaseEvent(ABC):
    """Base class for all events in the system"""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    priority: EventPriority = EventPriority.NORMAL
    source: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    @abstractmethod
    def event_type(self) -> str:
        """Return the event type identifier"""
        pass


# Client-specific events
@dataclass
class HotkeyPressedEvent(BaseEvent):
    """Event fired when global hotkey is pressed"""
    hotkey_combination: str = ""
    is_recording_start: bool = False
    
    @property
    def event_type(self) -> str:
        return "hotkey.pressed"


@dataclass
class RecordingStartedEvent(BaseEvent):
    """Event fired when audio recording starts"""
    sample_rate: int = 16000
    channels: int = 1
    device_id: Optional[int] = None
    
    @property
    def event_type(self) -> str:
        return "recording.started"


@dataclass
class RecordingStoppedEvent(BaseEvent):
    """Event fired when audio recording stops"""
    duration_seconds: float = 0.0
    audio_size_bytes: int = 0
    
    @property
    def event_type(self) -> str:
        return "recording.stopped"


@dataclass
class AudioCapturedEvent(BaseEvent):
    """Event fired when audio data is captured"""
    audio_data: bytes = b""
    format: str = "wav"
    duration_seconds: float = 0.0
    
    @property
    def event_type(self) -> str:
        return "audio.captured"


@dataclass
class TranscriptionRequestedEvent(BaseEvent):
    """Event fired when transcription is requested"""
    audio_size: int = 0
    model: str = "base"
    language: str = "auto"
    
    @property
    def event_type(self) -> str:
        return "transcription.requested"


@dataclass
class TranscriptionReceivedEvent(BaseEvent):
    """Event fired when transcription is received"""
    text: str = ""
    language: str = "auto"
    processing_time: float = 0.0
    confidence: Optional[float] = None
    
    @property
    def event_type(self) -> str:
        return "transcription.received"


@dataclass
class TextInjectedEvent(BaseEvent):
    """Event fired when text is injected into active window"""
    text: str = ""
    target_window: Optional[str] = None
    injection_method: str = "keyboard"
    
    @property
    def event_type(self) -> str:
        return "text.injected"


@dataclass
class ConnectionStatusEvent(BaseEvent):
    """Event fired when server connection status changes"""
    status: str = "disconnected"  # "connected", "disconnected", "connecting", "error"
    server_url: str = ""
    error_message: Optional[str] = None
    
    @property
    def event_type(self) -> str:
        return "connection.status"


@dataclass
class ErrorEvent(BaseEvent):
    """Event fired when an error occurs"""
    error_type: str = "unknown"
    error_message: str = ""
    component: str = "system"
    stack_trace: Optional[str] = None
    
    @property
    def event_type(self) -> str:
        return "system.error"
    
    def __post_init__(self):
        self.priority = EventPriority.HIGH


# Event handler types
EventHandler = Callable[[BaseEvent], Result[None, Exception]]
AsyncEventHandler = Callable[[BaseEvent], asyncio.Future[Result[None, Exception]]]


class EventBus:
    """
    Central event bus for decoupled communication
    
    Consistent with server-side event bus implementation but adapted
    for client-specific patterns and requirements.
    """
    
    def __init__(self):
        self._handlers: Dict[str, List[EventHandler]] = {}
        self._async_handlers: Dict[str, List[AsyncEventHandler]] = {}
        self._middleware: List[Callable[[BaseEvent], Result[BaseEvent, Exception]]] = []
        self._running = False
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._processor_task: Optional[asyncio.Task] = None
        
        logger.info("Event bus initialized")
    
    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Subscribe to events of a specific type"""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        
        self._handlers[event_type].append(handler)
        logger.debug(f"Handler subscribed to {event_type}")
    
    def subscribe_async(self, event_type: str, handler: AsyncEventHandler) -> None:
        """Subscribe async handler to events of a specific type"""
        if event_type not in self._async_handlers:
            self._async_handlers[event_type] = []
        
        self._async_handlers[event_type].append(handler)
        logger.debug(f"Async handler subscribed to {event_type}")
    
    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Unsubscribe handler from events"""
        if event_type in self._handlers:
            try:
                self._handlers[event_type].remove(handler)
                logger.debug(f"Handler unsubscribed from {event_type}")
            except ValueError:
                logger.warning(f"Handler not found for {event_type}")
    
    def add_middleware(self, middleware: Callable[[BaseEvent], Result[BaseEvent, Exception]]) -> None:
        """Add event processing middleware"""
        self._middleware.append(middleware)
        logger.debug("Middleware added to event bus")
    
    async def start(self) -> None:
        """Start the event bus processor"""
        if self._running:
            logger.warning("Event bus is already running")
            return
        
        self._running = True
        self._processor_task = asyncio.create_task(self._process_events())
        logger.info("Event bus started")
    
    async def stop(self) -> None:
        """Stop the event bus processor"""
        if not self._running:
            return
        
        self._running = False
        
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Event bus stopped")
    
    async def publish(self, event: BaseEvent) -> Result[None, Exception]:
        """Publish an event to the bus"""
        try:
            # Apply middleware
            processed_event = event
            for middleware in self._middleware:
                result = middleware(processed_event)
                if result.is_failure():
                    logger.error(f"Middleware failed for {event.event_type}: {result.error}")
                    return result
                processed_event = result.value
            
            # Add to queue for processing
            await self._event_queue.put(processed_event)
            
            logger.debug(f"Event published: {event.event_type} (ID: {event.event_id})")
            return Success(None)
            
        except Exception as e:
            logger.error(f"Failed to publish event {event.event_type}: {e}")
            return Failure(e)
    
    def publish_sync(self, event: BaseEvent) -> Result[None, Exception]:
        """Publish event synchronously (for compatibility)"""
        try:
            # Create event loop if none exists
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            return loop.run_until_complete(self.publish(event))
            
        except Exception as e:
            logger.error(f"Failed to publish event synchronously: {e}")
            return Failure(e)
    
    async def _process_events(self) -> None:
        """Process events from the queue"""
        while self._running:
            try:
                # Get event with timeout to allow checking _running flag
                event = await asyncio.wait_for(self._event_queue.get(), timeout=0.1)
                await self._handle_event(event)
                
            except asyncio.TimeoutError:
                continue  # Check _running flag
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing events: {e}")
    
    async def _handle_event(self, event: BaseEvent) -> None:
        """Handle a single event"""
        event_type = event.event_type
        
        # Handle synchronous handlers
        if event_type in self._handlers:
            for handler in self._handlers[event_type]:
                try:
                    result = handler(event)
                    if result.is_failure():
                        logger.error(f"Handler failed for {event_type}: {result.error}")
                except Exception as e:
                    logger.error(f"Handler exception for {event_type}: {e}")
        
        # Handle async handlers
        if event_type in self._async_handlers:
            tasks = []
            for handler in self._async_handlers[event_type]:
                try:
                    task = asyncio.create_task(handler(event))
                    tasks.append(task)
                except Exception as e:
                    logger.error(f"Async handler setup failed for {event_type}: {e}")
            
            # Wait for all async handlers
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        logger.error(f"Async handler {i} failed for {event_type}: {result}")
                    elif hasattr(result, 'is_failure') and result.is_failure():
                        logger.error(f"Async handler {i} returned failure for {event_type}: {result.error}")


# Global event bus instance
_global_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get the global event bus instance"""
    global _global_event_bus
    
    if _global_event_bus is None:
        _global_event_bus = EventBus()
    
    return _global_event_bus


# Event middleware utilities
def logging_middleware(event: BaseEvent) -> Result[BaseEvent, Exception]:
    """Middleware to log all events"""
    logger.debug(f"Event: {event.event_type} from {event.source} at {event.timestamp}")
    return Success(event)


def timing_middleware(event: BaseEvent) -> Result[BaseEvent, Exception]:
    """Middleware to add timing information"""
    if 'processing_start_time' not in event.metadata:
        event.metadata['processing_start_time'] = time.time()
    
    return Success(event)


def priority_filter_middleware(min_priority: EventPriority):
    """Create middleware to filter events by priority"""
    def middleware(event: BaseEvent) -> Result[BaseEvent, Exception]:
        if event.priority.value >= min_priority.value:
            return Success(event)
        else:
            return Failure(f"Event priority {event.priority} below minimum {min_priority}")
    
    return middleware


# Decorators for event handling
def event_handler(event_type: str, event_bus: Optional[EventBus] = None):
    """Decorator to register event handlers"""
    def decorator(func: EventHandler):
        bus = event_bus or get_event_bus()
        bus.subscribe(event_type, func)
        return func
    return decorator


def async_event_handler(event_type: str, event_bus: Optional[EventBus] = None):
    """Decorator to register async event handlers"""
    def decorator(func: AsyncEventHandler):
        bus = event_bus or get_event_bus()
        bus.subscribe_async(event_type, func)
        return func
    return decorator
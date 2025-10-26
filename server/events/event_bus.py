#!/usr/bin/env python3

"""
Event-Driven Architecture

Provides a functional event bus with domain events, handlers, and middleware.
Uses Result monads for composable error handling in event processing.
"""

import asyncio
import logging
import time
import uuid
from typing import Dict, List, Optional, Any, Callable, TypeVar, Generic, Union, Set, Awaitable
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from enum import Enum

from ..functional.result_monad import Result, Success, Failure, traverse

logger = logging.getLogger(__name__)

T = TypeVar('T')

class EventPriority(Enum):
    """Event priority levels"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4

@dataclass(frozen=True)
class DomainEvent:
    """Base domain event with immutable data"""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = ""
    timestamp: float = field(default_factory=time.time)
    source: Optional[str] = None
    correlation_id: Optional[str] = None
    priority: EventPriority = EventPriority.NORMAL
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def with_data(self, **data) -> 'DomainEvent':
        """Create new event with additional data"""
        new_data = {**self.data, **data}
        return DomainEvent(
            event_id=self.event_id,
            event_type=self.event_type,
            timestamp=self.timestamp,
            source=self.source,
            correlation_id=self.correlation_id,
            priority=self.priority,
            data=new_data,
            metadata=self.metadata
        )
    
    def with_metadata(self, **metadata) -> 'DomainEvent':
        """Create new event with additional metadata"""
        new_metadata = {**self.metadata, **metadata}
        return DomainEvent(
            event_id=self.event_id,
            event_type=self.event_type,
            timestamp=self.timestamp,
            source=self.source,
            correlation_id=self.correlation_id,
            priority=self.priority,
            data=self.data,
            metadata=new_metadata
        )

# Audio-specific domain events
@dataclass(frozen=True)
class AudioUploadedEvent(DomainEvent):
    """Event fired when audio is uploaded"""
    event_type: str = "audio.uploaded"
    
    @classmethod
    def create(cls, request_id: str, file_path: str, file_size: int, client_id: str = None) -> 'AudioUploadedEvent':
        return cls(
            source="audio_service",
            correlation_id=request_id,
            data={
                "request_id": request_id,
                "file_path": file_path,
                "file_size": file_size,
                "client_id": client_id
            }
        )

@dataclass(frozen=True)
class TranscriptionStartedEvent(DomainEvent):
    """Event fired when transcription begins"""
    event_type: str = "transcription.started"
    
    @classmethod
    def create(cls, request_id: str, model: str, language: str = None, client_id: str = None) -> 'TranscriptionStartedEvent':
        return cls(
            source="transcription_service",
            correlation_id=request_id,
            data={
                "request_id": request_id,
                "model": model,
                "language": language,
                "client_id": client_id
            }
        )

@dataclass(frozen=True)
class TranscriptionCompletedEvent(DomainEvent):
    """Event fired when transcription completes"""
    event_type: str = "transcription.completed"
    
    @classmethod
    def create(cls, request_id: str, text: str, language: str, processing_time: float, client_id: str = None) -> 'TranscriptionCompletedEvent':
        return cls(
            source="transcription_service", 
            correlation_id=request_id,
            data={
                "request_id": request_id,
                "text": text,
                "language": language,
                "processing_time": processing_time,
                "client_id": client_id
            }
        )

@dataclass(frozen=True)
class TranscriptionFailedEvent(DomainEvent):
    """Event fired when transcription fails"""
    event_type: str = "transcription.failed"
    priority: EventPriority = EventPriority.HIGH
    
    @classmethod
    def create(cls, request_id: str, error: str, client_id: str = None) -> 'TranscriptionFailedEvent':
        return cls(
            source="transcription_service",
            correlation_id=request_id,
            data={
                "request_id": request_id,
                "error": error,
                "client_id": client_id
            }
        )

# TTS-specific domain events
@dataclass(frozen=True)
class TextSubmittedEvent(DomainEvent):
    """Event fired when text is submitted for synthesis"""
    event_type: str = "tts.text_submitted"

    @classmethod
    def create(cls, request_id: str, text: str, voice: str, client_id: str = None) -> 'TextSubmittedEvent':
        return cls(
            source="tts_service",
            correlation_id=request_id,
            data={
                "request_id": request_id,
                "text": text[:100],  # Truncate for logging
                "text_length": len(text),
                "voice": voice,
                "client_id": client_id
            }
        )

@dataclass(frozen=True)
class SynthesisStartedEvent(DomainEvent):
    """Event fired when TTS synthesis begins"""
    event_type: str = "tts.synthesis_started"

    @classmethod
    def create(cls, request_id: str, voice: str, text_length: int, client_id: str = None) -> 'SynthesisStartedEvent':
        return cls(
            source="tts_service",
            correlation_id=request_id,
            data={
                "request_id": request_id,
                "voice": voice,
                "text_length": text_length,
                "client_id": client_id
            }
        )

@dataclass(frozen=True)
class SynthesisCompletedEvent(DomainEvent):
    """Event fired when TTS synthesis completes"""
    event_type: str = "tts.synthesis_completed"

    @classmethod
    def create(cls, request_id: str, audio_size: int, duration: float, processing_time: float, client_id: str = None) -> 'SynthesisCompletedEvent':
        return cls(
            source="tts_service",
            correlation_id=request_id,
            data={
                "request_id": request_id,
                "audio_size": audio_size,
                "duration": duration,
                "processing_time": processing_time,
                "client_id": client_id
            }
        )

@dataclass(frozen=True)
class SynthesisFailedEvent(DomainEvent):
    """Event fired when TTS synthesis fails"""
    event_type: str = "tts.synthesis_failed"
    priority: EventPriority = EventPriority.HIGH

    @classmethod
    def create(cls, request_id: str, error: str, client_id: str = None) -> 'SynthesisFailedEvent':
        return cls(
            source="tts_service",
            correlation_id=request_id,
            data={
                "request_id": request_id,
                "error": error,
                "client_id": client_id
            }
        )

@dataclass(frozen=True)
class WebSocketConnectedEvent(DomainEvent):
    """Event fired when WebSocket client connects"""
    event_type: str = "websocket.connected"
    
    @classmethod
    def create(cls, client_id: str, remote_address: str = None) -> 'WebSocketConnectedEvent':
        return cls(
            source="websocket_manager",
            correlation_id=client_id,
            data={
                "client_id": client_id,
                "remote_address": remote_address
            }
        )

@dataclass(frozen=True)
class WebSocketDisconnectedEvent(DomainEvent):
    """Event fired when WebSocket client disconnects"""
    event_type: str = "websocket.disconnected"
    
    @classmethod
    def create(cls, client_id: str, reason: str = None) -> 'WebSocketDisconnectedEvent':
        return cls(
            source="websocket_manager",
            correlation_id=client_id,
            data={
                "client_id": client_id,
                "reason": reason
            }
        )

# Event handler types
EventHandler = Callable[[DomainEvent], Result[None, str]]
AsyncEventHandler = Callable[[DomainEvent], Awaitable[Result[None, str]]]

class EventHandlerRegistry:
    """Registry for event handlers with pattern matching"""
    
    def __init__(self):
        self._handlers: Dict[str, List[AsyncEventHandler]] = {}
        self._wildcard_handlers: List[AsyncEventHandler] = []
        self._middleware: List[AsyncEventHandler] = []
    
    def subscribe(self, event_type: str, handler: Union[EventHandler, AsyncEventHandler]) -> None:
        """Subscribe to specific event type"""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        
        # Wrap sync handlers
        if not asyncio.iscoroutinefunction(handler):
            async_handler = self._wrap_sync_handler(handler)
        else:
            async_handler = handler
        
        self._handlers[event_type].append(async_handler)
        logger.debug(f"Subscribed handler to event type: {event_type}")
    
    def subscribe_all(self, handler: Union[EventHandler, AsyncEventHandler]) -> None:
        """Subscribe to all events (wildcard)"""
        if not asyncio.iscoroutinefunction(handler):
            async_handler = self._wrap_sync_handler(handler)
        else:
            async_handler = handler
        
        self._wildcard_handlers.append(async_handler)
        logger.debug("Subscribed wildcard handler")
    
    def add_middleware(self, middleware: Union[EventHandler, AsyncEventHandler]) -> None:
        """Add middleware that processes all events before handlers"""
        if not asyncio.iscoroutinefunction(middleware):
            async_middleware = self._wrap_sync_handler(middleware)
        else:
            async_middleware = middleware
        
        self._middleware.append(async_middleware)
        logger.debug("Added event middleware")
    
    def unsubscribe(self, event_type: str, handler: AsyncEventHandler) -> bool:
        """Unsubscribe handler from event type"""
        if event_type in self._handlers:
            try:
                self._handlers[event_type].remove(handler)
                if not self._handlers[event_type]:
                    del self._handlers[event_type]
                logger.debug(f"Unsubscribed handler from event type: {event_type}")
                return True
            except ValueError:
                pass
        return False
    
    def get_handlers(self, event_type: str) -> List[AsyncEventHandler]:
        """Get all handlers for an event type"""
        handlers = []
        
        # Add specific handlers
        if event_type in self._handlers:
            handlers.extend(self._handlers[event_type])
        
        # Add wildcard handlers
        handlers.extend(self._wildcard_handlers)
        
        return handlers
    
    def get_middleware(self) -> List[AsyncEventHandler]:
        """Get all middleware"""
        return self._middleware.copy()
    
    def _wrap_sync_handler(self, handler: EventHandler) -> AsyncEventHandler:
        """Wrap synchronous handler for async execution"""
        async def wrapped_handler(event: DomainEvent) -> Result[None, str]:
            try:
                return handler(event)
            except Exception as e:
                logger.error(f"Sync handler error: {e}")
                return Failure(f"Handler error: {str(e)}")
        
        return wrapped_handler

class EventBus:
    """Functional event bus with middleware and error handling"""
    
    def __init__(self):
        self._registry = EventHandlerRegistry()
        self._processing_queue = asyncio.Queue()
        self._dead_letter_queue = asyncio.Queue()
        self._processing_task = None
        self._stopped = False
        
        # Metrics
        self._published_count = 0
        self._processed_count = 0
        self._failed_count = 0
    
    async def start(self) -> Result[None, str]:
        """Start the event bus processing"""
        try:
            if self._processing_task and not self._processing_task.done():
                return Failure("Event bus is already running")
            
            self._stopped = False
            self._processing_task = asyncio.create_task(self._process_events())
            
            logger.info("Event bus started")
            return Success(None)
            
        except Exception as e:
            logger.error(f"Failed to start event bus: {e}")
            return Failure(f"Event bus start failed: {str(e)}")
    
    async def stop(self) -> Result[None, str]:
        """Stop the event bus processing"""
        try:
            self._stopped = True
            
            if self._processing_task:
                self._processing_task.cancel()
                try:
                    await self._processing_task
                except asyncio.CancelledError:
                    pass
            
            logger.info("Event bus stopped")
            return Success(None)
            
        except Exception as e:
            logger.error(f"Failed to stop event bus: {e}")
            return Failure(f"Event bus stop failed: {str(e)}")
    
    async def publish(self, event: DomainEvent) -> Result[None, str]:
        """Publish an event to the bus"""
        try:
            if self._stopped:
                return Failure("Event bus is stopped")
            
            # Add event to processing queue
            await self._processing_queue.put(event)
            self._published_count += 1
            
            logger.debug(f"Published event: {event.event_type} (id: {event.event_id})")
            return Success(None)
            
        except Exception as e:
            logger.error(f"Failed to publish event: {e}")
            return Failure(f"Event publish failed: {str(e)}")
    
    def subscribe(self, event_type: str, handler: Union[EventHandler, AsyncEventHandler]) -> None:
        """Subscribe to events"""
        self._registry.subscribe(event_type, handler)
    
    def subscribe_all(self, handler: Union[EventHandler, AsyncEventHandler]) -> None:
        """Subscribe to all events"""
        self._registry.subscribe_all(handler)
    
    def add_middleware(self, middleware: Union[EventHandler, AsyncEventHandler]) -> None:
        """Add middleware"""
        self._registry.add_middleware(middleware)
    
    async def _process_events(self) -> None:
        """Main event processing loop"""
        logger.info("Event processing started")
        
        try:
            while not self._stopped:
                try:
                    # Wait for event with timeout to allow graceful shutdown
                    event = await asyncio.wait_for(self._processing_queue.get(), timeout=1.0)
                    await self._process_event(event)
                    
                except asyncio.TimeoutError:
                    continue  # Normal timeout, check if stopped
                except Exception as e:
                    logger.error(f"Event processing error: {e}")
                    
        except asyncio.CancelledError:
            logger.info("Event processing cancelled")
            raise
        except Exception as e:
            logger.error(f"Fatal event processing error: {e}")
        
        logger.info("Event processing stopped")
    
    async def _process_event(self, event: DomainEvent) -> None:
        """Process a single event"""
        try:
            start_time = time.time()
            
            # Process middleware first
            middleware_result = await self._process_middleware(event)
            if middleware_result.is_failure():
                logger.error(f"Middleware failed for event {event.event_id}: {middleware_result.get_error()}")
                await self._send_to_dead_letter(event, middleware_result.get_error())
                return
            
            # Get handlers
            handlers = self._registry.get_handlers(event.event_type)
            if not handlers:
                logger.debug(f"No handlers for event type: {event.event_type}")
                return
            
            # Process handlers in parallel
            handler_results = await self._process_handlers(event, handlers)
            
            # Check results
            successful_handlers = sum(1 for result in handler_results if result.is_success())
            failed_handlers = len(handler_results) - successful_handlers
            
            processing_time = time.time() - start_time
            
            if failed_handlers > 0:
                self._failed_count += 1
                logger.warning(f"Event {event.event_id} processed with {failed_handlers} handler failures")
                
                # Send to dead letter queue if all handlers failed
                if successful_handlers == 0:
                    await self._send_to_dead_letter(event, "All handlers failed")
            else:
                logger.debug(f"Event {event.event_id} processed successfully in {processing_time:.3f}s")
            
            self._processed_count += 1
            
        except Exception as e:
            self._failed_count += 1
            logger.error(f"Failed to process event {event.event_id}: {e}")
            await self._send_to_dead_letter(event, str(e))
    
    async def _process_middleware(self, event: DomainEvent) -> Result[None, str]:
        """Process event through middleware pipeline"""
        try:
            middleware_list = self._registry.get_middleware()
            
            for middleware in middleware_list:
                try:
                    result = await middleware(event)
                    if isinstance(result, Result) and result.is_failure():
                        return result
                except Exception as e:
                    logger.error(f"Middleware exception: {e}")
                    return Failure(f"Middleware error: {str(e)}")
            
            return Success(None)
            
        except Exception as e:
            return Failure(f"Middleware processing failed: {str(e)}")
    
    async def _process_handlers(self, event: DomainEvent, handlers: List[AsyncEventHandler]) -> List[Result[None, str]]:
        """Process event handlers in parallel"""
        try:
            # Create tasks for all handlers
            tasks = [self._safe_handler_call(handler, event) for handler in handlers]
            
            # Wait for all handlers to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Convert exceptions to Failure results
            processed_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    processed_results.append(Failure(f"Handler exception: {str(result)}"))
                elif isinstance(result, Result):
                    processed_results.append(result)
                else:
                    processed_results.append(Success(None))  # Handler returned None
            
            return processed_results
            
        except Exception as e:
            logger.error(f"Handler processing failed: {e}")
            return [Failure(f"Handler processing error: {str(e)}")]
    
    async def _safe_handler_call(self, handler: AsyncEventHandler, event: DomainEvent) -> Result[None, str]:
        """Safely call a handler with error handling"""
        try:
            result = await handler(event)
            return result if isinstance(result, Result) else Success(None)
        except Exception as e:
            logger.error(f"Handler error: {e}")
            return Failure(f"Handler exception: {str(e)}")
    
    async def _send_to_dead_letter(self, event: DomainEvent, error: str) -> None:
        """Send failed event to dead letter queue"""
        try:
            dead_letter_event = event.with_metadata(
                dead_letter_reason=error,
                dead_letter_timestamp=time.time()
            )
            await self._dead_letter_queue.put(dead_letter_event)
            logger.warning(f"Event {event.event_id} sent to dead letter queue: {error}")
        except Exception as e:
            logger.error(f"Failed to send event to dead letter queue: {e}")
    
    def get_metrics(self) -> Dict[str, int]:
        """Get event bus metrics"""
        return {
            "published_count": self._published_count,
            "processed_count": self._processed_count,
            "failed_count": self._failed_count,
            "queue_size": self._processing_queue.qsize(),
            "dead_letter_size": self._dead_letter_queue.qsize()
        }

# Global event bus instance
_global_event_bus = EventBus()

def get_event_bus() -> EventBus:
    """Get the global event bus instance"""
    return _global_event_bus

# Convenience functions for common domain events
async def publish_audio_uploaded(request_id: str, file_path: str, file_size: int, client_id: str = None) -> Result[None, str]:
    """Publish audio uploaded event"""
    event = AudioUploadedEvent.create(request_id, file_path, file_size, client_id)
    return await _global_event_bus.publish(event)

async def publish_transcription_started(request_id: str, model: str, language: str = None, client_id: str = None) -> Result[None, str]:
    """Publish transcription started event"""
    event = TranscriptionStartedEvent.create(request_id, model, language, client_id)
    return await _global_event_bus.publish(event)

async def publish_transcription_completed(request_id: str, text: str, language: str, processing_time: float, client_id: str = None) -> Result[None, str]:
    """Publish transcription completed event"""
    event = TranscriptionCompletedEvent.create(request_id, text, language, processing_time, client_id)
    return await _global_event_bus.publish(event)

async def publish_transcription_failed(request_id: str, error: str, client_id: str = None) -> Result[None, str]:
    """Publish transcription failed event"""
    event = TranscriptionFailedEvent.create(request_id, error, client_id)
    return await _global_event_bus.publish(event)

async def publish_websocket_connected(client_id: str, remote_address: str = None) -> Result[None, str]:
    """Publish WebSocket connected event"""
    event = WebSocketConnectedEvent.create(client_id, remote_address)
    return await _global_event_bus.publish(event)

async def publish_websocket_disconnected(client_id: str, reason: str = None) -> Result[None, str]:
    """Publish WebSocket disconnected event"""
    event = WebSocketDisconnectedEvent.create(client_id, reason)
    return await _global_event_bus.publish(event)
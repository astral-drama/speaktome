"""
Event-Driven Architecture Module

Provides domain events, event bus, and handler registration capabilities.
"""

from .event_bus import (
    EventBus,
    EventHandlerRegistry,
    DomainEvent,
    EventPriority,
    AudioUploadedEvent,
    TranscriptionStartedEvent,
    TranscriptionCompletedEvent,
    TranscriptionFailedEvent,
    WebSocketConnectedEvent,
    WebSocketDisconnectedEvent,
    EventHandler,
    AsyncEventHandler,
    get_event_bus,
    publish_audio_uploaded,
    publish_transcription_started,
    publish_transcription_completed,
    publish_transcription_failed,
    publish_websocket_connected,
    publish_websocket_disconnected
)

__all__ = [
    "EventBus",
    "EventHandlerRegistry", 
    "DomainEvent",
    "EventPriority",
    "AudioUploadedEvent",
    "TranscriptionStartedEvent",
    "TranscriptionCompletedEvent",
    "TranscriptionFailedEvent",
    "WebSocketConnectedEvent",
    "WebSocketDisconnectedEvent",
    "EventHandler",
    "AsyncEventHandler",
    "get_event_bus",
    "publish_audio_uploaded",
    "publish_transcription_started", 
    "publish_transcription_completed",
    "publish_transcription_failed",
    "publish_websocket_connected",
    "publish_websocket_disconnected"
]
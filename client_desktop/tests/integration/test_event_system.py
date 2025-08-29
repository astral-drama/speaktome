#!/usr/bin/env python3

"""
Test Event System Integration

Integration tests for event-driven communication between client components.
Tests event flow, handler registration, and system-wide event orchestration.
"""

import asyncio
import pytest
from typing import List
from unittest.mock import Mock

from shared.events import (
    EventBus, get_event_bus,
    HotkeyPressedEvent, RecordingStartedEvent, RecordingStoppedEvent,
    AudioCapturedEvent, TranscriptionReceivedEvent, TextInjectedEvent,
    ConnectionStatusEvent, ErrorEvent,
    EventPriority, logging_middleware, timing_middleware
)
from shared.functional import Result, Success, Failure
from tests.conftest import assert_result_success, wait_for_condition


class TestEventBusIntegration:
    """Test event bus integration and component communication"""
    
    @pytest.mark.asyncio
    async def test_event_bus_lifecycle(self):
        """Test event bus startup and shutdown"""
        event_bus = EventBus()
        
        # Should start successfully
        await event_bus.start()
        assert event_bus._running
        
        # Should stop cleanly
        await event_bus.stop()
        assert not event_bus._running
    
    @pytest.mark.asyncio
    async def test_event_publication_and_subscription(self, test_event_bus):
        """Test basic event publication and subscription"""
        received_events = []
        
        def event_handler(event):
            received_events.append(event)
            return Success(None)
        
        # Subscribe to events
        test_event_bus.subscribe("hotkey.pressed", event_handler)
        
        # Create and publish test event
        test_event = HotkeyPressedEvent(
            hotkey_combination="ctrl+shift+t",
            is_recording_start=True,
            source="test"
        )
        
        result = await test_event_bus.publish(test_event)
        assert_result_success(result)
        
        # Wait for event processing
        await wait_for_condition(lambda: len(received_events) > 0)
        
        # Verify event was received
        assert len(received_events) == 1
        assert received_events[0].hotkey_combination == "ctrl+shift+t"
    
    @pytest.mark.asyncio
    async def test_multiple_handlers_same_event(self, test_event_bus):
        """Test multiple handlers for the same event type"""
        handler1_calls = []
        handler2_calls = []
        
        def handler1(event):
            handler1_calls.append(event)
            return Success(None)
        
        def handler2(event):
            handler2_calls.append(event)
            return Success(None)
        
        # Subscribe both handlers
        test_event_bus.subscribe("recording.started", handler1)
        test_event_bus.subscribe("recording.started", handler2)
        
        # Publish event
        event = RecordingStartedEvent(
            sample_rate=16000,
            channels=1,
            source="test"
        )
        
        await test_event_bus.publish(event)
        
        # Wait for processing
        await wait_for_condition(lambda: len(handler1_calls) > 0 and len(handler2_calls) > 0)
        
        # Both handlers should receive the event
        assert len(handler1_calls) == 1
        assert len(handler2_calls) == 1
    
    @pytest.mark.asyncio
    async def test_async_event_handlers(self, test_event_bus):
        """Test async event handler support"""
        received_events = []
        
        async def async_handler(event):
            await asyncio.sleep(0.01)  # Simulate async work
            received_events.append(event)
            return Success(None)
        
        # Subscribe async handler
        test_event_bus.subscribe_async("transcription.received", async_handler)
        
        # Publish event
        event = TranscriptionReceivedEvent(
            text="test transcription",
            language="en",
            processing_time=0.1,
            source="test"
        )
        
        await test_event_bus.publish(event)
        
        # Wait for async processing
        await wait_for_condition(lambda: len(received_events) > 0)
        
        assert len(received_events) == 1
        assert received_events[0].text == "test transcription"
    
    @pytest.mark.asyncio
    async def test_event_handler_failure_handling(self, test_event_bus):
        """Test that handler failures don't break event processing"""
        successful_calls = []
        
        def failing_handler(event):
            raise Exception("Handler failure")
        
        def successful_handler(event):
            successful_calls.append(event)
            return Success(None)
        
        # Subscribe both handlers
        test_event_bus.subscribe("system.error", failing_handler)
        test_event_bus.subscribe("system.error", successful_handler)
        
        # Publish event
        event = ErrorEvent(
            error_type="test_error",
            error_message="Test error message",
            component="test_component",
            source="test"
        )
        
        await test_event_bus.publish(event)
        
        # Wait for processing
        await wait_for_condition(lambda: len(successful_calls) > 0)
        
        # Successful handler should still receive the event
        assert len(successful_calls) == 1
    
    @pytest.mark.asyncio
    async def test_event_middleware(self, test_event_bus):
        """Test event middleware functionality"""
        middleware_calls = []
        handler_calls = []
        
        def test_middleware(event):
            middleware_calls.append(event)
            # Add middleware metadata
            event.metadata["middleware_processed"] = True
            return Success(event)
        
        def event_handler(event):
            handler_calls.append(event)
            return Success(None)
        
        # Add middleware and subscribe handler
        test_event_bus.add_middleware(test_middleware)
        test_event_bus.subscribe("connection.status", event_handler)
        
        # Publish event
        event = ConnectionStatusEvent(
            status="connected",
            server_url="ws://test:8000",
            source="test"
        )
        
        await test_event_bus.publish(event)
        
        # Wait for processing
        await wait_for_condition(lambda: len(handler_calls) > 0)
        
        # Middleware should process event first
        assert len(middleware_calls) == 1
        assert len(handler_calls) == 1
        
        # Handler should receive modified event
        received_event = handler_calls[0]
        assert received_event.metadata.get("middleware_processed") is True


class TestEventFlow:
    """Test realistic event flows through the system"""
    
    @pytest.mark.asyncio
    async def test_voice_recording_workflow_events(self, test_event_bus):
        """Test complete voice recording workflow event sequence"""
        event_sequence = []
        
        def track_events(event):
            event_sequence.append(event.event_type)
            return Success(None)
        
        # Subscribe to all relevant events
        event_types = [
            "hotkey.pressed",
            "recording.started", 
            "recording.stopped",
            "audio.captured",
            "transcription.received",
            "text.injected"
        ]
        
        for event_type in event_types:
            test_event_bus.subscribe(event_type, track_events)
        
        # Simulate complete workflow
        events = [
            HotkeyPressedEvent(hotkey_combination="ctrl+shift+w", is_recording_start=True),
            RecordingStartedEvent(sample_rate=16000, channels=1),
            RecordingStoppedEvent(duration_seconds=2.5, audio_size_bytes=80000),
            AudioCapturedEvent(audio_data=b"audio", format="wav", duration_seconds=2.5),
            TranscriptionReceivedEvent(text="Hello world", language="en", processing_time=0.3),
            TextInjectedEvent(text="Hello world", injection_method="keyboard")
        ]
        
        # Publish events in sequence
        for event in events:
            await test_event_bus.publish(event)
            await asyncio.sleep(0.01)  # Small delay between events
        
        # Wait for all events to be processed
        await wait_for_condition(lambda: len(event_sequence) >= len(events))
        
        # Verify event sequence
        expected_sequence = [
            "hotkey.pressed",
            "recording.started",
            "recording.stopped", 
            "audio.captured",
            "transcription.received",
            "text.injected"
        ]
        
        assert event_sequence == expected_sequence
    
    @pytest.mark.asyncio
    async def test_error_handling_workflow(self, test_event_bus):
        """Test error event propagation and handling"""
        error_events = []
        
        def error_handler(event):
            error_events.append(event)
            return Success(None)
        
        test_event_bus.subscribe("system.error", error_handler)
        
        # Simulate various error conditions
        errors = [
            ErrorEvent(
                error_type="audio_error",
                error_message="Microphone not available",
                component="audio_provider"
            ),
            ErrorEvent(
                error_type="connection_error", 
                error_message="Server connection failed",
                component="transcription_client"
            ),
            ErrorEvent(
                error_type="injection_error",
                error_message="Text injection failed",
                component="text_injection_provider"
            )
        ]
        
        # Publish error events
        for error in errors:
            await test_event_bus.publish(error)
        
        # Wait for processing
        await wait_for_condition(lambda: len(error_events) >= len(errors))
        
        # Verify all errors were captured
        assert len(error_events) == len(errors)
        
        # Check error details
        error_types = [e.error_type for e in error_events]
        assert "audio_error" in error_types
        assert "connection_error" in error_types
        assert "injection_error" in error_types
    
    @pytest.mark.asyncio 
    async def test_event_priority_handling(self, test_event_bus):
        """Test event priority processing"""
        processed_events = []
        
        def priority_handler(event):
            processed_events.append((event.event_type, event.priority))
            return Success(None)
        
        # Subscribe to different event types
        test_event_bus.subscribe("system.error", priority_handler)
        test_event_bus.subscribe("recording.started", priority_handler)
        
        # Create events with different priorities
        high_priority_error = ErrorEvent(
            error_type="critical_error",
            error_message="Critical system failure",
            component="system"
        )
        high_priority_error.priority = EventPriority.HIGH
        
        normal_recording = RecordingStartedEvent(
            sample_rate=16000,
            channels=1
        )
        normal_recording.priority = EventPriority.NORMAL
        
        # Publish in reverse priority order
        await test_event_bus.publish(normal_recording)
        await test_event_bus.publish(high_priority_error)
        
        # Wait for processing
        await wait_for_condition(lambda: len(processed_events) >= 2)
        
        # Verify events were processed
        assert len(processed_events) == 2
        event_priorities = [priority for _, priority in processed_events]
        assert EventPriority.HIGH in event_priorities
        assert EventPriority.NORMAL in event_priorities


class TestEventMiddleware:
    """Test event middleware functionality"""
    
    @pytest.mark.asyncio
    async def test_logging_middleware(self, test_event_bus):
        """Test logging middleware integration"""
        # Add logging middleware
        test_event_bus.add_middleware(logging_middleware)
        
        handler_calls = []
        def test_handler(event):
            handler_calls.append(event)
            return Success(None)
        
        test_event_bus.subscribe("hotkey.pressed", test_handler)
        
        # Publish event
        event = HotkeyPressedEvent(
            hotkey_combination="ctrl+shift+w",
            is_recording_start=True,
            source="middleware_test"
        )
        
        await test_event_bus.publish(event)
        
        # Wait for processing
        await wait_for_condition(lambda: len(handler_calls) > 0)
        
        # Event should be processed normally
        assert len(handler_calls) == 1
    
    @pytest.mark.asyncio
    async def test_timing_middleware(self, test_event_bus):
        """Test timing middleware integration"""
        # Add timing middleware
        test_event_bus.add_middleware(timing_middleware)
        
        handler_calls = []
        def test_handler(event):
            handler_calls.append(event)
            return Success(None)
        
        test_event_bus.subscribe("recording.started", test_handler)
        
        # Publish event
        event = RecordingStartedEvent(
            sample_rate=16000,
            channels=1,
            source="timing_test"
        )
        
        await test_event_bus.publish(event)
        
        # Wait for processing
        await wait_for_condition(lambda: len(handler_calls) > 0)
        
        # Event should have timing metadata
        processed_event = handler_calls[0]
        assert "processing_start_time" in processed_event.metadata
    
    @pytest.mark.asyncio
    async def test_middleware_chain(self, test_event_bus):
        """Test multiple middleware in chain"""
        middleware_order = []
        
        def middleware1(event):
            middleware_order.append("middleware1")
            event.metadata["middleware1"] = True
            return Success(event)
        
        def middleware2(event):
            middleware_order.append("middleware2")
            event.metadata["middleware2"] = True
            return Success(event)
        
        # Add middleware in order
        test_event_bus.add_middleware(middleware1)
        test_event_bus.add_middleware(middleware2)
        
        handler_calls = []
        def test_handler(event):
            handler_calls.append(event)
            return Success(None)
        
        test_event_bus.subscribe("text.injected", test_handler)
        
        # Publish event
        event = TextInjectedEvent(
            text="test",
            source="middleware_chain_test"
        )
        
        await test_event_bus.publish(event)
        
        # Wait for processing
        await wait_for_condition(lambda: len(handler_calls) > 0)
        
        # Middleware should execute in order
        assert middleware_order == ["middleware1", "middleware2"]
        
        # Event should have metadata from both middleware
        processed_event = handler_calls[0]
        assert processed_event.metadata.get("middleware1") is True
        assert processed_event.metadata.get("middleware2") is True
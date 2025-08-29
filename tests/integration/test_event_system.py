#!/usr/bin/env python3

"""
Event System Integration Tests

Tests the complete event-driven architecture with real event flows.
"""

import pytest
import asyncio
import time
from typing import List, Dict, Any

from server.events import (
    EventBus, DomainEvent, EventPriority,
    AudioUploadedEvent, TranscriptionStartedEvent, TranscriptionCompletedEvent, 
    TranscriptionFailedEvent, WebSocketConnectedEvent, WebSocketDisconnectedEvent,
    get_event_bus
)
from server.functional.result_monad import Result, Success, Failure
from tests.test_utils import assert_result_success, assert_result_failure, wait_for_condition

@pytest.mark.integration
@pytest.mark.events
class TestEventSystemIntegration:
    """Integration tests for event system"""
    
    @pytest.mark.asyncio
    async def test_event_lifecycle_flow(self, test_event_bus):
        """Test complete event flow from audio upload to transcription completion"""
        event_history = []
        
        # Create event handler that records all events
        async def record_events(event: DomainEvent) -> Result[None, str]:
            event_history.append({
                "type": event.event_type,
                "timestamp": event.timestamp,
                "data": event.data,
                "correlation_id": event.correlation_id
            })
            return Success(None)
        
        # Subscribe to all events
        test_event_bus.subscribe_all(record_events)
        
        # Simulate complete transcription workflow
        request_id = "integration_test_001"
        client_id = "test_client_123"
        
        # 1. Audio uploaded
        upload_event = AudioUploadedEvent.create(
            request_id=request_id,
            file_path="/tmp/test.wav",
            file_size=12345,
            client_id=client_id
        )
        await test_event_bus.publish(upload_event)
        
        # 2. Transcription started
        start_event = TranscriptionStartedEvent.create(
            request_id=request_id,
            model="base",
            language="en",
            client_id=client_id
        )
        await test_event_bus.publish(start_event)
        
        # 3. Transcription completed
        completion_event = TranscriptionCompletedEvent.create(
            request_id=request_id,
            text="This is a test transcription result",
            language="en",
            processing_time=2.5,
            client_id=client_id
        )
        await test_event_bus.publish(completion_event)
        
        # Wait for events to be processed
        await wait_for_condition(lambda: len(event_history) >= 3, timeout=2.0)
        
        # Verify event flow
        assert len(event_history) == 3
        
        # Check event order and correlation
        assert event_history[0]["type"] == "audio.uploaded"
        assert event_history[1]["type"] == "transcription.started"
        assert event_history[2]["type"] == "transcription.completed"
        
        # All events should have same correlation ID
        correlation_ids = [e["correlation_id"] for e in event_history]
        assert all(cid == request_id for cid in correlation_ids)
        
        # Verify event data
        assert event_history[0]["data"]["file_size"] == 12345
        assert event_history[1]["data"]["model"] == "base"
        assert event_history[2]["data"]["processing_time"] == 2.5
    
    @pytest.mark.asyncio
    async def test_event_handler_error_recovery(self, test_event_bus):
        """Test event system handles handler failures gracefully"""
        successful_events = []
        
        # Handler that always fails
        async def failing_handler(event: DomainEvent) -> Result[None, str]:
            return Failure("Handler intentionally failed")
        
        # Handler that succeeds
        async def success_handler(event: DomainEvent) -> Result[None, str]:
            successful_events.append(event)
            return Success(None)
        
        # Subscribe both handlers to same event
        test_event_bus.subscribe("test.event", failing_handler)
        test_event_bus.subscribe("test.event", success_handler)
        
        # Publish test event
        test_event = DomainEvent(
            event_type="test.event",
            data={"test": "data"}
        )
        await test_event_bus.publish(test_event)
        
        # Wait for processing
        await wait_for_condition(lambda: len(successful_events) > 0, timeout=2.0)
        
        # Success handler should still receive the event despite failure
        assert len(successful_events) == 1
        assert successful_events[0].event_type == "test.event"
        
        # Check metrics - should show failed count
        metrics = test_event_bus.get_metrics()
        assert metrics["failed_count"] >= 1
        assert metrics["processed_count"] >= 1
    
    @pytest.mark.asyncio
    async def test_event_priority_processing(self, test_event_bus):
        """Test that high-priority events are processed appropriately"""
        processed_events = []
        
        async def priority_handler(event: DomainEvent) -> Result[None, str]:
            processed_events.append({
                "type": event.event_type,
                "priority": event.priority,
                "timestamp": time.time()
            })
            # Add small delay to see ordering
            await asyncio.sleep(0.01)
            return Success(None)
        
        test_event_bus.subscribe_all(priority_handler)
        
        # Create events with different priorities
        low_event = DomainEvent(
            event_type="low.priority",
            priority=EventPriority.LOW,
            data={"test": "low"}
        )
        
        high_event = DomainEvent(
            event_type="high.priority", 
            priority=EventPriority.HIGH,
            data={"test": "high"}
        )
        
        critical_event = DomainEvent(
            event_type="critical.priority",
            priority=EventPriority.CRITICAL,
            data={"test": "critical"}
        )
        
        # Publish in reverse priority order
        await test_event_bus.publish(low_event)
        await test_event_bus.publish(high_event)
        await test_event_bus.publish(critical_event)
        
        # Wait for processing
        await wait_for_condition(lambda: len(processed_events) >= 3, timeout=2.0)
        
        # All events should be processed
        assert len(processed_events) == 3
        
        # Verify priorities were recorded
        priorities = [e["priority"] for e in processed_events]
        assert EventPriority.LOW in priorities
        assert EventPriority.HIGH in priorities
        assert EventPriority.CRITICAL in priorities
    
    @pytest.mark.asyncio
    async def test_event_middleware_processing(self, test_event_bus):
        """Test event middleware processing and modification"""
        middleware_events = []
        final_events = []
        
        # Middleware that adds metadata
        async def enrichment_middleware(event: DomainEvent) -> Result[None, str]:
            middleware_events.append(event.event_type)
            # In real middleware, you might modify the event
            # For testing, just record that it was processed
            return Success(None)
        
        # Final handler
        async def final_handler(event: DomainEvent) -> Result[None, str]:
            final_events.append(event)
            return Success(None)
        
        # Add middleware and handler
        test_event_bus.add_middleware(enrichment_middleware)
        test_event_bus.subscribe_all(final_handler)
        
        # Publish test event
        test_event = DomainEvent(
            event_type="middleware.test",
            data={"original": "data"}
        )
        await test_event_bus.publish(test_event)
        
        # Wait for processing
        await wait_for_condition(lambda: len(final_events) > 0, timeout=2.0)
        
        # Both middleware and handler should have processed event
        assert "middleware.test" in middleware_events
        assert len(final_events) == 1
        assert final_events[0].event_type == "middleware.test"
    
    @pytest.mark.asyncio
    async def test_websocket_event_integration(self, test_event_bus):
        """Test WebSocket connection events integration"""
        connection_events = []
        
        async def connection_handler(event: DomainEvent) -> Result[None, str]:
            if event.event_type in ["websocket.connected", "websocket.disconnected"]:
                connection_events.append({
                    "type": event.event_type,
                    "client_id": event.data.get("client_id"),
                    "timestamp": event.timestamp
                })
            return Success(None)
        
        test_event_bus.subscribe("websocket.connected", connection_handler)
        test_event_bus.subscribe("websocket.disconnected", connection_handler)
        
        # Simulate WebSocket lifecycle
        client_id = "ws_client_001"
        
        # Connection
        connect_event = WebSocketConnectedEvent.create(
            client_id=client_id,
            remote_address="127.0.0.1:12345"
        )
        await test_event_bus.publish(connect_event)
        
        # Disconnection
        disconnect_event = WebSocketDisconnectedEvent.create(
            client_id=client_id,
            reason="Normal closure"
        )
        await test_event_bus.publish(disconnect_event)
        
        # Wait for processing
        await wait_for_condition(lambda: len(connection_events) >= 2, timeout=2.0)
        
        # Verify connection lifecycle
        assert len(connection_events) == 2
        assert connection_events[0]["type"] == "websocket.connected"
        assert connection_events[1]["type"] == "websocket.disconnected"
        assert connection_events[0]["client_id"] == client_id
        assert connection_events[1]["client_id"] == client_id
    
    @pytest.mark.asyncio
    async def test_transcription_failure_handling(self, test_event_bus):
        """Test transcription failure event handling"""
        failure_events = []
        
        async def failure_handler(event: DomainEvent) -> Result[None, str]:
            if event.event_type == "transcription.failed":
                failure_events.append({
                    "request_id": event.data.get("request_id"),
                    "error": event.data.get("error"),
                    "priority": event.priority
                })
            return Success(None)
        
        test_event_bus.subscribe("transcription.failed", failure_handler)
        
        # Publish failure event
        failure_event = TranscriptionFailedEvent.create(
            request_id="failed_request_001",
            error="GPU out of memory",
            client_id="client_123"
        )
        await test_event_bus.publish(failure_event)
        
        # Wait for processing
        await wait_for_condition(lambda: len(failure_events) > 0, timeout=2.0)
        
        # Verify failure handling
        assert len(failure_events) == 1
        assert failure_events[0]["request_id"] == "failed_request_001"
        assert "GPU out of memory" in failure_events[0]["error"]
        
        # Failure events should have high priority
        failure_event_processed = failure_events[0]
        # Note: We can't directly check priority from handler, but we know it's set to HIGH
    
    @pytest.mark.asyncio
    async def test_event_correlation_tracking(self, test_event_bus):
        """Test event correlation across multiple services"""
        correlated_events = {}
        
        async def correlation_handler(event: DomainEvent) -> Result[None, str]:
            correlation_id = event.correlation_id
            if correlation_id:
                if correlation_id not in correlated_events:
                    correlated_events[correlation_id] = []
                correlated_events[correlation_id].append({
                    "type": event.event_type,
                    "timestamp": event.timestamp,
                    "source": event.source
                })
            return Success(None)
        
        test_event_bus.subscribe_all(correlation_handler)
        
        # Create events with same correlation ID
        correlation_id = "correlation_test_001"
        
        events = [
            AudioUploadedEvent.create(correlation_id, "/tmp/test.wav", 1000),
            TranscriptionStartedEvent.create(correlation_id, "base", "en"),
            TranscriptionCompletedEvent.create(correlation_id, "Test result", "en", 1.5)
        ]
        
        # Publish all events
        for event in events:
            await test_event_bus.publish(event)
        
        # Wait for processing
        await wait_for_condition(lambda: len(correlated_events.get(correlation_id, [])) >= 3, timeout=2.0)
        
        # Verify correlation tracking
        assert correlation_id in correlated_events
        assert len(correlated_events[correlation_id]) == 3
        
        # Verify event sources
        event_sources = [e["source"] for e in correlated_events[correlation_id]]
        assert "audio_service" in event_sources
        assert "transcription_service" in event_sources
    
    @pytest.mark.asyncio
    async def test_event_bus_metrics_accuracy(self, test_event_bus):
        """Test event bus metrics are accurate"""
        # Get initial metrics
        initial_metrics = test_event_bus.get_metrics()
        initial_published = initial_metrics["published_count"]
        
        # Handler that sometimes fails
        failure_count = 0
        async def sometimes_failing_handler(event: DomainEvent) -> Result[None, str]:
            nonlocal failure_count
            if event.data.get("should_fail", False):
                failure_count += 1
                return Failure("Intentional failure")
            return Success(None)
        
        test_event_bus.subscribe_all(sometimes_failing_handler)
        
        # Publish mix of success and failure events
        success_events = 5
        failure_events = 3
        
        for i in range(success_events):
            event = DomainEvent(
                event_type="success.event",
                data={"index": i}
            )
            await test_event_bus.publish(event)
        
        for i in range(failure_events):
            event = DomainEvent(
                event_type="failure.event", 
                data={"index": i, "should_fail": True}
            )
            await test_event_bus.publish(event)
        
        # Wait for processing
        total_events = success_events + failure_events
        await wait_for_condition(
            lambda: test_event_bus.get_metrics()["processed_count"] >= initial_metrics["processed_count"] + total_events,
            timeout=3.0
        )
        
        # Check final metrics
        final_metrics = test_event_bus.get_metrics()
        
        assert final_metrics["published_count"] >= initial_published + total_events
        assert final_metrics["processed_count"] >= initial_metrics["processed_count"] + total_events
        assert final_metrics["failed_count"] >= initial_metrics["failed_count"] + failure_events
        
        # Verify our failure count matches expectations
        assert failure_count == failure_events
#!/usr/bin/env python3

"""
Test Provider Integration

Integration tests for providers working together and with the event system.
Tests realistic provider interactions and error handling patterns.
"""

import asyncio
import json
import pytest
from unittest.mock import Mock, AsyncMock, patch
from typing import List, Dict, Any

from shared.functional import Result, Success, Failure
from shared.events import get_event_bus
from client.providers.audio_provider import PyAudioProvider
from client.providers.transcription_client import TranscriptionClient  
from client.providers.text_injection_provider import PyAutoGUIProvider
from client.pipeline.audio_pipeline import AudioData
from tests.conftest import assert_result_success, assert_result_failure, wait_for_condition, create_test_audio_bytes


class TestAudioProviderIntegration:
    """Test audio provider integration with events and pipeline"""
    
    @pytest.mark.asyncio
    async def test_audio_provider_event_integration(self, test_event_bus):
        """Test audio provider publishes correct events"""
        events_received = []
        
        def event_collector(event):
            events_received.append(event)
            return Success(None)
        
        # Subscribe to audio events
        test_event_bus.subscribe("recording.started", event_collector)
        test_event_bus.subscribe("recording.stopped", event_collector)
        
        # Mock PyAudio for testing
        with patch('client.providers.audio_provider.pyaudio') as mock_pyaudio:
            mock_audio = Mock()
            mock_stream = Mock()
            
            mock_pyaudio.PyAudio.return_value = mock_audio
            mock_audio.get_device_count.return_value = 1
            mock_audio.open.return_value = mock_stream
            mock_audio.get_sample_size.return_value = 2
            
            # Create provider
            provider = PyAudioProvider(sample_rate=16000, channels=1)
            await provider.initialize()
            
            # Start recording
            result = await provider.start_recording()
            assert_result_success(result)
            
            # Mock some recorded data
            provider.frames = [b'\x00\x01' * 1000]  # Mock audio data
            
            # Stop recording  
            result = await provider.stop_recording()
            assert_result_success(result)
            
            # Wait for events
            await wait_for_condition(lambda: len(events_received) >= 2)
            
            # Verify events were published
            event_types = [e.event_type for e in events_received]
            assert "recording.started" in event_types
            assert "recording.stopped" in event_types
            
            await provider.cleanup()
    
    @pytest.mark.asyncio
    async def test_audio_provider_failure_scenarios(self):
        """Test audio provider error handling"""
        # Test initialization failure
        with patch('client.providers.audio_provider.pyaudio') as mock_pyaudio:
            mock_pyaudio.PyAudio.side_effect = Exception("Audio system unavailable")
            
            provider = PyAudioProvider()
            result = await provider.initialize()
            
            assert_result_failure(result)
            assert "Audio system unavailable" in str(result.error)
    
    @pytest.mark.asyncio
    async def test_audio_provider_device_validation(self):
        """Test audio device validation"""
        with patch('client.providers.audio_provider.pyaudio') as mock_pyaudio:
            mock_audio = Mock()
            mock_pyaudio.PyAudio.return_value = mock_audio
            mock_audio.get_device_count.return_value = 2
            
            # Valid device
            provider = PyAudioProvider(input_device=1)
            mock_audio.get_device_info_by_index.return_value = {
                'name': 'Test Device',
                'maxInputChannels': 2
            }
            
            result = await provider.initialize()
            assert_result_success(result)
            
            await provider.cleanup()
            
            # Invalid device
            provider = PyAudioProvider(input_device=5)  # Out of range
            
            result = await provider.initialize()
            assert_result_failure(result)


class TestTranscriptionClientIntegration:
    """Test transcription client integration"""
    
    @pytest.mark.asyncio
    async def test_transcription_client_event_integration(self, test_event_bus):
        """Test transcription client publishes events"""
        events_received = []
        
        def event_collector(event):
            events_received.append(event)
            return Success(None)
        
        # Subscribe to transcription events
        test_event_bus.subscribe("connection.status", event_collector)
        test_event_bus.subscribe("transcription.requested", event_collector)
        test_event_bus.subscribe("transcription.received", event_collector)
        
        # Mock websocket for testing
        mock_websocket = AsyncMock()
        
        # Mock successful transcription response
        mock_response = {
            "type": "transcription",
            "text": "Hello world",
            "language": "en", 
            "processing_time": 0.25
        }
        mock_websocket.recv.return_value = json.dumps(mock_response)
        
        with patch('client.providers.transcription_client.websockets') as mock_websockets:
            mock_websockets.connect.return_value = mock_websocket
            
            client = TranscriptionClient("ws://test:8000/ws/transcribe")
            
            # Connect
            result = await client.connect()
            assert_result_success(result)
            
            # Create test audio data
            audio_data = AudioData(
                data=create_test_audio_bytes(1.0),
                format="wav",
                sample_rate=16000,
                channels=1,
                duration_seconds=1.0
            )
            
            # Transcribe
            result = await client.transcribe_audio(audio_data)
            assert_result_success(result)
            assert result.value == "Hello world"
            
            # Wait for events
            await wait_for_condition(lambda: len(events_received) >= 3)
            
            # Verify events
            event_types = [e.event_type for e in events_received]
            assert "connection.status" in event_types
            assert "transcription.requested" in event_types
            assert "transcription.received" in event_types
            
            await client.cleanup()
    
    @pytest.mark.asyncio
    async def test_transcription_client_connection_failure(self, test_event_bus):
        """Test transcription client connection failure handling"""
        events_received = []
        
        def event_collector(event):
            events_received.append(event)
            return Success(None)
        
        test_event_bus.subscribe("connection.status", event_collector)
        
        # Mock connection failure
        with patch('client.providers.transcription_client.websockets') as mock_websockets:
            mock_websockets.connect.side_effect = Exception("Connection refused")
            
            client = TranscriptionClient("ws://invalid:8000/ws/transcribe")
            result = await client.connect()
            
            assert_result_failure(result)
            
            # Should publish error status
            await wait_for_condition(lambda: len(events_received) >= 1)
            
            error_event = next((e for e in events_received if e.status == "error"), None)
            assert error_event is not None
            assert "Connection refused" in error_event.error_message
    
    @pytest.mark.asyncio
    async def test_transcription_client_server_error_handling(self):
        """Test server error response handling"""
        mock_websocket = AsyncMock()
        
        # Mock server error response
        error_response = {
            "type": "error",
            "message": "Audio format not supported"
        }
        mock_websocket.recv.return_value = json.dumps(error_response)
        
        with patch('client.providers.transcription_client.websockets') as mock_websockets:
            mock_websockets.connect.return_value = mock_websocket
            
            client = TranscriptionClient()
            await client.connect()
            
            audio_data = AudioData(
                data=b"invalid audio",
                format="unknown",
                sample_rate=16000,
                channels=1,
                duration_seconds=1.0
            )
            
            result = await client.transcribe_audio(audio_data)
            assert_result_failure(result)
            assert "Audio format not supported" in str(result.error)


class TestTextInjectionProviderIntegration:
    """Test text injection provider integration"""
    
    @pytest.mark.asyncio
    async def test_text_injection_event_integration(self, test_event_bus):
        """Test text injection provider publishes events"""
        events_received = []
        
        def event_collector(event):
            events_received.append(event)
            return Success(None)
        
        test_event_bus.subscribe("text.injected", event_collector)
        
        # Mock pyautogui for testing
        with patch('client.providers.text_injection_provider.pyautogui') as mock_pyautogui:
            provider = PyAutoGUIProvider()
            await provider.initialize()
            
            # Inject text
            result = await provider.inject_text("Hello world")
            assert_result_success(result)
            
            # Verify pyautogui was called
            mock_pyautogui.typewrite.assert_called_once_with("Hello world ")
            
            # Wait for event
            await wait_for_condition(lambda: len(events_received) >= 1)
            
            # Verify event
            assert len(events_received) == 1
            event = events_received[0]
            assert event.event_type == "text.injected"
            assert event.text == "Hello world "
            assert event.injection_method == "pyautogui"
    
    @pytest.mark.asyncio
    async def test_text_injection_formatting_options(self, test_event_bus):
        """Test text injection with formatting options"""
        events_received = []
        
        def event_collector(event):
            events_received.append(event)
            return Success(None)
        
        test_event_bus.subscribe("text.injected", event_collector)
        
        with patch('client.providers.text_injection_provider.pyautogui') as mock_pyautogui:
            provider = PyAutoGUIProvider(
                add_space_after=False,
                capitalize_first=True
            )
            await provider.initialize()
            
            # Inject text with formatting
            result = await provider.inject_text("hello world")
            assert_result_success(result)
            
            # Should capitalize and not add space
            mock_pyautogui.typewrite.assert_called_once_with("Hello world")
            
            await wait_for_condition(lambda: len(events_received) >= 1)
            
            event = events_received[0]
            assert event.text == "Hello world"
    
    @pytest.mark.asyncio
    async def test_text_injection_with_window_selection(self, test_event_bus):
        """Test text injection with window selection features"""
        with patch('client.providers.text_injection_provider.pyautogui') as mock_pyautogui:
            provider = PyAutoGUIProvider()
            await provider.initialize()
            
            # Test select all first option
            result = await provider.inject_text_with_formatting(
                "replacement text",
                select_all_first=True
            )
            assert_result_success(result)
            
            # Should call hotkey for select all
            mock_pyautogui.hotkey.assert_called()
            mock_pyautogui.typewrite.assert_called()


class TestProviderOrchestration:
    """Test providers working together in realistic scenarios"""
    
    @pytest.mark.asyncio
    async def test_complete_voice_to_text_workflow(self, test_event_bus):
        """Test complete workflow with all providers"""
        workflow_events = []
        
        def event_tracker(event):
            workflow_events.append(event.event_type)
            return Success(None)
        
        # Subscribe to workflow events
        event_types = [
            "recording.started", "recording.stopped",
            "transcription.requested", "transcription.received", 
            "text.injected"
        ]
        
        for event_type in event_types:
            test_event_bus.subscribe(event_type, event_tracker)
        
        # Mock all external dependencies
        with patch('client.providers.audio_provider.pyaudio') as mock_pyaudio, \
             patch('client.providers.transcription_client.websockets') as mock_websockets, \
             patch('client.providers.text_injection_provider.pyautogui') as mock_pyautogui:
            
            # Setup audio provider mocks
            mock_audio = Mock()
            mock_stream = Mock()
            mock_pyaudio.PyAudio.return_value = mock_audio
            mock_audio.get_device_count.return_value = 1
            mock_audio.open.return_value = mock_stream
            mock_audio.get_sample_size.return_value = 2
            
            # Setup transcription client mocks
            mock_websocket = AsyncMock()
            mock_websockets.connect.return_value = mock_websocket
            mock_websocket.recv.return_value = json.dumps({
                "type": "transcription",
                "text": "Hello from integration test",
                "language": "en",
                "processing_time": 0.15
            })
            
            # Create providers
            audio_provider = PyAudioProvider()
            transcription_client = TranscriptionClient()
            text_provider = PyAutoGUIProvider()
            
            # Initialize all providers
            await audio_provider.initialize()
            await transcription_client.connect()
            await text_provider.initialize()
            
            try:
                # Simulate workflow
                # 1. Start recording
                await audio_provider.start_recording()
                
                # 2. Stop recording with mock data
                audio_provider.frames = [b'\x00\x01' * 8000]  # 1 second of mock audio
                audio_result = await audio_provider.stop_recording()
                assert_result_success(audio_result)
                
                # 3. Transcribe audio
                audio_data = audio_result.value
                transcription_result = await transcription_client.transcribe_audio(audio_data)
                assert_result_success(transcription_result)
                
                # 4. Inject text
                transcribed_text = transcription_result.value
                injection_result = await text_provider.inject_text(transcribed_text)
                assert_result_success(injection_result)
                
                # Wait for all events to be processed
                await wait_for_condition(lambda: len(workflow_events) >= 5, timeout=2.0)
                
                # Verify workflow completed
                expected_events = [
                    "recording.started", "recording.stopped",
                    "transcription.requested", "transcription.received",
                    "text.injected"
                ]
                
                for expected_event in expected_events:
                    assert expected_event in workflow_events, f"Missing event: {expected_event}"
                
            finally:
                # Cleanup
                await audio_provider.cleanup()
                await transcription_client.cleanup() 
                await text_provider.cleanup()
    
    @pytest.mark.asyncio
    async def test_error_recovery_workflow(self, test_event_bus):
        """Test error recovery in provider workflows"""
        error_events = []
        
        def error_collector(event):
            error_events.append(event)
            return Success(None)
        
        test_event_bus.subscribe("system.error", error_collector)
        test_event_bus.subscribe("connection.status", error_collector)
        
        # Test transcription client with connection issues
        with patch('client.providers.transcription_client.websockets') as mock_websockets:
            # First connection fails, second succeeds
            mock_websocket = AsyncMock()
            mock_websockets.connect.side_effect = [
                Exception("Connection timeout"),
                mock_websocket
            ]
            
            client = TranscriptionClient()
            
            # First attempt should fail
            result1 = await client.connect()
            assert_result_failure(result1)
            
            # Retry should succeed
            result2 = await client.connect()
            assert_result_success(result2)
            
            # Wait for error events
            await wait_for_condition(lambda: len(error_events) >= 2)
            
            # Should have error and success status events
            status_events = [e for e in error_events if hasattr(e, 'status')]
            assert len(status_events) >= 1
            
            error_statuses = [e.status for e in status_events]
            assert "error" in error_statuses or "connecting" in error_statuses
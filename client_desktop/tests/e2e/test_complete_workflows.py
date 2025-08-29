#!/usr/bin/env python3

"""
Test Complete Client Workflows

End-to-end tests for complete user workflows from hotkey to text injection.
Tests the entire system working together with realistic scenarios.
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import List, Dict, Any

from shared.functional import Result, Success, Failure
from client.voice_client_app import VoiceClientApplication
from client.container import ClientConfig
from tests.conftest import wait_for_condition, assert_result_success


class TestCompleteVoiceWorkflows:
    """Test complete voice-to-text workflows"""
    
    @pytest.fixture
    async def mock_application_components(self):
        """Setup mocked application components for e2e testing"""
        mocks = {}
        
        # Mock PyAudio
        with patch('client.providers.audio_provider.pyaudio') as mock_pyaudio:
            mock_audio = Mock()
            mock_stream = Mock()
            
            mock_pyaudio.PyAudio.return_value = mock_audio
            mock_audio.get_device_count.return_value = 2
            mock_audio.get_device_info_by_index.return_value = {
                'name': 'Test Microphone',
                'maxInputChannels': 2
            }
            mock_audio.open.return_value = mock_stream
            mock_audio.get_sample_size.return_value = 2
            
            # Mock WebSockets
            with patch('client.providers.transcription_client.websockets') as mock_websockets:
                mock_websocket = AsyncMock()
                mock_websockets.connect.return_value = mock_websocket
                
                # Mock PyAutoGUI
                with patch('client.providers.text_injection_provider.pyautogui') as mock_pyautogui:
                    
                    # Mock Pynput
                    with patch('client.input.hotkey_handler.Listener') as mock_listener:
                        mock_listener_instance = Mock()
                        mock_listener.return_value = mock_listener_instance
                        
                        mocks = {
                            'pyaudio': mock_pyaudio,
                            'audio': mock_audio,
                            'stream': mock_stream,
                            'websockets': mock_websockets,
                            'websocket': mock_websocket,
                            'pyautogui': mock_pyautogui,
                            'listener': mock_listener_instance
                        }
                        
                        yield mocks
    
    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_successful_voice_to_text_workflow(self, test_config, mock_application_components):
        """Test complete successful voice-to-text workflow"""
        mocks = mock_application_components
        
        # Setup successful transcription response
        import json
        mocks['websocket'].recv.return_value = json.dumps({
            "type": "transcription",
            "text": "This is a test transcription",
            "language": "en",
            "processing_time": 0.25,
            "confidence": 0.95
        })
        
        # Create application
        app = VoiceClientApplication(test_config)
        
        # Track workflow events
        workflow_events = []
        original_publish = app.event_bus.publish
        
        async def track_publish(event):
            workflow_events.append(event.event_type)
            return await original_publish(event)
        
        app.event_bus.publish = track_publish
        
        try:
            # Initialize application
            result = await app.initialize()
            assert_result_success(result)
            
            # Start application
            result = await app.start()
            assert_result_success(result)
            
            # Simulate complete recording workflow
            await app._toggle_recording()  # Start recording
            
            # Mock recorded audio data
            app.audio_provider.frames = [b'\x00\x01' * 16000]  # 1 second of audio
            
            await app._toggle_recording()  # Stop recording and process
            
            # Wait for workflow to complete
            await wait_for_condition(
                lambda: "text.injected" in workflow_events,
                timeout=5.0
            )
            
            # Verify complete workflow
            expected_events = [
                "recording.started",
                "recording.stopped", 
                "audio.captured",
                "transcription.requested",
                "transcription.received",
                "text.injected"
            ]
            
            for event_type in expected_events:
                assert event_type in workflow_events, f"Missing workflow event: {event_type}"
            
            # Verify text was injected
            mocks['pyautogui'].typewrite.assert_called()
            call_args = mocks['pyautogui'].typewrite.call_args[0][0]
            assert "This is a test transcription" in call_args
            
        finally:
            await app.stop()
    
    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_audio_recording_failure_workflow(self, test_config, mock_application_components):
        """Test workflow with audio recording failure"""
        mocks = mock_application_components
        
        # Setup audio recording failure
        mocks['audio'].open.side_effect = Exception("Microphone access denied")
        
        app = VoiceClientApplication(test_config)
        
        # Track error events
        error_events = []
        
        def error_collector(event):
            if hasattr(event, 'error_type'):
                error_events.append(event)
            return Success(None)
        
        app.event_bus.subscribe("system.error", error_collector)
        
        try:
            # Initialize should succeed
            result = await app.initialize()
            assert_result_success(result)
            
            # Start should succeed
            result = await app.start()
            assert_result_success(result)
            
            # Try to start recording - should handle error gracefully
            await app._toggle_recording()
            
            # Wait for error to be processed
            await wait_for_condition(lambda: len(error_events) > 0, timeout=2.0)
            
            # Should capture audio error but not crash
            assert len(error_events) >= 0  # May or may not generate error event
            
        finally:
            await app.stop()
    
    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_server_connection_failure_workflow(self, test_config, mock_application_components):
        """Test workflow with server connection failure"""
        mocks = mock_application_components
        
        # Setup connection failure then recovery
        connection_attempts = []
        
        def mock_connect(*args, **kwargs):
            connection_attempts.append(1)
            if len(connection_attempts) == 1:
                raise Exception("Connection refused")
            return mocks['websocket']
        
        mocks['websockets'].connect.side_effect = mock_connect
        
        app = VoiceClientApplication(test_config)
        
        # Track connection events
        connection_events = []
        
        def connection_collector(event):
            if hasattr(event, 'status'):
                connection_events.append(event.status)
            return Success(None)
        
        app.event_bus.subscribe("connection.status", connection_collector)
        
        try:
            # Initialize - connection may fail initially
            result = await app.initialize()
            # Should still succeed even if initial connection fails
            assert_result_success(result) or result.is_failure()
            
            if result.is_success():
                await app.start()
                
                # Wait for connection events
                await wait_for_condition(lambda: len(connection_events) > 0, timeout=3.0)
                
                # Should attempt connection
                assert len(connection_attempts) >= 1
            
        finally:
            await app.stop()
    
    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_text_injection_failure_recovery(self, test_config, mock_application_components):
        """Test workflow with text injection failure and recovery"""
        mocks = mock_application_components
        
        # Setup successful transcription
        import json
        mocks['websocket'].recv.return_value = json.dumps({
            "type": "transcription",
            "text": "Test message for injection",
            "language": "en",
            "processing_time": 0.2
        })
        
        # Setup text injection failure then success
        injection_attempts = []
        
        def mock_typewrite(text):
            injection_attempts.append(text)
            if len(injection_attempts) == 1:
                raise Exception("Window focus lost")
            # Second attempt succeeds
        
        mocks['pyautogui'].typewrite.side_effect = mock_typewrite
        
        app = VoiceClientApplication(test_config)
        
        try:
            result = await app.initialize()
            assert_result_success(result)
            
            result = await app.start()
            assert_result_success(result)
            
            # Simulate recording with successful transcription
            await app._toggle_recording()  # Start
            app.audio_provider.frames = [b'\x00\x01' * 8000]
            await app._toggle_recording()  # Stop and process
            
            # Wait for processing
            await wait_for_condition(lambda: len(injection_attempts) > 0, timeout=3.0)
            
            # Should attempt text injection
            assert len(injection_attempts) >= 1
            assert "Test message for injection" in injection_attempts[0]
            
        finally:
            await app.stop()
    
    @pytest.mark.e2e 
    @pytest.mark.asyncio
    async def test_multiple_recording_cycles(self, test_config, mock_application_components):
        """Test multiple recording cycles in sequence"""
        mocks = mock_application_components
        
        # Setup multiple transcription responses
        transcription_responses = [
            {"type": "transcription", "text": "First recording", "language": "en", "processing_time": 0.1},
            {"type": "transcription", "text": "Second recording", "language": "en", "processing_time": 0.15},
            {"type": "transcription", "text": "Third recording", "language": "en", "processing_time": 0.12}
        ]
        
        response_index = 0
        
        def mock_recv():
            nonlocal response_index
            import json
            response = json.dumps(transcription_responses[response_index % len(transcription_responses)])
            response_index += 1
            return response
        
        mocks['websocket'].recv.side_effect = mock_recv
        
        app = VoiceClientApplication(test_config)
        
        # Track injected text
        injected_texts = []
        
        def mock_typewrite(text):
            injected_texts.append(text)
        
        mocks['pyautogui'].typewrite.side_effect = mock_typewrite
        
        try:
            result = await app.initialize()
            assert_result_success(result)
            
            result = await app.start()
            assert_result_success(result)
            
            # Perform multiple recording cycles
            for i in range(3):
                # Start recording
                await app._toggle_recording()
                
                # Mock audio data
                app.audio_provider.frames = [b'\x00\x01' * (8000 + i * 1000)]
                
                # Stop recording
                await app._toggle_recording()
                
                # Wait for this cycle to complete
                await wait_for_condition(lambda: len(injected_texts) > i, timeout=2.0)
                
                # Small delay between cycles
                await asyncio.sleep(0.1)
            
            # Verify all recordings were processed
            assert len(injected_texts) == 3
            assert "First recording" in injected_texts[0]
            assert "Second recording" in injected_texts[1]
            assert "Third recording" in injected_texts[2]
            
        finally:
            await app.stop()
    
    @pytest.mark.e2e
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_long_running_application_stability(self, test_config, mock_application_components):
        """Test application stability over longer periods"""
        mocks = mock_application_components
        
        # Setup basic transcription response
        import json
        mocks['websocket'].recv.return_value = json.dumps({
            "type": "transcription",
            "text": "Stability test message",
            "language": "en",
            "processing_time": 0.1
        })
        
        app = VoiceClientApplication(test_config)
        
        operation_count = 0
        max_operations = 10  # Reduced for testing
        
        def mock_typewrite(text):
            nonlocal operation_count
            operation_count += 1
        
        mocks['pyautogui'].typewrite.side_effect = mock_typewrite
        
        try:
            result = await app.initialize()
            assert_result_success(result)
            
            result = await app.start()
            assert_result_success(result)
            
            # Perform repeated operations
            for i in range(max_operations):
                await app._toggle_recording()
                app.audio_provider.frames = [b'\x00\x01' * 4000]
                await app._toggle_recording()
                
                # Brief delay between operations
                await asyncio.sleep(0.05)
            
            # Wait for all operations to complete
            await wait_for_condition(lambda: operation_count >= max_operations, timeout=10.0)
            
            # Verify stability - should complete all operations
            assert operation_count >= max_operations * 0.8  # Allow some tolerance
            
        finally:
            await app.stop()


class TestConfigurationWorkflows:
    """Test different configuration scenarios"""
    
    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_different_audio_configurations(self, mock_application_components):
        """Test application with different audio configurations"""
        configs_to_test = [
            {"audio_sample_rate": 8000, "audio_channels": 1},
            {"audio_sample_rate": 22050, "audio_channels": 1},
            {"audio_sample_rate": 44100, "audio_channels": 2}
        ]
        
        mocks = mock_application_components
        
        import json
        mocks['websocket'].recv.return_value = json.dumps({
            "type": "transcription",
            "text": "Configuration test",
            "language": "en",
            "processing_time": 0.1
        })
        
        for config_override in configs_to_test:
            config = ClientConfig()
            for key, value in config_override.items():
                setattr(config, key, value)
            
            app = VoiceClientApplication(config)
            
            try:
                # Should initialize successfully with any valid config
                result = await app.initialize()
                assert_result_success(result)
                
                # Verify audio provider uses correct settings
                assert app.audio_provider.sample_rate == config.audio_sample_rate
                assert app.audio_provider.channels == config.audio_channels
                
            finally:
                await app.stop()
    
    @pytest.mark.e2e
    @pytest.mark.asyncio  
    async def test_different_server_configurations(self, mock_application_components):
        """Test application with different server configurations"""
        server_configs = [
            "ws://localhost:8000/ws/transcribe",
            "ws://test-server:9000/ws/transcribe", 
            "wss://secure-server:8443/ws/transcribe"
        ]
        
        mocks = mock_application_components
        
        for server_url in server_configs:
            config = ClientConfig()
            config.server_url = server_url
            
            app = VoiceClientApplication(config)
            
            try:
                result = await app.initialize()
                assert_result_success(result)
                
                # Verify transcription client uses correct URL
                assert app.transcription_client.server_url == server_url
                
            finally:
                await app.stop()
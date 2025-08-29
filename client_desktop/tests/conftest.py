#!/usr/bin/env python3

"""
Test Configuration and Fixtures

Provides shared test fixtures and configuration following server test patterns.
Emphasizes integration testing with real components and functional validation.
"""

import asyncio
import json
import logging
import tempfile
import uuid
from pathlib import Path
from typing import Dict, Any, Optional
from unittest.mock import Mock, AsyncMock

import pytest
import pytest_asyncio

# Add project paths for imports
import sys
client_dir = Path(__file__).parent.parent
sys.path.insert(0, str(client_dir))
sys.path.insert(0, str(client_dir.parent))

from shared.functional import Result, Success, Failure, setup_logging
from shared.events import EventBus, get_event_bus
from client.container import ClientContainer, ClientConfig
from client.pipeline.audio_pipeline import AudioData, ProcessingContext, create_basic_pipeline


# Configure test logging
setup_logging("DEBUG")
logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_config() -> ClientConfig:
    """Provide test configuration with safe defaults"""
    config = ClientConfig()
    config.server_url = "ws://localhost:18000/ws/transcribe"  # Test port
    config.hotkey = "ctrl+shift+t"  # Test hotkey
    config.audio_sample_rate = 16000
    config.audio_channels = 1
    config.audio_chunk_size = 512  # Smaller for tests
    config.logging_level = "DEBUG"
    
    return config


@pytest_asyncio.fixture
async def test_event_bus() -> EventBus:
    """Provide isolated event bus for testing"""
    event_bus = EventBus()
    await event_bus.start()
    
    yield event_bus
    
    await event_bus.stop()


@pytest_asyncio.fixture
async def test_container(test_config: ClientConfig, test_event_bus: EventBus) -> ClientContainer:
    """Provide dependency injection container for testing"""
    container = ClientContainer(test_config)
    container.register_singleton("event_bus", test_event_bus)
    
    yield container
    
    await container.cleanup_services()


@pytest.fixture
def sample_audio_data() -> AudioData:
    """Provide sample audio data for testing"""
    # Generate simple test audio data (silence)
    sample_rate = 16000
    duration = 2.0  # 2 seconds
    samples = int(sample_rate * duration)
    
    # Simple WAV-like data (silence)
    audio_bytes = b'\x00\x00' * samples
    
    return AudioData(
        data=audio_bytes,
        format="wav",
        sample_rate=sample_rate,
        channels=1,
        duration_seconds=duration,
        metadata={"test": True, "generated": True}
    )


@pytest.fixture
def processing_context() -> ProcessingContext:
    """Provide processing context for pipeline testing"""
    return ProcessingContext(
        request_id=str(uuid.uuid4())
    )


@pytest.fixture
def test_audio_pipeline():
    """Provide audio pipeline for testing"""
    return create_basic_pipeline()


@pytest.fixture
def temp_config_file(test_config: ClientConfig) -> str:
    """Create temporary configuration file"""
    config_dict = {
        "server_url": test_config.server_url,
        "model": test_config.model,
        "hotkey": test_config.hotkey,
        "audio_sample_rate": test_config.audio_sample_rate,
        "audio_channels": test_config.audio_channels,
        "logging_level": test_config.logging_level
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config_dict, f)
        config_path = f.name
    
    yield config_path
    
    # Cleanup
    Path(config_path).unlink(missing_ok=True)


@pytest.fixture
def mock_audio_provider():
    """Provide mock audio provider for testing"""
    provider = Mock()
    provider.initialize = AsyncMock(return_value=Success(None))
    provider.start_recording = AsyncMock(return_value=Success(None))
    provider.stop_recording = AsyncMock()
    provider.cleanup = AsyncMock()
    provider.is_recording = Mock(return_value=False)
    
    return provider


@pytest.fixture
def mock_transcription_client():
    """Provide mock transcription client for testing"""
    client = Mock()
    client.connect = AsyncMock(return_value=Success(None))
    client.disconnect = AsyncMock(return_value=Success(None))
    client.transcribe_audio = AsyncMock()
    client.cleanup = AsyncMock()
    
    return client


@pytest.fixture
def mock_text_injection_provider():
    """Provide mock text injection provider for testing"""
    provider = Mock()
    provider.initialize = AsyncMock(return_value=Success(None))
    provider.inject_text = AsyncMock(return_value=Success(None))
    provider.cleanup = AsyncMock()
    
    return provider


@pytest.fixture
def mock_hotkey_handler():
    """Provide mock hotkey handler for testing"""
    handler = Mock()
    handler.initialize = AsyncMock(return_value=Success(None))
    handler.register_hotkey = AsyncMock(return_value=Success(None))
    handler.unregister_hotkey = AsyncMock(return_value=Success(None))
    handler.cleanup = AsyncMock()
    handler.is_active = Mock(return_value=True)
    
    return handler


@pytest.fixture
def mock_websocket():
    """Provide mock websocket for transcription client testing"""
    websocket = AsyncMock()
    websocket.send = AsyncMock()
    websocket.recv = AsyncMock()
    websocket.close = AsyncMock()
    
    return websocket


# Test utilities
def assert_result_success(result: Result, expected_value=None):
    """Assert that a Result is successful"""
    assert result.is_success(), f"Expected Success, got Failure: {result.error if result.is_failure() else 'N/A'}"
    if expected_value is not None:
        assert result.value == expected_value


def assert_result_failure(result: Result, expected_error_type=None):
    """Assert that a Result is a failure"""
    assert result.is_failure(), f"Expected Failure, got Success: {result.value if result.is_success() else 'N/A'}"
    if expected_error_type is not None:
        assert isinstance(result.error, expected_error_type)


async def wait_for_condition(condition_func, timeout=5.0, interval=0.1):
    """Wait for a condition to become true"""
    elapsed = 0.0
    while elapsed < timeout:
        if condition_func():
            return True
        await asyncio.sleep(interval)
        elapsed += interval
    return False


def create_test_audio_bytes(duration_seconds: float = 1.0, sample_rate: int = 16000) -> bytes:
    """Create test audio data"""
    samples = int(duration_seconds * sample_rate)
    # Generate simple sine wave test data
    import math
    frequency = 440.0  # A4 note
    
    audio_data = []
    for i in range(samples):
        # Generate sine wave
        t = i / sample_rate
        sample = int(32767 * 0.1 * math.sin(2 * math.pi * frequency * t))
        # Convert to 16-bit little-endian
        audio_data.extend([sample & 0xFF, (sample >> 8) & 0xFF])
    
    return bytes(audio_data)


# Marks for test categorization (matching server patterns)
pytest.mark.unit = pytest.mark.unit
pytest.mark.integration = pytest.mark.integration
pytest.mark.e2e = pytest.mark.e2e
pytest.mark.functional = pytest.mark.functional
pytest.mark.pipeline = pytest.mark.pipeline
pytest.mark.events = pytest.mark.events
pytest.mark.providers = pytest.mark.providers
pytest.mark.slow = pytest.mark.slow
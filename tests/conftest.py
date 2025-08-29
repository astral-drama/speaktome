#!/usr/bin/env python3

"""
Test Configuration and Fixtures

Provides shared fixtures for integration and end-to-end testing.
"""

import asyncio
import os
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, Optional
import pytest
import pytest_asyncio

# Test data and utilities
from tests.test_utils import (
    create_test_audio_file,
    create_test_wav_data,
    MockTranscriptionProvider,
    MockWebSocketClient,
    MockFileUploader
)

# System imports
from server.container import DependencyContainer, get_container
from server.events import EventBus, get_event_bus
from server.plugins import get_plugin_registry, register_example_plugins
from server.status import get_server_status_provider
from server.validation import create_audio_validator
from server.connection import WebSocketConnectionManager
from server.routing import create_transcription_router, create_websocket_handlers

@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def temp_dir():
    """Create temporary directory for tests"""
    temp_path = tempfile.mkdtemp(prefix="whisper_test_")
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)

@pytest_asyncio.fixture
async def test_container():
    """Create test dependency injection container"""
    container = DependencyContainer()
    
    # Register test services
    from server.validation import FileValidator, create_audio_validator
    file_validator = create_audio_validator(max_size_mb=10.0)
    container.register_instance(FileValidator, file_validator)
    
    # Register test transcription provider
    test_provider = MockTranscriptionProvider()
    container.register_instance(MockTranscriptionProvider, test_provider, name="test_transcription")
    
    yield container
    await container.dispose()

@pytest_asyncio.fixture
async def test_event_bus():
    """Create test event bus"""
    event_bus = EventBus()
    await event_bus.start()
    
    yield event_bus
    
    await event_bus.stop()

@pytest_asyncio.fixture
async def websocket_manager(test_event_bus):
    """Create WebSocket connection manager"""
    manager = WebSocketConnectionManager()
    yield manager
    await manager.shutdown()

@pytest_asyncio.fixture
async def test_audio_files(temp_dir):
    """Create test audio files"""
    files = {}
    
    # Create different format test files
    files['wav'] = create_test_audio_file(temp_dir, 'test.wav', duration=2.0)
    files['mp3'] = create_test_audio_file(temp_dir, 'test.mp3', duration=1.5)
    files['large'] = create_test_audio_file(temp_dir, 'large.wav', duration=30.0)
    files['invalid'] = Path(temp_dir) / "invalid.txt"
    files['invalid'].write_text("This is not an audio file")
    
    yield files

@pytest.fixture
def test_transcription_config():
    """Test transcription configuration"""
    return {
        "available_models": ["base", "small"],
        "default_model": "base",
        "max_file_size": 10 * 1024 * 1024,  # 10MB
        "supported_formats": ["wav", "mp3", "flac", "webm"],
        "temp_dir": "/tmp/whisper_test"
    }

@pytest_asyncio.fixture
async def transcription_router(temp_dir, test_transcription_config):
    """Create transcription router for testing"""
    router = create_transcription_router(
        available_models=test_transcription_config["available_models"],
        temp_dir=temp_dir,
        max_file_size_mb=10.0
    )
    
    yield router

@pytest_asyncio.fixture
async def websocket_handlers(temp_dir, test_transcription_config):
    """Create WebSocket handlers for testing"""
    handlers = create_websocket_handlers(
        temp_dir=temp_dir,
        available_models=test_transcription_config["available_models"],
        max_file_size_mb=10.0
    )
    
    yield handlers

@pytest_asyncio.fixture
async def test_server_components(test_container, test_event_bus, websocket_manager, temp_dir):
    """Create integrated server components"""
    components = {
        'container': test_container,
        'event_bus': test_event_bus,
        'websocket_manager': websocket_manager,
        'temp_dir': temp_dir,
        'status_provider': get_server_status_provider()
    }
    
    yield components

@pytest.fixture
def test_websocket_client():
    """Create test WebSocket client"""
    return MockWebSocketClient()

@pytest.fixture
def test_file_uploader():
    """Create test file uploader"""
    return MockFileUploader()

@pytest.fixture(scope="session")
def test_plugin_configs():
    """Plugin configurations for testing"""
    return {
        "metrics_collector": {
            "enabled": True
        },
        "websocket_logger": {
            "enabled": True,
            "log_level": "DEBUG"
        },
        "notification_sender": {
            "enabled": False,  # Disabled for tests
            "webhook_url": "http://localhost:8999/webhook"
        },
        "storage_manager": {
            "enabled": True,
            "storage_path": "/tmp/whisper_test_storage"
        }
    }

@pytest_asyncio.fixture
async def test_plugins(test_plugin_configs, temp_dir):
    """Set up test plugins"""
    registry = get_plugin_registry()
    
    # Register example plugins
    register_example_plugins()
    
    # Load and start plugins with test configs
    load_result = await registry.load_and_start_all(test_plugin_configs)
    
    yield {
        'registry': registry,
        'load_result': load_result
    }
    
    # Clean up
    await registry.stop_all_plugins()

@pytest.fixture
def sample_audio_data():
    """Sample audio data for testing"""
    return create_test_wav_data(duration=1.0, sample_rate=16000)

@pytest.fixture
def mock_transcription_request():
    """Mock transcription request data"""
    return {
        "model": "base",
        "language": "en",
        "file_size": 1024,
        "format": "wav"
    }

# Test environment setup
@pytest_asyncio.fixture(autouse=True)
async def setup_test_environment():
    """Set up test environment before each test"""
    # Ensure clean state
    os.environ['WHISPER_ENV'] = 'test'
    os.environ['LOG_LEVEL'] = 'DEBUG'
    
    yield
    
    # Cleanup after test
    test_vars = [k for k in os.environ.keys() if k.startswith('WHISPER_TEST_')]
    for var in test_vars:
        del os.environ[var]

# Markers for different test types
def pytest_configure(config):
    """Configure pytest markers"""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "e2e: End-to-end tests")
    config.addinivalue_line("markers", "slow: Slow running tests")
    config.addinivalue_line("markers", "plugin: Plugin system tests")
    config.addinivalue_line("markers", "pipeline: Audio pipeline tests")
    config.addinivalue_line("markers", "events: Event system tests")
    config.addinivalue_line("markers", "websocket: WebSocket tests")

# Custom test collection
def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers automatically"""
    for item in items:
        # Add markers based on test file location
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        elif "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        elif "e2e" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)
        
        # Add markers based on test name patterns
        if "test_plugin" in item.name:
            item.add_marker(pytest.mark.plugin)
        if "test_pipeline" in item.name:
            item.add_marker(pytest.mark.pipeline)
        if "test_event" in item.name:
            item.add_marker(pytest.mark.events)
        if "websocket" in item.name:
            item.add_marker(pytest.mark.websocket)

# Test data cleanup
@pytest.fixture(autouse=True)
def cleanup_test_data():
    """Clean up test data after each test"""
    yield
    
    # Clean up any test files in temp directories
    import glob
    for pattern in ["/tmp/whisper_test*", "/tmp/test_audio*"]:
        for path in glob.glob(pattern):
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.unlink(path)
            except:
                pass  # Ignore cleanup errors
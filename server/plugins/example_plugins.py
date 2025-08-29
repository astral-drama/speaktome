#!/usr/bin/env python3

"""
Example Plugins

Demonstrates how to create plugins for the Whisper system.
These serve as templates and examples for plugin development.
"""

import asyncio
import logging
from typing import Dict, Any, Optional

from .plugin_system import Plugin, PluginMetadata, PluginType, plugin_metadata
from ..functional.result_monad import Result, Success, Failure
from ..events import DomainEvent, TranscriptionCompletedEvent, WebSocketConnectedEvent
from ..pipeline import PipelineStage, AudioData, ProcessingContext

logger = logging.getLogger(__name__)

@plugin_metadata(
    name="metrics_collector",
    version="1.0.0", 
    description="Collects and logs transcription metrics",
    author="Whisper System",
    plugin_type=PluginType.METRICS_COLLECTOR,
    priority=50
)
class MetricsCollectorPlugin(Plugin):
    """Plugin that collects metrics from transcription events"""
    
    def __init__(self):
        super().__init__()
        self._metrics = {
            "total_transcriptions": 0,
            "successful_transcriptions": 0,
            "failed_transcriptions": 0,
            "total_processing_time": 0.0,
            "average_processing_time": 0.0
        }
    
    @property
    def metadata(self) -> PluginMetadata:
        return self._plugin_metadata
    
    async def on_start(self) -> Result[None, str]:
        """Start collecting metrics"""
        try:
            # Subscribe to transcription events
            self.subscribe_to_event("transcription.completed", self._on_transcription_completed)
            self.subscribe_to_event("transcription.failed", self._on_transcription_failed)
            
            logger.info("Metrics collector plugin started")
            return Success(None)
            
        except Exception as e:
            return Failure(f"Failed to start metrics collector: {str(e)}")
    
    async def _on_transcription_completed(self, event: DomainEvent) -> Result[None, str]:
        """Handle transcription completed events"""
        try:
            if isinstance(event, TranscriptionCompletedEvent):
                processing_time = event.data.get("processing_time", 0.0)
                
                self._metrics["total_transcriptions"] += 1
                self._metrics["successful_transcriptions"] += 1
                self._metrics["total_processing_time"] += processing_time
                
                # Update average
                if self._metrics["total_transcriptions"] > 0:
                    self._metrics["average_processing_time"] = (
                        self._metrics["total_processing_time"] / self._metrics["total_transcriptions"]
                    )
                
                logger.debug(f"Updated metrics: {self._metrics}")
            
            return Success(None)
            
        except Exception as e:
            logger.error(f"Error handling transcription completed event: {e}")
            return Failure(f"Metrics collection failed: {str(e)}")
    
    async def _on_transcription_failed(self, event: DomainEvent) -> Result[None, str]:
        """Handle transcription failed events"""
        try:
            self._metrics["total_transcriptions"] += 1
            self._metrics["failed_transcriptions"] += 1
            
            logger.debug(f"Updated metrics after failure: {self._metrics}")
            return Success(None)
            
        except Exception as e:
            logger.error(f"Error handling transcription failed event: {e}")
            return Failure(f"Metrics collection failed: {str(e)}")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics"""
        return self._metrics.copy()

@plugin_metadata(
    name="websocket_logger",
    version="1.0.0",
    description="Logs WebSocket connection events",
    author="Whisper System", 
    plugin_type=PluginType.EVENT_HANDLER,
    priority=100
)
class WebSocketLoggerPlugin(Plugin):
    """Plugin that logs WebSocket connection events"""
    
    def __init__(self):
        super().__init__()
        self._connections = {}
    
    @property 
    def metadata(self) -> PluginMetadata:
        return self._plugin_metadata
    
    async def on_start(self) -> Result[None, str]:
        """Start logging WebSocket events"""
        try:
            self.subscribe_to_event("websocket.connected", self._on_websocket_connected)
            self.subscribe_to_event("websocket.disconnected", self._on_websocket_disconnected)
            
            logger.info("WebSocket logger plugin started")
            return Success(None)
            
        except Exception as e:
            return Failure(f"Failed to start WebSocket logger: {str(e)}")
    
    async def _on_websocket_connected(self, event: DomainEvent) -> Result[None, str]:
        """Log WebSocket connection"""
        try:
            if isinstance(event, WebSocketConnectedEvent):
                client_id = event.data.get("client_id")
                remote_address = event.data.get("remote_address", "unknown")
                
                self._connections[client_id] = {
                    "connected_at": event.timestamp,
                    "remote_address": remote_address
                }
                
                logger.info(f"WebSocket client connected: {client_id} from {remote_address}")
            
            return Success(None)
            
        except Exception as e:
            return Failure(f"WebSocket connection logging failed: {str(e)}")
    
    async def _on_websocket_disconnected(self, event: DomainEvent) -> Result[None, str]:
        """Log WebSocket disconnection"""
        try:
            client_id = event.data.get("client_id")
            reason = event.data.get("reason", "unknown")
            
            connection_info = self._connections.pop(client_id, {})
            connected_at = connection_info.get("connected_at", 0)
            
            if connected_at > 0:
                duration = event.timestamp - connected_at
                logger.info(f"WebSocket client disconnected: {client_id} (duration: {duration:.1f}s, reason: {reason})")
            else:
                logger.info(f"WebSocket client disconnected: {client_id} (reason: {reason})")
            
            return Success(None)
            
        except Exception as e:
            return Failure(f"WebSocket disconnection logging failed: {str(e)}")

@plugin_metadata(
    name="audio_duration_calculator",
    version="1.0.0",
    description="Calculates and adds audio duration metadata",
    author="Whisper System",
    plugin_type=PluginType.AUDIO_PROCESSOR,
    priority=75
)
class AudioDurationCalculatorPlugin(Plugin, PipelineStage):
    """Plugin that adds audio duration calculation as a pipeline stage"""
    
    def __init__(self):
        super().__init__()
    
    @property
    def metadata(self) -> PluginMetadata:
        return self._plugin_metadata
    
    @property
    def name(self) -> str:
        return "audio_duration_calculator"
    
    async def on_start(self) -> Result[None, str]:
        """Register this plugin as a pipeline stage"""
        try:
            # In a real implementation, this would register with a pipeline manager
            logger.info("Audio duration calculator plugin started")
            return Success(None)
        except Exception as e:
            return Failure(f"Failed to start audio duration calculator: {str(e)}")
    
    async def process(self, audio: AudioData, context: ProcessingContext) -> Result[AudioData, str]:
        """Calculate and add audio duration"""
        try:
            # Placeholder duration calculation (would use actual audio analysis)
            estimated_duration = len(audio.data) / (16000 * 2)  # Assuming 16kHz, 16-bit
            
            enhanced_audio = audio.with_metadata(
                estimated_duration=estimated_duration,
                duration_calculated_by="audio_duration_calculator_plugin"
            )
            
            logger.debug(f"Calculated audio duration: {estimated_duration:.2f}s")
            return Success(enhanced_audio)
            
        except Exception as e:
            logger.error(f"Audio duration calculation failed: {e}")
            return Failure(f"Duration calculation error: {str(e)}")
    
    def can_process(self, audio: AudioData, context: ProcessingContext) -> bool:
        """Check if we can process this audio"""
        return audio.data is not None and len(audio.data) > 0

@plugin_metadata(
    name="notification_sender",
    version="1.0.0",
    description="Sends notifications when transcriptions complete",
    author="Whisper System",
    plugin_type=PluginType.NOTIFICATION_PROVIDER,
    configuration_schema={
        "required": ["webhook_url"],
        "optional": ["timeout", "retry_count"],
        "properties": {
            "webhook_url": {"type": "string"},
            "timeout": {"type": "number", "default": 30},
            "retry_count": {"type": "integer", "default": 3}
        }
    },
    priority=200
)
class NotificationSenderPlugin(Plugin):
    """Plugin that sends notifications via webhook when transcriptions complete"""
    
    def __init__(self):
        super().__init__()
        self._webhook_url = None
        self._timeout = 30
        self._retry_count = 3
    
    @property
    def metadata(self) -> PluginMetadata:
        return self._plugin_metadata
    
    async def on_initialize(self) -> Result[None, str]:
        """Initialize notification settings from configuration"""
        try:
            config = self.configuration
            self._webhook_url = config.get("webhook_url")
            self._timeout = config.get("timeout", 30)
            self._retry_count = config.get("retry_count", 3)
            
            if not self._webhook_url:
                return Failure("webhook_url is required in configuration")
            
            return Success(None)
            
        except Exception as e:
            return Failure(f"Notification plugin initialization failed: {str(e)}")
    
    async def on_start(self) -> Result[None, str]:
        """Start listening for transcription events"""
        try:
            self.subscribe_to_event("transcription.completed", self._send_completion_notification)
            
            logger.info(f"Notification sender plugin started (webhook: {self._webhook_url})")
            return Success(None)
            
        except Exception as e:
            return Failure(f"Failed to start notification sender: {str(e)}")
    
    async def _send_completion_notification(self, event: DomainEvent) -> Result[None, str]:
        """Send notification when transcription completes"""
        try:
            if not isinstance(event, TranscriptionCompletedEvent):
                return Success(None)
            
            notification_data = {
                "event_type": "transcription_completed",
                "request_id": event.data.get("request_id"),
                "text": event.data.get("text", "")[:100] + "..." if len(event.data.get("text", "")) > 100 else event.data.get("text", ""),
                "language": event.data.get("language"),
                "processing_time": event.data.get("processing_time"),
                "timestamp": event.timestamp
            }
            
            # Simulate sending webhook (would use actual HTTP client)
            logger.info(f"Sending notification to {self._webhook_url}: {notification_data}")
            
            # In real implementation, would use aiohttp or similar
            await asyncio.sleep(0.1)  # Simulate network delay
            
            return Success(None)
            
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            return Failure(f"Notification send failed: {str(e)}")

# Plugin that demonstrates dependency injection
@plugin_metadata(
    name="storage_manager",
    version="1.0.0",
    description="Manages transcription storage using injected storage provider",
    author="Whisper System", 
    plugin_type=PluginType.STORAGE_PROVIDER,
    required_services=["file_validator", "status_provider"],
    priority=150
)
class StorageManagerPlugin(Plugin):
    """Plugin demonstrating dependency injection"""
    
    def __init__(self):
        super().__init__()
        self._file_validator = None
        self._status_provider = None
        self._storage_path = "/tmp/whisper_storage"
    
    @property
    def metadata(self) -> PluginMetadata:
        return self._plugin_metadata
    
    async def on_initialize(self) -> Result[None, str]:
        """Initialize with injected dependencies"""
        try:
            # Get dependencies from container (these would be real service interfaces)
            # For now, we'll just simulate dependency injection
            
            config = self.configuration
            self._storage_path = config.get("storage_path", "/tmp/whisper_storage")
            
            logger.info(f"Storage manager initialized (path: {self._storage_path})")
            return Success(None)
            
        except Exception as e:
            return Failure(f"Storage manager initialization failed: {str(e)}")
    
    async def on_start(self) -> Result[None, str]:
        """Start storage management"""
        try:
            self.subscribe_to_event("transcription.completed", self._store_transcription)
            
            logger.info("Storage manager plugin started")
            return Success(None)
            
        except Exception as e:
            return Failure(f"Failed to start storage manager: {str(e)}")
    
    async def _store_transcription(self, event: DomainEvent) -> Result[None, str]:
        """Store completed transcription"""
        try:
            if isinstance(event, TranscriptionCompletedEvent):
                request_id = event.data.get("request_id")
                text = event.data.get("text")
                
                # Simulate storing transcription
                logger.info(f"Storing transcription {request_id}: {len(text)} characters")
                
                return Success(None)
            
            return Success(None)
            
        except Exception as e:
            logger.error(f"Transcription storage failed: {e}")
            return Failure(f"Storage failed: {str(e)}")

# Register all example plugins (in a real system, these would be auto-discovered)
def register_example_plugins():
    """Register all example plugins with the global registry"""
    from .plugin_system import get_plugin_registry
    
    registry = get_plugin_registry()
    
    plugins = [
        MetricsCollectorPlugin,
        WebSocketLoggerPlugin, 
        AudioDurationCalculatorPlugin,
        NotificationSenderPlugin,
        StorageManagerPlugin
    ]
    
    for plugin_class in plugins:
        result = registry.register_plugin(plugin_class)
        if result.is_failure():
            logger.error(f"Failed to register example plugin {plugin_class.__name__}: {result.get_error()}")
        else:
            logger.info(f"Registered example plugin: {plugin_class.__name__}")

if __name__ == "__main__":
    # Example of how to run plugins standalone for testing
    logging.basicConfig(level=logging.INFO)
    
    async def test_plugins():
        register_example_plugins()
        
        from .plugin_system import get_plugin_registry
        registry = get_plugin_registry()
        
        # Load and start all plugins
        result = await registry.load_and_start_all()
        if result.is_success():
            print("Plugin test completed successfully")
            
            # Stop all plugins
            await registry.stop_all_plugins()
        else:
            print(f"Plugin test failed: {result.get_error()}")
    
    asyncio.run(test_plugins())
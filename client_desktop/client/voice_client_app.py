#!/usr/bin/env python3

"""
Main Voice Client Application

Event-driven voice client with functional architecture matching the server design.
Orchestrates all components through event-driven patterns and dependency injection.
"""

import asyncio
import json
import logging
import signal
import sys
import uuid
from pathlib import Path
from typing import Optional, Dict, Any

from shared.functional import Result, Success, Failure, setup_logging, merge_configs, validate_required_keys
from shared.events import (
    get_event_bus, 
    HotkeyPressedEvent,
    RecordingStartedEvent,
    RecordingStoppedEvent,
    AudioCapturedEvent,
    TranscriptionReceivedEvent,
    TextInjectedEvent,
    ConnectionStatusEvent,
    ErrorEvent,
    event_handler,
    async_event_handler
)

from .container import ClientContainer, ClientConfig, get_container, set_container
from .pipeline.audio_pipeline import AudioData, ProcessingContext, create_basic_pipeline
from .providers.audio_provider import PyAudioProvider
from .providers.transcription_client import TranscriptionClient
from .providers.text_injection_provider import PyAutoGUIProvider
from .input.hotkey_handler import PynputHotkeyHandler, HotkeyRegistry

logger = logging.getLogger(__name__)


class VoiceClientApplication:
    """
    Main voice client application
    
    Orchestrates all components using event-driven architecture and functional patterns
    consistent with the server design philosophy.
    """
    
    def __init__(self, config: ClientConfig):
        self.config = config
        self.running = False
        self.recording_state = False
        
        # Initialize container and event bus
        self.container = ClientContainer(config)
        self.event_bus = get_event_bus()
        
        # Components (will be injected)
        self.audio_provider: Optional[PyAudioProvider] = None
        self.transcription_client: Optional[TranscriptionClient] = None
        self.text_injection_provider: Optional[PyAutoGUIProvider] = None
        self.hotkey_registry: Optional[HotkeyRegistry] = None
        self.audio_pipeline = None
        
        logger.info("Voice client application initialized")
    
    async def initialize(self) -> Result[None, Exception]:
        """Initialize all application components"""
        logger.info("Initializing voice client application...")
        
        try:
            # Setup logging
            setup_logging(self.config.logging_level)
            
            # Initialize event bus
            await self.event_bus.start()
            
            # Register event handlers
            self._register_event_handlers()
            
            # Initialize components
            init_result = await self._initialize_components()
            if init_result.is_failure():
                return init_result
            
            # Register services in container
            self._register_services()
            
            # Initialize container services
            container_result = await self.container.initialize_services()
            if container_result.is_failure():
                return Failure(Exception(f"Container initialization failed: {container_result.error}"))
            
            # Register global hotkeys
            hotkey_result = await self._setup_hotkeys()
            if hotkey_result.is_failure():
                return hotkey_result
            
            logger.info("Voice client application initialized successfully")
            return Success(None)
            
        except Exception as e:
            logger.error(f"Application initialization failed: {e}")
            return Failure(e)
    
    async def start(self) -> Result[None, Exception]:
        """Start the voice client application"""
        if self.running:
            return Failure(Exception("Application is already running"))
        
        logger.info("Starting voice client application...")
        
        # Initialize if not already done
        if not self.audio_provider:
            init_result = await self.initialize()
            if init_result.is_failure():
                return init_result
        
        self.running = True
        
        # Setup signal handlers
        self._setup_signal_handlers()
        
        logger.info("🎤 Voice client started!")
        logger.info(f"Press {self.config.hotkey.upper()} to start/stop recording")
        
        return Success(None)
    
    async def stop(self) -> Result[None, Exception]:
        """Stop the voice client application"""
        if not self.running:
            return Success(None)
        
        logger.info("Stopping voice client application...")
        
        self.running = False
        
        # Stop any ongoing recording
        if self.recording_state and self.audio_provider:
            await self.audio_provider.stop_recording()
        
        # Cleanup components
        await self._cleanup_components()
        
        # Stop event bus
        await self.event_bus.stop()
        
        logger.info("Voice client application stopped")
        return Success(None)
    
    async def run(self) -> Result[None, Exception]:
        """Run the voice client application main loop"""
        start_result = await self.start()
        if start_result.is_failure():
            return start_result
        
        try:
            # Main application loop
            while self.running:
                await asyncio.sleep(0.1)
                
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        except Exception as e:
            logger.error(f"Application error: {e}")
            return Failure(e)
        finally:
            await self.stop()
        
        return Success(None)
    
    async def _initialize_components(self) -> Result[None, Exception]:
        """Initialize all application components"""
        try:
            # Initialize audio provider
            self.audio_provider = PyAudioProvider(
                sample_rate=self.config.audio_sample_rate,
                channels=self.config.audio_channels,
                chunk_size=self.config.audio_chunk_size,
                input_device=self.config.audio_input_device
            )
            
            audio_init = await self.audio_provider.initialize()
            if audio_init.is_failure():
                return Failure(Exception(f"Audio provider initialization failed: {audio_init.error}"))
            
            # Initialize transcription client
            self.transcription_client = TranscriptionClient(self.config.server_url)
            transcription_init = await self.transcription_client.connect()
            if transcription_init.is_failure():
                logger.warning(f"Initial server connection failed: {transcription_init.error}")
                # Continue - will try to reconnect when needed
            
            # Initialize text injection provider
            self.text_injection_provider = PyAutoGUIProvider(
                add_space_after=self.config.text_add_space_after,
                capitalize_first=self.config.text_capitalize_first
            )
            
            text_init = await self.text_injection_provider.initialize()
            if text_init.is_failure():
                return Failure(Exception(f"Text injection provider initialization failed: {text_init.error}"))
            
            # Initialize hotkey handler
            hotkey_handler = PynputHotkeyHandler()
            hotkey_init = await hotkey_handler.initialize()
            if hotkey_init.is_failure():
                return Failure(Exception(f"Hotkey handler initialization failed: {hotkey_init.error}"))
            
            self.hotkey_registry = HotkeyRegistry(hotkey_handler)
            
            # Initialize audio pipeline
            self.audio_pipeline = create_basic_pipeline()
            
            logger.info("All components initialized successfully")
            return Success(None)
            
        except Exception as e:
            logger.error(f"Component initialization failed: {e}")
            return Failure(e)
    
    def _register_services(self):
        """Register services in the dependency injection container"""
        self.container.register_singleton("audio_provider", self.audio_provider)
        self.container.register_singleton("transcription_client", self.transcription_client)
        self.container.register_singleton("text_injection_provider", self.text_injection_provider)
        self.container.register_singleton("hotkey_registry", self.hotkey_registry)
        self.container.register_singleton("audio_pipeline", self.audio_pipeline)
        self.container.register_singleton("event_bus", self.event_bus)
        
        logger.debug("Services registered in container")
    
    async def _setup_hotkeys(self) -> Result[None, Exception]:
        """Setup global hotkeys"""
        if not self.hotkey_registry:
            return Failure(Exception("Hotkey registry not initialized"))
        
        # Register main voice recording hotkey
        return await self.hotkey_registry.register_voice_trigger(
            self.config.hotkey,
            self._handle_voice_hotkey
        )
    
    def _register_event_handlers(self):
        """Register event handlers for application orchestration"""
        
        @async_event_handler("hotkey.pressed")
        async def handle_hotkey_pressed(event: HotkeyPressedEvent) -> Result[None, Exception]:
            logger.debug(f"Hotkey pressed: {event.hotkey_combination}")
            return Success(None)
        
        @async_event_handler("recording.started")
        async def handle_recording_started(event: RecordingStartedEvent) -> Result[None, Exception]:
            self.recording_state = True
            logger.info(f"🔴 Recording started at {event.sample_rate}Hz")
            return Success(None)
        
        @async_event_handler("recording.stopped") 
        async def handle_recording_stopped(event: RecordingStoppedEvent) -> Result[None, Exception]:
            self.recording_state = False
            logger.info(f"⏹️ Recording stopped: {event.duration_seconds:.2f}s")
            return Success(None)
        
        @async_event_handler("audio.captured")
        async def handle_audio_captured(event: AudioCapturedEvent) -> Result[None, Exception]:
            logger.info(f"🎵 Audio captured: {event.duration_seconds:.2f}s")
            return Success(None)
        
        @async_event_handler("transcription.received")
        async def handle_transcription_received(event: TranscriptionReceivedEvent) -> Result[None, Exception]:
            logger.info(f"📝 Transcription: '{event.text}' ({event.processing_time:.3f}s)")
            
            # Inject text into active window
            if self.text_injection_provider and event.text.strip():
                await self.text_injection_provider.inject_text(event.text)
            
            return Success(None)
        
        @async_event_handler("text.injected")
        async def handle_text_injected(event: TextInjectedEvent) -> Result[None, Exception]:
            logger.info(f"✅ Text injected: '{event.text[:30]}...'")
            return Success(None)
        
        @async_event_handler("connection.status")
        async def handle_connection_status(event: ConnectionStatusEvent) -> Result[None, Exception]:
            if event.status == "connected":
                logger.info(f"🌐 Connected to server: {event.server_url}")
            elif event.status == "disconnected":
                logger.warning(f"🌐 Disconnected from server: {event.server_url}")
            elif event.status == "error":
                logger.error(f"🌐 Connection error: {event.error_message}")
            
            return Success(None)
        
        @async_event_handler("system.error")
        async def handle_system_error(event: ErrorEvent) -> Result[None, Exception]:
            logger.error(f"❌ {event.component} error: {event.error_message}")
            return Success(None)
        
        logger.debug("Event handlers registered")
    
    def _handle_voice_hotkey(self):
        """Handle voice recording hotkey press"""
        if not self.running:
            return
        
        # Use asyncio to handle the hotkey in the event loop
        asyncio.create_task(self._toggle_recording())
    
    async def _toggle_recording(self):
        """Toggle recording state"""
        if not self.audio_provider:
            logger.error("Audio provider not available")
            return
        
        if self.recording_state:
            # Stop recording
            result = await self.audio_provider.stop_recording()
            
            if result.is_success():
                audio_data = result.value
                
                # Process through pipeline
                context = ProcessingContext(request_id=str(uuid.uuid4()))
                pipeline_result = await self.audio_pipeline.process(audio_data, context)
                
                if pipeline_result.is_success():
                    processed_audio = pipeline_result.value
                    
                    # Send for transcription
                    if self.transcription_client:
                        transcription_result = await self.transcription_client.transcribe_audio(
                            processed_audio,
                            model=self.config.model
                        )
                        
                        if transcription_result.is_failure():
                            logger.error(f"Transcription failed: {transcription_result.error}")
                    else:
                        logger.error("Transcription client not available")
                else:
                    logger.error(f"Audio pipeline failed: {pipeline_result.error}")
            else:
                logger.error(f"Failed to stop recording: {result.error}")
        else:
            # Start recording
            result = await self.audio_provider.start_recording()
            if result.is_failure():
                logger.error(f"Failed to start recording: {result.error}")
    
    async def _cleanup_components(self):
        """Cleanup all application components"""
        if self.hotkey_registry:
            await self.hotkey_registry.cleanup()
        
        if self.audio_provider:
            await self.audio_provider.cleanup()
        
        if self.transcription_client:
            await self.transcription_client.cleanup()
        
        if self.text_injection_provider:
            await self.text_injection_provider.cleanup()
        
        if self.container:
            await self.container.cleanup_services()
        
        logger.info("Component cleanup completed")
    
    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            logger.info(f"Signal {signum} received, initiating shutdown...")
            asyncio.create_task(self.stop())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)


def load_config_from_file(config_path: str) -> Result[ClientConfig, Exception]:
    """Load configuration from file with validation"""
    def _load_config():
        config_file = Path(config_path)
        
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        with open(config_file, 'r') as f:
            config_dict = json.load(f)
        
        # Validate required keys
        required_keys = ['server_url', 'hotkey']
        validation_result = validate_required_keys(config_dict, required_keys)
        if validation_result.is_failure():
            raise ValueError(validation_result.error)
        
        # Create config object
        config = ClientConfig()
        
        # Update with file values
        for key, value in config_dict.items():
            if hasattr(config, key):
                setattr(config, key, value)
            elif key.startswith('audio_'):
                attr_name = key  # audio_sample_rate, etc.
                if hasattr(config, attr_name):
                    setattr(config, attr_name, value)
            elif key.startswith('text_'):
                attr_name = key  # text_add_space_after, etc.
                if hasattr(config, attr_name):
                    setattr(config, attr_name, value)
            elif key.startswith('ui_'):
                attr_name = key  # ui_show_notifications, etc.
                if hasattr(config, attr_name):
                    setattr(config, attr_name, value)
        
        return config
    
    return from_callable(_load_config)


async def main():
    """Main application entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="SpeakToMe Desktop Voice Client")
    parser.add_argument(
        "--config",
        help="Configuration file path",
        default="voice_client_config.json"
    )
    parser.add_argument(
        "--server",
        help="SpeakToMe server URL",
        default=None
    )
    parser.add_argument(
        "--hotkey",
        help="Global hotkey combination",
        default=None
    )
    parser.add_argument(
        "--model",
        help="Whisper model to use",
        default=None
    )
    parser.add_argument(
        "--log-level",
        help="Logging level",
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"]
    )
    
    args = parser.parse_args()
    
    # Load configuration
    if Path(args.config).exists():
        config_result = load_config_from_file(args.config)
        if config_result.is_failure():
            print(f"❌ Failed to load config: {config_result.error}")
            return 1
        config = config_result.value
    else:
        config = ClientConfig()
        print(f"⚠️ Config file not found, using defaults: {args.config}")
    
    # Override with command line arguments
    if args.server:
        config.server_url = args.server
    if args.hotkey:
        config.hotkey = args.hotkey
    if args.model:
        config.model = args.model
    if args.log_level:
        config.logging_level = args.log_level
    
    # Create and run application
    app = VoiceClientApplication(config)
    
    try:
        result = await app.run()
        if result.is_failure():
            print(f"❌ Application failed: {result.error}")
            return 1
        
        return 0
        
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
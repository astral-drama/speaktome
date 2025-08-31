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
from typing import Optional, Dict, Any, Callable, Awaitable

from shared.functional import Result, Success, Failure, setup_logging, merge_configs, validate_required_keys, from_callable
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
from .settings import get_settings_manager, AppSettings

# GUI imports (optional - only imported if GUI is enabled)
try:
    import tkinter as tk
    from .gui import MainWindow, SettingsWindow, HistoryWindow
    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False
    MainWindow = SettingsWindow = HistoryWindow = None
    tk = None

logger = logging.getLogger(__name__)


class VoiceClientApplication:
    """
    Main voice client application
    
    Orchestrates all components using event-driven architecture and functional patterns
    consistent with the server design philosophy.
    """
    
    def __init__(self, config: ClientConfig, show_gui: bool = False, config_file: Optional[str] = None):
        self.config = config
        self.running = False
        self.recording_state = False
        self.show_gui = show_gui
        
        # Store reference to main event loop for thread-safe callbacks
        self.main_loop: Optional[asyncio.AbstractEventLoop] = None
        
        # Initialize settings manager
        self.settings_manager = get_settings_manager(config_file)
        self.app_settings: Optional[AppSettings] = None
        
        # Initialize container and event bus
        self.container = ClientContainer(config)
        self.event_bus = get_event_bus()
        
        # Components (will be injected)
        self.audio_provider: Optional[PyAudioProvider] = None
        self.transcription_client: Optional[TranscriptionClient] = None
        self.text_injection_provider: Optional[PyAutoGUIProvider] = None
        self.hotkey_registry: Optional[HotkeyRegistry] = None
        self.audio_pipeline = None
        
        # GUI components (optional)
        self.gui_main_window = None
        self.gui_settings_window = None
        self.gui_history_window = None
        
        logger.info("Voice client application initialized")
    
    async def initialize(self) -> Result[None, Exception]:
        """Initialize all application components"""
        logger.info("Initializing voice client application...")
        
        try:
            # Load application settings
            settings_result = self.settings_manager.load_settings()
            if settings_result.is_success():
                self.app_settings = settings_result.value
                logger.info("Application settings loaded successfully")
                
                # Update config with settings (for backwards compatibility)
                self.config.hotkey = self.app_settings.hotkey
                self.config.server_url = self.app_settings.server_url
                self.config.model = self.app_settings.model
                self.config.audio_sample_rate = self.app_settings.audio_sample_rate
                self.config.audio_channels = self.app_settings.audio_channels
                self.config.logging_level = self.app_settings.logging_level
            else:
                logger.warning(f"Failed to load settings: {settings_result.error}")
                self.app_settings = AppSettings()
            
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
        
        # Store reference to the main event loop for thread-safe callbacks
        self.main_loop = asyncio.get_running_loop()
        logger.debug(f"Stored main event loop reference: {self.main_loop}")
        
        # Setup signal handlers
        self._setup_signal_handlers()
        
        logger.info("Voice client started")
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
        
        # Show GUI if enabled
        if self.show_gui and self.gui_main_window:
            gui_result = self.show_gui_window()
            if gui_result.is_failure():
                logger.warning(f"Failed to show GUI: {gui_result.error}")
        
        try:
            # Main application loop
            if self.show_gui and self.gui_main_window:
                # GUI mode - run Tkinter mainloop in main thread
                # Use asyncio with tkinter integration
                while self.running:
                    # Process tkinter events
                    if self.gui_main_window.root:
                        try:
                            self.gui_main_window.root.update()
                            # Check if GUI window was closed
                            if not self.gui_main_window.is_running:
                                logger.info("GUI window closed, stopping application")
                                self.running = False
                                break
                        except tk.TclError:
                            # Window was closed
                            logger.info("GUI window destroyed, stopping application")
                            self.running = False
                            break
                    await asyncio.sleep(0.01)  # 100 FPS for smooth GUI
            else:
                # Headless mode - simple loop
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
            hotkey_handler = PynputHotkeyHandler(main_loop=self.main_loop)
            hotkey_init = await hotkey_handler.initialize()
            if hotkey_init.is_failure():
                return Failure(Exception(f"Hotkey handler initialization failed: {hotkey_init.error}"))
            
            self.hotkey_registry = HotkeyRegistry(hotkey_handler)
            
            # Initialize audio pipeline
            self.audio_pipeline = create_basic_pipeline()
            
            # Initialize GUI components if requested
            if self.show_gui:
                gui_init_result = self._initialize_gui()
                if gui_init_result.is_failure():
                    logger.warning(f"GUI initialization failed: {gui_init_result.error}")
                    # Don't fail the entire app if GUI fails
            
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
        
        # Get current hotkey from settings (not cached config)
        settings_result = self.settings_manager.load_settings()
        if settings_result.is_failure():
            logger.warning(f"Failed to load settings for hotkey setup: {settings_result.error}")
            current_hotkey = self.config.hotkey  # fallback to config
        else:
            current_hotkey = settings_result.value.hotkey
            
        logger.info(f"Setting up global hotkey: {current_hotkey}")
        
        # Register main voice recording hotkey
        return await self.hotkey_registry.register_voice_trigger(
            current_hotkey,
            self._handle_voice_hotkey
        )
    
    # Thread-safe event publishing utility (functional composition)
    @staticmethod
    def create_thread_safe_publisher(event_bus) -> Callable[[Any], Result[None, Exception]]:
        """Factory function to create thread-safe event publisher"""
        def publish_event_thread_safe(event) -> Result[None, Exception]:
            """Thread-safe event publisher with proper error handling"""
            try:
                # Get the current event loop
                try:
                    loop = asyncio.get_running_loop()
                    # We are in an async context with a running loop
                    if loop.is_running():
                        # Schedule the publish task in the event loop
                        loop.call_soon_threadsafe(
                            lambda: asyncio.create_task(event_bus.publish(event))
                        )
                    else:
                        # Loop exists but is not running - create task directly
                        asyncio.create_task(event_bus.publish(event))
                except RuntimeError:
                    # No running loop - we need to handle this case
                    try:
                        # Try to get the main loop if set
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            loop.call_soon_threadsafe(
                                lambda: asyncio.create_task(event_bus.publish(event))
                            )
                        else:
                            # Create and run the event publishing
                            asyncio.create_task(event_bus.publish(event))
                    except Exception:
                        # Fallback to sync publishing if available
                        if hasattr(event_bus, 'publish_sync'):
                            return event_bus.publish_sync(event)
                        else:
                            raise RuntimeError(f"Cannot publish event {event.event_type}: no valid event loop")
                
                logger.debug(f"Event published thread-safely: {event.event_type}")
                return Success(None)
                
            except Exception as e:
                logger.error(f"Failed to publish event {getattr(event, 'event_type', 'unknown')}: {e}")
                return Failure(e)
        
        return publish_event_thread_safe
    
    @staticmethod
    async def create_async_publisher(event_bus) -> Callable[[Any], Awaitable[Result[None, Exception]]]:
        """Factory function to create async event publisher"""
        async def publish_event_async(event) -> Result[None, Exception]:
            """Async event publisher with proper error handling"""
            try:
                result = await event_bus.publish(event)
                logger.debug(f"Event published async: {event.event_type}")
                return result if hasattr(result, 'is_success') else Success(None)
            except Exception as e:
                logger.error(f"Failed to publish event async {getattr(event, 'event_type', 'unknown')}: {e}")
                return Failure(e)
        
        return publish_event_async

    # Pure functions for event handling (functional composition)
    @staticmethod
    def _create_success_result() -> Result[None, Exception]:
        """Pure function returning success result"""
        return Success(None)
    
    def _update_recording_state(self, is_recording: bool) -> Result[None, Exception]:
        """Pure state update function"""
        try:
            self.recording_state = is_recording
            state_desc = "started" if is_recording else "stopped"
            logger.info(f"Recording state updated: {state_desc}")
            return Success(None)
        except Exception as e:
            return Failure(e)
    
    @staticmethod
    def _copy_to_clipboard_systems(text: str) -> Result[None, Exception]:
        """Pure function to copy text to all clipboard systems"""
        try:
            import pyperclip
            pyperclip.copy(text)
            logger.debug(f"Text copied to clipboard: '{text[:30]}...'")
            
            # Also copy to primary selection on Linux
            try:
                import subprocess
                import platform
                if platform.system() == "Linux":
                    for cmd in [['xsel', '-pi'], ['xclip', '-selection', 'primary']]:
                        try:
                            subprocess.run(cmd, input=text.encode(), check=True, timeout=1)
                            logger.debug(f"Text copied to primary selection: '{text[:30]}...'")
                            break
                        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                            continue
                    else:
                        logger.debug("Neither xsel nor xclip available for primary selection")
            except Exception as e:
                logger.debug(f"Could not set primary selection: {e}")
            
            return Success(None)
        except Exception as e:
            return Failure(e)
    
    async def _inject_text_with_delay(self, text: str) -> Result[None, Exception]:
        """Function to inject text with proper delay and formatting"""
        if not self.text_injection_provider or not text.strip():
            return Success(None)
            
        try:
            await asyncio.sleep(0.2)  # Delay for user focus
            
            injection_result = await self.text_injection_provider.inject_text(
                text,
                add_space_after=True,
                delay=0.1
            )
            
            if injection_result.is_failure():
                logger.error(f"Failed to inject text: {injection_result.error}")
                return injection_result
            else:
                logger.info("✅ Text successfully injected into active window")
                return Success(None)
                
        except Exception as e:
            return Failure(e)
    
    def _register_event_handlers(self):
        """Register event handlers for application orchestration"""
        
        @async_event_handler("hotkey.pressed")
        async def handle_hotkey_pressed(event: HotkeyPressedEvent) -> Result[None, Exception]:
            logger.debug(f"Hotkey pressed: {event.hotkey_combination} (source: {event.source})")
            await self._toggle_recording()
            return self._create_success_result()
        
        @async_event_handler("recording.started")
        async def handle_recording_started(event: RecordingStartedEvent) -> Result[None, Exception]:
            logger.info(f"Recording started at {event.sample_rate}Hz")
            return self._update_recording_state(True)
        
        @async_event_handler("recording.stopped") 
        async def handle_recording_stopped(event: RecordingStoppedEvent) -> Result[None, Exception]:
            logger.info(f"Recording stopped: {event.duration_seconds:.2f}s")
            return self._update_recording_state(False)
        
        @async_event_handler("audio.captured")
        async def handle_audio_captured(event: AudioCapturedEvent) -> Result[None, Exception]:
            logger.info(f"Audio captured: {event.duration_seconds:.2f}s")
            return self._create_success_result()
        
        @async_event_handler("transcription.received")
        async def handle_transcription_received(event: TranscriptionReceivedEvent) -> Result[None, Exception]:
            logger.info(f"Transcription received: '{event.text}' ({event.processing_time:.3f}s)")
            
            if not event.text.strip():
                return self._create_success_result()
            
            logger.debug(f"Auto-injecting transcription: '{event.text}'")
            
            # Sequential functional composition with proper async handling
            clipboard_result = self._copy_to_clipboard_systems(event.text)
            if clipboard_result.is_failure():
                logger.warning(f"Clipboard operation failed: {clipboard_result.error}")
            
            injection_result = await self._inject_text_with_delay(event.text)
            if injection_result.is_failure():
                return injection_result
                
            return self._create_success_result()
        
        @async_event_handler("text.injected")
        async def handle_text_injected(event: TextInjectedEvent) -> Result[None, Exception]:
            logger.info(f"✅ Text injected: '{event.text[:30]}...'")
            return self._create_success_result()
        
        @async_event_handler("connection.status")
        async def handle_connection_status(event: ConnectionStatusEvent) -> Result[None, Exception]:
            status_messages = {
                "connected": lambda: logger.info(f"Connected to server: {event.server_url}"),
                "disconnected": lambda: logger.warning(f"Disconnected from server: {event.server_url}"),
                "error": lambda: logger.error(f"Connection error: {event.error_message}")
            }
            
            status_handler = status_messages.get(event.status)
            if status_handler:
                status_handler()
            
            return self._create_success_result()
        
        @async_event_handler("system.error")
        async def handle_system_error(event: ErrorEvent) -> Result[None, Exception]:
            logger.error(f"{event.component} error: {event.error_message}")
            return self._create_success_result()
        
        logger.debug("Event handlers registered")
    
    def _handle_voice_hotkey(self):
        """Handle voice recording hotkey press"""
        logger.debug("Voice hotkey pressed, handling event")
        if not self.running:
            logger.warning("Hotkey pressed but app not running, ignoring")
            return
        
        # Schedule the async task in the main event loop (thread-safe)
        try:
            if self.main_loop and not self.main_loop.is_closed():
                logger.debug("Scheduling toggle recording in main event loop")
                self.main_loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(self._toggle_recording())
                )
            else:
                logger.warning("Main event loop not available - cannot handle hotkey")
        except Exception as e:
            logger.error(f"Failed to schedule recording toggle: {e}")
    
    async def _toggle_recording(self):
        """Toggle recording state"""
        logger.debug(f"Toggle recording called - current state: {self.recording_state}")
        
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
                            # Publish error event to notify GUI
                            from shared.events import ErrorEvent
                            await self.event_bus.publish(ErrorEvent(
                                error_message=f"Transcription failed: {transcription_result.error}",
                                error_type="transcription_error",
                                source="voice_client_app"
                            ))
                        else:
                            logger.info(f"📝 Transcription successful: '{transcription_result.value}'")
                            # The transcription_client should handle publishing TranscriptionReceivedEvent
                    else:
                        logger.error("Transcription client not available")
                else:
                    logger.error(f"Audio pipeline failed: {pipeline_result.error}")
                    # Publish error event to notify GUI
                    from shared.events import ErrorEvent
                    await self.event_bus.publish(ErrorEvent(
                        error_message=f"Audio pipeline failed: {pipeline_result.error}",
                        error_type="pipeline_error",
                        source="voice_client_app"
                    ))
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
        
        # Cleanup GUI if present
        if self.gui_main_window:
            self.gui_main_window.destroy()
        if self.gui_settings_window:
            self.gui_settings_window.destroy()
        if self.gui_history_window:
            self.gui_history_window.destroy()
        
        logger.info("Component cleanup completed")
    
    def _initialize_gui(self) -> Result[None, Exception]:
        """Initialize GUI components"""
        if not GUI_AVAILABLE:
            return Failure(Exception("GUI components not available - tkinter not installed"))
        
        try:
            # Create main window
            self.gui_main_window = MainWindow(self.event_bus, self.config.__dict__, self.settings_manager)
            gui_init_result = self.gui_main_window.initialize()
            if gui_init_result.is_failure():
                return gui_init_result
            
            # Create settings window
            self.gui_settings_window = SettingsWindow(
                self.event_bus, 
                self.config.__dict__,
                on_settings_changed=self._on_gui_settings_changed,
                config_file=str(self.settings_manager.config_file)
            )
            
            # Create history window  
            self.gui_history_window = HistoryWindow(self.event_bus)
            
            # Connect history and settings windows to main window
            self.gui_main_window.history_window = self.gui_history_window
            self.gui_main_window.settings_window = self.gui_settings_window
            
            # Subscribe to transcription events to update history
            # Note: MainWindow handles its own transcription history via _handle_transcription_received
            # No need for duplicate subscription here
            # self.event_bus.subscribe("transcription.received", self._handle_gui_transcription)
            
            logger.info("GUI components initialized")
            return Success(None)
            
        except Exception as e:
            logger.error(f"GUI initialization failed: {e}")
            return Failure(e)
    
    # Note: Removed _handle_gui_transcription to prevent duplicate history entries
    # MainWindow now handles all transcription history management directly
    
    def _on_gui_settings_changed(self, new_settings: Dict[str, Any]) -> None:
        """Handle settings changes from GUI"""
        # Update config (for backwards compatibility)
        for key, value in new_settings.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
        
        # Update app settings
        if self.app_settings:
            for key, value in new_settings.items():
                if hasattr(self.app_settings, key):
                    setattr(self.app_settings, key, value)
        
        # Apply hotkey changes if needed
        if 'hotkey' in new_settings and self.hotkey_registry:
            logger.info(f"Hotkey change detected: {new_settings['hotkey']}")
            # Re-register hotkey
            task = asyncio.create_task(self._reregister_hotkey(new_settings['hotkey']))
            logger.info("Hotkey re-registration task created")
        
        # Apply server URL changes
        if 'server_url' in new_settings and self.transcription_client:
            # Note: Server URL changes require restart - inform user
            logger.info("Server URL changed - restart required to take effect")
        
        # Refresh GUI display if GUI is available
        if hasattr(self, 'gui_main_window') and self.gui_main_window:
            try:
                self.gui_main_window.refresh_settings_display()
                logger.info("GUI display refreshed after settings update")
            except Exception as e:
                logger.warning(f"Failed to refresh GUI display: {e}")
        
        logger.info(f"Settings updated from GUI: {list(new_settings.keys())}")
    
    async def _reregister_hotkey(self, new_hotkey: str) -> None:
        """Re-register hotkey with new combination"""
        logger.info(f"_reregister_hotkey called with: {new_hotkey}")
        
        if self.hotkey_registry:
            logger.info("Hotkey registry available, starting re-registration...")
            
            # Show current registered hotkeys before unregistering
            current_hotkeys = self.hotkey_registry.get_registered_combinations()
            logger.info(f"Current registered hotkeys: {list(current_hotkeys.keys())}")
            
            # Unregister all old hotkeys
            logger.info("Unregistering old hotkeys...")
            unregister_result = await self.hotkey_registry.unregister_all()
            if unregister_result.is_failure():
                logger.warning(f"Failed to unregister old hotkeys: {unregister_result.error}")
            else:
                logger.info("Successfully unregistered old hotkeys")
            
            # Register new hotkey with the same callback as original setup
            logger.info(f"Registering new hotkey: {new_hotkey}")
            register_result = await self.hotkey_registry.register_voice_trigger(
                new_hotkey, 
                self._handle_voice_hotkey
            )
            if register_result.is_success():
                logger.info(f"✅ Hotkey successfully updated to: {new_hotkey}")
                
                # Verify registration
                updated_hotkeys = self.hotkey_registry.get_registered_combinations()
                logger.info(f"Verified registered hotkeys: {list(updated_hotkeys.keys())}")
            else:
                logger.error(f"❌ Failed to register new hotkey: {register_result.error}")
        else:
            logger.error("❌ Hotkey registry not available!")
    
    def show_gui_window(self) -> Result[None, Exception]:
        """Show the GUI window"""
        if not self.gui_main_window:
            return Failure(Exception("GUI not initialized"))
        
        return self.gui_main_window.show()
    
    def hide_gui_window(self) -> Result[None, Exception]:
        """Hide the GUI window"""
        if not self.gui_main_window:
            return Success(None)
        
        return self.gui_main_window.hide()
    
    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            logger.info(f"Signal {signum} received, initiating shutdown...")
            asyncio.create_task(self.stop())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)


# Pure functions for configuration loading (functional composition)
def _read_config_file(config_path: str) -> Result[dict, Exception]:
    """Pure function to read and parse config file"""
    try:
        config_file = Path(config_path)
        
        if not config_file.exists():
            return Failure(FileNotFoundError(f"Configuration file not found: {config_path}"))
        
        with open(config_file, 'r') as f:
            config_dict = json.load(f)
        
        return Success(config_dict)
    except Exception as e:
        return Failure(e)


def _validate_config_dict(config_dict: dict) -> Result[dict, Exception]:
    """Pure function to validate configuration dictionary"""
    required_keys = ['server_url', 'hotkey']
    validation_result = validate_required_keys(config_dict, required_keys)
    
    if validation_result.is_failure():
        return Failure(ValueError(validation_result.error))
    
    return Success(config_dict)


def _create_config_from_dict(config_dict: dict) -> Result[ClientConfig, Exception]:
    """Pure function to create ClientConfig from validated dictionary"""
    try:
        config = ClientConfig()
        
        # Define mapping for attribute updates
        attribute_prefixes = ['audio_', 'text_', 'ui_']
        
        for key, value in config_dict.items():
            if hasattr(config, key):
                setattr(config, key, value)
            else:
                # Check prefixed attributes
                for prefix in attribute_prefixes:
                    if key.startswith(prefix) and hasattr(config, key):
                        setattr(config, key, value)
                        break
        
        return Success(config)
    except Exception as e:
        return Failure(e)


def load_config_from_file(config_path: str) -> Result[ClientConfig, Exception]:
    """Load configuration from file using functional composition"""
    return (
        _read_config_file(config_path)
        .flat_map(_validate_config_dict)
        .flat_map(_create_config_from_dict)
    )


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
    parser.add_argument(
        "--gui",
        help="Show GUI window",
        action="store_true",
        default=False
    )
    parser.add_argument(
        "--headless",
        help="Run in headless mode (no GUI)",
        action="store_true", 
        default=False
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
    
    # Determine GUI mode
    show_gui = args.gui and not args.headless
    if args.gui and args.headless:
        print("⚠️ Warning: Both --gui and --headless specified. Using headless mode.")
        show_gui = False
    
    # Create and run application
    app = VoiceClientApplication(config, show_gui=show_gui, config_file=args.config)
    
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
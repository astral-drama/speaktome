#!/usr/bin/env python3

"""
SpeakToMe Desktop Voice Client

A cross-platform desktop client that captures voice input via global hotkeys
and sends transcribed text to the active window.

Features:
- Global hotkey (Ctrl-Shift-W) for voice recording
- Cross-platform audio recording (macOS/Linux/Windows)
- WebSocket connection to SpeakToMe server
- Text injection into any active window
- Visual recording feedback
- Configurable settings

Usage:
    python voice_client.py [--config config.json] [--server ws://localhost:8000]
"""

import asyncio
import json
import logging
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Dict, Any, Optional, Callable
import argparse
import platform

# Cross-platform imports with fallbacks
try:
    import pyaudio
except ImportError:
    print("❌ PyAudio not installed. Install with: pip install pyaudio")
    sys.exit(1)

try:
    import websockets
except ImportError:
    print("❌ WebSockets not installed. Install with: pip install websockets")
    sys.exit(1)

try:
    import pynput
    from pynput import keyboard
    from pynput.keyboard import Key, Listener, HotKey
except ImportError:
    print("❌ Pynput not installed. Install with: pip install pynput")
    sys.exit(1)

# Platform-specific text injection
if platform.system() == "Darwin":  # macOS
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
    except ImportError:
        print("❌ PyAutoGUI not installed. Install with: pip install pyautogui")
        sys.exit(1)
elif platform.system() == "Linux":
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
    except ImportError:
        print("❌ PyAutoGUI not installed. Install with: pip install pyautogui")
        sys.exit(1)
elif platform.system() == "Windows":
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
    except ImportError:
        print("❌ PyAutoGUI not installed. Install with: pip install pyautogui")
        sys.exit(1)

import base64
import wave
import tempfile
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AudioRecorder:
    """Cross-platform audio recording using PyAudio"""
    
    def __init__(self, sample_rate: int = 16000, channels: int = 1, chunk_size: int = 1024):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.format = pyaudio.paInt16
        
        self.audio = pyaudio.PyAudio()
        self.stream: Optional[pyaudio.Stream] = None
        self.frames = []
        self.is_recording = False
        
    def start_recording(self) -> bool:
        """Start audio recording"""
        try:
            self.frames = []
            self.stream = self.audio.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size
            )
            self.is_recording = True
            logger.info("🎤 Recording started")
            return True
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            return False
    
    def stop_recording(self) -> Optional[bytes]:
        """Stop recording and return audio data"""
        if not self.is_recording or not self.stream:
            return None
            
        try:
            self.is_recording = False
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
            
            # Convert to WAV format
            audio_data = self._frames_to_wav()
            logger.info(f"🔇 Recording stopped, {len(audio_data)} bytes captured")
            return audio_data
            
        except Exception as e:
            logger.error(f"Failed to stop recording: {e}")
            return None
    
    def record_chunk(self) -> Optional[bytes]:
        """Record a single chunk of audio"""
        if not self.is_recording or not self.stream:
            return None
            
        try:
            data = self.stream.read(self.chunk_size, exception_on_overflow=False)
            self.frames.append(data)
            return data
        except Exception as e:
            logger.error(f"Failed to record chunk: {e}")
            return None
    
    def _frames_to_wav(self) -> bytes:
        """Convert recorded frames to WAV format"""
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
            try:
                with wave.open(temp_file.name, 'wb') as wav_file:
                    wav_file.setnchannels(self.channels)
                    wav_file.setsampwidth(self.audio.get_sample_size(self.format))
                    wav_file.setframerate(self.sample_rate)
                    wav_file.writeframes(b''.join(self.frames))
                
                # Read the WAV file back
                with open(temp_file.name, 'rb') as f:
                    wav_data = f.read()
                    
                return wav_data
            finally:
                # Clean up temp file
                try:
                    os.unlink(temp_file.name)
                except:
                    pass
    
    def cleanup(self):
        """Clean up audio resources"""
        if self.stream:
            try:
                if self.is_recording:
                    self.stream.stop_stream()
                self.stream.close()
            except:
                pass
        
        if self.audio:
            try:
                self.audio.terminate()
            except:
                pass


class TextInjector:
    """Cross-platform text injection into active window"""
    
    @staticmethod
    def inject_text(text: str) -> bool:
        """Inject text into the currently active window"""
        try:
            # Small delay to ensure the window is ready
            time.sleep(0.1)
            
            # Use PyAutoGUI for cross-platform text injection
            pyautogui.typewrite(text)
            logger.info(f"📝 Injected text: {text[:50]}...")
            return True
            
        except Exception as e:
            logger.error(f"Failed to inject text: {e}")
            return False


class SpeakToMeClient:
    """WebSocket client for SpeakToMe server"""
    
    def __init__(self, server_url: str = "ws://localhost:8000/ws/transcribe"):
        self.server_url = server_url
        self.websocket: Optional[websockets.WebSocketServerProtocol] = None
        self.connected = False
        
    async def connect(self) -> bool:
        """Connect to SpeakToMe server"""
        try:
            self.websocket = await websockets.connect(self.server_url)
            self.connected = True
            logger.info(f"🌐 Connected to SpeakToMe server: {self.server_url}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to server: {e}")
            self.connected = False
            return False
    
    async def disconnect(self):
        """Disconnect from server"""
        if self.websocket:
            await self.websocket.close()
            self.connected = False
            logger.info("🌐 Disconnected from server")
    
    async def transcribe_audio(self, audio_data: bytes, model: str = "base") -> Optional[str]:
        """Send audio for transcription"""
        if not self.connected or not self.websocket:
            logger.error("Not connected to server")
            return None
        
        try:
            # Encode audio as base64
            audio_b64 = base64.b64encode(audio_data).decode('utf-8')
            
            # Send transcription request
            request = {
                "type": "audio",
                "data": audio_b64,
                "format": "wav",
                "model": model,
                "language": "auto"
            }
            
            await self.websocket.send(json.dumps(request))
            logger.info("📤 Sent audio for transcription")
            
            # Wait for response
            response_str = await self.websocket.recv()
            response = json.loads(response_str)
            
            if response.get("type") == "transcription":
                text = response.get("text", "").strip()
                logger.info(f"📥 Received transcription: {text}")
                return text
            else:
                logger.error(f"Unexpected response: {response}")
                return None
                
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return None


class VoiceClient:
    """Main voice client with global hotkey support"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.running = False
        
        # Components
        self.recorder = AudioRecorder(
            sample_rate=config.get('audio', {}).get('sample_rate', 16000),
            channels=config.get('audio', {}).get('channels', 1),
            chunk_size=config.get('audio', {}).get('chunk_size', 1024)
        )
        self.text_injector = TextInjector()
        self.client = SpeakToMeClient(config.get('server_url', 'ws://localhost:8000/ws/transcribe'))
        
        # State
        self.is_recording = False
        self.recording_thread: Optional[threading.Thread] = None
        
        # Hotkey setup
        self.hotkey_combo = config.get('hotkey', 'ctrl+shift+w')
        self.hotkey = None
        self.listener = None
        
    async def start(self):
        """Start the voice client"""
        logger.info("🚀 Starting SpeakToMe Voice Client...")
        
        # Connect to server
        if not await self.client.connect():
            logger.error("❌ Failed to connect to server. Make sure SpeakToMe server is running.")
            return False
        
        # Setup global hotkey
        self._setup_hotkey()
        
        self.running = True
        logger.info(f"✅ Voice client started. Press {self.hotkey_combo.upper()} to record.")
        
        return True
    
    async def stop(self):
        """Stop the voice client"""
        logger.info("🛑 Stopping voice client...")
        
        self.running = False
        
        # Stop any ongoing recording
        if self.is_recording:
            await self._stop_recording()
        
        # Cleanup hotkey listener
        if self.listener:
            self.listener.stop()
        
        # Disconnect from server
        await self.client.disconnect()
        
        # Cleanup audio
        self.recorder.cleanup()
        
        logger.info("👋 Voice client stopped")
    
    def _setup_hotkey(self):
        """Setup global hotkey listener"""
        try:
            # Parse hotkey combination
            keys = self.hotkey_combo.lower().split('+')
            key_combo = []
            
            for key in keys:
                if key == 'ctrl':
                    key_combo.append(Key.ctrl_l)
                elif key == 'shift':
                    key_combo.append(Key.shift_l)
                elif key == 'alt':
                    key_combo.append(Key.alt_l)
                elif key == 'cmd':
                    key_combo.append(Key.cmd)
                else:
                    key_combo.append(keyboard.KeyCode.from_char(key))
            
            # Create hotkey
            self.hotkey = HotKey(
                key_combo,
                self._on_hotkey_pressed
            )
            
            # Start listener
            self.listener = Listener(
                on_press=self.hotkey.press,
                on_release=self.hotkey.release
            )
            self.listener.start()
            
            logger.info(f"🔥 Global hotkey registered: {self.hotkey_combo.upper()}")
            
        except Exception as e:
            logger.error(f"Failed to setup hotkey: {e}")
    
    def _on_hotkey_pressed(self):
        """Handle hotkey press"""
        if not self.running:
            return
            
        if not self.is_recording:
            # Start recording
            asyncio.run_coroutine_threadsafe(
                self._start_recording(),
                asyncio.get_event_loop()
            )
        else:
            # Stop recording
            asyncio.run_coroutine_threadsafe(
                self._stop_recording(),
                asyncio.get_event_loop()
            )
    
    async def _start_recording(self):
        """Start voice recording"""
        if self.is_recording:
            return
        
        logger.info("🔴 Starting recording... (press hotkey again to stop)")
        
        if self.recorder.start_recording():
            self.is_recording = True
            
            # Start recording loop in background
            self.recording_thread = threading.Thread(
                target=self._recording_loop,
                daemon=True
            )
            self.recording_thread.start()
    
    async def _stop_recording(self):
        """Stop voice recording and process"""
        if not self.is_recording:
            return
        
        logger.info("⏹️ Stopping recording...")
        
        # Stop recording
        audio_data = self.recorder.stop_recording()
        self.is_recording = False
        
        if audio_data and len(audio_data) > 1000:  # Basic size check
            logger.info("🔄 Processing audio...")
            
            # Send for transcription
            text = await self.client.transcribe_audio(
                audio_data,
                self.config.get('model', 'base')
            )
            
            if text:
                # Inject text into active window
                success = self.text_injector.inject_text(text)
                if success:
                    logger.info(f"✅ Text injected: {text}")
                else:
                    logger.error("❌ Failed to inject text")
            else:
                logger.error("❌ No transcription received")
        else:
            logger.warning("⚠️ Recording too short or empty")
    
    def _recording_loop(self):
        """Background recording loop"""
        while self.is_recording:
            chunk = self.recorder.record_chunk()
            if not chunk:
                break
            time.sleep(0.01)  # Small delay to prevent CPU spinning


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load configuration from file or create default"""
    default_config = {
        "server_url": "ws://localhost:8000/ws/transcribe",
        "model": "base",
        "hotkey": "ctrl+shift+w",
        "audio": {
            "sample_rate": 16000,
            "channels": 1,
            "chunk_size": 1024
        },
        "logging": {
            "level": "INFO"
        }
    }
    
    if config_path and Path(config_path).exists():
        try:
            with open(config_path, 'r') as f:
                user_config = json.load(f)
                # Merge with defaults
                default_config.update(user_config)
                logger.info(f"📄 Loaded config from: {config_path}")
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            logger.info("Using default configuration")
    
    return default_config


async def main():
    """Main application entry point"""
    parser = argparse.ArgumentParser(description="SpeakToMe Desktop Voice Client")
    parser.add_argument(
        "--config",
        help="Configuration file path",
        default="voice_client_config.json"
    )
    parser.add_argument(
        "--server",
        help="SpeakToMe server URL",
        default="ws://localhost:8000/ws/transcribe"
    )
    parser.add_argument(
        "--hotkey",
        help="Global hotkey combination (default: ctrl+shift+w)",
        default="ctrl+shift+w"
    )
    
    args = parser.parse_args()
    
    # Load configuration
    config = load_config(args.config)
    
    # Override with command line args
    if args.server != "ws://localhost:8000/ws/transcribe":
        config["server_url"] = args.server
    if args.hotkey != "ctrl+shift+w":
        config["hotkey"] = args.hotkey
    
    # Create and start client
    client = VoiceClient(config)
    
    def signal_handler(signum, frame):
        """Handle shutdown signals"""
        logger.info("🛑 Shutdown signal received")
        asyncio.create_task(client.stop())
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Start client
        if await client.start():
            # Keep running until stopped
            while client.running:
                await asyncio.sleep(0.1)
        
    except KeyboardInterrupt:
        logger.info("🛑 Keyboard interrupt received")
    except Exception as e:
        logger.error(f"❌ Client error: {e}")
    finally:
        await client.stop()


if __name__ == "__main__":
    # Create event loop for the application
    if platform.system() == "Windows":
        # Windows requires ProactorEventLoop for signal handling
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("👋 Goodbye!")
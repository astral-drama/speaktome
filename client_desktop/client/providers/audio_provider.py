#!/usr/bin/env python3

"""
Audio Provider

Functional audio recording provider matching server architecture patterns.
"""

import asyncio
import logging
import time
import wave
import tempfile
import os
from typing import Optional, Dict, Any
from abc import ABC, abstractmethod

import pyaudio

from shared.functional import Result, Success, Failure, from_callable
from shared.events import get_event_bus, RecordingStartedEvent, RecordingStoppedEvent
from ..pipeline.audio_pipeline import AudioData

logger = logging.getLogger(__name__)


class AudioProvider(ABC):
    """Abstract audio provider interface"""
    
    @abstractmethod
    async def initialize(self) -> Result[None, Exception]:
        """Initialize the audio provider"""
        pass
    
    @abstractmethod
    async def start_recording(self) -> Result[None, Exception]:
        """Start audio recording"""
        pass
    
    @abstractmethod
    async def stop_recording(self) -> Result[AudioData, Exception]:
        """Stop recording and return audio data"""
        pass
    
    @abstractmethod
    async def cleanup(self) -> None:
        """Cleanup audio resources"""
        pass
    
    @abstractmethod
    def is_recording(self) -> bool:
        """Check if currently recording"""
        pass


class PyAudioProvider(AudioProvider):
    """
    PyAudio-based audio provider
    
    Provides cross-platform audio recording using PyAudio with functional
    error handling patterns matching the server architecture.
    """
    
    def __init__(self, 
                 sample_rate: int = 16000,
                 channels: int = 1,
                 chunk_size: int = 1024,
                 input_device: Optional[int] = None):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.input_device = input_device
        self.format = pyaudio.paInt16
        
        # State
        self.audio: Optional[pyaudio.PyAudio] = None
        self.stream: Optional[pyaudio.Stream] = None
        self.frames = []
        self._is_recording = False
        self._recording_start_time: Optional[float] = None
        
        self.event_bus = get_event_bus()
        
        logger.info(f"PyAudio provider initialized: {sample_rate}Hz, {channels}ch, chunk={chunk_size}")
    
    async def initialize(self) -> Result[None, Exception]:
        """Initialize PyAudio"""
        def _init():
            self.audio = pyaudio.PyAudio()
            device_count = self.audio.get_device_count()
            logger.info(f"Found {device_count} audio devices")
            
            # Validate input device if specified
            if self.input_device is not None:
                if self.input_device >= device_count:
                    raise ValueError(f"Input device {self.input_device} not found (max: {device_count-1})")
                
                device_info = self.audio.get_device_info_by_index(self.input_device)
                if device_info['maxInputChannels'] < self.channels:
                    raise ValueError(f"Device {self.input_device} doesn't support {self.channels} channels")
                
                logger.info(f"Using input device {self.input_device}: {device_info['name']}")
        
        result = from_callable(_init)
        if result.is_success():
            logger.info("PyAudio provider initialized successfully")
        else:
            logger.error(f"Failed to initialize PyAudio: {result.error}")
        
        return result.map(lambda _: None)
    
    async def start_recording(self) -> Result[None, Exception]:
        """Start audio recording"""
        if self._is_recording:
            return Failure(Exception("Already recording"))
        
        if not self.audio:
            return Failure(Exception("Audio provider not initialized"))
        
        def _start_recording():
            self.frames = []
            self._recording_start_time = time.time()
            
            self.stream = self.audio.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                input_device_index=self.input_device,
                frames_per_buffer=self.chunk_size
            )
            
            self._is_recording = True
        
        result = from_callable(_start_recording)
        
        if result.is_success():
            # Publish event
            await self.event_bus.publish(RecordingStartedEvent(
                sample_rate=self.sample_rate,
                channels=self.channels,
                device_id=self.input_device,
                source="audio_provider"
            ))
            
            logger.info("Audio recording started")
        else:
            logger.error(f"Failed to start recording: {result.error}")
        
        return result.map(lambda _: None)
    
    async def stop_recording(self) -> Result[AudioData, Exception]:
        """Stop recording and return audio data"""
        if not self._is_recording:
            return Failure(Exception("Not currently recording"))
        
        def _stop_recording() -> AudioData:
            # Stop the stream
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
                self.stream = None
            
            self._is_recording = False
            
            # Calculate duration
            duration = time.time() - (self._recording_start_time or time.time())
            
            # Convert frames to WAV data
            wav_data = self._frames_to_wav()
            
            return AudioData(
                data=wav_data,
                format="wav",
                sample_rate=self.sample_rate,
                channels=self.channels,
                duration_seconds=duration,
                metadata={
                    'recorded_at': self._recording_start_time,
                    'chunk_count': len(self.frames),
                    'device_id': self.input_device
                }
            )
        
        result = from_callable(_stop_recording)
        
        if result.is_success():
            audio_data = result.value
            
            # Publish event
            await self.event_bus.publish(RecordingStoppedEvent(
                duration_seconds=audio_data.duration_seconds,
                audio_size_bytes=len(audio_data.data),
                source="audio_provider"
            ))
            
            logger.info(f"Recording stopped: {audio_data.duration_seconds:.2f}s, {len(audio_data.data)} bytes")
        else:
            logger.error(f"Failed to stop recording: {result.error}")
        
        return result
    
    def is_recording(self) -> bool:
        """Check if currently recording"""
        return self._is_recording
    
    async def record_chunk(self) -> Result[bytes, Exception]:
        """Record a single chunk (for streaming)"""
        if not self._is_recording or not self.stream:
            return Failure(Exception("Not recording"))
        
        def _read_chunk():
            data = self.stream.read(self.chunk_size, exception_on_overflow=False)
            self.frames.append(data)
            return data
        
        return from_callable(_read_chunk)
    
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
    
    async def cleanup(self) -> None:
        """Cleanup audio resources"""
        if self._is_recording:
            await self.stop_recording()
        
        if self.stream:
            try:
                self.stream.close()
            except:
                pass
        
        if self.audio:
            try:
                self.audio.terminate()
            except:
                pass
        
        logger.info("PyAudio provider cleanup completed")


def get_audio_devices() -> Result[Dict[int, Dict[str, Any]], Exception]:
    """Get list of available audio input devices"""
    def _get_devices():
        audio = pyaudio.PyAudio()
        devices = {}
        
        try:
            device_count = audio.get_device_count()
            
            for i in range(device_count):
                try:
                    info = audio.get_device_info_by_index(i)
                    if info['maxInputChannels'] > 0:
                        devices[i] = {
                            'name': info['name'],
                            'max_input_channels': info['maxInputChannels'],
                            'default_sample_rate': info['defaultSampleRate'],
                            'host_api': info['hostApi']
                        }
                except:
                    continue
            
            return devices
        finally:
            audio.terminate()
    
    return from_callable(_get_devices)
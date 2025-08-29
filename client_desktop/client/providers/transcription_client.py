#!/usr/bin/env python3

"""
Transcription Client Provider

WebSocket client for communicating with SpeakToMe server using functional patterns.
"""

import asyncio
import json
import logging
import base64
import time
from typing import Optional, Dict, Any

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from shared.functional import Result, Success, Failure, from_async_callable
from shared.events import get_event_bus, ConnectionStatusEvent, TranscriptionReceivedEvent, TranscriptionRequestedEvent
from ..pipeline.audio_pipeline import AudioData

logger = logging.getLogger(__name__)


class TranscriptionClient:
    """
    WebSocket client for SpeakToMe server transcription
    
    Provides functional error handling and event-driven communication
    matching server architecture patterns.
    """
    
    def __init__(self, server_url: str = "ws://localhost:8000/ws/transcribe"):
        self.server_url = server_url
        self.websocket: Optional[websockets.WebSocketServerProtocol] = None
        self.connected = False
        self.connection_attempts = 0
        self.max_connection_attempts = 3
        self.reconnect_delay = 2.0
        
        self.event_bus = get_event_bus()
        
        logger.info(f"Transcription client initialized: {server_url}")
    
    async def connect(self) -> Result[None, Exception]:
        """Connect to the SpeakToMe server"""
        if self.connected and self.websocket:
            return Success(None)
        
        async def _connect():
            await self._publish_connection_status("connecting")
            
            try:
                self.websocket = await websockets.connect(
                    self.server_url,
                    max_size=10**7  # 10MB max message size for audio
                )
                
                self.connected = True
                self.connection_attempts = 0
                
                await self._publish_connection_status("connected")
                logger.info(f"Connected to SpeakToMe server: {self.server_url}")
                
            except Exception as e:
                self.connected = False
                self.connection_attempts += 1
                
                await self._publish_connection_status("error", str(e))
                logger.error(f"Failed to connect to server: {e}")
                raise e
        
        return await from_async_callable(_connect)
    
    async def disconnect(self) -> Result[None, Exception]:
        """Disconnect from the server"""
        async def _disconnect():
            if self.websocket:
                await self.websocket.close()
                self.websocket = None
            
            self.connected = False
            await self._publish_connection_status("disconnected")
            logger.info("Disconnected from SpeakToMe server")
        
        return await from_async_callable(_disconnect)
    
    async def transcribe_audio(self, audio_data: AudioData, model: str = "base", language: str = "auto") -> Result[str, Exception]:
        """Send audio for transcription and return the result"""
        if not self.connected or not self.websocket:
            # Try to reconnect
            connection_result = await self.connect()
            if connection_result.is_failure():
                return Failure(Exception(f"Not connected to server: {connection_result.error}"))
        
        async def _transcribe():
            # Publish transcription request event
            await self.event_bus.publish(TranscriptionRequestedEvent(
                audio_size=len(audio_data.data),
                model=model,
                language=language,
                source="transcription_client"
            ))
            
            # Encode audio as base64
            audio_b64 = base64.b64encode(audio_data.data).decode('utf-8')
            
            # Create request payload
            request = {
                "type": "audio",
                "data": audio_b64,
                "format": audio_data.format,
                "model": model,
                "language": language,
                "metadata": {
                    "sample_rate": audio_data.sample_rate,
                    "channels": audio_data.channels,
                    "duration": audio_data.duration_seconds,
                    "request_time": time.time()
                }
            }
            
            # Send request
            await self.websocket.send(json.dumps(request))
            logger.debug(f"Sent transcription request: {len(audio_data.data)} bytes, model={model}")
            
            # Wait for response with timeout - may need to skip connection messages
            try:
                while True:
                    response_str = await asyncio.wait_for(
                        self.websocket.recv(),
                        timeout=30.0  # 30 second timeout for transcription
                    )
                    
                    response = json.loads(response_str)
                    logger.info(f"Received WebSocket response: {response}")
                    
                    # Skip connection status messages and wait for transcription
                    if response.get("type") == "connection":
                        logger.info("Skipping connection message, waiting for transcription...")
                        continue
                    
                    # Process transcription response
                    if response.get("type") == "transcription":
                        text = response.get("text", "").strip()
                        processing_time = response.get("processing_time", 0.0)
                        detected_language = response.get("language", language)
                        confidence = response.get("confidence")
                        
                        # Publish transcription received event
                        await self.event_bus.publish(TranscriptionReceivedEvent(
                            text=text,
                        language=detected_language,
                        processing_time=processing_time,
                        confidence=confidence,
                        source="transcription_client"
                        ))
                        
                        logger.info(f"Transcription received: '{text[:50]}...' in {processing_time:.3f}s")
                        return text
                        
                    elif response.get("type") == "error":
                        error_message = response.get("message", "Unknown transcription error")
                        raise Exception(f"Server error: {error_message}")
                        
                    else:
                        raise Exception(f"Unexpected response type: {response.get('type')}")
                    
            except asyncio.TimeoutError:
                raise Exception("Transcription request timed out")
            except json.JSONDecodeError as e:
                raise Exception(f"Invalid JSON response: {e}")
            except ConnectionClosed:
                self.connected = False
                await self._publish_connection_status("disconnected")
                raise Exception("Connection lost during transcription")
        
        return await from_async_callable(_transcribe)
    
    async def test_connection(self) -> Result[Dict[str, Any], Exception]:
        """Test connection to server and get server info"""
        async def _test():
            test_request = {
                "type": "ping",
                "timestamp": time.time()
            }
            
            await self.websocket.send(json.dumps(test_request))
            
            response_str = await asyncio.wait_for(self.websocket.recv(), timeout=5.0)
            response = json.loads(response_str)
            
            return response
        
        if not self.connected:
            connection_result = await self.connect()
            if connection_result.is_failure():
                return Failure(connection_result.error)
        
        return await from_async_callable(_test)
    
    async def get_available_models(self) -> Result[list, Exception]:
        """Get list of available transcription models from server"""
        async def _get_models():
            models_request = {
                "type": "get_models"
            }
            
            await self.websocket.send(json.dumps(models_request))
            
            response_str = await asyncio.wait_for(self.websocket.recv(), timeout=10.0)
            response = json.loads(response_str)
            
            if response.get("type") == "models":
                return response.get("models", [])
            else:
                raise Exception(f"Unexpected response: {response}")
        
        if not self.connected:
            connection_result = await self.connect()
            if connection_result.is_failure():
                return Failure(connection_result.error)
        
        return await from_async_callable(_get_models)
    
    async def reconnect(self) -> Result[None, Exception]:
        """Attempt to reconnect to server with exponential backoff"""
        if self.connection_attempts >= self.max_connection_attempts:
            return Failure(Exception(f"Max connection attempts ({self.max_connection_attempts}) reached"))
        
        delay = self.reconnect_delay * (2 ** self.connection_attempts)
        
        logger.info(f"Attempting reconnection in {delay:.1f}s (attempt {self.connection_attempts + 1})")
        await asyncio.sleep(delay)
        
        return await self.connect()
    
    async def _publish_connection_status(self, status: str, error_message: Optional[str] = None):
        """Publish connection status change event"""
        await self.event_bus.publish(ConnectionStatusEvent(
            status=status,
            server_url=self.server_url,
            error_message=error_message,
            source="transcription_client"
        ))
    
    async def cleanup(self) -> None:
        """Cleanup client resources"""
        await self.disconnect()
        logger.info("Transcription client cleanup completed")
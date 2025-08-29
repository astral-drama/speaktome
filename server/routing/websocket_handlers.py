#!/usr/bin/env python3

"""
WebSocket Message Handlers

Handles different types of WebSocket messages for real-time transcription.
Provides clean separation between message routing and business logic.
"""

import asyncio
import base64
import logging
import os
import time
import uuid
from typing import Optional, Dict, Any

from ..connection import WebSocketMessage, ClientConnection, MessageHandler
from ..functional.result_monad import Result, Success, Failure
from ..providers.transcription_provider import TranscriptionResult
from ..validation import create_audio_validator

logger = logging.getLogger(__name__)

class WebSocketHandlers:
    """Collection of WebSocket message handlers for transcription service"""
    
    def __init__(self, temp_dir: str, available_models: list, max_file_size_mb: float = 50.0):
        self.temp_dir = temp_dir
        self.available_models = available_models
        self.file_validator = create_audio_validator(max_size_mb=max_file_size_mb)
        
        # Client configurations
        self._client_configs: Dict[str, Dict[str, Any]] = {}
        
        logger.info(f"WebSocket handlers initialized with models: {available_models}")
    
    async def handle_config_message(self, message: WebSocketMessage, connection: ClientConnection) -> Result[Optional[WebSocketMessage], str]:
        """Handle client configuration messages"""
        try:
            model = message.data.get("model", "base")
            language = message.data.get("language", None)
            
            # Validate model
            if model not in self.available_models:
                return Failure(f"Invalid model '{model}'. Available: {', '.join(self.available_models)}")
            
            # Store client configuration
            self._client_configs[connection.client_id] = {
                "model": model,
                "language": language,
                "configured_at": time.time()
            }
            
            logger.info(f"Client {connection.client_id} configured: model={model}, language={language}")
            
            # Send confirmation response
            response = WebSocketMessage(
                type="config",
                data={
                    "status": "configured",
                    "model": model,
                    "language": language
                }
            )
            
            return Success(response)
            
        except Exception as e:
            logger.error(f"Config message handling error: {e}")
            return Failure(f"Configuration failed: {str(e)}")
    
    async def handle_audio_message(self, message: WebSocketMessage, connection: ClientConnection) -> Result[Optional[WebSocketMessage], str]:
        """Handle audio data messages for real-time transcription"""
        try:
            audio_data = message.data.get("data")
            audio_format = message.data.get("format", "webm")
            
            if not audio_data:
                return Failure("No audio data provided")
            
            # Get client configuration
            client_config = self._client_configs.get(connection.client_id, {})
            model = client_config.get("model", "base")
            language = client_config.get("language", None)
            
            # Process audio data
            transcription_result = await self._process_streaming_audio(
                audio_data=audio_data,
                audio_format=audio_format,
                model=model,
                language=language,
                client_id=connection.client_id
            )
            
            if transcription_result.is_failure():
                return Failure(transcription_result.get_error())
            
            result = transcription_result.get_value()
            if result:
                # Send transcription response
                response = WebSocketMessage(
                    type="transcription",
                    data={
                        "status": "completed",
                        "text": result.text,
                        "language": result.language,
                        "processing_time": result.processing_time,
                        "timestamp": time.time()
                    }
                )
                
                return Success(response)
            
            # No result yet (still processing)
            return Success(None)
            
        except Exception as e:
            logger.error(f"Audio message handling error: {e}")
            return Failure(f"Audio processing failed: {str(e)}")
    
    async def handle_ping_message(self, message: WebSocketMessage, connection: ClientConnection) -> Result[Optional[WebSocketMessage], str]:
        """Handle ping messages for keep-alive"""
        try:
            response = WebSocketMessage(
                type="pong",
                data={
                    "timestamp": time.time(),
                    "client_id": connection.client_id
                }
            )
            
            return Success(response)
            
        except Exception as e:
            logger.error(f"Ping message handling error: {e}")
            return Failure(f"Ping handling failed: {str(e)}")
    
    async def handle_status_message(self, message: WebSocketMessage, connection: ClientConnection) -> Result[Optional[WebSocketMessage], str]:
        """Handle status request messages"""
        try:
            # Get client configuration
            client_config = self._client_configs.get(connection.client_id, {})
            
            # Get transcription service status
            queue_status = await transcription_service.get_queue_status()
            
            response = WebSocketMessage(
                type="status",
                data={
                    "client_config": client_config,
                    "queue_status": queue_status,
                    "timestamp": time.time()
                }
            )
            
            return Success(response)
            
        except Exception as e:
            logger.error(f"Status message handling error: {e}")
            return Failure(f"Status handling failed: {str(e)}")
    
    async def _process_streaming_audio(self, 
                                     audio_data: str, 
                                     audio_format: str,
                                     model: str = "base",
                                     language: Optional[str] = None,
                                     client_id: Optional[str] = None) -> Result[Optional[TranscriptionResult], str]:
        """Process streaming audio data for transcription"""
        try:
            # Decode base64 audio data
            try:
                audio_bytes = base64.b64decode(audio_data)
            except Exception as e:
                return Failure(f"Invalid base64 audio data: {str(e)}")
            
            # Validate audio size
            if len(audio_bytes) > 10 * 1024 * 1024:  # 10MB limit for streaming
                return Failure("Audio chunk too large for streaming")
            
            # Save to temporary file
            os.makedirs(self.temp_dir, exist_ok=True)
            temp_file = os.path.join(
                self.temp_dir,
                f"stream_{client_id}_{uuid.uuid4()}.{audio_format}"
            )
            
            try:
                with open(temp_file, "wb") as f:
                    f.write(audio_bytes)
                
                logger.debug(f"Saved streaming audio: {temp_file} ({len(audio_bytes)} bytes)")
            except Exception as e:
                return Failure(f"Failed to save audio file: {str(e)}")
            
            # Submit transcription request
            try:
                request_id = await transcription_service.submit_transcription(
                    audio_file_path=temp_file,
                    model=model,
                    language=language,
                    client_id=client_id
                )
            except Exception as e:
                # Clean up temp file on error
                try:
                    os.unlink(temp_file)
                except:
                    pass
                return Failure(f"Failed to submit transcription: {str(e)}")
            
            # Wait for result with timeout
            timeout = 30  # seconds
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                result = await transcription_service.get_result(request_id)
                if result:
                    # Clean up temp file
                    try:
                        os.unlink(temp_file)
                    except:
                        pass
                    
                    logger.info(f"Streaming transcription completed for client {client_id}: '{result.text[:50]}...'")
                    return Success(result)
                
                await asyncio.sleep(0.1)
            
            # Timeout - clean up and return error
            try:
                os.unlink(temp_file)
            except:
                pass
            
            logger.warning(f"Transcription timeout for streaming audio from {client_id}")
            return Success(None)  # Return None to indicate timeout, not failure
            
        except Exception as e:
            logger.error(f"Error processing streaming audio: {e}")
            return Failure(f"Audio processing failed: {str(e)}")
    
    def get_client_config(self, client_id: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific client"""
        return self._client_configs.get(client_id)
    
    def remove_client_config(self, client_id: str) -> None:
        """Remove client configuration when client disconnects"""
        if client_id in self._client_configs:
            del self._client_configs[client_id]
            logger.debug(f"Removed configuration for client {client_id}")
    
    def get_handler_mapping(self) -> Dict[str, MessageHandler]:
        """Get mapping of message types to handler functions"""
        return {
            "config": self.handle_config_message,
            "audio": self.handle_audio_message,
            "ping": self.handle_ping_message,
            "status": self.handle_status_message
        }

def create_websocket_handlers(temp_dir: str, 
                            available_models: list,
                            max_file_size_mb: float = 50.0) -> WebSocketHandlers:
    """Factory function to create WebSocket handlers"""
    return WebSocketHandlers(
        temp_dir=temp_dir,
        available_models=available_models,
        max_file_size_mb=max_file_size_mb
    )
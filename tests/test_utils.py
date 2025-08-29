#!/usr/bin/env python3

"""
Test Utilities

Provides utilities for creating test data, mock services, and test clients.
"""

import asyncio
import io
import json
import struct
import wave
import time
from pathlib import Path
from typing import Dict, Any, Optional, List, Union

from server.functional.result_monad import Result, Success, Failure
from server.providers import (
    TranscriptionProvider, TranscriptionRequest, TranscriptionResult, 
    TranscriptionStatus, ModelInfo, QueueStatus
)

def create_test_wav_data(duration: float = 1.0, sample_rate: int = 16000, frequency: int = 440) -> bytes:
    """Create test WAV audio data"""
    samples = int(duration * sample_rate)
    
    # Generate sine wave
    audio_data = []
    for i in range(samples):
        # Simple sine wave
        sample = int(32767 * 0.1 * (i / samples))  # Gentle fade-in to avoid harsh sound
        audio_data.append(struct.pack('<h', sample))
    
    # Create WAV file in memory
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b''.join(audio_data))
    
    return wav_buffer.getvalue()

def create_test_audio_file(temp_dir: str, filename: str, duration: float = 1.0) -> Path:
    """Create a test audio file"""
    file_path = Path(temp_dir) / filename
    
    if filename.endswith('.wav'):
        audio_data = create_test_wav_data(duration)
        file_path.write_bytes(audio_data)
    elif filename.endswith('.mp3'):
        # Create a minimal MP3 file (not valid but enough for testing)
        mp3_header = b'\xff\xfb\x10\x04'  # Basic MP3 header
        padding = b'\x00' * int(duration * 1000)  # Padding based on duration
        file_path.write_bytes(mp3_header + padding)
    else:
        # Create generic binary file
        data = b'\x00' * int(duration * 1000)
        file_path.write_bytes(data)
    
    return file_path

class MockTranscriptionProvider(TranscriptionProvider):
    """Test implementation of TranscriptionProvider"""
    
    def __init__(self):
        self._requests: Dict[str, TranscriptionRequest] = {}
        self._results: Dict[str, TranscriptionResult] = {}
        self._models = ["base", "small", "medium"]
        self._processing_delay = 0.1  # Fast processing for tests
    
    async def initialize(self) -> Result[None, str]:
        return Success(None)
    
    async def shutdown(self) -> Result[None, str]:
        return Success(None)
    
    async def submit_transcription(self, request: TranscriptionRequest) -> Result[str, str]:
        try:
            self._requests[request.id] = request
            
            # Simulate processing
            asyncio.create_task(self._process_request(request))
            
            return Success(request.id)
        except Exception as e:
            return Failure(f"Submit failed: {str(e)}")
    
    async def _process_request(self, request: TranscriptionRequest) -> None:
        """Simulate transcription processing"""
        try:
            await asyncio.sleep(self._processing_delay)
            
            # Create mock transcription result
            text = f"This is a test transcription for {Path(request.audio_file_path).name}"
            
            result = TranscriptionResult(
                id=request.id,
                status=TranscriptionStatus.COMPLETED,
                text=text,
                language=request.language or "en",
                confidence=0.95,
                processing_time=self._processing_delay,
                model_used=request.model,
                completed_at=time.time()
            )
            
            self._results[request.id] = result
            
        except Exception as e:
            # Create failure result
            result = TranscriptionResult(
                id=request.id,
                status=TranscriptionStatus.FAILED,
                error=str(e),
                completed_at=time.time()
            )
            self._results[request.id] = result
    
    async def get_result(self, request_id: str) -> Result[Optional[TranscriptionResult], str]:
        try:
            result = self._results.get(request_id)
            return Success(result)
        except Exception as e:
            return Failure(f"Get result failed: {str(e)}")
    
    async def get_status(self, request_id: str) -> Result[Optional[TranscriptionStatus], str]:
        try:
            if request_id in self._results:
                return Success(self._results[request_id].status)
            elif request_id in self._requests:
                return Success(TranscriptionStatus.PROCESSING)
            else:
                return Success(None)
        except Exception as e:
            return Failure(f"Get status failed: {str(e)}")
    
    async def cancel_request(self, request_id: str) -> Result[bool, str]:
        try:
            if request_id in self._requests:
                # Remove from processing
                del self._requests[request_id]
                
                # Add cancelled result
                result = TranscriptionResult(
                    id=request_id,
                    status=TranscriptionStatus.CANCELLED,
                    completed_at=time.time()
                )
                self._results[request_id] = result
                
                return Success(True)
            return Success(False)
        except Exception as e:
            return Failure(f"Cancel failed: {str(e)}")
    
    async def get_queue_status(self) -> Result[QueueStatus, str]:
        try:
            processing = len([r for r in self._requests.values()])
            completed = len([r for r in self._results.values() if r.status == TranscriptionStatus.COMPLETED])
            failed = len([r for r in self._results.values() if r.status == TranscriptionStatus.FAILED])
            
            avg_time = 0.0
            completed_results = [r for r in self._results.values() if r.processing_time is not None]
            if completed_results:
                avg_time = sum(r.processing_time for r in completed_results) / len(completed_results)
            
            queue_status = QueueStatus(
                pending_requests=0,
                processing_requests=processing,
                completed_requests=completed,
                failed_requests=failed,
                average_processing_time=avg_time,
                estimated_wait_time=self._processing_delay,
                active_workers=1
            )
            
            return Success(queue_status)
        except Exception as e:
            return Failure(f"Queue status failed: {str(e)}")
    
    async def get_available_models(self) -> Result[List[ModelInfo], str]:
        try:
            models = [
                ModelInfo(name="base", size_mb=74, description="Test base model"),
                ModelInfo(name="small", size_mb=244, description="Test small model"),
                ModelInfo(name="medium", size_mb=769, description="Test medium model")
            ]
            return Success(models)
        except Exception as e:
            return Failure(f"Get models failed: {str(e)}")
    
    async def load_model(self, model_name: str) -> Result[None, str]:
        if model_name in self._models:
            return Success(None)
        return Failure(f"Model not found: {model_name}")
    
    async def unload_model(self, model_name: str) -> Result[None, str]:
        return Success(None)
    
    async def health_check(self) -> Result[Dict[str, Any], str]:
        return Success({
            "status": "healthy",
            "models_loaded": self._models,
            "requests_processed": len(self._results),
            "timestamp": time.time()
        })
    
    # Test utilities
    def set_processing_delay(self, delay: float) -> None:
        """Set processing delay for testing"""
        self._processing_delay = delay
    
    def get_request_count(self) -> int:
        """Get number of requests submitted"""
        return len(self._requests)
    
    def get_result_count(self) -> int:
        """Get number of results generated"""
        return len(self._results)
    
    def clear_requests(self) -> None:
        """Clear all requests and results"""
        self._requests.clear()
        self._results.clear()

class MockWebSocketClient:
    """Test WebSocket client for integration testing"""
    
    def __init__(self):
        self.connected = False
        self.messages_sent = []
        self.messages_received = []
        self.connection_events = []
    
    async def connect(self, url: str) -> Result[None, str]:
        """Simulate WebSocket connection"""
        try:
            await asyncio.sleep(0.01)  # Simulate connection time
            self.connected = True
            self.connection_events.append(("connected", time.time()))
            return Success(None)
        except Exception as e:
            return Failure(f"Connection failed: {str(e)}")
    
    async def disconnect(self) -> Result[None, str]:
        """Simulate WebSocket disconnection"""
        try:
            self.connected = False
            self.connection_events.append(("disconnected", time.time()))
            return Success(None)
        except Exception as e:
            return Failure(f"Disconnection failed: {str(e)}")
    
    async def send_message(self, message: Dict[str, Any]) -> Result[None, str]:
        """Simulate sending WebSocket message"""
        try:
            if not self.connected:
                return Failure("Not connected")
            
            self.messages_sent.append({
                "message": message,
                "timestamp": time.time()
            })
            
            # Simulate response for certain message types
            await self._simulate_response(message)
            
            return Success(None)
        except Exception as e:
            return Failure(f"Send failed: {str(e)}")
    
    async def _simulate_response(self, message: Dict[str, Any]) -> None:
        """Simulate server responses"""
        msg_type = message.get("type")
        
        if msg_type == "config":
            response = {
                "type": "config",
                "status": "configured",
                "model": message.get("model", "base"),
                "language": message.get("language")
            }
            self.messages_received.append({
                "message": response,
                "timestamp": time.time()
            })
        
        elif msg_type == "audio":
            # Simulate transcription response
            await asyncio.sleep(0.1)  # Processing delay
            response = {
                "type": "transcription",
                "status": "completed",
                "text": "Test transcription result",
                "language": "en",
                "processing_time": 0.1,
                "timestamp": time.time()
            }
            self.messages_received.append({
                "message": response,
                "timestamp": time.time()
            })
        
        elif msg_type == "ping":
            response = {
                "type": "pong",
                "timestamp": time.time()
            }
            self.messages_received.append({
                "message": response,
                "timestamp": time.time()
            })
    
    def get_last_message_received(self) -> Optional[Dict[str, Any]]:
        """Get the last received message"""
        return self.messages_received[-1]["message"] if self.messages_received else None
    
    def get_messages_by_type(self, msg_type: str) -> List[Dict[str, Any]]:
        """Get all received messages of a specific type"""
        return [
            msg["message"] for msg in self.messages_received
            if msg["message"].get("type") == msg_type
        ]
    
    def clear_history(self) -> None:
        """Clear message history"""
        self.messages_sent.clear()
        self.messages_received.clear()
        self.connection_events.clear()

class MockFileUploader:
    """Test file uploader for HTTP endpoint testing"""
    
    def __init__(self):
        self.upload_history = []
        self.response_delay = 0.05
    
    async def upload_file(self, 
                         file_path: str, 
                         endpoint: str = "/api/transcribe",
                         model: str = "base",
                         language: Optional[str] = None) -> Result[Dict[str, Any], str]:
        """Simulate file upload"""
        try:
            await asyncio.sleep(self.response_delay)
            
            file_size = Path(file_path).stat().st_size if Path(file_path).exists() else 0
            
            upload_record = {
                "file_path": file_path,
                "endpoint": endpoint,
                "model": model,
                "language": language,
                "file_size": file_size,
                "timestamp": time.time()
            }
            
            self.upload_history.append(upload_record)
            
            # Simulate successful upload response
            response = {
                "id": f"test_request_{len(self.upload_history)}",
                "status": "pending"
            }
            
            return Success(response)
            
        except Exception as e:
            return Failure(f"Upload failed: {str(e)}")
    
    async def get_result(self, request_id: str) -> Result[Dict[str, Any], str]:
        """Simulate getting transcription result"""
        try:
            await asyncio.sleep(self.response_delay)
            
            # Simulate completed result
            response = {
                "id": request_id,
                "status": "completed",
                "text": f"Test transcription for {request_id}",
                "language": "en",
                "processing_time": 0.1
            }
            
            return Success(response)
            
        except Exception as e:
            return Failure(f"Get result failed: {str(e)}")
    
    def set_response_delay(self, delay: float) -> None:
        """Set response delay for testing"""
        self.response_delay = delay
    
    def get_upload_count(self) -> int:
        """Get number of uploads performed"""
        return len(self.upload_history)
    
    def clear_history(self) -> None:
        """Clear upload history"""
        self.upload_history.clear()

def create_mock_fastapi_upload_file(file_path: str, content_type: str = "audio/wav"):
    """Create a mock FastAPI UploadFile for testing"""
    class MockUploadFile:
        def __init__(self, file_path: str, content_type: str):
            self.filename = Path(file_path).name
            self.content_type = content_type
            self.size = Path(file_path).stat().st_size if Path(file_path).exists() else 0
            self._file_path = file_path
        
        async def read(self) -> bytes:
            if Path(self._file_path).exists():
                return Path(self._file_path).read_bytes()
            return b"mock file data"
    
    return MockUploadFile(file_path, content_type)

async def wait_for_condition(condition_func, timeout: float = 5.0, interval: float = 0.1) -> bool:
    """Wait for a condition to become true"""
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        if await condition_func() if asyncio.iscoroutinefunction(condition_func) else condition_func():
            return True
        await asyncio.sleep(interval)
    
    return False

def assert_result_success(result: Result, message: str = "Expected successful result"):
    """Assert that a Result is successful"""
    assert result.is_success(), f"{message}: {result.get_error() if result.is_failure() else 'Unknown error'}"

def assert_result_failure(result: Result, expected_error: str = None):
    """Assert that a Result is a failure"""
    assert result.is_failure(), "Expected failure result but got success"
    if expected_error:
        assert expected_error in result.get_error(), f"Expected error containing '{expected_error}', got '{result.get_error()}'"
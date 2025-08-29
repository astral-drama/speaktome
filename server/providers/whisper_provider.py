#!/usr/bin/env python3

"""
SpeakToMe Transcription Provider Implementation

Real implementation of transcription provider using OpenAI Whisper models.
Provides both batch and streaming transcription capabilities.
"""

import asyncio
import logging
import time
import uuid
import os
import tempfile
from typing import Dict, List, Optional, Any, AsyncGenerator
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from .transcription_provider import (
    TranscriptionProvider,
    StreamingTranscriptionProvider, 
    TranscriptionRequest,
    TranscriptionResult,
    TranscriptionStatus,
    ModelInfo,
    QueueStatus
)
from ..functional.result_monad import Result, Success, Failure
from whisper_transcriber import WhisperTranscriber

logger = logging.getLogger(__name__)

class WhisperTranscriptionProvider(StreamingTranscriptionProvider):
    """Real Whisper transcription provider implementation"""
    
    def __init__(self, default_model: str = "base", max_workers: int = 2):
        self.default_model = default_model
        self.max_workers = max_workers
        
        # Internal state
        self._transcribers: Dict[str, WhisperTranscriber] = {}
        self._requests: Dict[str, TranscriptionRequest] = {}
        self._results: Dict[str, TranscriptionResult] = {}
        self._streaming_sessions: Dict[str, Dict[str, Any]] = {}
        self._executor: Optional[ThreadPoolExecutor] = None
        self._initialized = False
        
        # Stats
        self._total_requests = 0
        self._completed_requests = 0
        self._failed_requests = 0
        self._processing_times: List[float] = []
        
    async def initialize(self) -> Result[None, str]:
        """Initialize the transcription provider"""
        try:
            if self._initialized:
                return Success(None)
                
            logger.info(f"Initializing Whisper transcription provider with {self.max_workers} workers")
            
            # Create thread pool for CPU-intensive transcription work
            self._executor = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="whisper-")
            
            # Pre-load default model
            result = await self.load_model(self.default_model)
            if result.is_failure():
                return result
                
            self._initialized = True
            logger.info("Whisper transcription provider initialized successfully")
            return Success(None)
            
        except Exception as e:
            logger.error(f"Failed to initialize Whisper provider: {e}")
            return Failure(f"Initialization failed: {str(e)}")
    
    async def shutdown(self) -> Result[None, str]:
        """Shutdown the transcription provider and cleanup resources"""
        try:
            logger.info("Shutting down Whisper transcription provider")
            
            # Cancel all streaming sessions
            for session_id in list(self._streaming_sessions.keys()):
                await self.end_streaming_transcription(session_id)
            
            # Cleanup transcribers
            for model_name, transcriber in self._transcribers.items():
                try:
                    transcriber.cleanup()
                    logger.info(f"Cleaned up transcriber for model: {model_name}")
                except Exception as e:
                    logger.error(f"Error cleaning up transcriber {model_name}: {e}")
            
            self._transcribers.clear()
            
            # Shutdown thread pool
            if self._executor:
                self._executor.shutdown(wait=True, cancel_futures=True)
                self._executor = None
            
            self._initialized = False
            logger.info("Whisper transcription provider shutdown complete")
            return Success(None)
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
            return Failure(f"Shutdown failed: {str(e)}")
    
    async def submit_transcription(self, request: TranscriptionRequest) -> Result[str, str]:
        """Submit a transcription request and return request ID"""
        try:
            if not self._initialized:
                return Failure("Provider not initialized")
            
            # Validate request
            if not Path(request.audio_file_path).exists():
                return Failure(f"Audio file not found: {request.audio_file_path}")
            
            # Store request
            self._requests[request.id] = request
            self._total_requests += 1
            
            # Create initial result
            result = TranscriptionResult(
                id=request.id,
                status=TranscriptionStatus.PENDING
            )
            self._results[request.id] = result
            
            # Submit to thread pool
            future = self._executor.submit(self._process_transcription, request)
            
            logger.info(f"Submitted transcription request {request.id} for file {request.audio_file_path}")
            return Success(request.id)
            
        except Exception as e:
            logger.error(f"Failed to submit transcription request: {e}")
            return Failure(f"Submit failed: {str(e)}")
    
    def _process_transcription(self, request: TranscriptionRequest) -> None:
        """Process transcription in thread pool (synchronous)"""
        try:
            # Update status to processing
            self._results[request.id] = TranscriptionResult(
                id=request.id,
                status=TranscriptionStatus.PROCESSING
            )
            
            start_time = time.time()
            
            # Get or create transcriber for this model
            transcriber = self._transcribers.get(request.model)
            if not transcriber:
                logger.info(f"Loading model {request.model} for transcription")
                transcriber = WhisperTranscriber(
                    model_size=request.model,
                    language=request.language
                )
                self._transcribers[request.model] = transcriber
            
            # Perform transcription
            logger.info(f"Processing transcription {request.id} with model {request.model}")
            result = transcriber.transcribe_file(request.audio_file_path)
            
            processing_time = time.time() - start_time
            self._processing_times.append(processing_time)
            
            if result:
                # Success
                transcription_result = TranscriptionResult(
                    id=request.id,
                    status=TranscriptionStatus.COMPLETED,
                    text=result['text'],
                    language=result['language'], 
                    processing_time=processing_time,
                    model_used=request.model,
                    segments=result.get('segments'),
                    completed_at=time.time(),
                    metadata={'audio_file': result['audio_file']}
                )
                self._results[request.id] = transcription_result
                self._completed_requests += 1
                
                logger.info(f"Transcription {request.id} completed successfully in {processing_time:.2f}s")
                logger.info(f"Result: '{result['text']}'")
                
            else:
                # Failure
                self._results[request.id] = TranscriptionResult(
                    id=request.id,
                    status=TranscriptionStatus.FAILED,
                    error="Transcription failed - no result returned",
                    completed_at=time.time()
                )
                self._failed_requests += 1
                logger.error(f"Transcription {request.id} failed")
                
        except Exception as e:
            # Handle errors
            logger.error(f"Error processing transcription {request.id}: {e}")
            self._results[request.id] = TranscriptionResult(
                id=request.id,
                status=TranscriptionStatus.FAILED,
                error=str(e),
                completed_at=time.time()
            )
            self._failed_requests += 1
    
    async def get_result(self, request_id: str) -> Result[Optional[TranscriptionResult], str]:
        """Get transcription result by request ID"""
        try:
            result = self._results.get(request_id)
            return Success(result)
        except Exception as e:
            logger.error(f"Error getting result for {request_id}: {e}")
            return Failure(f"Get result failed: {str(e)}")
    
    async def get_status(self, request_id: str) -> Result[Optional[TranscriptionStatus], str]:
        """Get transcription status by request ID"""
        try:
            result = self._results.get(request_id)
            status = result.status if result else None
            return Success(status)
        except Exception as e:
            logger.error(f"Error getting status for {request_id}: {e}")
            return Failure(f"Get status failed: {str(e)}")
    
    async def cancel_request(self, request_id: str) -> Result[bool, str]:
        """Cancel a transcription request"""
        try:
            result = self._results.get(request_id)
            if not result:
                return Failure(f"Request {request_id} not found")
            
            if result.status in [TranscriptionStatus.COMPLETED, TranscriptionStatus.FAILED, TranscriptionStatus.CANCELLED]:
                return Success(False)  # Already finished
            
            # Mark as cancelled
            self._results[request_id] = TranscriptionResult(
                id=request_id,
                status=TranscriptionStatus.CANCELLED,
                completed_at=time.time()
            )
            
            logger.info(f"Cancelled transcription request {request_id}")
            return Success(True)
            
        except Exception as e:
            logger.error(f"Error cancelling request {request_id}: {e}")
            return Failure(f"Cancel failed: {str(e)}")
    
    async def get_queue_status(self) -> Result[QueueStatus, str]:
        """Get current queue status"""
        try:
            pending = sum(1 for r in self._results.values() if r.status == TranscriptionStatus.PENDING)
            processing = sum(1 for r in self._results.values() if r.status == TranscriptionStatus.PROCESSING)
            
            avg_processing_time = sum(self._processing_times) / len(self._processing_times) if self._processing_times else 0.0
            estimated_wait = avg_processing_time * pending
            
            status = QueueStatus(
                pending_requests=pending,
                processing_requests=processing,
                completed_requests=self._completed_requests,
                failed_requests=self._failed_requests,
                average_processing_time=avg_processing_time,
                estimated_wait_time=estimated_wait,
                active_workers=self.max_workers
            )
            
            return Success(status)
            
        except Exception as e:
            logger.error(f"Error getting queue status: {e}")
            return Failure(f"Get queue status failed: {str(e)}")
    
    async def get_available_models(self) -> Result[List[ModelInfo], str]:
        """Get list of available models"""
        try:
            models = [
                ModelInfo(
                    name="tiny",
                    size_mb=39,
                    description="Fastest model, least accurate",
                    accuracy_level="low",
                    speed_level="very_fast",
                    loaded="tiny" in self._transcribers
                ),
                ModelInfo(
                    name="base", 
                    size_mb=74,
                    description="Balanced speed and accuracy",
                    accuracy_level="medium",
                    speed_level="fast",
                    loaded="base" in self._transcribers
                ),
                ModelInfo(
                    name="small",
                    size_mb=244,
                    description="Better accuracy, slower",
                    accuracy_level="good",
                    speed_level="medium",
                    loaded="small" in self._transcribers
                ),
                ModelInfo(
                    name="medium",
                    size_mb=769,
                    description="High accuracy, slower processing",
                    accuracy_level="high",
                    speed_level="slow",
                    loaded="medium" in self._transcribers
                ),
                ModelInfo(
                    name="large",
                    size_mb=1550,
                    description="Best accuracy, slowest processing",
                    accuracy_level="very_high", 
                    speed_level="very_slow",
                    loaded="large" in self._transcribers
                )
            ]
            
            return Success(models)
            
        except Exception as e:
            logger.error(f"Error getting available models: {e}")
            return Failure(f"Get models failed: {str(e)}")
    
    async def load_model(self, model_name: str) -> Result[None, str]:
        """Load a specific model"""
        try:
            if model_name in self._transcribers:
                logger.info(f"Model {model_name} already loaded")
                return Success(None)
            
            logger.info(f"Loading Whisper model: {model_name}")
            
            # Load model in thread pool to avoid blocking
            def _load_model():
                return WhisperTranscriber(model_size=model_name)
            
            loop = asyncio.get_event_loop()
            transcriber = await loop.run_in_executor(self._executor, _load_model)
            
            self._transcribers[model_name] = transcriber
            logger.info(f"Successfully loaded model: {model_name}")
            return Success(None)
            
        except Exception as e:
            logger.error(f"Failed to load model {model_name}: {e}")
            return Failure(f"Model loading failed: {str(e)}")
    
    async def unload_model(self, model_name: str) -> Result[None, str]:
        """Unload a specific model to free resources"""
        try:
            transcriber = self._transcribers.get(model_name)
            if not transcriber:
                return Failure(f"Model {model_name} not loaded")
            
            # Don't unload if it's the default model and we have active requests
            if model_name == self.default_model:
                active_requests = sum(1 for r in self._results.values() 
                                    if r.status in [TranscriptionStatus.PENDING, TranscriptionStatus.PROCESSING])
                if active_requests > 0:
                    return Failure(f"Cannot unload default model {model_name} while requests are active")
            
            transcriber.cleanup()
            del self._transcribers[model_name]
            
            logger.info(f"Unloaded model: {model_name}")
            return Success(None)
            
        except Exception as e:
            logger.error(f"Failed to unload model {model_name}: {e}")
            return Failure(f"Model unloading failed: {str(e)}")
    
    async def health_check(self) -> Result[Dict[str, Any], str]:
        """Perform health check and return status"""
        try:
            queue_status_result = await self.get_queue_status()
            if queue_status_result.is_failure():
                return queue_status_result
            
            queue_status = queue_status_result.get_value()
            
            health_data = {
                "status": "healthy" if self._initialized else "not_initialized",
                "initialized": self._initialized,
                "loaded_models": list(self._transcribers.keys()),
                "total_requests": self._total_requests,
                "completed_requests": self._completed_requests, 
                "failed_requests": self._failed_requests,
                "pending_requests": queue_status.pending_requests,
                "processing_requests": queue_status.processing_requests,
                "average_processing_time": queue_status.average_processing_time,
                "active_workers": self.max_workers,
                "executor_active": self._executor is not None and not self._executor._shutdown
            }
            
            return Success(health_data)
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return Failure(f"Health check failed: {str(e)}")
    
    # Streaming transcription methods (simplified implementation for now)
    async def start_streaming_transcription(self, 
                                          client_id: str,
                                          model: str,
                                          language: Optional[str] = None) -> Result[str, str]:
        """Start a streaming transcription session"""
        try:
            session_id = str(uuid.uuid4())
            
            # Create temporary directory for audio chunks
            temp_dir = tempfile.mkdtemp(prefix=f"whisper_stream_{session_id}_")
            
            self._streaming_sessions[session_id] = {
                'client_id': client_id,
                'model': model,
                'language': language,
                'temp_dir': temp_dir,
                'chunks': [],
                'created_at': time.time(),
                'last_activity': time.time()
            }
            
            logger.info(f"Started streaming session {session_id} for client {client_id}")
            return Success(session_id)
            
        except Exception as e:
            logger.error(f"Failed to start streaming session: {e}")
            return Failure(f"Start streaming failed: {str(e)}")
    
    async def send_audio_chunk(self, 
                              session_id: str,
                              audio_data: bytes,
                              is_final: bool = False) -> Result[None, str]:
        """Send audio chunk to streaming session"""
        try:
            session = self._streaming_sessions.get(session_id)
            if not session:
                return Failure(f"Streaming session {session_id} not found")
            
            # Save audio chunk to temporary file
            chunk_file = Path(session['temp_dir']) / f"chunk_{len(session['chunks'])}.wav"
            chunk_file.write_bytes(audio_data)
            session['chunks'].append(str(chunk_file))
            session['last_activity'] = time.time()
            
            logger.debug(f"Received audio chunk for session {session_id}, total chunks: {len(session['chunks'])}")
            
            if is_final:
                # Process all chunks at once for now (simplified streaming)
                await self._process_streaming_chunks(session_id)
            
            return Success(None)
            
        except Exception as e:
            logger.error(f"Failed to send audio chunk: {e}")
            return Failure(f"Send audio chunk failed: {str(e)}")
    
    async def get_streaming_results(self, session_id: str) -> AsyncGenerator[TranscriptionResult, None]:
        """Get streaming transcription results as they become available"""
        # Simplified implementation - just return final result when available
        session = self._streaming_sessions.get(session_id)
        if not session:
            return
        
        # Wait for processing to complete and yield results
        while session_id in self._streaming_sessions:
            if 'final_result' in session:
                yield session['final_result']
                break
            await asyncio.sleep(0.1)
    
    async def end_streaming_transcription(self, session_id: str) -> Result[TranscriptionResult, str]:
        """End streaming transcription and get final result"""
        try:
            session = self._streaming_sessions.get(session_id)
            if not session:
                return Failure(f"Streaming session {session_id} not found")
            
            # Process any remaining chunks
            if session['chunks'] and 'final_result' not in session:
                await self._process_streaming_chunks(session_id)
            
            # Get final result
            final_result = session.get('final_result')
            if not final_result:
                final_result = TranscriptionResult(
                    id=session_id,
                    status=TranscriptionStatus.COMPLETED,
                    text="",
                    language=session['language'],
                    processing_time=0.0
                )
            
            # Cleanup
            await self._cleanup_streaming_session(session_id)
            
            return Success(final_result)
            
        except Exception as e:
            logger.error(f"Failed to end streaming session: {e}")
            return Failure(f"End streaming failed: {str(e)}")
    
    async def _process_streaming_chunks(self, session_id: str) -> None:
        """Process accumulated audio chunks for streaming session"""
        session = self._streaming_sessions.get(session_id)
        if not session or not session['chunks']:
            return
        
        try:
            # For now, just process the last chunk (simplified streaming)
            last_chunk = session['chunks'][-1]
            
            # Create transcription request
            request = TranscriptionRequest(
                id=f"stream_{session_id}",
                audio_file_path=last_chunk,
                model=session['model'],
                language=session['language'],
                client_id=session['client_id'],
                created_at=time.time()
            )
            
            # Process in thread pool
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(self._executor, self._process_transcription, request)
            
            # Get result and store in session
            result = self._results.get(f"stream_{session_id}")
            if result:
                session['final_result'] = result
                
        except Exception as e:
            logger.error(f"Error processing streaming chunks for {session_id}: {e}")
    
    async def _cleanup_streaming_session(self, session_id: str) -> None:
        """Cleanup streaming session resources"""
        session = self._streaming_sessions.pop(session_id, None)
        if session:
            # Remove temporary files
            temp_dir = Path(session['temp_dir'])
            if temp_dir.exists():
                for chunk_file in temp_dir.glob("*"):
                    try:
                        chunk_file.unlink()
                    except Exception as e:
                        logger.warning(f"Failed to remove chunk file {chunk_file}: {e}")
                try:
                    temp_dir.rmdir()
                except Exception as e:
                    logger.warning(f"Failed to remove temp directory {temp_dir}: {e}")
            
            logger.debug(f"Cleaned up streaming session {session_id}")
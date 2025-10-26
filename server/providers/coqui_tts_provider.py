#!/usr/bin/env python3

"""
Coqui TTS Provider Implementation

GPU-accelerated neural TTS using Coqui TTS library.
Provides high-quality speech synthesis on NVIDIA GPUs.
"""

import asyncio
import logging
import time
import tempfile
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any
from concurrent.futures import ThreadPoolExecutor

from .tts_provider import (
    TTSProvider, SynthesisRequest, SynthesisResult, SynthesisStatus,
    VoiceInfo, TTSQueueStatus
)
from ..functional.result_monad import Result, Success, Failure

logger = logging.getLogger(__name__)

class CoquiTTSProvider(TTSProvider):
    """Coqui TTS provider with GPU acceleration"""

    def __init__(
        self,
        default_voice: str = "tts_models/en/ljspeech/vits",
        device: str = "cuda",
        max_workers: int = 2
    ):
        """
        Initialize Coqui TTS provider

        Args:
            default_voice: Default TTS model/voice to use
            device: Device to run on ('cuda' for GPU, 'cpu' for CPU)
            max_workers: Maximum concurrent synthesis tasks
        """
        self.default_voice = default_voice
        self.device = device
        self.max_workers = max_workers

        self.tts = None
        self.executor = None
        self.is_initialized = False

        # Request tracking
        self.active_requests: Dict[str, Dict[str, Any]] = {}
        self.completed_requests: Dict[str, SynthesisResult] = {}

        # Statistics
        self.total_completed = 0
        self.total_failed = 0
        self.processing_times: List[float] = []

    async def initialize(self) -> Result[None, str]:
        """Initialize Coqui TTS with GPU support"""
        try:
            logger.info(f"🎤 Initializing Coqui TTS provider on {self.device}")

            # Import TTS library
            try:
                from TTS.api import TTS
            except ImportError as e:
                logger.error(f"Failed to import TTS library: {e}")
                return Failure(
                    "TTS library not installed. Install with: pip install TTS"
                )

            # Check CUDA availability
            if self.device == "cuda":
                try:
                    import torch
                    if not torch.cuda.is_available():
                        logger.warning("CUDA not available, falling back to CPU")
                        self.device = "cpu"
                    else:
                        logger.info(f"✅ CUDA available: {torch.cuda.get_device_name(0)}")
                except Exception as e:
                    logger.warning(f"Could not check CUDA: {e}, using CPU")
                    self.device = "cpu"

            # Initialize TTS model
            logger.info(f"Loading TTS model: {self.default_voice}")
            self.tts = TTS(self.default_voice).to(self.device)
            logger.info(f"✅ TTS model loaded on {self.device}")

            # Create thread pool executor for async operations
            self.executor = ThreadPoolExecutor(max_workers=self.max_workers)

            self.is_initialized = True
            logger.info("✅ Coqui TTS provider initialized successfully")

            return Success(None)

        except Exception as e:
            logger.error(f"❌ Failed to initialize Coqui TTS provider: {e}")
            return Failure(f"Initialization failed: {str(e)}")

    async def shutdown(self) -> Result[None, str]:
        """Shutdown TTS provider and cleanup"""
        try:
            logger.info("🛑 Shutting down Coqui TTS provider")

            if self.executor:
                self.executor.shutdown(wait=True)
                logger.info("✅ Thread pool executor shut down")

            self.tts = None
            self.is_initialized = False

            logger.info("✅ Coqui TTS provider shutdown complete")
            return Success(None)

        except Exception as e:
            logger.error(f"❌ Error during shutdown: {e}")
            return Failure(f"Shutdown failed: {str(e)}")

    async def submit_synthesis(self, request: SynthesisRequest) -> Result[str, str]:
        """Submit a synthesis request"""
        try:
            if not self.is_initialized:
                return Failure("TTS provider not initialized")

            # Validate request
            if not request.text or not request.text.strip():
                return Failure("Text cannot be empty")

            if len(request.text) > 5000:
                return Failure("Text too long (max 5000 characters)")

            # Store request
            self.active_requests[request.id] = {
                'request': request,
                'status': SynthesisStatus.PENDING,
                'start_time': time.time()
            }

            # Process asynchronously
            asyncio.create_task(self._process_synthesis(request))

            logger.info(f"✅ Synthesis request {request.id} submitted")
            return Success(request.id)

        except Exception as e:
            logger.error(f"❌ Failed to submit synthesis request: {e}")
            return Failure(f"Submission failed: {str(e)}")

    async def _process_synthesis(self, request: SynthesisRequest):
        """Process synthesis request asynchronously"""
        try:
            # Update status to processing
            self.active_requests[request.id]['status'] = SynthesisStatus.PROCESSING
            start_time = self.active_requests[request.id]['start_time']

            logger.info(f"🎵 Processing synthesis for request {request.id}")

            # Run synthesis in thread pool (TTS is blocking)
            loop = asyncio.get_event_loop()
            audio_data, sample_rate = await loop.run_in_executor(
                self.executor,
                self._synthesize_speech,
                request.text,
                request.voice or self.default_voice
            )

            if audio_data is None:
                raise Exception("Synthesis failed to produce audio")

            # Calculate processing time
            processing_time = time.time() - start_time
            self.processing_times.append(processing_time)

            # Create result
            result = SynthesisResult(
                id=request.id,
                status=SynthesisStatus.COMPLETED,
                audio_data=audio_data,
                audio_format=request.output_format,
                sample_rate=sample_rate,
                processing_time=processing_time,
                voice_used=request.voice or self.default_voice,
                completed_at=time.time()
            )

            # Store result
            self.completed_requests[request.id] = result
            del self.active_requests[request.id]

            self.total_completed += 1
            logger.info(
                f"✅ Synthesis completed for {request.id} "
                f"({processing_time:.2f}s, {len(audio_data)} bytes)"
            )

        except Exception as e:
            logger.error(f"❌ Synthesis failed for {request.id}: {e}")

            # Create error result
            result = SynthesisResult(
                id=request.id,
                status=SynthesisStatus.FAILED,
                error=str(e),
                completed_at=time.time()
            )

            self.completed_requests[request.id] = result
            if request.id in self.active_requests:
                del self.active_requests[request.id]

            self.total_failed += 1

    def _preprocess_text(self, text: str) -> str:
        """
        Preprocess text for better TTS quality

        Handles:
        - Contraction expansion (optional - some models handle them well)
        - Number normalization
        - Special character cleanup
        """
        import re

        # Common contractions that often cause issues
        contractions = {
            "won't": "will not",
            "can't": "cannot",
            "n't": " not",  # General 'nt' pattern
            "'re": " are",
            "'ve": " have",
            "'ll": " will",
            "'d": " would",
            "'m": " am",
            "let's": "let us",
        }

        processed = text

        # Only expand contractions if using older models like Tacotron
        # VITS and XTTS handle contractions well
        if 'tacotron' in self.default_voice.lower():
            for contraction, expansion in contractions.items():
                processed = re.sub(
                    rf"\b(\w+){re.escape(contraction)}\b",
                    rf"\1{expansion}",
                    processed,
                    flags=re.IGNORECASE
                )

        # Normalize whitespace
        processed = ' '.join(processed.split())

        # Ensure sentences end with punctuation for better prosody
        if processed and processed[-1] not in '.!?':
            processed += '.'

        return processed

    def _synthesize_speech(self, text: str, voice: str) -> tuple[bytes, int]:
        """
        Synthesize speech from text (blocking operation)

        Returns:
            Tuple of (audio_data_bytes, sample_rate)
        """
        try:
            # Preprocess text for better quality
            processed_text = self._preprocess_text(text)

            # Create temporary file for output
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
                output_path = tmp_file.name

            # Generate speech
            logger.debug(f"Synthesizing: '{processed_text[:50]}...'")
            self.tts.tts_to_file(text=processed_text, file_path=output_path)

            # Read audio data
            with open(output_path, 'rb') as f:
                audio_data = f.read()

            # Clean up temp file
            Path(output_path).unlink(missing_ok=True)

            # Get sample rate from TTS config
            sample_rate = getattr(self.tts, 'sample_rate', 22050)

            logger.debug(f"Generated {len(audio_data)} bytes of audio at {sample_rate}Hz")
            return audio_data, sample_rate

        except Exception as e:
            logger.error(f"Speech synthesis error: {e}")
            raise

    async def get_result(self, request_id: str) -> Result[Optional[SynthesisResult], str]:
        """Get synthesis result by request ID"""
        try:
            if request_id in self.completed_requests:
                return Success(self.completed_requests[request_id])

            if request_id in self.active_requests:
                # Still processing
                return Success(None)

            return Failure(f"Request {request_id} not found")

        except Exception as e:
            logger.error(f"Error getting result: {e}")
            return Failure(f"Failed to get result: {str(e)}")

    async def get_status(self, request_id: str) -> Result[Optional[SynthesisStatus], str]:
        """Get synthesis status by request ID"""
        try:
            if request_id in self.completed_requests:
                return Success(self.completed_requests[request_id].status)

            if request_id in self.active_requests:
                return Success(self.active_requests[request_id]['status'])

            return Failure(f"Request {request_id} not found")

        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return Failure(f"Failed to get status: {str(e)}")

    async def cancel_request(self, request_id: str) -> Result[bool, str]:
        """Cancel a synthesis request"""
        try:
            if request_id in self.active_requests:
                del self.active_requests[request_id]
                logger.info(f"Cancelled synthesis request {request_id}")
                return Success(True)

            return Success(False)

        except Exception as e:
            logger.error(f"Error cancelling request: {e}")
            return Failure(f"Failed to cancel: {str(e)}")

    async def get_queue_status(self) -> Result[TTSQueueStatus, str]:
        """Get current queue status"""
        try:
            pending = sum(
                1 for req in self.active_requests.values()
                if req['status'] == SynthesisStatus.PENDING
            )
            processing = sum(
                1 for req in self.active_requests.values()
                if req['status'] == SynthesisStatus.PROCESSING
            )

            avg_time = (
                sum(self.processing_times[-100:]) / len(self.processing_times[-100:])
                if self.processing_times else 0.0
            )

            status = TTSQueueStatus(
                pending_requests=pending,
                processing_requests=processing,
                completed_requests=self.total_completed,
                failed_requests=self.total_failed,
                average_processing_time=avg_time,
                estimated_wait_time=avg_time * pending,
                active_workers=self.max_workers
            )

            return Success(status)

        except Exception as e:
            logger.error(f"Error getting queue status: {e}")
            return Failure(f"Failed to get queue status: {str(e)}")

    async def get_available_voices(self) -> Result[List[VoiceInfo], str]:
        """Get list of available voices"""
        try:
            # Coqui TTS has many models, return high-quality ones
            voices = [
                VoiceInfo(
                    name="tts_models/multilingual/multi-dataset/xtts_v2",
                    language="en",
                    description="XTTS v2 - Most natural, handles contractions well (multilingual)",
                    sample_rate=24000,
                    loaded=(self.default_voice == "tts_models/multilingual/multi-dataset/xtts_v2")
                ),
                VoiceInfo(
                    name="tts_models/en/ljspeech/vits",
                    language="en",
                    description="VITS - Fast, natural, good with contractions",
                    sample_rate=22050,
                    loaded=(self.default_voice == "tts_models/en/ljspeech/vits")
                ),
                VoiceInfo(
                    name="tts_models/en/vctk/vits",
                    language="en",
                    description="VITS Multi-speaker - Multiple voices available",
                    sample_rate=22050,
                    is_multispeaker=True,
                    loaded=(self.default_voice == "tts_models/en/vctk/vits")
                ),
                VoiceInfo(
                    name="tts_models/en/ljspeech/tacotron2-DDC",
                    language="en",
                    description="Tacotron2 - Classic model (may struggle with contractions)",
                    sample_rate=22050,
                    loaded=(self.default_voice == "tts_models/en/ljspeech/tacotron2-DDC")
                ),
                VoiceInfo(
                    name="tts_models/en/multi-dataset/tortoise-v2",
                    language="en",
                    description="Tortoise v2 - Highest quality, slower (best naturalness)",
                    sample_rate=24000,
                    loaded=(self.default_voice == "tts_models/en/multi-dataset/tortoise-v2")
                )
            ]

            return Success(voices)

        except Exception as e:
            logger.error(f"Error getting voices: {e}")
            return Failure(f"Failed to get voices: {str(e)}")

    async def load_voice(self, voice_name: str) -> Result[None, str]:
        """Load a specific voice"""
        try:
            logger.info(f"Loading voice: {voice_name}")
            from TTS.api import TTS

            self.tts = TTS(voice_name).to(self.device)
            self.default_voice = voice_name

            logger.info(f"✅ Voice {voice_name} loaded")
            return Success(None)

        except Exception as e:
            logger.error(f"Failed to load voice {voice_name}: {e}")
            return Failure(f"Failed to load voice: {str(e)}")

    async def unload_voice(self, voice_name: str) -> Result[None, str]:
        """Unload a specific voice"""
        # For Coqui TTS, we just note this; actual unloading would require model management
        logger.info(f"Voice unload requested: {voice_name}")
        return Success(None)

    async def health_check(self) -> Result[Dict[str, Any], str]:
        """Perform health check"""
        try:
            health = {
                'status': 'healthy' if self.is_initialized else 'not_initialized',
                'device': self.device,
                'default_voice': self.default_voice,
                'active_requests': len(self.active_requests),
                'completed_requests': self.total_completed,
                'failed_requests': self.total_failed,
                'max_workers': self.max_workers
            }

            return Success(health)

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return Failure(f"Health check failed: {str(e)}")

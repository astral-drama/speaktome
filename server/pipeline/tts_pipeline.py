#!/usr/bin/env python3

"""
Text-to-Speech Processing Pipeline

Composable TTS pipeline mirroring the STT pipeline architecture.
Provides functional stages for text validation, synthesis, and audio post-processing.
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

from .audio_pipeline import AudioData, ProcessingContext
from ..functional.result_monad import Result, Success, Failure

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class TextData:
    """Immutable text data container for TTS"""
    text: str
    language: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def with_metadata(self, **metadata) -> 'TextData':
        """Create new TextData with additional metadata"""
        new_metadata = {**self.metadata, **metadata}
        return TextData(
            text=self.text,
            language=self.language,
            metadata=new_metadata
        )

@dataclass(frozen=True)
class TTSContext:
    """Processing context for TTS pipeline stages"""
    request_id: str
    client_id: Optional[str] = None
    voice: str = "default"
    speed: float = 1.0
    output_format: str = "wav"
    started_at: float = field(default_factory=time.time)
    stage_metrics: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def with_stage_metric(self, stage: str, duration: float) -> 'TTSContext':
        """Add stage processing time"""
        new_metrics = {**self.stage_metrics, stage: duration}
        return TTSContext(
            request_id=self.request_id,
            client_id=self.client_id,
            voice=self.voice,
            speed=self.speed,
            output_format=self.output_format,
            started_at=self.started_at,
            stage_metrics=new_metrics,
            metadata=self.metadata
        )

    def with_metadata(self, **metadata) -> 'TTSContext':
        """Add metadata"""
        new_metadata = {**self.metadata, **metadata}
        return TTSContext(
            request_id=self.request_id,
            client_id=self.client_id,
            voice=self.voice,
            speed=self.speed,
            output_format=self.output_format,
            started_at=self.started_at,
            stage_metrics=self.stage_metrics,
            metadata=new_metadata
        )

class TTSPipelineStage(ABC):
    """Abstract base class for TTS pipeline stages"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stage name"""
        pass

    @abstractmethod
    async def process(self, data: Any, context: TTSContext) -> Result[Any, str]:
        """Process data through this stage"""
        pass

    @abstractmethod
    def can_process(self, data: Any, context: TTSContext) -> bool:
        """Check if this stage can process the given data"""
        pass

class TextValidationStage(TTSPipelineStage):
    """Validates input text for TTS synthesis"""

    def __init__(self, max_length: int = 5000, min_length: int = 1):
        self.max_length = max_length
        self.min_length = min_length

    @property
    def name(self) -> str:
        return "text_validation"

    async def process(self, data: TextData, context: TTSContext) -> Result[TextData, str]:
        """Validate text data"""
        try:
            start_time = time.time()

            # Check if text exists
            if not data.text:
                return Failure("Text is empty")

            # Check length
            text_length = len(data.text)
            if text_length < self.min_length:
                return Failure(f"Text too short (min: {self.min_length} chars)")

            if text_length > self.max_length:
                return Failure(f"Text too long (max: {self.max_length} chars)")

            # Check for valid characters
            if not data.text.strip():
                return Failure("Text contains only whitespace")

            # Add validation metadata
            validated_data = data.with_metadata(
                validated_at=time.time(),
                text_length=text_length,
                validation_stage="text_validation"
            )

            processing_time = time.time() - start_time
            logger.debug(f"Text validation passed ({text_length} chars)")

            return Success(validated_data)

        except Exception as e:
            logger.error(f"Text validation failed: {e}")
            return Failure(f"Text validation error: {str(e)}")

    def can_process(self, data: Any, context: TTSContext) -> bool:
        return isinstance(data, TextData)

class TextPreprocessingStage(TTSPipelineStage):
    """Preprocesses text for better TTS synthesis"""

    @property
    def name(self) -> str:
        return "text_preprocessing"

    async def process(self, data: TextData, context: TTSContext) -> Result[TextData, str]:
        """Preprocess text"""
        try:
            start_time = time.time()

            # Normalize whitespace
            processed_text = ' '.join(data.text.split())

            # Remove unsupported characters (keep basic punctuation)
            # This is a simple implementation; could be more sophisticated
            allowed_chars = set(
                'abcdefghijklmnopqrstuvwxyz'
                'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
                '0123456789'
                ' .,!?;:\'-"'
            )
            processed_text = ''.join(c for c in processed_text if c in allowed_chars)

            # Create new text data
            preprocessed_data = TextData(
                text=processed_text,
                language=data.language,
                metadata={
                    **data.metadata,
                    'preprocessed_at': time.time(),
                    'original_length': len(data.text),
                    'processed_length': len(processed_text)
                }
            )

            processing_time = time.time() - start_time
            logger.debug(f"Text preprocessing complete")

            return Success(preprocessed_data)

        except Exception as e:
            logger.error(f"Text preprocessing failed: {e}")
            return Failure(f"Text preprocessing error: {str(e)}")

    def can_process(self, data: Any, context: TTSContext) -> bool:
        return isinstance(data, TextData)

class SynthesisStage(TTSPipelineStage):
    """Performs TTS synthesis using the TTS provider"""

    def __init__(self, tts_provider):
        self.tts_provider = tts_provider

    @property
    def name(self) -> str:
        return "synthesis"

    async def process(self, data: TextData, context: TTSContext) -> Result[AudioData, str]:
        """Synthesize speech from text"""
        try:
            start_time = time.time()

            # Create synthesis request
            from ..providers.tts_provider import SynthesisRequest
            request = SynthesisRequest(
                id=context.request_id,
                text=data.text,
                voice=context.voice,
                language=data.language,
                speed=context.speed,
                output_format=context.output_format,
                client_id=context.client_id
            )

            # Submit synthesis
            request_id_result = await self.tts_provider.submit_synthesis(request)
            if request_id_result.is_failure():
                return Failure(f"Synthesis submission failed: {request_id_result.get_error()}")

            # Wait for result
            result = await self._wait_for_synthesis(request_id_result.get_value())
            if result.is_failure():
                return result

            synthesis_result = result.get_value()

            # Convert to AudioData
            audio_data = AudioData(
                data=synthesis_result.audio_data,
                format=synthesis_result.audio_format,
                sample_rate=synthesis_result.sample_rate,
                metadata={
                    **data.metadata,
                    'synthesis_time': synthesis_result.processing_time,
                    'voice_used': synthesis_result.voice_used,
                    'synthesized_at': time.time()
                }
            )

            processing_time = time.time() - start_time
            logger.info(f"Synthesis completed: {len(audio_data.data)} bytes")

            return Success(audio_data)

        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            return Failure(f"Synthesis error: {str(e)}")

    async def _wait_for_synthesis(self, request_id: str, timeout: float = 30.0) -> Result[Any, str]:
        """Wait for synthesis to complete"""
        try:
            start_time = time.time()

            while time.time() - start_time < timeout:
                result = await self.tts_provider.get_result(request_id)
                if result.is_success() and result.get_value():
                    synthesis_result = result.get_value()
                    if synthesis_result.status.value == "completed":
                        return Success(synthesis_result)
                    elif synthesis_result.status.value == "failed":
                        return Failure(synthesis_result.error or "Synthesis failed")

                await asyncio.sleep(0.1)

            return Failure("Synthesis timeout")

        except Exception as e:
            return Failure(f"Error waiting for synthesis: {str(e)}")

    def can_process(self, data: Any, context: TTSContext) -> bool:
        return isinstance(data, TextData)

class AudioPostProcessingStage(TTSPipelineStage):
    """Post-processes synthesized audio"""

    @property
    def name(self) -> str:
        return "audio_post_processing"

    async def process(self, data: AudioData, context: TTSContext) -> Result[AudioData, str]:
        """Post-process audio"""
        try:
            start_time = time.time()

            # Placeholder for post-processing
            # Could include: normalization, effects, format conversion, etc.

            processed_audio = data.with_metadata(
                post_processed_at=time.time(),
                post_processing_applied=True
            )

            processing_time = time.time() - start_time
            logger.debug("Audio post-processing complete")

            return Success(processed_audio)

        except Exception as e:
            logger.error(f"Audio post-processing failed: {e}")
            return Failure(f"Audio post-processing error: {str(e)}")

    def can_process(self, data: Any, context: TTSContext) -> bool:
        return isinstance(data, AudioData)

class TTSPipeline:
    """Composable TTS processing pipeline"""

    def __init__(self):
        self.stages: List[TTSPipelineStage] = []

    def add_stage(self, stage: TTSPipelineStage) -> 'TTSPipeline':
        """Add a processing stage"""
        self.stages.append(stage)
        return self

    async def process(self, text_data: TextData, context: TTSContext) -> Result[AudioData, str]:
        """Process text through the TTS pipeline"""
        try:
            current_data = text_data

            # Process through stages
            for stage in self.stages:
                if stage.can_process(current_data, context):
                    stage_result = await stage.process(current_data, context)
                    if stage_result.is_failure():
                        logger.error(f"Stage {stage.name} failed: {stage_result.get_error()}")
                        return stage_result

                    current_data = stage_result.get_value()
                else:
                    logger.debug(f"Skipping stage {stage.name} - cannot process current data")

            # Final data should be AudioData
            if not isinstance(current_data, AudioData):
                return Failure("Pipeline did not produce audio data")

            total_processing_time = time.time() - context.started_at
            final_audio = current_data.with_metadata(
                pipeline_completed=True,
                total_processing_time=total_processing_time
            )

            logger.info(f"TTS pipeline processing completed in {total_processing_time:.2f}s")
            return Success(final_audio)

        except Exception as e:
            logger.error(f"TTS pipeline processing failed: {e}")
            return Failure(f"Pipeline error: {str(e)}")

def create_default_tts_pipeline(tts_provider) -> TTSPipeline:
    """Create a default TTS processing pipeline"""
    pipeline = TTSPipeline()

    # Add sequential stages
    pipeline.add_stage(TextValidationStage())
    pipeline.add_stage(TextPreprocessingStage())
    pipeline.add_stage(SynthesisStage(tts_provider))
    pipeline.add_stage(AudioPostProcessingStage())

    return pipeline

def create_fast_tts_pipeline(tts_provider) -> TTSPipeline:
    """Create a fast TTS pipeline with minimal stages"""
    pipeline = TTSPipeline()

    pipeline.add_stage(TextValidationStage())
    pipeline.add_stage(SynthesisStage(tts_provider))

    return pipeline

def create_quality_tts_pipeline(tts_provider) -> TTSPipeline:
    """Create a quality-focused TTS pipeline"""
    pipeline = TTSPipeline()

    pipeline.add_stage(TextValidationStage(max_length=10000))
    pipeline.add_stage(TextPreprocessingStage())
    pipeline.add_stage(SynthesisStage(tts_provider))
    pipeline.add_stage(AudioPostProcessingStage())

    return pipeline

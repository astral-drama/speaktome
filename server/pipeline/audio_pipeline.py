#!/usr/bin/env python3

"""
Composable Audio Processing Pipeline

Functional pipeline for audio processing using category theory concepts.
Provides composable stages with Result monads for clean error handling.
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Any, Callable, TypeVar, Generic, Union, Awaitable
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from pathlib import Path

from ..functional.result_monad import Result, Success, Failure, traverse

logger = logging.getLogger(__name__)

T = TypeVar('T')
U = TypeVar('U')

@dataclass(frozen=True)
class AudioData:
    """Immutable audio data container"""
    data: bytes
    format: str
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    duration: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def with_data(self, data: bytes) -> 'AudioData':
        """Create new AudioData with different data"""
        return AudioData(
            data=data,
            format=self.format,
            sample_rate=self.sample_rate,
            channels=self.channels,
            duration=self.duration,
            metadata=self.metadata
        )
    
    def with_format(self, format: str) -> 'AudioData':
        """Create new AudioData with different format"""
        return AudioData(
            data=self.data,
            format=format,
            sample_rate=self.sample_rate,
            channels=self.channels,
            duration=self.duration,
            metadata=self.metadata
        )
    
    def with_metadata(self, **metadata) -> 'AudioData':
        """Create new AudioData with additional metadata"""
        new_metadata = {**self.metadata, **metadata}
        return AudioData(
            data=self.data,
            format=self.format,
            sample_rate=self.sample_rate,
            channels=self.channels,
            duration=self.duration,
            metadata=new_metadata
        )

@dataclass(frozen=True)
class ProcessingContext:
    """Processing context for pipeline stages"""
    request_id: str
    client_id: Optional[str] = None
    model: str = "base"
    language: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    stage_metrics: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def with_stage_metric(self, stage: str, duration: float) -> 'ProcessingContext':
        """Add stage processing time"""
        new_metrics = {**self.stage_metrics, stage: duration}
        return ProcessingContext(
            request_id=self.request_id,
            client_id=self.client_id,
            model=self.model,
            language=self.language,
            started_at=self.started_at,
            stage_metrics=new_metrics,
            metadata=self.metadata
        )
    
    def with_metadata(self, **metadata) -> 'ProcessingContext':
        """Add metadata"""
        new_metadata = {**self.metadata, **metadata}
        return ProcessingContext(
            request_id=self.request_id,
            client_id=self.client_id,
            model=self.model,
            language=self.language,
            started_at=self.started_at,
            stage_metrics=self.stage_metrics,
            metadata=new_metadata
        )

# Pipeline stage function type
StageFunction = Callable[[AudioData, ProcessingContext], Result[AudioData, str]]
AsyncStageFunction = Callable[[AudioData, ProcessingContext], Awaitable[Result[AudioData, str]]]

class PipelineStage(ABC):
    """Abstract base class for pipeline stages"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Stage name"""
        pass
    
    @abstractmethod
    async def process(self, audio: AudioData, context: ProcessingContext) -> Result[AudioData, str]:
        """Process audio data"""
        pass
    
    @abstractmethod
    def can_process(self, audio: AudioData, context: ProcessingContext) -> bool:
        """Check if this stage can process the given audio data"""
        pass

class FormatValidationStage(PipelineStage):
    """Validates audio format and basic properties"""
    
    def __init__(self, supported_formats: List[str] = None):
        self.supported_formats = supported_formats or [
            'wav', 'mp3', 'flac', 'webm', 'ogg', 'm4a', 'mp4'
        ]
    
    @property
    def name(self) -> str:
        return "format_validation"
    
    async def process(self, audio: AudioData, context: ProcessingContext) -> Result[AudioData, str]:
        """Validate audio format"""
        try:
            start_time = time.time()
            
            # Basic validation
            if not audio.data:
                return Failure("Audio data is empty")
            
            if not audio.format:
                return Failure("Audio format not specified")
            
            if audio.format not in self.supported_formats:
                return Failure(f"Unsupported format: {audio.format}. Supported: {', '.join(self.supported_formats)}")
            
            # Add validation metadata
            validated_audio = audio.with_metadata(
                validated_at=time.time(),
                validation_stage="format_validation"
            )
            
            processing_time = time.time() - start_time
            new_context = context.with_stage_metric(self.name, processing_time)
            
            logger.debug(f"Format validation passed for {audio.format} ({len(audio.data)} bytes)")
            return Success(validated_audio)
            
        except Exception as e:
            logger.error(f"Format validation failed: {e}")
            return Failure(f"Format validation error: {str(e)}")
    
    def can_process(self, audio: AudioData, context: ProcessingContext) -> bool:
        return True

class AudioConversionStage(PipelineStage):
    """Converts audio to optimal format for transcription"""
    
    def __init__(self, target_format: str = 'wav', target_sample_rate: int = 16000):
        self.target_format = target_format
        self.target_sample_rate = target_sample_rate
        
        # Initialize the real audio processor
        from ..audio_processor import AudioProcessor
        self.audio_processor = AudioProcessor(
            target_sample_rate=target_sample_rate, 
            target_channels=1
        )
    
    @property
    def name(self) -> str:
        return "audio_conversion"
    
    async def process(self, audio: AudioData, context: ProcessingContext) -> Result[AudioData, str]:
        """Convert audio format if needed"""
        try:
            start_time = time.time()
            
            # Check if conversion is needed
            if (audio.format == self.target_format and 
                audio.sample_rate == self.target_sample_rate):
                logger.debug("No conversion needed")
                return Success(audio)
            
            # Perform conversion (placeholder - would use FFmpeg or similar)
            converted_data = await self._convert_audio(audio)
            if converted_data.is_failure():
                return converted_data
            
            converted_audio = audio.with_data(converted_data.get_value()).with_format(self.target_format)
            converted_audio = converted_audio.with_metadata(
                converted_from=audio.format,
                converted_at=time.time(),
                target_sample_rate=self.target_sample_rate
            )
            
            processing_time = time.time() - start_time
            new_context = context.with_stage_metric(self.name, processing_time)
            
            logger.info(f"Converted audio from {audio.format} to {self.target_format}")
            return Success(converted_audio)
            
        except Exception as e:
            logger.error(f"Audio conversion failed: {e}")
            return Failure(f"Audio conversion error: {str(e)}")
    
    async def _convert_audio(self, audio: AudioData) -> Result[bytes, str]:
        """Convert audio using real AudioProcessor"""
        try:
            import tempfile
            import os
            
            # Write incoming audio data to temporary file
            input_temp = tempfile.NamedTemporaryFile(
                suffix=f'.{audio.format}', 
                delete=False
            )
            input_temp.write(audio.data)
            input_temp.close()
            
            try:
                # Convert using AudioProcessor
                output_path = await self.audio_processor.convert_to_wav(
                    input_path=input_temp.name,
                    sample_rate=self.target_sample_rate,
                    channels=1
                )
                
                # Read converted data
                with open(output_path, 'rb') as f:
                    converted_data = f.read()
                
                # Clean up temporary files
                os.unlink(input_temp.name)
                if output_path != input_temp.name:
                    os.unlink(output_path)
                
                logger.debug(f"Successfully converted {audio.format} to WAV ({len(converted_data)} bytes)")
                return Success(converted_data)
                
            except Exception as cleanup_error:
                # Ensure cleanup happens even if conversion fails
                try:
                    os.unlink(input_temp.name)
                except:
                    pass
                raise cleanup_error
            
        except Exception as e:
            logger.error(f"Audio conversion failed: {e}")
            return Failure(f"Audio conversion failed: {str(e)}")
    
    def can_process(self, audio: AudioData, context: ProcessingContext) -> bool:
        return audio.format != self.target_format or audio.sample_rate != self.target_sample_rate

class NoiseReductionStage(PipelineStage):
    """Applies noise reduction to improve transcription quality"""
    
    def __init__(self, enabled: bool = True, strength: float = 0.5):
        self.enabled = enabled
        self.strength = strength
    
    @property
    def name(self) -> str:
        return "noise_reduction"
    
    async def process(self, audio: AudioData, context: ProcessingContext) -> Result[AudioData, str]:
        """Apply noise reduction"""
        try:
            if not self.enabled:
                return Success(audio)
            
            start_time = time.time()
            
            # Apply noise reduction (placeholder)
            processed_data = await self._apply_noise_reduction(audio)
            if processed_data.is_failure():
                return processed_data
            
            processed_audio = audio.with_data(processed_data.get_value())
            processed_audio = processed_audio.with_metadata(
                noise_reduction_applied=True,
                noise_reduction_strength=self.strength,
                processed_at=time.time()
            )
            
            processing_time = time.time() - start_time
            new_context = context.with_stage_metric(self.name, processing_time)
            
            logger.debug(f"Applied noise reduction (strength: {self.strength})")
            return Success(processed_audio)
            
        except Exception as e:
            logger.error(f"Noise reduction failed: {e}")
            return Failure(f"Noise reduction error: {str(e)}")
    
    async def _apply_noise_reduction(self, audio: AudioData) -> Result[bytes, str]:
        """Apply noise reduction algorithm (placeholder)"""
        try:
            # This would use audio processing libraries like librosa or similar
            await asyncio.sleep(0.05)  # Simulate processing time
            
            logger.debug("Noise reduction simulated")
            return Success(audio.data)
            
        except Exception as e:
            return Failure(f"Noise reduction failed: {str(e)}")
    
    def can_process(self, audio: AudioData, context: ProcessingContext) -> bool:
        return self.enabled and audio.format in ['wav', 'flac']

class TranscriptionStage(PipelineStage):
    """Performs the actual transcription using Whisper"""
    
    def __init__(self, transcription_provider):
        self.transcription_provider = transcription_provider
    
    @property
    def name(self) -> str:
        return "transcription"
    
    async def process(self, audio: AudioData, context: ProcessingContext) -> Result[AudioData, str]:
        """Perform transcription"""
        try:
            start_time = time.time()
            
            # Save audio to temporary file for transcription
            temp_file = await self._save_to_temp_file(audio)
            if temp_file.is_failure():
                return temp_file
            
            temp_path = temp_file.get_value()
            
            try:
                # Create transcription request
                from ..providers import TranscriptionRequest
                request = TranscriptionRequest(
                    id=context.request_id,
                    audio_file_path=temp_path,
                    model=context.model,
                    language=context.language,
                    client_id=context.client_id
                )
                
                # Submit transcription
                request_id_result = await self.transcription_provider.submit_transcription(request)
                if request_id_result.is_failure():
                    return Failure(f"Transcription submission failed: {request_id_result.get_error()}")
                
                # Wait for result
                result = await self._wait_for_transcription(request_id_result.get_value())
                if result.is_failure():
                    return result
                
                transcription_result = result.get_value()
                
                # Add transcription metadata
                transcribed_audio = audio.with_metadata(
                    transcription_text=transcription_result.text,
                    transcription_language=transcription_result.language,
                    transcription_confidence=transcription_result.confidence,
                    transcribed_at=time.time(),
                    model_used=transcription_result.model_used
                )
                
                processing_time = time.time() - start_time
                new_context = context.with_stage_metric(self.name, processing_time)
                
                logger.info(f"Transcription completed: '{transcription_result.text[:50]}...'")
                return Success(transcribed_audio)
                
            finally:
                # Clean up temp file
                try:
                    Path(temp_path).unlink()
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return Failure(f"Transcription error: {str(e)}")
    
    async def _save_to_temp_file(self, audio: AudioData) -> Result[str, str]:
        """Save audio data to temporary file"""
        try:
            import tempfile
            import uuid
            
            suffix = f".{audio.format}"
            temp_file = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
            
            with temp_file as f:
                f.write(audio.data)
            
            return Success(temp_file.name)
            
        except Exception as e:
            return Failure(f"Failed to save temp file: {str(e)}")
    
    async def _wait_for_transcription(self, request_id: str, timeout: float = 30.0) -> Result[Any, str]:
        """Wait for transcription to complete"""
        try:
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                result = await self.transcription_provider.get_result(request_id)
                if result.is_success() and result.get_value():
                    transcription_result = result.get_value()
                    if transcription_result.status.value == "completed":
                        return Success(transcription_result)
                    elif transcription_result.status.value == "failed":
                        return Failure(transcription_result.error or "Transcription failed")
                
                await asyncio.sleep(0.1)
            
            return Failure("Transcription timeout")
            
        except Exception as e:
            return Failure(f"Error waiting for transcription: {str(e)}")
    
    def can_process(self, audio: AudioData, context: ProcessingContext) -> bool:
        return True

class AudioProcessingPipeline:
    """Composable audio processing pipeline"""
    
    def __init__(self):
        self.stages: List[PipelineStage] = []
        self.parallel_stages: Dict[str, List[PipelineStage]] = {}
        
    def add_stage(self, stage: PipelineStage) -> 'AudioProcessingPipeline':
        """Add a sequential processing stage"""
        self.stages.append(stage)
        return self
    
    def add_parallel_stages(self, group_name: str, stages: List[PipelineStage]) -> 'AudioProcessingPipeline':
        """Add parallel processing stages"""
        self.parallel_stages[group_name] = stages
        return self
    
    async def process(self, audio: AudioData, context: ProcessingContext) -> Result[AudioData, str]:
        """Process audio through the pipeline"""
        try:
            current_audio = audio
            current_context = context
            
            # Process sequential stages
            for stage in self.stages:
                if stage.can_process(current_audio, current_context):
                    stage_result = await stage.process(current_audio, current_context)
                    if stage_result.is_failure():
                        logger.error(f"Stage {stage.name} failed: {stage_result.get_error()}")
                        return stage_result
                    
                    current_audio = stage_result.get_value()
                    # Update context with stage metrics would be handled by stages
                else:
                    logger.debug(f"Skipping stage {stage.name} - cannot process current audio")
            
            # Process parallel stages
            for group_name, parallel_stages in self.parallel_stages.items():
                parallel_results = await self._process_parallel_stages(
                    parallel_stages, current_audio, current_context
                )
                
                if parallel_results.is_failure():
                    logger.error(f"Parallel group {group_name} failed: {parallel_results.get_error()}")
                    return parallel_results
                
                # For parallel stages, we could merge results or select the best one
                # For simplicity, we'll use the first successful result
                results = parallel_results.get_value()
                if results:
                    current_audio = results[0]
            
            total_processing_time = time.time() - context.started_at
            final_audio = current_audio.with_metadata(
                pipeline_completed=True,
                total_processing_time=total_processing_time
            )
            
            logger.info(f"Pipeline processing completed in {total_processing_time:.2f}s")
            return Success(final_audio)
            
        except Exception as e:
            logger.error(f"Pipeline processing failed: {e}")
            return Failure(f"Pipeline error: {str(e)}")
    
    async def _process_parallel_stages(self, 
                                     stages: List[PipelineStage], 
                                     audio: AudioData, 
                                     context: ProcessingContext) -> Result[List[AudioData], str]:
        """Process stages in parallel"""
        try:
            # Filter stages that can process the audio
            applicable_stages = [stage for stage in stages if stage.can_process(audio, context)]
            
            if not applicable_stages:
                return Success([audio])  # No applicable stages, return original
            
            # Run stages in parallel
            tasks = [stage.process(audio, context) for stage in applicable_stages]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Collect successful results
            successful_results = []
            errors = []
            
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    errors.append(f"Stage {applicable_stages[i].name}: {str(result)}")
                elif isinstance(result, Result):
                    if result.is_success():
                        successful_results.append(result.get_value())
                    else:
                        errors.append(f"Stage {applicable_stages[i].name}: {result.get_error()}")
            
            if not successful_results and errors:
                return Failure(f"All parallel stages failed: {'; '.join(errors)}")
            
            return Success(successful_results)
            
        except Exception as e:
            return Failure(f"Parallel processing failed: {str(e)}")

def create_default_pipeline(transcription_provider) -> AudioProcessingPipeline:
    """Create a default audio processing pipeline"""
    pipeline = AudioProcessingPipeline()
    
    # Add sequential stages
    pipeline.add_stage(FormatValidationStage())
    pipeline.add_stage(AudioConversionStage())
    pipeline.add_stage(NoiseReductionStage())
    pipeline.add_stage(TranscriptionStage(transcription_provider))
    
    return pipeline

def create_fast_pipeline(transcription_provider) -> AudioProcessingPipeline:
    """Create a fast processing pipeline with minimal stages"""
    pipeline = AudioProcessingPipeline()
    
    pipeline.add_stage(FormatValidationStage())
    pipeline.add_stage(TranscriptionStage(transcription_provider))
    
    return pipeline

def create_quality_pipeline(transcription_provider) -> AudioProcessingPipeline:
    """Create a quality-focused pipeline with all enhancement stages"""
    pipeline = AudioProcessingPipeline()
    
    pipeline.add_stage(FormatValidationStage())
    pipeline.add_stage(AudioConversionStage(target_sample_rate=48000))  # Higher quality
    pipeline.add_stage(NoiseReductionStage(strength=0.7))  # More aggressive noise reduction
    pipeline.add_stage(TranscriptionStage(transcription_provider))
    
    return pipeline
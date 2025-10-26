#!/usr/bin/env python3

"""
Client Audio Pipeline

Composable audio processing pipeline matching server architecture patterns.
Provides functional composition of audio processing stages with Result monads.
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, List, Callable, TypeVar
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

from shared.functional import Result, Success, Failure, compose
from shared.events import BaseEvent, AudioCapturedEvent, get_event_bus

logger = logging.getLogger(__name__)

T = TypeVar('T')
U = TypeVar('U')


@dataclass
class AudioData:
    """
    Immutable audio data representation
    
    Consistent with server AudioData structure for shared understanding.
    """
    data: bytes
    format: str
    sample_rate: int
    channels: int
    duration_seconds: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def with_metadata(self, **kwargs) -> 'AudioData':
        """Return new AudioData with updated metadata"""
        new_metadata = self.metadata.copy()
        new_metadata.update(kwargs)
        
        return AudioData(
            data=self.data,
            format=self.format,
            sample_rate=self.sample_rate,
            channels=self.channels,
            duration_seconds=self.duration_seconds,
            metadata=new_metadata
        )
    
    def with_data(self, data: bytes, format: str = None) -> 'AudioData':
        """Return new AudioData with updated data and format"""
        return AudioData(
            data=data,
            format=format or self.format,
            sample_rate=self.sample_rate,
            channels=self.channels,
            duration_seconds=self.duration_seconds,
            metadata=self.metadata
        )


@dataclass
class ProcessingContext:
    """
    Processing context for pipeline stages
    
    Matches server ProcessingContext for consistency.
    """
    request_id: str
    start_time: float = field(default_factory=time.time)
    stage_timings: Dict[str, float] = field(default_factory=dict)
    stage_metadata: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    def with_timing(self, stage_name: str, duration: float) -> 'ProcessingContext':
        """Add timing information for a stage"""
        new_timings = self.stage_timings.copy()
        new_timings[stage_name] = duration
        
        return ProcessingContext(
            request_id=self.request_id,
            start_time=self.start_time,
            stage_timings=new_timings,
            stage_metadata=self.stage_metadata
        )
    
    def with_metadata(self, stage_name: str, metadata: Dict[str, Any]) -> 'ProcessingContext':
        """Add metadata for a stage"""
        new_stage_metadata = self.stage_metadata.copy()
        new_stage_metadata[stage_name] = metadata
        
        return ProcessingContext(
            request_id=self.request_id,
            start_time=self.start_time,
            stage_timings=self.stage_timings,
            stage_metadata=new_stage_metadata
        )


class PipelineStage(ABC):
    """
    Abstract pipeline stage
    
    Consistent with server pipeline stage architecture.
    """
    
    @property
    @abstractmethod
    def stage_name(self) -> str:
        """Return the name of this pipeline stage"""
        pass
    
    @abstractmethod
    async def process(self, audio_data: AudioData, context: ProcessingContext) -> Result[AudioData, Exception]:
        """Process audio data through this stage"""
        pass
    
    async def process_with_timing(self, audio_data: AudioData, context: ProcessingContext) -> Result[AudioData, Exception]:
        """Process with automatic timing measurement"""
        start_time = time.time()
        
        try:
            result = await self.process(audio_data, context)
            
            if result.is_success():
                duration = time.time() - start_time
                updated_context = context.with_timing(self.stage_name, duration)
                
                logger.debug(f"Stage {self.stage_name} completed in {duration:.3f}s")
                
                # Store context in metadata for next stage
                updated_audio = result.value.with_metadata(
                    processing_context=updated_context
                )
                
                return Success(updated_audio)
            else:
                return result
                
        except Exception as e:
            logger.error(f"Stage {self.stage_name} failed: {e}")
            return Failure(e)


class AudioRecordingStage(PipelineStage):
    """Pipeline stage for audio recording"""
    
    def __init__(self, recorder):
        self.recorder = recorder
    
    @property
    def stage_name(self) -> str:
        return "audio_recording"
    
    async def process(self, audio_data: AudioData, context: ProcessingContext) -> Result[AudioData, Exception]:
        """This stage doesn't process existing data - it creates new audio data"""
        # This is handled by the audio recording component
        return Success(audio_data)


class AudioValidationStage(PipelineStage):
    """Pipeline stage for audio validation"""
    
    def __init__(self, min_duration: float = 0.1, max_duration: float = 300.0, min_size: int = 1000):
        self.min_duration = min_duration
        self.max_duration = max_duration
        self.min_size = min_size
    
    @property
    def stage_name(self) -> str:
        return "audio_validation"
    
    async def process(self, audio_data: AudioData, context: ProcessingContext) -> Result[AudioData, Exception]:
        """Validate audio data"""
        # Duration validation
        if audio_data.duration_seconds < self.min_duration:
            return Failure(f"Audio too short: {audio_data.duration_seconds:.2f}s < {self.min_duration}s")
        
        if audio_data.duration_seconds > self.max_duration:
            return Failure(f"Audio too long: {audio_data.duration_seconds:.2f}s > {self.max_duration}s")
        
        # Size validation
        if len(audio_data.data) < self.min_size:
            return Failure(f"Audio data too small: {len(audio_data.data)} bytes < {self.min_size}")
        
        # Format validation
        if audio_data.format not in ['wav', 'mp3', 'webm', 'flac']:
            logger.warning(f"Unusual audio format: {audio_data.format}")
        
        logger.debug(f"Audio validated: {audio_data.duration_seconds:.2f}s, {len(audio_data.data)} bytes")
        
        return Success(audio_data.with_metadata(
            validation_passed=True,
            validation_timestamp=time.time()
        ))


class AudioFormatStage(PipelineStage):
    """Pipeline stage for audio format conversion"""
    
    def __init__(self, target_format: str = "wav", target_sample_rate: int = 16000):
        self.target_format = target_format
        self.target_sample_rate = target_sample_rate
    
    @property
    def stage_name(self) -> str:
        return "audio_format"
    
    async def process(self, audio_data: AudioData, context: ProcessingContext) -> Result[AudioData, Exception]:
        """Convert audio format if needed"""
        # If already in target format and sample rate, pass through
        if (audio_data.format == self.target_format and 
            audio_data.sample_rate == self.target_sample_rate):
            return Success(audio_data)
        
        # For now, assume conversion is handled externally
        # In a full implementation, this would use FFmpeg or similar
        logger.debug(f"Audio format conversion: {audio_data.format} -> {self.target_format}")
        
        return Success(audio_data.with_metadata(
            format_conversion=f"{audio_data.format}->{self.target_format}",
            original_format=audio_data.format,
            original_sample_rate=audio_data.sample_rate
        ))


class TranscriptionRequestStage(PipelineStage):
    """Pipeline stage for preparing transcription requests"""

    def __init__(self, model: str = "base", language: Optional[str] = None):
        self.model = model
        self.language = language
    
    @property
    def stage_name(self) -> str:
        return "transcription_request"
    
    async def process(self, audio_data: AudioData, context: ProcessingContext) -> Result[AudioData, Exception]:
        """Prepare audio for transcription"""
        # Add transcription parameters to metadata
        transcription_metadata = {
            'model': self.model,
            'language': self.language,
            'request_id': context.request_id,
            'prepared_at': time.time()
        }
        
        result_audio = audio_data.with_metadata(**transcription_metadata)
        
        logger.debug(f"Transcription request prepared: model={self.model}, language={self.language}")
        
        return Success(result_audio)


class AudioPipeline:
    """
    Composable audio processing pipeline
    
    Matches server pipeline architecture with functional composition.
    """
    
    def __init__(self, stages: List[PipelineStage]):
        self.stages = stages
        self.event_bus = get_event_bus()
        
        logger.info(f"Audio pipeline created with {len(stages)} stages")
    
    async def process(self, audio_data: AudioData, context: ProcessingContext) -> Result[AudioData, Exception]:
        """Process audio through all pipeline stages"""
        current_audio = audio_data
        current_context = context
        
        logger.debug(f"Starting pipeline processing with {len(self.stages)} stages")
        
        for stage in self.stages:
            # Extract context from audio metadata if updated by previous stage
            if 'processing_context' in current_audio.metadata:
                current_context = current_audio.metadata['processing_context']
            
            result = await stage.process_with_timing(current_audio, current_context)
            
            if result.is_failure():
                logger.error(f"Pipeline failed at stage {stage.stage_name}: {result.error}")
                return result
            
            current_audio = result.value
        
        # Publish completion event
        total_duration = time.time() - context.start_time
        await self.event_bus.publish(AudioCapturedEvent(
            audio_data=current_audio.data,
            format=current_audio.format,
            duration_seconds=current_audio.duration_seconds,
            metadata={
                'pipeline_duration': total_duration,
                'stages_completed': len(self.stages),
                'request_id': context.request_id
            }
        ))
        
        logger.info(f"Pipeline completed successfully in {total_duration:.3f}s")
        return Success(current_audio)


# Pipeline factory functions
def create_basic_pipeline() -> AudioPipeline:
    """Create basic audio processing pipeline"""
    stages = [
        AudioValidationStage(),
        AudioFormatStage(target_format="wav"),
        TranscriptionRequestStage()
    ]
    
    return AudioPipeline(stages)


def create_quality_pipeline() -> AudioPipeline:
    """Create quality-focused audio processing pipeline"""
    stages = [
        AudioValidationStage(min_duration=0.5, min_size=2000),
        AudioFormatStage(target_format="wav", target_sample_rate=22050),
        TranscriptionRequestStage(model="small", language=None)
    ]
    
    return AudioPipeline(stages)


def create_fast_pipeline() -> AudioPipeline:
    """Create speed-focused audio processing pipeline"""
    stages = [
        AudioValidationStage(min_duration=0.1),
        TranscriptionRequestStage(model="tiny", language="en")
    ]
    
    return AudioPipeline(stages)
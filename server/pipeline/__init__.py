"""
Audio Processing Pipeline Module

Provides composable audio processing capabilities using functional pipelines.
"""

from .audio_pipeline import (
    AudioProcessingPipeline,
    PipelineStage,
    AudioData,
    ProcessingContext,
    FormatValidationStage,
    AudioConversionStage,
    NoiseReductionStage,
    TranscriptionStage,
    create_default_pipeline,
    create_fast_pipeline,
    create_quality_pipeline
)

__all__ = [
    "AudioProcessingPipeline",
    "PipelineStage",
    "AudioData",
    "ProcessingContext", 
    "FormatValidationStage",
    "AudioConversionStage",
    "NoiseReductionStage",
    "TranscriptionStage",
    "create_default_pipeline",
    "create_fast_pipeline",
    "create_quality_pipeline"
]
"""
Providers Module

Provides abstract interfaces and implementations for transcription services.
"""

from .transcription_provider import (
    TranscriptionProvider,
    StreamingTranscriptionProvider,
    BatchTranscriptionProvider,
    TranscriptionProviderRegistry,
    TranscriptionRequest,
    TranscriptionResult,
    TranscriptionStatus,
    ModelInfo,
    QueueStatus,
    transcription_registry,
    get_transcription_registry
)

__all__ = [
    "TranscriptionProvider",
    "StreamingTranscriptionProvider", 
    "BatchTranscriptionProvider",
    "TranscriptionProviderRegistry",
    "TranscriptionRequest",
    "TranscriptionResult",
    "TranscriptionStatus",
    "ModelInfo",
    "QueueStatus",
    "transcription_registry",
    "get_transcription_registry"
]
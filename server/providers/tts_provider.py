#!/usr/bin/env python3

"""
Text-to-Speech (TTS) Provider Interface

Defines the contract for TTS services using abstract base classes.
Mirrors the transcription_provider.py structure for symmetry.
"""

import asyncio
import logging
import time
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Any
from pathlib import Path

from ..functional.result_monad import Result, Success, Failure

logger = logging.getLogger(__name__)

class SynthesisStatus(Enum):
    """Speech synthesis request status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass(frozen=True)
class SynthesisRequest:
    """TTS synthesis request data"""
    id: str
    text: str
    voice: str
    language: Optional[str] = None
    speed: float = 1.0
    output_format: str = "wav"
    client_id: Optional[str] = None
    created_at: float = 0.0
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            object.__setattr__(self, 'metadata', {})

@dataclass(frozen=True)
class SynthesisResult:
    """TTS synthesis result data"""
    id: str
    status: SynthesisStatus
    audio_data: Optional[bytes] = None
    audio_format: str = "wav"
    sample_rate: Optional[int] = None
    duration: Optional[float] = None
    processing_time: Optional[float] = None
    voice_used: Optional[str] = None
    error: Optional[str] = None
    completed_at: Optional[float] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            object.__setattr__(self, 'metadata', {})

@dataclass(frozen=True)
class VoiceInfo:
    """Information about available voices"""
    name: str
    language: str
    gender: Optional[str] = None
    description: Optional[str] = None
    sample_rate: Optional[int] = None
    is_multispeaker: bool = False
    loaded: bool = False

@dataclass(frozen=True)
class TTSQueueStatus:
    """TTS queue status information"""
    pending_requests: int = 0
    processing_requests: int = 0
    completed_requests: int = 0
    failed_requests: int = 0
    average_processing_time: float = 0.0
    estimated_wait_time: float = 0.0
    active_workers: int = 0

class TTSProvider(ABC):
    """Abstract base class for TTS providers"""

    @abstractmethod
    async def initialize(self) -> Result[None, str]:
        """Initialize the TTS provider and load models"""
        pass

    @abstractmethod
    async def shutdown(self) -> Result[None, str]:
        """Shutdown the TTS provider and cleanup resources"""
        pass

    @abstractmethod
    async def submit_synthesis(self, request: SynthesisRequest) -> Result[str, str]:
        """Submit a synthesis request and return request ID"""
        pass

    @abstractmethod
    async def get_result(self, request_id: str) -> Result[Optional[SynthesisResult], str]:
        """Get synthesis result by request ID"""
        pass

    @abstractmethod
    async def get_status(self, request_id: str) -> Result[Optional[SynthesisStatus], str]:
        """Get synthesis status by request ID"""
        pass

    @abstractmethod
    async def cancel_request(self, request_id: str) -> Result[bool, str]:
        """Cancel a synthesis request"""
        pass

    @abstractmethod
    async def get_queue_status(self) -> Result[TTSQueueStatus, str]:
        """Get current queue status"""
        pass

    @abstractmethod
    async def get_available_voices(self) -> Result[List[VoiceInfo], str]:
        """Get list of available voices"""
        pass

    @abstractmethod
    async def load_voice(self, voice_name: str) -> Result[None, str]:
        """Load a specific voice"""
        pass

    @abstractmethod
    async def unload_voice(self, voice_name: str) -> Result[None, str]:
        """Unload a specific voice to free resources"""
        pass

    @abstractmethod
    async def health_check(self) -> Result[Dict[str, Any], str]:
        """Perform health check and return status"""
        pass

class TTSProviderRegistry:
    """Registry for managing multiple TTS providers"""

    def __init__(self):
        self._providers: Dict[str, TTSProvider] = {}
        self._default_provider: Optional[str] = None

    def register_provider(self, name: str, provider: TTSProvider) -> Result[None, str]:
        """Register a TTS provider"""
        try:
            self._providers[name] = provider

            if self._default_provider is None:
                self._default_provider = name

            logger.info(f"Registered TTS provider: {name}")
            return Success(None)

        except Exception as e:
            logger.error(f"Failed to register TTS provider {name}: {e}")
            return Failure(f"Provider registration failed: {str(e)}")

    def get_provider(self, name: Optional[str] = None) -> Result[TTSProvider, str]:
        """Get a TTS provider by name (or default)"""
        provider_name = name or self._default_provider

        if not provider_name:
            return Failure("No TTS providers registered")

        if provider_name not in self._providers:
            return Failure(f"TTS provider {provider_name} not found")

        return Success(self._providers[provider_name])

    def list_providers(self) -> List[str]:
        """List all registered provider names"""
        return list(self._providers.keys())

# Global registry instance
tts_registry = TTSProviderRegistry()

def get_tts_registry() -> TTSProviderRegistry:
    """Get the global TTS provider registry"""
    return tts_registry

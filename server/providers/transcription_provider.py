#!/usr/bin/env python3

"""
Transcription Provider Interface

Defines the contract for transcription services using abstract base classes.
Provides a clean abstraction that can be implemented by different transcription backends.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Any, AsyncGenerator
from pathlib import Path

from ..functional.result_monad import Result, Success, Failure

logger = logging.getLogger(__name__)

class TranscriptionStatus(Enum):
    """Transcription request status"""
    PENDING = "pending"
    PROCESSING = "processing" 
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass(frozen=True)
class TranscriptionRequest:
    """Transcription request data"""
    id: str
    audio_file_path: str
    model: str
    language: Optional[str] = None
    client_id: Optional[str] = None
    created_at: float = 0.0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            object.__setattr__(self, 'metadata', {})

@dataclass(frozen=True)
class TranscriptionResult:
    """Transcription result data"""
    id: str
    status: TranscriptionStatus
    text: Optional[str] = None
    language: Optional[str] = None
    confidence: Optional[float] = None
    segments: Optional[List[Dict[str, Any]]] = None
    processing_time: Optional[float] = None
    model_used: Optional[str] = None
    error: Optional[str] = None
    completed_at: Optional[float] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            object.__setattr__(self, 'metadata', {})

@dataclass(frozen=True)
class ModelInfo:
    """Information about available models"""
    name: str
    size_mb: Optional[int] = None
    description: Optional[str] = None
    languages: Optional[List[str]] = None
    accuracy_level: Optional[str] = None
    speed_level: Optional[str] = None
    loaded: bool = False

@dataclass(frozen=True)
class QueueStatus:
    """Queue status information"""
    pending_requests: int = 0
    processing_requests: int = 0
    completed_requests: int = 0
    failed_requests: int = 0
    average_processing_time: float = 0.0
    estimated_wait_time: float = 0.0
    active_workers: int = 0

class TranscriptionProvider(ABC):
    """Abstract base class for transcription providers"""
    
    @abstractmethod
    async def initialize(self) -> Result[None, str]:
        """Initialize the transcription provider"""
        pass
    
    @abstractmethod
    async def shutdown(self) -> Result[None, str]:
        """Shutdown the transcription provider and cleanup resources"""
        pass
    
    @abstractmethod
    async def submit_transcription(self, request: TranscriptionRequest) -> Result[str, str]:
        """Submit a transcription request and return request ID"""
        pass
    
    @abstractmethod
    async def get_result(self, request_id: str) -> Result[Optional[TranscriptionResult], str]:
        """Get transcription result by request ID"""
        pass
    
    @abstractmethod
    async def get_status(self, request_id: str) -> Result[Optional[TranscriptionStatus], str]:
        """Get transcription status by request ID"""
        pass
    
    @abstractmethod
    async def cancel_request(self, request_id: str) -> Result[bool, str]:
        """Cancel a transcription request"""
        pass
    
    @abstractmethod
    async def get_queue_status(self) -> Result[QueueStatus, str]:
        """Get current queue status"""
        pass
    
    @abstractmethod
    async def get_available_models(self) -> Result[List[ModelInfo], str]:
        """Get list of available models"""
        pass
    
    @abstractmethod
    async def load_model(self, model_name: str) -> Result[None, str]:
        """Load a specific model"""
        pass
    
    @abstractmethod
    async def unload_model(self, model_name: str) -> Result[None, str]:
        """Unload a specific model to free resources"""
        pass
    
    @abstractmethod
    async def health_check(self) -> Result[Dict[str, Any], str]:
        """Perform health check and return status"""
        pass

class StreamingTranscriptionProvider(TranscriptionProvider):
    """Extended interface for providers that support streaming transcription"""
    
    @abstractmethod
    async def start_streaming_transcription(self, 
                                          client_id: str,
                                          model: str,
                                          language: Optional[str] = None) -> Result[str, str]:
        """Start a streaming transcription session"""
        pass
    
    @abstractmethod
    async def send_audio_chunk(self, 
                              session_id: str,
                              audio_data: bytes,
                              is_final: bool = False) -> Result[None, str]:
        """Send audio chunk to streaming session"""
        pass
    
    @abstractmethod
    async def get_streaming_results(self, session_id: str) -> AsyncGenerator[TranscriptionResult, None]:
        """Get streaming transcription results as they become available"""
        pass
    
    @abstractmethod
    async def end_streaming_transcription(self, session_id: str) -> Result[TranscriptionResult, str]:
        """End streaming transcription and get final result"""
        pass

class BatchTranscriptionProvider(TranscriptionProvider):
    """Extended interface for providers that support batch transcription"""
    
    @abstractmethod
    async def submit_batch(self, requests: List[TranscriptionRequest]) -> Result[List[str], str]:
        """Submit multiple transcription requests as a batch"""
        pass
    
    @abstractmethod
    async def get_batch_status(self, batch_id: str) -> Result[Dict[str, TranscriptionStatus], str]:
        """Get status of all requests in a batch"""
        pass
    
    @abstractmethod
    async def get_batch_results(self, batch_id: str) -> Result[List[TranscriptionResult], str]:
        """Get results of all completed requests in a batch"""
        pass

class TranscriptionProviderRegistry:
    """Registry for managing multiple transcription providers"""
    
    def __init__(self):
        self._providers: Dict[str, TranscriptionProvider] = {}
        self._default_provider: Optional[str] = None
    
    def register_provider(self, name: str, provider: TranscriptionProvider) -> Result[None, str]:
        """Register a transcription provider"""
        try:
            self._providers[name] = provider
            
            # Set as default if it's the first provider
            if self._default_provider is None:
                self._default_provider = name
            
            logger.info(f"Registered transcription provider: {name}")
            return Success(None)
            
        except Exception as e:
            logger.error(f"Failed to register provider {name}: {e}")
            return Failure(f"Provider registration failed: {str(e)}")
    
    def unregister_provider(self, name: str) -> Result[None, str]:
        """Unregister a transcription provider"""
        try:
            if name not in self._providers:
                return Failure(f"Provider {name} not found")
            
            del self._providers[name]
            
            # Update default provider if needed
            if self._default_provider == name:
                self._default_provider = next(iter(self._providers.keys()), None)
            
            logger.info(f"Unregistered transcription provider: {name}")
            return Success(None)
            
        except Exception as e:
            logger.error(f"Failed to unregister provider {name}: {e}")
            return Failure(f"Provider unregistration failed: {str(e)}")
    
    def get_provider(self, name: Optional[str] = None) -> Result[TranscriptionProvider, str]:
        """Get a transcription provider by name (or default)"""
        provider_name = name or self._default_provider
        
        if not provider_name:
            return Failure("No providers registered")
        
        if provider_name not in self._providers:
            return Failure(f"Provider {provider_name} not found")
        
        return Success(self._providers[provider_name])
    
    def set_default_provider(self, name: str) -> Result[None, str]:
        """Set the default provider"""
        if name not in self._providers:
            return Failure(f"Provider {name} not found")
        
        self._default_provider = name
        logger.info(f"Set default transcription provider: {name}")
        return Success(None)
    
    def list_providers(self) -> List[str]:
        """List all registered provider names"""
        return list(self._providers.keys())
    
    def get_default_provider_name(self) -> Optional[str]:
        """Get the name of the default provider"""
        return self._default_provider
    
    async def initialize_all(self) -> Result[Dict[str, bool], str]:
        """Initialize all registered providers"""
        results = {}
        
        for name, provider in self._providers.items():
            try:
                init_result = await provider.initialize()
                results[name] = init_result.is_success()
                
                if init_result.is_failure():
                    logger.error(f"Failed to initialize provider {name}: {init_result.get_error()}")
                else:
                    logger.info(f"Successfully initialized provider: {name}")
                    
            except Exception as e:
                logger.error(f"Exception initializing provider {name}: {e}")
                results[name] = False
        
        return Success(results)
    
    async def shutdown_all(self) -> Result[Dict[str, bool], str]:
        """Shutdown all registered providers"""
        results = {}
        
        for name, provider in self._providers.items():
            try:
                shutdown_result = await provider.shutdown()
                results[name] = shutdown_result.is_success()
                
                if shutdown_result.is_failure():
                    logger.error(f"Failed to shutdown provider {name}: {shutdown_result.get_error()}")
                else:
                    logger.info(f"Successfully shutdown provider: {name}")
                    
            except Exception as e:
                logger.error(f"Exception shutting down provider {name}: {e}")
                results[name] = False
        
        return Success(results)

# Global registry instance
transcription_registry = TranscriptionProviderRegistry()

def get_transcription_registry() -> TranscriptionProviderRegistry:
    """Get the global transcription provider registry"""
    return transcription_registry
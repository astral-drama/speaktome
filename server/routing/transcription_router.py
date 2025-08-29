#!/usr/bin/env python3

"""
Transcription Router

Handles HTTP routing logic for transcription endpoints.
Separates route definitions from business logic for better testability and maintenance.
"""

import logging
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, File, UploadFile, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..functional.result_monad import Result, Success, Failure
from ..validation import FileValidator, ValidationResult, create_audio_validator
from ..providers.transcription_provider import TranscriptionStatus, TranscriptionResult

logger = logging.getLogger(__name__)

# Pydantic models for API
class TranscriptionRequest(BaseModel):
    """Request model for transcription"""
    model: str = Field(default="base", description="Whisper model to use")
    language: Optional[str] = Field(default=None, description="Language code (auto-detect if None)")

class TranscriptionResponse(BaseModel):
    """Response model for transcription results"""
    id: str
    status: str
    text: Optional[str] = None
    language: Optional[str] = None
    processing_time: Optional[float] = None
    error: Optional[str] = None

class ModelInfo(BaseModel):
    """Model information for available models endpoint"""
    name: str
    size_mb: Optional[int] = None
    description: str

class TranscriptionRouter:
    """Router class for transcription endpoints"""
    
    def __init__(self, 
                 available_models: List[str], 
                 temp_dir: str,
                 file_validator: Optional[FileValidator] = None):
        self.available_models = available_models
        self.temp_dir = temp_dir
        self.file_validator = file_validator or create_audio_validator()
        
        # Create FastAPI router
        self.router = APIRouter(
            prefix="/api",
            tags=["transcription"],
            responses={404: {"description": "Not found"}}
        )
        
        # Register routes
        self._register_routes()
        
        logger.info(f"TranscriptionRouter initialized with models: {available_models}")
    
    def _register_routes(self) -> None:
        """Register all transcription routes"""
        
        @self.router.get("/models", response_model=List[ModelInfo])
        async def get_available_models():
            """Get list of available Whisper models"""
            return await self._handle_get_models()
        
        @self.router.post("/transcribe", response_model=TranscriptionResponse)
        async def transcribe_audio(
            file: UploadFile = File(...),
            model: str = "base",
            language: Optional[str] = None
        ):
            """Upload audio file for transcription"""
            return await self._handle_transcription_request(file, model, language)
        
        @self.router.get("/transcribe/{request_id}", response_model=TranscriptionResponse)
        async def get_transcription_result(request_id: str):
            """Get transcription result by request ID"""
            return await self._handle_get_result(request_id)
        
        @self.router.delete("/transcribe/{request_id}")
        async def cancel_transcription(request_id: str):
            """Cancel a transcription request"""
            return await self._handle_cancel_request(request_id)
    
    async def _handle_get_models(self) -> List[ModelInfo]:
        """Handle getting available models"""
        model_info = {
            "tiny": {"size_mb": 39, "description": "Fastest, least accurate model"},
            "base": {"size_mb": 74, "description": "Good balance of speed and accuracy"}, 
            "small": {"size_mb": 244, "description": "Better accuracy, slower processing"},
            "medium": {"size_mb": 769, "description": "High accuracy model"},
            "large": {"size_mb": 1550, "description": "Best accuracy, slowest processing"}
        }
        
        return [
            ModelInfo(
                name=model,
                size_mb=info["size_mb"],
                description=info["description"]
            )
            for model, info in model_info.items()
            if model in self.available_models
        ]
    
    async def _handle_transcription_request(self, 
                                          file: UploadFile, 
                                          model: str, 
                                          language: Optional[str]) -> TranscriptionResponse:
        """Handle transcription request with validation and processing"""
        
        # Validate model
        model_validation = self._validate_model(model)
        if model_validation.is_failure():
            raise HTTPException(
                status_code=400,
                detail=model_validation.get_error()
            )
        
        # Validate file
        file_validation_result = await self.file_validator.validate_upload_file(file)
        if file_validation_result.is_failure():
            raise HTTPException(
                status_code=400,
                detail=file_validation_result.get_error()
            )
        
        try:
            # Save uploaded file
            file_save_result = await self._save_uploaded_file(file, file_validation_result.get_value())
            if file_save_result.is_failure():
                raise HTTPException(
                    status_code=500,
                    detail=file_save_result.get_error()
                )
            
            file_path = file_save_result.get_value()
            
            # Submit transcription request
            request_id = await transcription_service.submit_transcription(
                audio_file_path=file_path,
                model=model,
                language=language
            )
            
            logger.info(f"Transcription request submitted: {request_id} for file {file.filename}")
            
            return TranscriptionResponse(
                id=request_id,
                status=TranscriptionStatus.PENDING.value
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error in transcription request: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def _handle_get_result(self, request_id: str) -> TranscriptionResponse:
        """Handle getting transcription result"""
        
        result = await transcription_service.get_result(request_id)
        if not result:
            # Check if request exists but not completed
            status = await transcription_service.get_status(request_id)
            if status:
                return TranscriptionResponse(
                    id=request_id,
                    status=status.value
                )
            else:
                raise HTTPException(
                    status_code=404,
                    detail="Transcription request not found"
                )
        
        return TranscriptionResponse(
            id=result.id,
            status=result.status.value,
            text=result.text,
            language=result.language,
            processing_time=result.processing_time,
            error=result.error
        )
    
    async def _handle_cancel_request(self, request_id: str) -> Dict[str, str]:
        """Handle canceling a transcription request"""
        
        success = await transcription_service.cancel_request(request_id)
        if not success:
            raise HTTPException(
                status_code=404,
                detail="Transcription request not found"
            )
        
        logger.info(f"Transcription request cancelled: {request_id}")
        return {"message": f"Transcription request {request_id} cancelled"}
    
    def _validate_model(self, model: str) -> Result[str, str]:
        """Validate the requested model"""
        if model not in self.available_models:
            return Failure(
                f"Invalid model '{model}'. Available models: {', '.join(self.available_models)}"
            )
        return Success(model)
    
    async def _save_uploaded_file(self, 
                                upload_file: UploadFile, 
                                validation_result: ValidationResult) -> Result[str, str]:
        """Save uploaded file to temporary directory"""
        try:
            # Create unique filename
            file_extension = validation_result.extension or "unknown"
            unique_filename = f"{uuid.uuid4()}.{file_extension}"
            file_path = Path(self.temp_dir) / unique_filename
            
            # Ensure temp directory exists
            Path(self.temp_dir).mkdir(parents=True, exist_ok=True)
            
            # Save file
            content = await upload_file.read()
            with open(file_path, "wb") as f:
                f.write(content)
            
            logger.info(f"Saved uploaded file: {file_path} ({len(content)} bytes)")
            return Success(str(file_path))
            
        except Exception as e:
            logger.error(f"Failed to save uploaded file: {e}")
            return Failure(f"File save failed: {str(e)}")
    
    def get_router(self) -> APIRouter:
        """Get the configured FastAPI router"""
        return self.router

# Factory function for creating transcription router
def create_transcription_router(available_models: List[str], 
                              temp_dir: str,
                              max_file_size_mb: float = 50.0) -> TranscriptionRouter:
    """Create a transcription router with default configuration"""
    
    file_validator = create_audio_validator(max_size_mb=max_file_size_mb)
    
    return TranscriptionRouter(
        available_models=available_models,
        temp_dir=temp_dir,
        file_validator=file_validator
    )
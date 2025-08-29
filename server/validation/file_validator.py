#!/usr/bin/env python3

"""
File Validator

Handles file validation logic including size, format, and content validation.
Provides composable validation pipeline using Result monads.
"""

import logging
import mimetypes
import os
from pathlib import Path
from typing import List, Optional, Dict, Any, Callable
from dataclasses import dataclass
from enum import Enum

from fastapi import UploadFile

from ..functional.result_monad import Result, Success, Failure, traverse

logger = logging.getLogger(__name__)

class FileValidationError(Enum):
    """File validation error types"""
    FILE_TOO_LARGE = "file_too_large"
    UNSUPPORTED_FORMAT = "unsupported_format"
    INVALID_MIME_TYPE = "invalid_mime_type"
    FILE_CORRUPTED = "file_corrupted"
    MISSING_FILE = "missing_file"
    INVALID_EXTENSION = "invalid_extension"
    SECURITY_RISK = "security_risk"

@dataclass(frozen=True)
class FileValidationConfig:
    """Configuration for file validation"""
    max_file_size: int = 50 * 1024 * 1024  # 50MB default
    supported_extensions: List[str] = None
    supported_mime_types: List[str] = None
    allowed_mime_patterns: List[str] = None
    security_scan_enabled: bool = True
    content_validation_enabled: bool = False
    
    def __post_init__(self):
        # Set default audio formats if none provided
        if self.supported_extensions is None:
            object.__setattr__(self, 'supported_extensions', [
                'wav', 'wave', 'mp3', 'flac', 'm4a', 'webm', 'ogg', 'mp4'
            ])
        
        if self.supported_mime_types is None:
            object.__setattr__(self, 'supported_mime_types', [
                'audio/wav', 'audio/wave', 'audio/x-wav',
                'audio/mpeg', 'audio/mp3', 
                'audio/flac',
                'audio/m4a', 'audio/x-m4a',
                'audio/webm',
                'audio/ogg',
                'audio/mp4'
            ])

@dataclass(frozen=True)
class ValidationResult:
    """Result of file validation with metadata"""
    is_valid: bool
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    extension: Optional[str] = None
    detected_format: Optional[str] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            object.__setattr__(self, 'metadata', {})

# Type alias for validation functions
ValidationFunction = Callable[[UploadFile, FileValidationConfig], Result[ValidationResult, str]]

class FileValidator:
    """Composable file validator using functional validation pipeline"""
    
    def __init__(self, config: Optional[FileValidationConfig] = None):
        self.config = config or FileValidationConfig()
        self._validators: List[ValidationFunction] = []
        self._setup_default_validators()
    
    def _setup_default_validators(self) -> None:
        """Setup default validation pipeline"""
        self.add_validator(self._validate_file_exists)
        self.add_validator(self._validate_file_size)
        self.add_validator(self._validate_file_extension)
        self.add_validator(self._validate_mime_type)
        
        if self.config.security_scan_enabled:
            self.add_validator(self._validate_security)
        
        if self.config.content_validation_enabled:
            self.add_validator(self._validate_content)
    
    def add_validator(self, validator: ValidationFunction) -> 'FileValidator':
        """Add a validation function to the pipeline"""
        self._validators.append(validator)
        return self
    
    def remove_validator(self, validator: ValidationFunction) -> 'FileValidator':
        """Remove a validation function from the pipeline"""
        if validator in self._validators:
            self._validators.remove(validator)
        return self
    
    async def validate_upload_file(self, upload_file: UploadFile) -> Result[ValidationResult, str]:
        """Validate an uploaded file through the validation pipeline"""
        try:
            # Run all validators in sequence
            validation_results = []
            
            for validator in self._validators:
                result = validator(upload_file, self.config)
                if result.is_failure():
                    logger.warning(f"Validation failed: {result.get_error()}")
                    return result
                
                validation_results.append(result.get_value())
            
            # Combine all validation results
            final_result = self._combine_validation_results(validation_results)
            
            logger.info(f"File validation passed: {upload_file.filename} ({final_result.file_size} bytes)")
            return Success(final_result)
            
        except Exception as e:
            logger.error(f"File validation error: {e}")
            return Failure(f"Validation process failed: {str(e)}")
    
    async def validate_file_path(self, file_path: str) -> Result[ValidationResult, str]:
        """Validate a file by path"""
        try:
            if not os.path.exists(file_path):
                return Failure(f"File not found: {file_path}")
            
            path = Path(file_path)
            file_size = path.stat().st_size
            
            # Create a mock UploadFile-like object for validation
            class FileInfo:
                def __init__(self, path: Path):
                    self.filename = path.name
                    self.size = file_size
                    self.content_type = mimetypes.guess_type(str(path))[0]
            
            file_info = FileInfo(path)
            
            # Run validation pipeline
            validation_results = []
            for validator in self._validators:
                result = validator(file_info, self.config)
                if result.is_failure():
                    return result
                validation_results.append(result.get_value())
            
            final_result = self._combine_validation_results(validation_results)
            final_result = ValidationResult(
                is_valid=final_result.is_valid,
                file_path=file_path,
                file_size=file_size,
                mime_type=final_result.mime_type,
                extension=final_result.extension,
                detected_format=final_result.detected_format,
                metadata=final_result.metadata
            )
            
            return Success(final_result)
            
        except Exception as e:
            logger.error(f"File path validation error: {e}")
            return Failure(f"Path validation failed: {str(e)}")
    
    def _validate_file_exists(self, file: UploadFile, config: FileValidationConfig) -> Result[ValidationResult, str]:
        """Validate that file exists and is accessible"""
        if not file:
            return Failure("No file provided")
        
        if not file.filename:
            return Failure("File has no name")
        
        return Success(ValidationResult(
            is_valid=True,
            metadata={"validation_step": "file_exists"}
        ))
    
    def _validate_file_size(self, file: UploadFile, config: FileValidationConfig) -> Result[ValidationResult, str]:
        """Validate file size against limits"""
        file_size = getattr(file, 'size', None)
        
        if file_size is None:
            # Try to determine size if not available
            logger.warning("File size not available, skipping size validation")
            return Success(ValidationResult(
                is_valid=True,
                metadata={"validation_step": "file_size", "size_unknown": True}
            ))
        
        if file_size > config.max_file_size:
            max_mb = config.max_file_size / (1024 * 1024)
            actual_mb = file_size / (1024 * 1024)
            return Failure(
                f"File too large: {actual_mb:.1f}MB exceeds limit of {max_mb:.1f}MB"
            )
        
        return Success(ValidationResult(
            is_valid=True,
            file_size=file_size,
            metadata={"validation_step": "file_size"}
        ))
    
    def _validate_file_extension(self, file: UploadFile, config: FileValidationConfig) -> Result[ValidationResult, str]:
        """Validate file extension"""
        if not file.filename:
            return Failure("Cannot validate extension: no filename")
        
        extension = Path(file.filename).suffix.lower().lstrip('.')
        
        if not extension:
            return Failure("File has no extension")
        
        if extension not in config.supported_extensions:
            return Failure(
                f"Unsupported file extension '.{extension}'. "
                f"Supported formats: {', '.join(config.supported_extensions)}"
            )
        
        return Success(ValidationResult(
            is_valid=True,
            extension=extension,
            metadata={"validation_step": "file_extension"}
        ))
    
    def _validate_mime_type(self, file: UploadFile, config: FileValidationConfig) -> Result[ValidationResult, str]:
        """Validate MIME type"""
        mime_type = file.content_type
        
        if not mime_type:
            # Try to guess MIME type from filename
            if file.filename:
                guessed_type = mimetypes.guess_type(file.filename)[0]
                if guessed_type:
                    mime_type = guessed_type
                    logger.info(f"Guessed MIME type: {mime_type}")
        
        if not mime_type:
            return Failure("Cannot determine file MIME type")
        
        # Check against supported MIME types
        if mime_type not in config.supported_mime_types:
            # Check against patterns if provided
            if config.allowed_mime_patterns:
                for pattern in config.allowed_mime_patterns:
                    if pattern in mime_type:
                        break
                else:
                    return Failure(
                        f"Unsupported MIME type '{mime_type}'. "
                        f"Supported types: {', '.join(config.supported_mime_types)}"
                    )
            else:
                return Failure(
                    f"Unsupported MIME type '{mime_type}'. "
                    f"Supported types: {', '.join(config.supported_mime_types)}"
                )
        
        # Detect format from MIME type
        detected_format = self._detect_format_from_mime(mime_type)
        
        return Success(ValidationResult(
            is_valid=True,
            mime_type=mime_type,
            detected_format=detected_format,
            metadata={"validation_step": "mime_type"}
        ))
    
    def _validate_security(self, file: UploadFile, config: FileValidationConfig) -> Result[ValidationResult, str]:
        """Basic security validation"""
        if not file.filename:
            return Success(ValidationResult(
                is_valid=True,
                metadata={"validation_step": "security", "filename_missing": True}
            ))
        
        filename = file.filename.lower()
        
        # Check for suspicious file extensions
        suspicious_extensions = ['.exe', '.bat', '.cmd', '.com', '.scr', '.pif', '.js', '.vbs']
        if any(filename.endswith(ext) for ext in suspicious_extensions):
            return Failure(f"Potentially dangerous file type detected: {filename}")
        
        # Check for path traversal attempts
        if '..' in filename or '/' in filename or '\\' in filename:
            return Failure("Invalid filename: path traversal detected")
        
        # Check filename length
        if len(filename) > 255:
            return Failure("Filename too long")
        
        return Success(ValidationResult(
            is_valid=True,
            metadata={"validation_step": "security"}
        ))
    
    def _validate_content(self, file: UploadFile, config: FileValidationConfig) -> Result[ValidationResult, str]:
        """Validate file content (placeholder for future implementation)"""
        # This would implement actual content validation
        # For audio files: check headers, validate format structure, etc.
        
        return Success(ValidationResult(
            is_valid=True,
            metadata={"validation_step": "content", "implemented": False}
        ))
    
    def _combine_validation_results(self, results: List[ValidationResult]) -> ValidationResult:
        """Combine multiple validation results into a single result"""
        if not results:
            return ValidationResult(is_valid=False)
        
        # Merge all metadata
        combined_metadata = {}
        file_size = None
        mime_type = None
        extension = None
        detected_format = None
        file_path = None
        
        for result in results:
            combined_metadata.update(result.metadata)
            if result.file_size is not None:
                file_size = result.file_size
            if result.mime_type is not None:
                mime_type = result.mime_type
            if result.extension is not None:
                extension = result.extension
            if result.detected_format is not None:
                detected_format = result.detected_format
            if result.file_path is not None:
                file_path = result.file_path
        
        return ValidationResult(
            is_valid=True,  # All validations passed if we got here
            file_path=file_path,
            file_size=file_size,
            mime_type=mime_type,
            extension=extension,
            detected_format=detected_format,
            metadata=combined_metadata
        )
    
    def _detect_format_from_mime(self, mime_type: str) -> str:
        """Detect audio format from MIME type"""
        mime_to_format = {
            'audio/wav': 'wav',
            'audio/wave': 'wav',
            'audio/x-wav': 'wav',
            'audio/mpeg': 'mp3',
            'audio/mp3': 'mp3',
            'audio/flac': 'flac',
            'audio/m4a': 'm4a',
            'audio/x-m4a': 'm4a',
            'audio/webm': 'webm',
            'audio/ogg': 'ogg',
            'audio/mp4': 'mp4'
        }
        
        return mime_to_format.get(mime_type, 'unknown')

# Factory function for creating validators
def create_audio_validator(max_size_mb: float = 50.0, additional_formats: List[str] = None) -> FileValidator:
    """Create a file validator configured for audio files"""
    additional_formats = additional_formats or []
    
    config = FileValidationConfig(
        max_file_size=int(max_size_mb * 1024 * 1024),
        supported_extensions=['wav', 'wave', 'mp3', 'flac', 'm4a', 'webm', 'ogg', 'mp4'] + additional_formats,
        security_scan_enabled=True,
        content_validation_enabled=False
    )
    
    return FileValidator(config)

def create_strict_validator(max_size_mb: float = 10.0) -> FileValidator:
    """Create a strict file validator with content validation"""
    config = FileValidationConfig(
        max_file_size=int(max_size_mb * 1024 * 1024),
        supported_extensions=['wav', 'mp3', 'flac'],  # Only common formats
        security_scan_enabled=True,
        content_validation_enabled=True
    )
    
    return FileValidator(config)
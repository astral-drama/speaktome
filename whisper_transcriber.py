#!/usr/bin/env python3

import whisper
import torch
import logging
from pathlib import Path
import time

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
)
logger = logging.getLogger(__name__)

class WhisperTranscriber:
    def __init__(self, model_size="base", device=None, language=None):
        """
        Initialize Whisper transcriber
        
        Args:
            model_size: Size of Whisper model ('tiny', 'base', 'small', 'medium', 'large')
            device: Device to use ('cuda', 'cpu', or None for auto-detection)
            language: Language code for transcription (None for auto-detection)
        """
        self.model_size = model_size
        self.language = language
        
        # Auto-detect device if not specified
        if device is None:
            if torch.cuda.is_available():
                self.device = "cuda"
                gpu_name = torch.cuda.get_device_name(0)
                logger.info(f"CUDA available - using GPU: {gpu_name}")
            else:
                self.device = "cpu"
                logger.warning("CUDA not available - using CPU")
        else:
            self.device = device
            
        logger.info(f"Initializing Whisper model - size={model_size}, device={self.device}")
        
        try:
            self.model = whisper.load_model(model_size, device=self.device)
            logger.info("Whisper model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            raise

    def transcribe_file(self, audio_file_path, **kwargs):
        """
        Transcribe audio file
        
        Args:
            audio_file_path: Path to audio file
            **kwargs: Additional arguments for whisper.transcribe()
            
        Returns:
            dict: Transcription result with text and metadata
        """
        if not Path(audio_file_path).exists():
            logger.error(f"Audio file not found: {audio_file_path}")
            return None
            
        logger.info(f"Starting transcription of {audio_file_path}")
        start_time = time.time()
        
        try:
            # Set default options
            options = {
                'language': self.language,
                'task': 'transcribe',
                'fp16': self.device == 'cuda',  # Use fp16 for GPU acceleration
                **kwargs
            }
            
            # Remove None values
            options = {k: v for k, v in options.items() if v is not None}
            
            logger.info(f"Transcription options: {options}")
            
            result = self.model.transcribe(str(audio_file_path), **options)
            
            duration = time.time() - start_time
            text = result.get('text', '').strip()
            detected_language = result.get('language', 'unknown')
            
            logger.info(f"Transcription completed in {duration:.2f}s")
            logger.info(f"Detected language: {detected_language}")
            logger.info(f"Transcribed text: '{text}'")
            
            return {
                'text': text,
                'language': detected_language,
                'duration': duration,
                'segments': result.get('segments', []),
                'audio_file': str(audio_file_path)
            }
            
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return None

    def get_available_models(self):
        """Get list of available Whisper model sizes"""
        models = ['tiny', 'base', 'small', 'medium', 'large']
        logger.info(f"Available Whisper models: {models}")
        return models

    def get_device_info(self):
        """Get information about the current device"""
        info = {
            'device': self.device,
            'cuda_available': torch.cuda.is_available(),
        }
        
        if torch.cuda.is_available():
            info['gpu_name'] = torch.cuda.get_device_name(0)
            info['gpu_memory'] = torch.cuda.get_device_properties(0).total_memory / (1024**3)  # GB
            info['gpu_memory_allocated'] = torch.cuda.memory_allocated(0) / (1024**3)  # GB
            
        logger.info(f"Device info: {info}")
        return info

    def set_language(self, language):
        """Set the language for transcription"""
        self.language = language
        logger.info(f"Language set to: {language}")

    def cleanup(self):
        """Clean up resources"""
        if hasattr(self, 'model'):
            del self.model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        logger.info("WhisperTranscriber cleanup completed")
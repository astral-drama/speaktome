#!/usr/bin/env python3

import asyncio
import logging
import os
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Tuple
import wave
import subprocess

logger = logging.getLogger(__name__)

class AudioProcessor:
    """Audio processing utilities for format conversion and optimization"""
    
    def __init__(self, target_sample_rate: int = 16000, target_channels: int = 1):
        self.target_sample_rate = target_sample_rate
        self.target_channels = target_channels
        
        # Check if ffmpeg is available
        self.ffmpeg_available = self._check_ffmpeg()
        if not self.ffmpeg_available:
            logger.warning("FFmpeg not found. Audio conversion capabilities limited.")

    def _check_ffmpeg(self) -> bool:
        """Check if ffmpeg is available"""
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"], 
                capture_output=True, 
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
            return False

    async def convert_to_wav(
        self, 
        input_path: str, 
        output_path: Optional[str] = None,
        sample_rate: Optional[int] = None,
        channels: Optional[int] = None
    ) -> str:
        """
        Convert audio file to WAV format optimized for Whisper
        
        Args:
            input_path: Path to input audio file
            output_path: Path for output WAV file (auto-generated if None)
            sample_rate: Target sample rate (uses default if None)
            channels: Target channels (uses default if None)
            
        Returns:
            Path to converted WAV file
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input file not found: {input_path}")
        
        # Use provided values or defaults
        target_sr = sample_rate or self.target_sample_rate
        target_ch = channels or self.target_channels
        
        # Generate output path if not provided
        if output_path is None:
            input_file = Path(input_path)
            output_path = str(input_file.with_suffix('.wav'))
        
        # Check if input is already WAV with correct format
        if await self._is_correct_format(input_path, target_sr, target_ch):
            logger.info(f"Audio file already in correct format: {input_path}")
            if input_path != output_path:
                shutil.copy2(input_path, output_path)
            return output_path
        
        logger.info(f"Converting {input_path} to WAV format")
        
        if self.ffmpeg_available:
            await self._convert_with_ffmpeg(input_path, output_path, target_sr, target_ch)
        else:
            # Fallback conversion (limited format support)
            await self._convert_with_wave(input_path, output_path)
        
        logger.info(f"Audio conversion completed: {output_path}")
        return output_path

    async def _convert_with_ffmpeg(
        self, 
        input_path: str, 
        output_path: str, 
        sample_rate: int, 
        channels: int
    ):
        """Convert audio using FFmpeg"""
        cmd = [
            "ffmpeg",
            "-y",  # Overwrite output files
            "-i", input_path,
            "-acodec", "pcm_s16le",  # 16-bit PCM
            "-ar", str(sample_rate),  # Sample rate
            "-ac", str(channels),     # Number of channels
            "-f", "wav",             # Output format
            output_path
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown FFmpeg error"
                raise RuntimeError(f"FFmpeg conversion failed: {error_msg}")
                
            logger.debug(f"FFmpeg conversion successful: {output_path}")
            
        except Exception as e:
            logger.error(f"FFmpeg conversion error: {e}")
            raise

    async def _convert_with_wave(self, input_path: str, output_path: str):
        """Fallback conversion using wave module (WAV files only)"""
        try:
            # This is a simple copy for WAV files
            # More sophisticated conversion would require additional libraries
            if not input_path.lower().endswith('.wav'):
                raise RuntimeError("Cannot convert non-WAV files without FFmpeg")
            
            shutil.copy2(input_path, output_path)
            logger.debug(f"Wave module conversion: copied {input_path} to {output_path}")
            
        except Exception as e:
            logger.error(f"Wave conversion error: {e}")
            raise

    async def _is_correct_format(
        self, 
        file_path: str, 
        target_sample_rate: int, 
        target_channels: int
    ) -> bool:
        """Check if audio file is already in the correct format"""
        try:
            if not file_path.lower().endswith('.wav'):
                return False
            
            # Use ffprobe to get audio information
            if self.ffmpeg_available:
                cmd = [
                    "ffprobe",
                    "-v", "quiet",
                    "-print_format", "json",
                    "-show_streams",
                    file_path
                ]
                
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, _ = await process.communicate()
                
                if process.returncode == 0:
                    import json
                    data = json.loads(stdout.decode())
                    
                    for stream in data.get('streams', []):
                        if stream.get('codec_type') == 'audio':
                            sample_rate = int(stream.get('sample_rate', 0))
                            channels = int(stream.get('channels', 0))
                            
                            return (
                                sample_rate == target_sample_rate and 
                                channels == target_channels
                            )
            
            # Fallback: use wave module for WAV files
            with wave.open(file_path, 'rb') as wav_file:
                return (
                    wav_file.getframerate() == target_sample_rate and
                    wav_file.getnchannels() == target_channels
                )
                
        except Exception as e:
            logger.debug(f"Error checking audio format: {e}")
            return False

    async def get_audio_info(self, file_path: str) -> dict:
        """Get detailed information about an audio file"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Audio file not found: {file_path}")
        
        info = {
            'file_path': file_path,
            'file_size': os.path.getsize(file_path),
            'format': Path(file_path).suffix.lower().lstrip('.'),
        }
        
        try:
            if self.ffmpeg_available:
                # Use ffprobe for detailed information
                cmd = [
                    "ffprobe",
                    "-v", "quiet",
                    "-print_format", "json",
                    "-show_streams",
                    "-show_format",
                    file_path
                ]
                
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, _ = await process.communicate()
                
                if process.returncode == 0:
                    import json
                    data = json.loads(stdout.decode())
                    
                    # Extract format information
                    format_info = data.get('format', {})
                    info['duration'] = float(format_info.get('duration', 0))
                    info['bitrate'] = int(format_info.get('bit_rate', 0))
                    
                    # Extract audio stream information
                    for stream in data.get('streams', []):
                        if stream.get('codec_type') == 'audio':
                            info['sample_rate'] = int(stream.get('sample_rate', 0))
                            info['channels'] = int(stream.get('channels', 0))
                            info['codec'] = stream.get('codec_name', 'unknown')
                            info['bits_per_sample'] = int(stream.get('bits_per_raw_sample', 0))
                            break
            
            elif file_path.lower().endswith('.wav'):
                # Fallback for WAV files using wave module
                with wave.open(file_path, 'rb') as wav_file:
                    info['sample_rate'] = wav_file.getframerate()
                    info['channels'] = wav_file.getnchannels()
                    info['bits_per_sample'] = wav_file.getsampwidth() * 8
                    info['duration'] = wav_file.getnframes() / wav_file.getframerate()
                    info['codec'] = 'pcm'
            
        except Exception as e:
            logger.warning(f"Could not extract audio info for {file_path}: {e}")
            info['error'] = str(e)
        
        return info

    async def validate_audio_file(self, file_path: str) -> Tuple[bool, str]:
        """
        Validate audio file for processing
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            if not os.path.exists(file_path):
                return False, "File does not exist"
            
            if os.path.getsize(file_path) == 0:
                return False, "File is empty"
            
            # Get audio information
            info = await self.get_audio_info(file_path)
            
            if 'error' in info:
                return False, f"Could not read audio file: {info['error']}"
            
            # Check duration (must be at least 0.1 seconds, max 10 minutes for reasonable processing)
            duration = info.get('duration', 0)
            if duration < 0.1:
                return False, "Audio file too short (minimum 0.1 seconds)"
            
            if duration > 600:  # 10 minutes
                return False, "Audio file too long (maximum 10 minutes)"
            
            # Check sample rate (must be positive)
            sample_rate = info.get('sample_rate', 0)
            if sample_rate <= 0:
                return False, "Invalid sample rate"
            
            # Check channels (must be positive)
            channels = info.get('channels', 0)
            if channels <= 0:
                return False, "Invalid number of channels"
            
            return True, "Audio file is valid"
            
        except Exception as e:
            logger.error(f"Error validating audio file {file_path}: {e}")
            return False, f"Validation error: {str(e)}"

    async def preprocess_for_whisper(self, input_path: str) -> str:
        """
        Preprocess audio file for optimal Whisper transcription
        
        Returns:
            Path to preprocessed audio file
        """
        # Generate temporary output path
        temp_dir = tempfile.gettempdir()
        output_filename = f"whisper_preprocessed_{os.path.basename(input_path)}"
        output_path = os.path.join(temp_dir, f"{Path(output_filename).stem}.wav")
        
        try:
            # Convert to Whisper's preferred format: 16kHz mono WAV
            converted_path = await self.convert_to_wav(
                input_path=input_path,
                output_path=output_path,
                sample_rate=16000,
                channels=1
            )
            
            logger.info(f"Audio preprocessed for Whisper: {converted_path}")
            return converted_path
            
        except Exception as e:
            logger.error(f"Error preprocessing audio for Whisper: {e}")
            # Return original path if preprocessing fails
            return input_path

    def cleanup_temp_file(self, file_path: str):
        """Clean up temporary audio file"""
        try:
            if os.path.exists(file_path):
                os.unlink(file_path)
                logger.debug(f"Cleaned up temporary file: {file_path}")
        except Exception as e:
            logger.warning(f"Could not clean up temporary file {file_path}: {e}")

# Global audio processor instance
audio_processor = AudioProcessor()
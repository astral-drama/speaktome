#!/usr/bin/env python3

"""
Recording Storage Manager

Manages temporary storage of audio recordings for the session lifetime.
Recordings are saved to disk and cleaned up when the application exits.
"""

import os
import tempfile
import logging
import time
from pathlib import Path
from typing import Dict, Optional
from dataclasses import dataclass

from shared.functional import Result, Success, Failure, from_callable

logger = logging.getLogger(__name__)


@dataclass
class StoredRecording:
    """Information about a stored recording"""
    recording_id: str
    file_path: str
    timestamp: float
    duration_seconds: float
    format: str = "wav"


class RecordingStorage:
    """
    Session-lifetime storage for audio recordings

    Saves recordings to temporary directory and maintains index.
    Cleans up all recordings when cleanup() is called.
    """

    def __init__(self, base_dir: Optional[str] = None):
        """
        Initialize recording storage

        Args:
            base_dir: Optional base directory for recordings. If None, uses system temp.
        """
        if base_dir:
            self.storage_dir = Path(base_dir)
        else:
            # Create temp directory for this session
            self.storage_dir = Path(tempfile.mkdtemp(prefix="speaktome_recordings_"))

        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.recordings: Dict[str, StoredRecording] = {}

        logger.info(f"Recording storage initialized at: {self.storage_dir}")

    def save_recording(self, recording_id: str, audio_data: bytes,
                      duration_seconds: float, audio_format: str = "wav") -> Result[StoredRecording, Exception]:
        """
        Save audio recording to disk

        Args:
            recording_id: Unique identifier for this recording
            audio_data: Audio data bytes
            duration_seconds: Duration of recording
            audio_format: Audio format (default: wav)

        Returns:
            Result containing StoredRecording info or error
        """
        def _save():
            # Generate filename
            timestamp = time.time()
            filename = f"{recording_id}_{int(timestamp)}.{audio_format}"
            file_path = self.storage_dir / filename

            # Write audio data to file
            with open(file_path, 'wb') as f:
                f.write(audio_data)

            # Create recording info
            stored = StoredRecording(
                recording_id=recording_id,
                file_path=str(file_path),
                timestamp=timestamp,
                duration_seconds=duration_seconds,
                format=audio_format
            )

            # Store in index
            self.recordings[recording_id] = stored

            logger.info(f"Saved recording {recording_id} to {file_path} ({len(audio_data)} bytes)")
            return stored

        return from_callable(_save)

    def get_recording(self, recording_id: str) -> Result[StoredRecording, str]:
        """
        Get stored recording info

        Args:
            recording_id: Recording identifier

        Returns:
            Result containing StoredRecording or error message
        """
        if recording_id in self.recordings:
            return Success(self.recordings[recording_id])
        return Failure(f"Recording {recording_id} not found")

    def get_recording_data(self, recording_id: str) -> Result[bytes, Exception]:
        """
        Load recording audio data from disk

        Args:
            recording_id: Recording identifier

        Returns:
            Result containing audio bytes or error
        """
        recording_result = self.get_recording(recording_id)
        if recording_result.is_failure():
            return Failure(Exception(recording_result.error))

        recording = recording_result.value

        def _load():
            with open(recording.file_path, 'rb') as f:
                return f.read()

        return from_callable(_load)

    def delete_recording(self, recording_id: str) -> Result[None, Exception]:
        """
        Delete a specific recording

        Args:
            recording_id: Recording identifier

        Returns:
            Result indicating success or error
        """
        def _delete():
            if recording_id not in self.recordings:
                raise Exception(f"Recording {recording_id} not found")

            recording = self.recordings[recording_id]

            # Delete file
            file_path = Path(recording.file_path)
            if file_path.exists():
                file_path.unlink()

            # Remove from index
            del self.recordings[recording_id]

            logger.info(f"Deleted recording {recording_id}")

        return from_callable(_delete)

    def cleanup(self) -> Result[int, Exception]:
        """
        Clean up all recordings and temporary directory

        Returns:
            Result containing count of files deleted or error
        """
        def _cleanup():
            deleted_count = 0

            # Delete all recording files
            for recording_id in list(self.recordings.keys()):
                result = self.delete_recording(recording_id)
                if result.is_success():
                    deleted_count += 1
                else:
                    logger.warning(f"Failed to delete recording {recording_id}: {result.error}")

            # Remove storage directory if empty
            try:
                if self.storage_dir.exists():
                    # Remove any remaining files
                    for file in self.storage_dir.iterdir():
                        try:
                            file.unlink()
                            deleted_count += 1
                        except Exception as e:
                            logger.warning(f"Failed to delete file {file}: {e}")

                    # Remove directory
                    self.storage_dir.rmdir()
                    logger.info(f"Removed storage directory: {self.storage_dir}")
            except Exception as e:
                logger.warning(f"Failed to remove storage directory: {e}")

            logger.info(f"Recording storage cleanup completed: {deleted_count} files deleted")
            return deleted_count

        return from_callable(_cleanup)

    def get_storage_stats(self) -> Dict[str, any]:
        """Get statistics about stored recordings"""
        total_size = 0
        for recording in self.recordings.values():
            try:
                total_size += Path(recording.file_path).stat().st_size
            except:
                pass

        return {
            'recording_count': len(self.recordings),
            'total_size_bytes': total_size,
            'total_size_mb': total_size / (1024 * 1024),
            'storage_dir': str(self.storage_dir)
        }


# Global storage instance
_recording_storage: Optional[RecordingStorage] = None


def get_recording_storage(base_dir: Optional[str] = None) -> RecordingStorage:
    """Get global recording storage instance"""
    global _recording_storage

    if _recording_storage is None:
        _recording_storage = RecordingStorage(base_dir)

    return _recording_storage


def cleanup_recording_storage() -> Result[int, Exception]:
    """Clean up global recording storage"""
    global _recording_storage

    if _recording_storage is not None:
        result = _recording_storage.cleanup()
        _recording_storage = None
        return result

    return Success(0)

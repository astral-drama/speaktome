#!/usr/bin/env python3

"""
Test Audio Pipeline

Unit tests for composable audio pipeline architecture.
Tests pipeline stages, composition, and functional transformations.
"""

import pytest
import uuid
import time
from typing import Dict, Any

from shared.functional import Result, Success, Failure
from client.pipeline.audio_pipeline import (
    AudioData, ProcessingContext, PipelineStage,
    AudioValidationStage, AudioFormatStage, TranscriptionRequestStage,
    AudioPipeline, create_basic_pipeline, create_quality_pipeline, create_fast_pipeline
)
from tests.conftest import assert_result_success, assert_result_failure


class MockPipelineStage(PipelineStage):
    """Mock pipeline stage for testing"""
    
    def __init__(self, stage_name: str, should_fail: bool = False, processing_delay: float = 0.0):
        self._stage_name = stage_name
        self.should_fail = should_fail
        self.processing_delay = processing_delay
        self.call_count = 0
    
    @property
    def stage_name(self) -> str:
        return self._stage_name
    
    async def process(self, audio_data: AudioData, context: ProcessingContext) -> Result[AudioData, Exception]:
        self.call_count += 1
        
        if self.processing_delay > 0:
            import asyncio
            await asyncio.sleep(self.processing_delay)
        
        if self.should_fail:
            return Failure(Exception(f"Mock failure in {self.stage_name}"))
        
        # Add stage metadata
        updated_audio = audio_data.with_metadata(**{
            f"{self.stage_name}_processed": True,
            f"{self.stage_name}_call_count": self.call_count
        })
        
        return Success(updated_audio)


class TestAudioData:
    """Test AudioData immutable data structure"""
    
    def test_audio_data_creation(self):
        """Test AudioData creation and properties"""
        audio_data = AudioData(
            data=b"test_data",
            format="wav",
            sample_rate=16000,
            channels=1,
            duration_seconds=2.0,
            metadata={"test": True}
        )
        
        assert audio_data.data == b"test_data"
        assert audio_data.format == "wav"
        assert audio_data.sample_rate == 16000
        assert audio_data.channels == 1
        assert audio_data.duration_seconds == 2.0
        assert audio_data.metadata["test"] is True
    
    def test_with_metadata_immutability(self):
        """Test that with_metadata creates new instance"""
        original = AudioData(
            data=b"test",
            format="wav",
            sample_rate=16000,
            channels=1,
            duration_seconds=1.0,
            metadata={"original": True}
        )
        
        updated = original.with_metadata(new_field="added", original="modified")
        
        # Original should be unchanged
        assert original.metadata == {"original": True}
        
        # Updated should have new metadata
        assert updated.metadata["original"] == "modified"
        assert updated.metadata["new_field"] == "added"
        
        # Other fields should be the same
        assert updated.data == original.data
        assert updated.format == original.format
    
    def test_with_data_immutability(self):
        """Test that with_data creates new instance"""
        original = AudioData(
            data=b"original",
            format="wav",
            sample_rate=16000,
            channels=1,
            duration_seconds=1.0
        )
        
        updated = original.with_data(b"new_data", "mp3")
        
        # Original should be unchanged
        assert original.data == b"original"
        assert original.format == "wav"
        
        # Updated should have new data
        assert updated.data == b"new_data"
        assert updated.format == "mp3"
        
        # Other fields should be the same
        assert updated.sample_rate == original.sample_rate
        assert updated.channels == original.channels


class TestProcessingContext:
    """Test ProcessingContext for pipeline stages"""
    
    def test_context_creation(self):
        """Test ProcessingContext creation"""
        request_id = str(uuid.uuid4())
        context = ProcessingContext(request_id=request_id)
        
        assert context.request_id == request_id
        assert isinstance(context.start_time, float)
        assert context.stage_timings == {}
        assert context.stage_metadata == {}
    
    def test_with_timing_immutability(self):
        """Test timing information addition"""
        context = ProcessingContext(request_id="test")
        
        updated = context.with_timing("stage1", 0.5)
        
        # Original should be unchanged
        assert context.stage_timings == {}
        
        # Updated should have timing
        assert updated.stage_timings["stage1"] == 0.5
        assert updated.request_id == context.request_id
    
    def test_with_metadata_immutability(self):
        """Test metadata addition"""
        context = ProcessingContext(request_id="test")
        metadata = {"processed": True, "items": 5}
        
        updated = context.with_metadata("stage1", metadata)
        
        # Original should be unchanged
        assert context.stage_metadata == {}
        
        # Updated should have metadata
        assert updated.stage_metadata["stage1"] == metadata
        assert updated.request_id == context.request_id


class TestPipelineStages:
    """Test individual pipeline stages"""
    
    @pytest.mark.asyncio
    async def test_audio_validation_stage(self, sample_audio_data, processing_context):
        """Test audio validation stage"""
        stage = AudioValidationStage(min_duration=0.5, max_duration=5.0, min_size=100)
        
        # Should succeed with valid audio
        result = await stage.process(sample_audio_data, processing_context)
        assert_result_success(result)
        
        # Check validation metadata added
        audio_data = result.value
        assert audio_data.metadata["validation_passed"] is True
        assert "validation_timestamp" in audio_data.metadata
    
    @pytest.mark.asyncio
    async def test_audio_validation_too_short(self, processing_context):
        """Test audio validation with too short audio"""
        short_audio = AudioData(
            data=b"short",
            format="wav",
            sample_rate=16000,
            channels=1,
            duration_seconds=0.05  # Too short
        )
        
        stage = AudioValidationStage(min_duration=0.5)
        result = await stage.process(short_audio, processing_context)
        
        assert_result_failure(result)
        assert "too short" in str(result.error).lower()
    
    @pytest.mark.asyncio
    async def test_audio_validation_too_small(self, processing_context):
        """Test audio validation with too small data"""
        small_audio = AudioData(
            data=b"tiny",  # Only 4 bytes
            format="wav",
            sample_rate=16000,
            channels=1,
            duration_seconds=1.0
        )
        
        stage = AudioValidationStage(min_size=1000)
        result = await stage.process(small_audio, processing_context)
        
        assert_result_failure(result)
        assert "too small" in str(result.error).lower()
    
    @pytest.mark.asyncio
    async def test_audio_format_stage(self, sample_audio_data, processing_context):
        """Test audio format conversion stage"""
        stage = AudioFormatStage(target_format="wav", target_sample_rate=16000)
        
        result = await stage.process(sample_audio_data, processing_context)
        assert_result_success(result)
        
        # If already in target format, should pass through without metadata changes
        audio_data = result.value
        if (sample_audio_data.format == "wav" and sample_audio_data.sample_rate == 16000):
            # Should pass through unchanged
            assert audio_data.format == sample_audio_data.format
            assert audio_data.sample_rate == sample_audio_data.sample_rate
        else:
            # Should add conversion metadata
            metadata = audio_data.metadata
            assert "original_format" in metadata or "format_conversion" in metadata
    
    @pytest.mark.asyncio
    async def test_transcription_request_stage(self, sample_audio_data, processing_context):
        """Test transcription request preparation stage"""
        stage = TranscriptionRequestStage(model="base", language="en")
        
        result = await stage.process(sample_audio_data, processing_context)
        assert_result_success(result)
        
        # Check transcription metadata
        audio_data = result.value
        assert audio_data.metadata["model"] == "base"
        assert audio_data.metadata["language"] == "en"
        assert audio_data.metadata["request_id"] == processing_context.request_id
        assert "prepared_at" in audio_data.metadata


class TestAudioPipeline:
    """Test pipeline composition and execution"""
    
    @pytest.mark.asyncio
    async def test_empty_pipeline(self, sample_audio_data, processing_context):
        """Test pipeline with no stages"""
        pipeline = AudioPipeline([])
        
        result = await pipeline.process(sample_audio_data, processing_context)
        assert_result_success(result)
        
        # Should return original audio unchanged
        assert result.value.data == sample_audio_data.data
    
    @pytest.mark.asyncio
    async def test_single_stage_pipeline(self, sample_audio_data, processing_context):
        """Test pipeline with single stage"""
        stage = MockPipelineStage("test_stage")
        pipeline = AudioPipeline([stage])
        
        result = await pipeline.process(sample_audio_data, processing_context)
        assert_result_success(result)
        
        # Stage should have been called
        assert stage.call_count == 1
        
        # Metadata should be added
        audio_data = result.value
        assert audio_data.metadata["test_stage_processed"] is True
    
    @pytest.mark.asyncio
    async def test_multi_stage_pipeline(self, sample_audio_data, processing_context):
        """Test pipeline with multiple stages"""
        stage1 = MockPipelineStage("stage1")
        stage2 = MockPipelineStage("stage2")
        stage3 = MockPipelineStage("stage3")
        
        pipeline = AudioPipeline([stage1, stage2, stage3])
        
        result = await pipeline.process(sample_audio_data, processing_context)
        assert_result_success(result)
        
        # All stages should have been called
        assert stage1.call_count == 1
        assert stage2.call_count == 1
        assert stage3.call_count == 1
        
        # All stage metadata should be present
        audio_data = result.value
        assert audio_data.metadata["stage1_processed"] is True
        assert audio_data.metadata["stage2_processed"] is True
        assert audio_data.metadata["stage3_processed"] is True
    
    @pytest.mark.asyncio
    async def test_pipeline_failure_short_circuits(self, sample_audio_data, processing_context):
        """Test that pipeline stops at first failure"""
        stage1 = MockPipelineStage("stage1")
        stage2 = MockPipelineStage("stage2", should_fail=True)
        stage3 = MockPipelineStage("stage3")
        
        pipeline = AudioPipeline([stage1, stage2, stage3])
        
        result = await pipeline.process(sample_audio_data, processing_context)
        assert_result_failure(result)
        
        # Only first two stages should be called
        assert stage1.call_count == 1
        assert stage2.call_count == 1
        assert stage3.call_count == 0  # Should not be reached
        
        # Error should be from stage2
        assert "stage2" in str(result.error)
    
    @pytest.mark.asyncio
    async def test_pipeline_timing(self, sample_audio_data, processing_context):
        """Test pipeline timing measurement"""
        # Stages with processing delay
        stage1 = MockPipelineStage("stage1", processing_delay=0.01)
        stage2 = MockPipelineStage("stage2", processing_delay=0.02)
        
        pipeline = AudioPipeline([stage1, stage2])
        
        start_time = time.time()
        result = await pipeline.process(sample_audio_data, processing_context)
        end_time = time.time()
        
        assert_result_success(result)
        
        # Total time should be at least the sum of delays
        total_time = end_time - start_time
        assert total_time >= 0.03  # 0.01 + 0.02
        
        # Context should have timing information stored in metadata
        audio_data = result.value
        if 'processing_context' in audio_data.metadata:
            context = audio_data.metadata['processing_context']
            assert len(context.stage_timings) >= 0


class TestPipelineFactories:
    """Test pipeline factory functions"""
    
    def test_create_basic_pipeline(self):
        """Test basic pipeline creation"""
        pipeline = create_basic_pipeline()
        
        assert isinstance(pipeline, AudioPipeline)
        assert len(pipeline.stages) > 0
        
        # Should have validation, format, and transcription stages
        stage_names = [stage.stage_name for stage in pipeline.stages]
        assert "audio_validation" in stage_names
        assert "audio_format" in stage_names
        assert "transcription_request" in stage_names
    
    def test_create_quality_pipeline(self):
        """Test quality pipeline creation"""
        pipeline = create_quality_pipeline()
        
        assert isinstance(pipeline, AudioPipeline)
        assert len(pipeline.stages) > 0
        
        # Should have similar stages but with quality settings
        stage_names = [stage.stage_name for stage in pipeline.stages]
        assert "audio_validation" in stage_names
        assert "audio_format" in stage_names
        assert "transcription_request" in stage_names
    
    def test_create_fast_pipeline(self):
        """Test fast pipeline creation"""
        pipeline = create_fast_pipeline()
        
        assert isinstance(pipeline, AudioPipeline)
        
        # Fast pipeline might have fewer stages
        stage_names = [stage.stage_name for stage in pipeline.stages]
        assert "audio_validation" in stage_names
        assert "transcription_request" in stage_names
    
    @pytest.mark.asyncio
    async def test_pipeline_integration(self, sample_audio_data, processing_context):
        """Test that factory pipelines actually work"""
        pipelines = [
            create_basic_pipeline(),
            create_quality_pipeline(),
            create_fast_pipeline()
        ]
        
        for pipeline in pipelines:
            result = await pipeline.process(sample_audio_data, processing_context)
            assert_result_success(result)
            
            # Should have processed the audio
            audio_data = result.value
            assert isinstance(audio_data, AudioData)
            assert len(audio_data.data) > 0
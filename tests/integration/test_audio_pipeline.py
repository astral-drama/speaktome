#!/usr/bin/env python3

"""
Audio Pipeline Integration Tests

Tests the complete audio processing pipeline with real components.
"""

import pytest
import time
from pathlib import Path

from server.pipeline import (
    AudioProcessingPipeline, AudioData, ProcessingContext,
    FormatValidationStage, AudioConversionStage, NoiseReductionStage, TranscriptionStage,
    create_default_pipeline, create_fast_pipeline, create_quality_pipeline
)
from server.functional.result_monad import Result
from tests.test_utils import (
    MockTranscriptionProvider, create_test_wav_data, create_test_audio_file,
    assert_result_success, assert_result_failure, wait_for_condition
)

@pytest.mark.integration
@pytest.mark.pipeline
class TestAudioPipelineIntegration:
    """Integration tests for audio processing pipeline"""
    
    @pytest.mark.asyncio
    async def test_complete_pipeline_processing(self, temp_dir):
        """Test complete pipeline with all stages"""
        # Create test provider
        provider = MockTranscriptionProvider()
        await provider.initialize()
        
        # Create pipeline
        pipeline = create_default_pipeline(provider)
        
        # Create test audio data
        audio_data = AudioData(
            data=create_test_wav_data(duration=1.0),
            format="wav",
            sample_rate=16000,
            channels=1
        )
        
        # Create processing context
        context = ProcessingContext(
            request_id="test_pipeline_001",
            model="base",
            language="en"
        )
        
        # Process through pipeline
        result = await pipeline.process(audio_data, context)
        
        # Verify success
        assert_result_success(result, "Pipeline processing should succeed")
        
        processed_audio = result.get_value()
        
        # Verify metadata was added by stages
        assert "validated_at" in processed_audio.metadata
        assert "transcription_text" in processed_audio.metadata
        assert "pipeline_completed" in processed_audio.metadata
        assert "total_processing_time" in processed_audio.metadata
        
        # Verify transcription was performed
        assert processed_audio.metadata["transcription_text"]
        assert processed_audio.metadata["transcription_language"] == "en"
    
    @pytest.mark.asyncio
    async def test_pipeline_with_invalid_audio(self):
        """Test pipeline behavior with invalid audio data"""
        provider = MockTranscriptionProvider()
        await provider.initialize()
        
        pipeline = create_default_pipeline(provider)
        
        # Create invalid audio data
        audio_data = AudioData(
            data=b"",  # Empty data
            format="wav"
        )
        
        context = ProcessingContext(request_id="test_invalid_001")
        
        # Process should fail at validation stage
        result = await pipeline.process(audio_data, context)
        assert_result_failure(result, "Audio data is empty")
    
    @pytest.mark.asyncio
    async def test_fast_pipeline_performance(self):
        """Test fast pipeline has minimal processing stages"""
        provider = MockTranscriptionProvider()
        provider.set_processing_delay(0.01)  # Very fast
        await provider.initialize()
        
        pipeline = create_fast_pipeline(provider)
        
        # Verify pipeline has minimal stages
        assert len(pipeline.stages) == 2  # Validation + Transcription only
        
        audio_data = AudioData(
            data=create_test_wav_data(duration=0.5),
            format="wav"
        )
        
        context = ProcessingContext(request_id="test_fast_001")
        
        start_time = time.time()
        result = await pipeline.process(audio_data, context)
        processing_time = time.time() - start_time
        
        assert_result_success(result)
        assert processing_time < 0.5, f"Fast pipeline took too long: {processing_time}s"
    
    @pytest.mark.asyncio
    async def test_quality_pipeline_enhancement(self):
        """Test quality pipeline includes all enhancement stages"""
        provider = MockTranscriptionProvider()
        await provider.initialize()
        
        pipeline = create_quality_pipeline(provider)
        
        # Quality pipeline should have all stages
        assert len(pipeline.stages) >= 4  # All enhancement stages
        
        audio_data = AudioData(
            data=create_test_wav_data(duration=1.0),
            format="mp3"  # Will need conversion
        )
        
        context = ProcessingContext(request_id="test_quality_001")
        
        result = await pipeline.process(audio_data, context)
        assert_result_success(result)
        
        processed_audio = result.get_value()
        
        # Verify enhancement metadata
        assert "converted_from" in processed_audio.metadata
        assert "noise_reduction_applied" in processed_audio.metadata
    
    @pytest.mark.asyncio
    async def test_pipeline_stage_error_handling(self):
        """Test pipeline handles individual stage failures"""
        provider = MockTranscriptionProvider()
        await provider.initialize()
        
        pipeline = AudioProcessingPipeline()
        
        # Add stages including one that will fail
        pipeline.add_stage(FormatValidationStage())
        pipeline.add_stage(FailingTestStage())  # This will fail
        pipeline.add_stage(TranscriptionStage(provider))
        
        audio_data = AudioData(
            data=create_test_wav_data(),
            format="wav"
        )
        
        context = ProcessingContext(request_id="test_error_001")
        
        result = await pipeline.process(audio_data, context)
        assert_result_failure(result, "Intentional test failure")
    
    @pytest.mark.asyncio
    async def test_pipeline_with_file_input(self, temp_dir):
        """Test pipeline processing with file input"""
        provider = MockTranscriptionProvider()
        await provider.initialize()
        
        pipeline = create_default_pipeline(provider)
        
        # Create test audio file
        audio_file = create_test_audio_file(temp_dir, "test_pipeline.wav", duration=2.0)
        
        # Load audio data from file
        audio_data = AudioData(
            data=audio_file.read_bytes(),
            format="wav"
        )
        
        context = ProcessingContext(
            request_id="test_file_001",
            client_id="test_client",
            model="base"
        )
        
        result = await pipeline.process(audio_data, context)
        assert_result_success(result)
        
        processed_audio = result.get_value()
        
        # Verify transcription was performed
        transcription_text = processed_audio.metadata.get("transcription_text", "")
        assert "test transcription" in transcription_text
        assert ".wav" in transcription_text
    
    @pytest.mark.asyncio
    async def test_pipeline_context_preservation(self):
        """Test that processing context is preserved through pipeline"""
        provider = MockTranscriptionProvider()
        await provider.initialize()
        
        pipeline = create_default_pipeline(provider)
        
        audio_data = AudioData(
            data=create_test_wav_data(),
            format="wav"
        )
        
        original_context = ProcessingContext(
            request_id="context_test_001",
            client_id="test_client_123",
            model="small",
            language="fr",
            metadata={"custom_field": "custom_value"}
        )
        
        result = await pipeline.process(audio_data, original_context)
        assert_result_success(result)
        
        # Context should be preserved in the result
        processed_audio = result.get_value()
        
        # Check that our context influenced the result
        assert processed_audio.metadata["transcription_language"] == "fr"
        assert processed_audio.metadata["model_used"] == "small"
    
    @pytest.mark.asyncio
    async def test_parallel_pipeline_processing(self):
        """Test pipeline can handle multiple concurrent requests"""
        provider = MockTranscriptionProvider()
        provider.set_processing_delay(0.1)
        await provider.initialize()
        
        pipeline = create_fast_pipeline(provider)
        
        # Create multiple processing tasks
        tasks = []
        for i in range(5):
            audio_data = AudioData(
                data=create_test_wav_data(duration=0.5),
                format="wav"
            )
            context = ProcessingContext(request_id=f"parallel_{i}")
            
            tasks.append(pipeline.process(audio_data, context))
        
        # Process all concurrently
        import asyncio
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # All should succeed
        for i, result in enumerate(results):
            assert not isinstance(result, Exception), f"Task {i} raised exception: {result}"
            assert_result_success(result, f"Task {i} should succeed")
        
        # Verify provider handled all requests
        assert provider.get_request_count() >= 5
    
    @pytest.mark.asyncio
    async def test_pipeline_metadata_accumulation(self):
        """Test that pipeline stages accumulate metadata correctly"""
        provider = MockTranscriptionProvider()
        await provider.initialize()
        
        # Create custom pipeline with metadata-adding stages
        pipeline = AudioProcessingPipeline()
        pipeline.add_stage(FormatValidationStage())
        pipeline.add_stage(MetadataTestStage("stage_1", {"custom_data": "value_1"}))
        pipeline.add_stage(MetadataTestStage("stage_2", {"custom_data_2": "value_2"}))
        pipeline.add_stage(TranscriptionStage(provider))
        
        audio_data = AudioData(
            data=create_test_wav_data(),
            format="wav",
            metadata={"initial": "data"}
        )
        
        context = ProcessingContext(request_id="metadata_test_001")
        
        result = await pipeline.process(audio_data, context)
        assert_result_success(result)
        
        processed_audio = result.get_value()
        
        # Verify metadata from all stages is present
        assert "initial" in processed_audio.metadata  # Original metadata
        assert "validated_at" in processed_audio.metadata  # Validation stage
        assert "stage_1_processed" in processed_audio.metadata  # Custom stage 1
        assert "stage_2_processed" in processed_audio.metadata  # Custom stage 2
        assert "transcription_text" in processed_audio.metadata  # Transcription stage
        assert processed_audio.metadata["custom_data"] == "value_1"
        assert processed_audio.metadata["custom_data_2"] == "value_2"

# Helper classes for testing
class FailingTestStage:
    """Test stage that always fails"""
    
    @property
    def name(self) -> str:
        return "failing_test_stage"
    
    async def process(self, audio, context):
        from server.functional.result_monad import Failure
        return Failure("Intentional test failure")
    
    def can_process(self, audio, context) -> bool:
        return True

class MetadataTestStage:
    """Test stage that adds specific metadata"""
    
    def __init__(self, stage_name: str, metadata: dict):
        self._name = stage_name
        self._metadata = metadata
    
    @property
    def name(self) -> str:
        return self._name
    
    async def process(self, audio, context):
        from server.functional.result_monad import Success
        
        # Add stage-specific metadata
        enhanced_metadata = {**self._metadata, f"{self._name}_processed": True}
        enhanced_audio = audio.with_metadata(**enhanced_metadata)
        
        return Success(enhanced_audio)
    
    def can_process(self, audio, context) -> bool:
        return True
#!/usr/bin/env python3

"""
Realistic End-to-End Tests

Tests complete workflows using real server, real HTTP requests, and real WebSocket connections.
No mocks - tests the actual system as users would interact with it.
"""

import pytest
import asyncio
import json
import tempfile
import time
import socket
from pathlib import Path
from typing import Dict, Any

import httpx
import websockets
from fastapi import FastAPI
from fastapi.testclient import TestClient
import uvicorn
import pytest_asyncio

from tests.test_utils import create_test_audio_file, create_test_wav_data


def get_free_port():
    """Get a free port for testing"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port

@pytest.mark.e2e
class TestRealisticWorkflows:
    """End-to-end tests with real server and real requests"""
    
    @pytest_asyncio.fixture
    async def test_server(self):
        """Start a real Phase 3 test server for E2E testing"""
        # Import the Phase 3 FastAPI app
        from server.phase3_server import app
        
        # Configure for testing
        import os
        os.environ['WHISPER_ENV'] = 'test'
        os.environ['LOG_LEVEL'] = 'ERROR'  # Reduce noise during testing
        
        # Use a random free port for testing to avoid conflicts
        test_port = get_free_port()
        
        # Start server in background
        config = uvicorn.Config(
            app, 
            host="127.0.0.1", 
            port=test_port, 
            log_level="error"
        )
        server = uvicorn.Server(config)
        
        # Run server in background task
        server_task = asyncio.create_task(server.serve())
        
        # Wait for server to start and verify it's responsive
        base_url = f"http://127.0.0.1:{test_port}"
        for _ in range(50):  # Try for up to 5 seconds
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(f"{base_url}/health", timeout=0.5)
                    if response.status_code == 200:
                        break
            except:
                pass
            await asyncio.sleep(0.1)
        
        yield {
            'base_url': base_url,
            'port': test_port,
            'server': server,
            'task': server_task
        }
        
        # Cleanup: stop server gracefully
        server.should_exit = True
        try:
            await asyncio.wait_for(server_task, timeout=2.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass
        
        # Wait a moment for cleanup
        await asyncio.sleep(0.1)
    
    @pytest_asyncio.fixture
    async def real_audio_file(self):
        """Create a real audio file for testing"""
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            audio_data = create_test_wav_data(duration=2.0, sample_rate=16000)
            f.write(audio_data)
            temp_path = f.name
        
        yield temp_path
        
        # Cleanup
        Path(temp_path).unlink(missing_ok=True)
    
    @pytest.mark.asyncio
    async def test_real_http_file_upload_workflow(self, test_server, real_audio_file):
        """Test complete HTTP file upload and transcription workflow"""
        base_url = test_server['base_url']
        
        async with httpx.AsyncClient() as client:
            # Test 1: Health check - verify server is running
            health_response = await client.get(f"{base_url}/health")
            assert health_response.status_code == 200
            health_data = health_response.json()
            assert health_data['status'] == 'healthy'
            
            # Test 2: Get server status
            status_response = await client.get(f"{base_url}/api/status")
            assert status_response.status_code == 200
            status_data = status_response.json()
            assert status_data['status'] == 'running'
            
            # Test 3: Get available models
            models_response = await client.get(f"{base_url}/api/models")
            assert models_response.status_code == 200
            models_data = models_response.json()
            assert len(models_data) > 0
            assert any(model['name'] == 'base' for model in models_data)
            
            # Test 4: Upload audio file for transcription
            with open(real_audio_file, 'rb') as audio:
                files = {'file': ('test_audio.wav', audio, 'audio/wav')}
                data = {'model': 'base'}
                
                upload_response = await client.post(
                    f"{base_url}/api/transcribe",
                    files=files,
                    data=data
                )
                
                assert upload_response.status_code == 200
                upload_data = upload_response.json()
                assert 'id' in upload_data
                assert upload_data['status'] in ['pending', 'processing']
                
                request_id = upload_data['id']
            
            # Test 5: Poll for transcription result
            max_attempts = 30  # 30 seconds timeout
            result_data = None
            
            for attempt in range(max_attempts):
                result_response = await client.get(f"{base_url}/api/transcribe/{request_id}")
                assert result_response.status_code == 200
                
                result_data = result_response.json()
                
                if result_data['status'] == 'completed':
                    break
                elif result_data['status'] == 'failed':
                    pytest.fail(f"Transcription failed: {result_data.get('error')}")
                
                await asyncio.sleep(1)
            
            # Test 6: Verify transcription result
            assert result_data is not None
            assert result_data['status'] == 'completed'
            assert result_data['text'] is not None
            assert len(result_data['text']) > 0
            assert result_data['processing_time'] is not None
            assert result_data['processing_time'] > 0
    
    @pytest.mark.asyncio
    async def test_real_websocket_connection_workflow(self, test_server, real_audio_file):
        """Test real WebSocket connection and real-time transcription"""
        port = test_server['port']
        websocket_url = f"ws://127.0.0.1:{port}/ws/transcribe"
        
        # Read audio file as base64
        import base64
        with open(real_audio_file, 'rb') as f:
            audio_bytes = f.read()
            audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
        
        async with websockets.connect(websocket_url) as websocket:
            # Test 1: Receive welcome message
            welcome_msg = await websocket.recv()
            welcome_data = json.loads(welcome_msg)
            
            assert welcome_data['type'] == 'connection'
            assert welcome_data['status'] == 'connected'
            assert 'client_id' in welcome_data
            
            # Test 2: Send configuration
            config_msg = {
                'type': 'config',
                'model': 'base',
                'language': 'en'
            }
            await websocket.send(json.dumps(config_msg))
            
            config_response = await websocket.recv()
            config_data = json.loads(config_response)
            
            assert config_data['type'] == 'config'
            assert config_data['status'] == 'configured'
            assert config_data['model'] == 'base'
            
            # Test 3: Send audio data
            audio_msg = {
                'type': 'audio',
                'data': audio_base64,
                'format': 'wav',
                'model': 'base'
            }
            await websocket.send(json.dumps(audio_msg))
            
            # Test 4: Receive transcription result
            # Wait for transcription response (with timeout)
            transcription_data = None
            timeout = 30  # seconds
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=5)
                    data = json.loads(response)
                    
                    if data['type'] == 'transcription':
                        transcription_data = data
                        break
                    elif data['type'] == 'error':
                        pytest.fail(f"WebSocket transcription error: {data['message']}")
                        
                except asyncio.TimeoutError:
                    continue
            
            # Test 5: Verify transcription result
            assert transcription_data is not None, "No transcription received within timeout"
            assert transcription_data['type'] == 'transcription'
            assert transcription_data['status'] == 'completed'
            assert transcription_data['text'] is not None
            assert len(transcription_data['text']) > 0
            assert transcription_data['processing_time'] > 0
            
            # Test 6: Test ping/pong for keep-alive
            ping_msg = {'type': 'ping'}
            await websocket.send(json.dumps(ping_msg))
            
            pong_response = await websocket.recv()
            pong_data = json.loads(pong_response)
            
            assert pong_data['type'] == 'pong'
            assert 'timestamp' in pong_data
    
    @pytest.mark.asyncio
    async def test_concurrent_requests_workflow(self, test_server, real_audio_file):
        """Test handling multiple concurrent transcription requests"""
        base_url = test_server['base_url']
        num_concurrent = 3
        
        async def make_transcription_request(client_id: int):
            async with httpx.AsyncClient() as client:
                with open(real_audio_file, 'rb') as audio:
                    files = {'file': (f'test_audio_{client_id}.wav', audio, 'audio/wav')}
                    data = {'model': 'base'}
                    
                    # Upload file
                    upload_response = await client.post(
                        f"{base_url}/api/transcribe",
                        files=files,
                        data=data
                    )
                    
                    assert upload_response.status_code == 200
                    upload_data = upload_response.json()
                    request_id = upload_data['id']
                    
                    # Poll for result
                    for _ in range(30):  # 30 second timeout
                        result_response = await client.get(f"{base_url}/api/transcribe/{request_id}")
                        result_data = result_response.json()
                        
                        if result_data['status'] == 'completed':
                            return result_data
                        elif result_data['status'] == 'failed':
                            pytest.fail(f"Request {client_id} failed: {result_data.get('error')}")
                        
                        await asyncio.sleep(1)
                    
                    pytest.fail(f"Request {client_id} timed out")
        
        # Submit multiple concurrent requests
        tasks = [make_transcription_request(i) for i in range(num_concurrent)]
        results = await asyncio.gather(*tasks)
        
        # Verify all requests completed successfully
        assert len(results) == num_concurrent
        for i, result in enumerate(results):
            assert result['status'] == 'completed'
            assert result['text'] is not None
            assert len(result['text']) > 0
            assert result['processing_time'] > 0
    
    @pytest.mark.asyncio
    async def test_error_handling_workflow(self, test_server):
        """Test error handling with invalid requests"""
        base_url = test_server['base_url']
        
        async with httpx.AsyncClient() as client:
            # Test 1: Upload invalid file format
            invalid_file_content = b"This is not an audio file"
            files = {'file': ('test.txt', invalid_file_content, 'text/plain')}
            
            response = await client.post(f"{base_url}/api/transcribe", files=files)
            assert response.status_code == 400
            error_data = response.json()
            assert 'Unsupported file format' in error_data['detail']
            
            # Test 2: Request non-existent transcription result
            response = await client.get(f"{base_url}/api/transcribe/non-existent-id")
            assert response.status_code == 404
            
            # Test 3: Use invalid model
            with tempfile.NamedTemporaryFile(suffix='.wav') as temp_file:
                audio_data = create_test_wav_data(duration=1.0)
                temp_file.write(audio_data)
                temp_file.flush()
                
                with open(temp_file.name, 'rb') as audio:
                    files = {'file': ('test.wav', audio, 'audio/wav')}
                    data = {'model': 'invalid-model'}
                    
                    response = await client.post(f"{base_url}/api/transcribe", files=files, data=data)
                    assert response.status_code == 400
                    error_data = response.json()
                    assert 'Invalid model' in error_data['detail']
    
    @pytest.mark.asyncio  
    async def test_status_websocket_workflow(self, test_server):
        """Test real-time status updates via WebSocket"""
        port = test_server['port']
        websocket_url = f"ws://127.0.0.1:{port}/ws/status"
        
        async with websockets.connect(websocket_url) as websocket:
            # Receive status update
            status_msg = await websocket.recv()
            status_data = json.loads(status_msg)
            
            # Verify status structure
            assert 'status' in status_data
            assert 'uptime' in status_data
            assert 'gpu_available' in status_data
            assert 'loaded_models' in status_data
            assert 'queue_status' in status_data
            assert 'active_connections' in status_data
            
            assert status_data['status'] == 'running'
            assert status_data['uptime'] > 0
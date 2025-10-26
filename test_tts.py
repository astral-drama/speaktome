#!/usr/bin/env python3

"""
Simple test script for TTS API

Tests the text-to-speech endpoints to verify the implementation works.
"""

import requests
import time
import json
import base64
from pathlib import Path

# Server configuration
BASE_URL = "http://localhost:8000"

def test_health_check():
    """Test health check endpoint"""
    print("🔍 Testing health check...")
    response = requests.get(f"{BASE_URL}/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    print()

def test_available_voices():
    """Test getting available voices"""
    print("🎤 Testing available voices...")
    response = requests.get(f"{BASE_URL}/api/voices")

    if response.status_code == 200:
        voices = response.json()
        print(f"Found {len(voices)} voices:")
        for voice in voices:
            print(f"  - {voice['name']} ({voice['language']}): {voice.get('description', 'N/A')}")
    else:
        print(f"❌ Error: {response.status_code} - {response.text}")
    print()

def test_synthesis_rest_api(text: str = "Hello, this is a test of the text to speech system."):
    """Test REST API synthesis"""
    print(f"🎵 Testing REST API synthesis...")
    print(f"Text: '{text}'")

    # Submit synthesis request
    request_data = {
        "text": text,
        "voice": "default",
        "speed": 1.0,
        "output_format": "wav"
    }

    print("Submitting synthesis request...")
    response = requests.post(f"{BASE_URL}/api/synthesize", json=request_data)

    if response.status_code != 200:
        print(f"❌ Error: {response.status_code} - {response.text}")
        return

    result = response.json()
    request_id = result['id']
    print(f"Request ID: {request_id}")
    print(f"Status: {result['status']}")

    # Poll for result
    print("Polling for result...")
    max_attempts = 30
    for attempt in range(max_attempts):
        time.sleep(1)
        response = requests.get(f"{BASE_URL}/api/synthesize/{request_id}")

        if response.status_code != 200:
            print(f"❌ Error: {response.status_code} - {response.text}")
            break

        result = response.json()
        status = result['status']
        print(f"  Attempt {attempt + 1}: {status}")

        if status == "completed":
            print(f"✅ Synthesis completed!")
            print(f"Processing time: {result.get('processing_time', 0):.2f}s")
            print(f"Audio format: {result.get('audio_format')}")

            # Save audio to file
            if result.get('audio_data'):
                audio_bytes = base64.b64decode(result['audio_data'])
                output_file = Path("test_output.wav")
                with open(output_file, 'wb') as f:
                    f.write(audio_bytes)
                print(f"💾 Audio saved to {output_file} ({len(audio_bytes)} bytes)")
            break

        elif status == "failed":
            print(f"❌ Synthesis failed: {result.get('error')}")
            break
    else:
        print(f"⏱️  Timeout waiting for synthesis")

    print()

def main():
    """Run TTS tests"""
    print("=" * 60)
    print("🎤 Text-to-Speech (TTS) API Test")
    print("=" * 60)
    print()

    try:
        # Test health check
        test_health_check()

        # Test available voices
        test_available_voices()

        # Test synthesis
        test_synthesis_rest_api()

        print("=" * 60)
        print("✅ TTS tests completed!")
        print("=" * 60)

    except requests.exceptions.ConnectionError:
        print("❌ Error: Could not connect to server")
        print("Make sure the server is running: python start_server.py")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

if __name__ == "__main__":
    main()

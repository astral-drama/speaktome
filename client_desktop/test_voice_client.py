#!/usr/bin/env python3

"""
Test script for SpeakToMe Desktop Voice Client

Tests various components without requiring full server setup.
"""

import asyncio
import json
import logging
import sys
import tempfile
import time
from pathlib import Path

# Test imports
def test_imports():
    """Test all required imports"""
    print("🧪 Testing imports...")
    
    try:
        import pyaudio
        print("✅ PyAudio imported")
    except ImportError:
        print("❌ PyAudio not available")
        return False
    
    try:
        import websockets
        print("✅ WebSockets imported")
    except ImportError:
        print("❌ WebSockets not available")
        return False
    
    try:
        import pynput
        print("✅ Pynput imported")
    except ImportError:
        print("❌ Pynput not available")
        return False
    
    try:
        import pyautogui
        print("✅ PyAutoGUI imported")
    except ImportError:
        print("❌ PyAutoGUI not available")
        return False
    
    return True

def test_audio_devices():
    """Test audio device detection"""
    print("\n🎤 Testing audio devices...")
    
    try:
        import pyaudio
        
        audio = pyaudio.PyAudio()
        device_count = audio.get_device_count()
        
        print(f"Found {device_count} audio devices:")
        
        input_devices = []
        for i in range(device_count):
            try:
                info = audio.get_device_info_by_index(i)
                if info['maxInputChannels'] > 0:
                    input_devices.append((i, info['name']))
                    print(f"  {i}: {info['name']} (inputs: {info['maxInputChannels']})")
            except:
                continue
        
        audio.terminate()
        
        if input_devices:
            print(f"✅ Found {len(input_devices)} input devices")
            return True
        else:
            print("❌ No input devices found")
            return False
            
    except Exception as e:
        print(f"❌ Audio test failed: {e}")
        return False

def test_audio_recording():
    """Test basic audio recording"""
    print("\n🔴 Testing audio recording...")
    
    try:
        from voice_client import AudioRecorder
        
        recorder = AudioRecorder(sample_rate=16000, channels=1, chunk_size=1024)
        
        print("Starting 2-second test recording...")
        if recorder.start_recording():
            # Record for 2 seconds
            for _ in range(int(16000 / 1024 * 2)):  # 2 seconds worth of chunks
                chunk = recorder.record_chunk()
                if not chunk:
                    break
                time.sleep(0.01)
            
            audio_data = recorder.stop_recording()
            recorder.cleanup()
            
            if audio_data and len(audio_data) > 1000:
                print(f"✅ Recording successful: {len(audio_data)} bytes")
                return True
            else:
                print("❌ Recording failed or too short")
                return False
        else:
            print("❌ Failed to start recording")
            return False
            
    except Exception as e:
        print(f"❌ Recording test failed: {e}")
        return False

def test_text_injection():
    """Test text injection functionality"""
    print("\n📝 Testing text injection...")
    
    try:
        from voice_client import TextInjector
        
        injector = TextInjector()
        
        print("Testing text injection in 3 seconds...")
        print("Switch to a text editor or terminal window!")
        
        for i in range(3, 0, -1):
            print(f"  {i}...")
            time.sleep(1)
        
        test_text = "Hello from SpeakToMe voice client test!"
        success = injector.inject_text(test_text)
        
        if success:
            print("✅ Text injection test completed")
            print("Check your active window for the test text")
            return True
        else:
            print("❌ Text injection failed")
            return False
            
    except Exception as e:
        print(f"❌ Text injection test failed: {e}")
        return False

def test_config_loading():
    """Test configuration loading"""
    print("\n⚙️ Testing configuration loading...")
    
    try:
        from voice_client import load_config
        
        # Test default config
        config = load_config()
        print("✅ Default config loaded")
        
        # Test with custom config file
        test_config = {
            "server_url": "ws://test.example.com:8000/ws/transcribe",
            "model": "large",
            "hotkey": "alt+space"
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_config, f)
            config_path = f.name
        
        try:
            config = load_config(config_path)
            if config['server_url'] == test_config['server_url']:
                print("✅ Custom config loaded correctly")
                return True
            else:
                print("❌ Custom config not loaded correctly")
                return False
        finally:
            Path(config_path).unlink()
            
    except Exception as e:
        print(f"❌ Config test failed: {e}")
        return False

async def test_websocket_connection():
    """Test WebSocket connection to server"""
    print("\n🌐 Testing WebSocket connection...")
    
    try:
        from voice_client import SpeakToMeClient
        
        client = SpeakToMeClient("ws://localhost:8000/ws/transcribe")
        
        print("Attempting to connect to server...")
        connected = await client.connect()
        
        if connected:
            print("✅ Connected to SpeakToMe server")
            await client.disconnect()
            return True
        else:
            print("❌ Failed to connect to server")
            print("  Make sure the SpeakToMe server is running: python start_server.py")
            return False
            
    except Exception as e:
        print(f"❌ WebSocket test failed: {e}")
        print("  Make sure the SpeakToMe server is running: python start_server.py")
        return False

def test_hotkey_parsing():
    """Test hotkey combination parsing"""
    print("\n🔥 Testing hotkey parsing...")
    
    try:
        from pynput import keyboard
        from pynput.keyboard import Key
        
        # Test various hotkey combinations
        test_combinations = [
            "ctrl+shift+w",
            "alt+space",
            "cmd+shift+v",
            "ctrl+alt+t"
        ]
        
        for combo in test_combinations:
            try:
                keys = combo.lower().split('+')
                key_combo = []
                
                for key in keys:
                    if key == 'ctrl':
                        key_combo.append(Key.ctrl_l)
                    elif key == 'shift':
                        key_combo.append(Key.shift_l)
                    elif key == 'alt':
                        key_combo.append(Key.alt_l)
                    elif key == 'cmd':
                        key_combo.append(Key.cmd)
                    else:
                        key_combo.append(keyboard.KeyCode.from_char(key))
                
                print(f"✅ Parsed hotkey: {combo}")
                
            except Exception as e:
                print(f"❌ Failed to parse {combo}: {e}")
                return False
        
        return True
        
    except Exception as e:
        print(f"❌ Hotkey test failed: {e}")
        return False

async def main():
    """Run all tests"""
    print("🧪 SpeakToMe Desktop Voice Client Test Suite")
    print("=" * 50)
    
    tests = [
        ("Import Test", test_imports),
        ("Audio Devices Test", test_audio_devices),
        ("Configuration Test", test_config_loading),
        ("Hotkey Parsing Test", test_hotkey_parsing),
        ("WebSocket Connection Test", test_websocket_connection),
    ]
    
    # Interactive tests (require user action)
    interactive_tests = [
        ("Audio Recording Test", test_audio_recording),
        ("Text Injection Test", test_text_injection),
    ]
    
    passed = 0
    total = len(tests)
    
    # Run automated tests
    for test_name, test_func in tests:
        print(f"\n--- {test_name} ---")
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            
            if result:
                passed += 1
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
    
    print(f"\n📊 Test Results: {passed}/{total} tests passed")
    
    # Ask about interactive tests
    if passed == total:
        print("\n🎯 All automated tests passed!")
        
        user_input = input("\nRun interactive tests? (requires microphone/text injection) [y/N]: ")
        if user_input.lower().startswith('y'):
            print("\n--- Interactive Tests ---")
            
            for test_name, test_func in interactive_tests:
                print(f"\n--- {test_name} ---")
                user_input = input(f"Run {test_name}? [y/N]: ")
                if user_input.lower().startswith('y'):
                    try:
                        result = test_func()
                        if result:
                            print(f"✅ {test_name} completed")
                        else:
                            print(f"❌ {test_name} failed")
                    except Exception as e:
                        print(f"❌ {test_name} failed with exception: {e}")
    
    print("\n🏁 Test suite completed!")
    
    if passed == total:
        print("✅ Ready to run voice client: python voice_client.py")
    else:
        print("❌ Some tests failed. Check your installation and dependencies.")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
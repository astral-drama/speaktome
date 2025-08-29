#!/usr/bin/env python3

import subprocess
import sys
from pathlib import Path

def check_system_packages():
    """Check required system packages"""
    print("🔍 Checking system packages...")
    
    required_packages = {
        'xdotool': 'Text injection tool',
        'portaudio19-dev': 'Audio development libraries',
        'python3-dev': 'Python development headers',
    }
    
    missing_packages = []
    
    for package, description in required_packages.items():
        try:
            result = subprocess.run(['dpkg', '-l', package], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                print(f"  ✓ {package} - {description}")
            else:
                print(f"  ✗ {package} - {description} (MISSING)")
                missing_packages.append(package)
        except Exception as e:
            print(f"  ? {package} - Could not check: {e}")
            
    if missing_packages:
        print(f"\n📦 To install missing packages:")
        print(f"sudo apt install -y {' '.join(missing_packages)}")
    
    return len(missing_packages) == 0

def check_python_packages():
    """Check Python packages in virtual environment"""
    print("\n🐍 Checking Python packages...")
    
    # Map package names to their import names
    required_packages = {
        'openai-whisper': ('whisper', 'OpenAI Whisper for speech recognition'),
        'torch': ('torch', 'PyTorch deep learning framework'),
        'torchaudio': ('torchaudio', 'PyTorch audio processing'),
        'pyaudio': ('pyaudio', 'Python audio I/O library'),
        'pynput': ('pynput', 'Input control and monitoring'),
        'python-xlib': ('Xlib', 'X11 library for Python'),
        'keyboard': ('keyboard', 'Global hotkey library'),
        'numpy': ('numpy', 'Numerical computing library'),
    }
    
    missing_packages = []
    
    for package_name, (import_name, description) in required_packages.items():
        try:
            __import__(import_name)
            print(f"  ✓ {package_name} - {description}")
        except ImportError as e:
            # Special handling for packages that need X11 display
            if 'platform is not supported' in str(e) and package_name in ['pynput']:
                try:
                    # Check if the package is installed by trying to import its module file
                    import importlib.util
                    spec = importlib.util.find_spec(import_name)
                    if spec is not None:
                        print(f"  ✓ {package_name} - {description} (installed, X11 required)")
                    else:
                        print(f"  ✗ {package_name} - {description} (MISSING)")
                        missing_packages.append(package_name)
                except:
                    print(f"  ✗ {package_name} - {description} (MISSING)")
                    missing_packages.append(package_name)
            else:
                print(f"  ✗ {package_name} - {description} (MISSING)")
                missing_packages.append(package_name)
    
    if missing_packages:
        print(f"\n📦 To install missing Python packages:")
        print(f"pip install {' '.join(missing_packages)}")
    
    return len(missing_packages) == 0

def check_gpu_support():
    """Check GPU and CUDA support"""
    print("\n🎮 Checking GPU support...")
    
    try:
        import torch
        
        cuda_available = torch.cuda.is_available()
        print(f"  CUDA Available: {cuda_available}")
        
        if cuda_available:
            gpu_count = torch.cuda.device_count()
            print(f"  GPU Count: {gpu_count}")
            
            for i in range(gpu_count):
                gpu_name = torch.cuda.get_device_name(i)
                gpu_memory = torch.cuda.get_device_properties(i).total_memory / (1024**3)
                print(f"  GPU {i}: {gpu_name} ({gpu_memory:.1f} GB)")
                
            return True
        else:
            print("  ❌ No CUDA GPUs detected")
            return False
            
    except ImportError:
        print("  ❌ PyTorch not available")
        return False

def check_audio_devices():
    """Check audio input devices"""
    print("\n🎤 Checking audio devices...")
    
    try:
        import pyaudio
        
        audio = pyaudio.PyAudio()
        input_devices = []
        
        for i in range(audio.get_device_count()):
            info = audio.get_device_info_by_index(i)
            if info['maxInputChannels'] > 0:
                input_devices.append({
                    'index': i,
                    'name': info['name'],
                    'channels': info['maxInputChannels']
                })
        
        if input_devices:
            print(f"  ✓ Found {len(input_devices)} input devices:")
            for device in input_devices:
                print(f"    - {device['name']} ({device['channels']} channels)")
        else:
            print("  ❌ No audio input devices found")
            
        audio.terminate()
        return len(input_devices) > 0
        
    except Exception as e:
        print(f"  ❌ Audio check failed: {e}")
        return False

def check_display_environment():
    """Check X11/display environment"""
    print("\n🖥️  Checking display environment...")
    
    import os
    
    display = os.environ.get('DISPLAY')
    if display:
        print(f"  ✓ DISPLAY variable set: {display}")
        
        try:
            import Xlib.display
            d = Xlib.display.Display()
            print(f"  ✓ X11 connection successful")
            d.close()
            return True
        except Exception as e:
            print(f"  ⚠️  X11 connection failed: {e}")
            print("  Note: This is expected when running via SSH without X11 forwarding")
            return False
    else:
        print("  ⚠️  DISPLAY variable not set")
        print("  Note: Required for window focus detection and text injection")
        return False

def main():
    print("🔧 Voice-to-Text System Package Verification\n")
    
    checks = [
        ("System Packages", check_system_packages),
        ("Python Packages", check_python_packages), 
        ("GPU Support", check_gpu_support),
        ("Audio Devices", check_audio_devices),
        ("Display Environment", check_display_environment),
    ]
    
    passed = 0
    total = len(checks)
    
    for check_name, check_func in checks:
        try:
            if check_func():
                passed += 1
        except Exception as e:
            print(f"  ❌ {check_name} check failed: {e}")
    
    print(f"\n📊 Summary: {passed}/{total} checks passed")
    
    if passed == total:
        print("🎉 All checks passed! System is ready for voice-to-text.")
    elif passed >= 3:  # Core functionality works
        print("✅ Core functionality available. Some features may be limited.")
        if passed < total:
            print("   Run on desktop environment for full functionality.")
    else:
        print("❌ System setup incomplete. Please address the issues above.")
        
    print(f"\n🚀 To run the application: python voice_to_text.py")

if __name__ == "__main__":
    main()
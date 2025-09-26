#!/usr/bin/env python3

"""
SpeakToMe Desktop Voice Client

Functional, event-driven voice-to-text client with architecture
consistent with the SpeakToMe server design patterns.

Usage:
    python speaktome_client.py [options]
    
Features:
    - Global hotkey voice recording
    - Cross-platform audio capture
    - Real-time transcription via SpeakToMe server
    - Text injection into any active window
    - Event-driven functional architecture
    - Result monad error handling
    - Dependency injection
    - Composable audio processing pipeline

Architecture:
    - Matches server Phase 3 functional patterns
    - Result monads for error handling
    - Event bus for component communication
    - Dependency injection container
    - Composable pipeline processing
    - Modular provider architecture
"""

import sys
import asyncio
import platform
import subprocess
from pathlib import Path

# Add current directory and parent to path for imports
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))
sys.path.insert(0, str(current_dir.parent))


def check_macos_permissions():
    """Check and provide guidance for macOS permissions"""
    try:
        # Check if we can access the microphone by attempting to query audio devices
        import pyaudio
        pa = pyaudio.PyAudio()
        pa.terminate()
        print("   ✅ Microphone access available")
    except Exception:
        print("   ❌ Microphone access blocked - grant permission in System Preferences")
    
    # Check accessibility permission by attempting to monitor events
    try:
        from pynput import keyboard
        # Try to create a listener (this will trigger permission prompt if needed)
        listener = keyboard.Listener(on_press=lambda key: None, on_release=lambda key: None)
        listener.start()
        listener.stop()
        print("   ✅ Accessibility permission appears to be granted")
    except Exception as e:
        if "not trusted" in str(e).lower() or "accessibility" in str(e).lower():
            print("   ❌ Accessibility permission needed - add Terminal/Python to Accessibility")
            print("   💡 Run the app once to trigger permission prompt")
        else:
            print(f"   ⚠️  Unable to verify accessibility permission: {e}")


try:
    # Import the main application
    from client.voice_client_app import main
    
    print("🎤 SpeakToMe Desktop Voice Client")
    print("=" * 50)
    print()
    print("Features:")
    print("  🔥 Global Hotkeys - Press Ctrl+Shift+W anywhere to record")
    print("  🖥️  GUI Interface - Visual status and controls (default, use --no-gui to disable)")
    print("  🎵 Cross-Platform Audio - Works on macOS, Linux, Windows")
    print("  📝 Text Injection - Types directly into active window")
    print("  ⚡ Real-Time Transcription - WebSocket connection to server")
    print("  🏗️ Functional Architecture - Consistent with server design")
    print()
    
    # Check platform and provide setup guidance
    system = platform.system()
    if system == "Darwin":
        print("🍎 macOS detected - Checking permissions...")
        print("   📋 System Preferences > Security & Privacy > Privacy")
        print("   🎤 Microphone: Add Terminal and Python")
        print("   ♿ Accessibility: Add Terminal and Python")
        print("   ⚠️  Global hotkeys need Accessibility permission!")
        print()
        check_macos_permissions()
    elif system == "Linux":
        print("🐧 Linux detected - Ensure audio groups and X11 support")
    elif system == "Windows":
        print("🪟 Windows detected - Grant microphone permissions")
    
    print()
    print("Starting client...")
    print()
    
    # Run the main application
    if __name__ == "__main__":
        # Handle event loop for different platforms
        if platform.system() == "Windows":
            # Windows requires ProactorEventLoop for signal handling
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        
        sys.exit(asyncio.run(main()))
        
except ImportError as e:
    print(f"❌ Import Error: {e}")
    print()
    print("Make sure all dependencies are installed:")
    print("  pip install -r requirements.txt")
    print()
    print("If you're missing system dependencies:")
    print("  ./install.sh")
    sys.exit(1)
    
except KeyboardInterrupt:
    print("\n👋 Goodbye!")
    sys.exit(0)
    
except Exception as e:
    import traceback
    print(f"❌ Unexpected error: {e}")
    print("Full traceback:")
    traceback.print_exc()
    sys.exit(1)
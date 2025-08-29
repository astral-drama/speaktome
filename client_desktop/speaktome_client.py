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
from pathlib import Path

# Add current directory and parent to path for imports
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))
sys.path.insert(0, str(current_dir.parent))

try:
    # Import the main application
    from client.voice_client_app import main
    
    print("🎤 SpeakToMe Desktop Voice Client")
    print("=" * 50)
    print()
    print("Features:")
    print("  🔥 Global Hotkeys - Press Ctrl+Shift+W anywhere to record")
    print("  🎵 Cross-Platform Audio - Works on macOS, Linux, Windows")
    print("  📝 Text Injection - Types directly into active window")
    print("  ⚡ Real-Time Transcription - WebSocket connection to server")
    print("  🏗️ Functional Architecture - Consistent with server design")
    print()
    
    # Check platform and provide setup guidance
    system = platform.system()
    if system == "Darwin":
        print("🍎 macOS detected - Grant microphone & accessibility permissions")
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
    print(f"❌ Unexpected error: {e}")
    print("Check the logs for more details.")
    sys.exit(1)
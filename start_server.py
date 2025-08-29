#!/usr/bin/env python3

"""
SpeakToMe Voice-to-Text Web Server Launcher

This script launches the FastAPI server with proper configuration.
"""

import sys
import os
import asyncio
import logging
from pathlib import Path

# Add current directory to Python path
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# Import server components  
from server.phase3_server import main

if __name__ == "__main__":
    print("🎤 SpeakToMe Voice-to-Text Web Server")
    print("=" * 50)
    print()
    
    # Check if we're in the right environment
    if not (current_dir / "server").exists():
        print("❌ Error: Server directory not found!")
        print("Make sure you're running this script from the speaktome project root.")
        sys.exit(1)
    
    # Check virtual environment
    venv_path = current_dir / ".venv"
    if venv_path.exists() and sys.prefix == sys.base_prefix:
        print("⚠️  Warning: Virtual environment not activated!")
        print("Run: source .venv/bin/activate")
        print()
    
    # Check if web requirements are installed
    try:
        import fastapi
        import uvicorn
        print("✅ Web dependencies found")
    except ImportError:
        print("❌ Error: Web dependencies not installed!")
        print("Install with: pip install -r requirements-web.txt")
        sys.exit(1)
    
    # Check if base requirements are installed
    try:
        import whisper
        import torch
        print("✅ Whisper and PyTorch found")
    except ImportError:
        print("❌ Error: Base dependencies not installed!")
        print("Install with: pip install -r requirements.txt")
        sys.exit(1)
    
    print("✅ Starting web server...")
    print()
    print("📖 Usage:")
    print("  - Web Interface: http://localhost:8000")
    print("  - API Documentation: http://localhost:8000/docs")
    print("  - Health Check: http://localhost:8000/health")
    print()
    print("🛑 Press Ctrl+C to stop the server")
    print()
    
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Server stopped by user")
    except Exception as e:
        print(f"\n❌ Server error: {e}")
        sys.exit(1)
#!/bin/bash

# SpeakToMe Desktop Voice Client Installation Script
# Supports macOS, Linux, and Windows (via Git Bash/WSL)

set -e

echo "🎤 SpeakToMe Desktop Voice Client Installer"
echo "============================================"

# Detect OS
OS="Unknown"
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="Linux"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macOS"
elif [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "msys" ]]; then
    OS="Windows"
fi

echo "Detected OS: $OS"
echo

# Check Python
echo "🐍 Checking Python installation..."
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo "❌ Python not found. Please install Python 3.8 or higher."
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | cut -d' ' -f2)
echo "✅ Found Python $PYTHON_VERSION"

# Check pip
echo "📦 Checking pip installation..."
if ! $PYTHON_CMD -m pip --version &> /dev/null; then
    echo "❌ pip not found. Please install pip."
    exit 1
fi
echo "✅ pip is available"

# Install system dependencies based on OS
echo "🔧 Installing system dependencies..."

case $OS in
    "Linux")
        echo "Installing Linux audio dependencies..."
        if command -v apt-get &> /dev/null; then
            sudo apt-get update
            sudo apt-get install -y portaudio19-dev python3-pyaudio python3-tk python3-dev xclip
        elif command -v yum &> /dev/null; then
            sudo yum install -y portaudio-devel tkinter xclip
        elif command -v dnf &> /dev/null; then
            sudo dnf install -y portaudio-devel python3-tkinter xclip
        elif command -v pacman &> /dev/null; then
            sudo pacman -S portaudio python-pyaudio tk xclip
        else
            echo "⚠️ Unknown Linux distribution. Please install portaudio development packages manually."
        fi
        ;;
    "macOS")
        echo "Installing macOS dependencies..."
        if command -v brew &> /dev/null; then
            brew install portaudio
            echo "✅ Installed portaudio via Homebrew"
        else
            echo "⚠️ Homebrew not found. Please install portaudio manually or install Homebrew first."
        fi
        ;;
    "Windows")
        echo "Windows detected. Dependencies should install via pip."
        ;;
    *)
        echo "⚠️ Unknown OS. Attempting to install Python dependencies only."
        ;;
esac

# Install Python dependencies
echo "📥 Installing Python dependencies..."
$PYTHON_CMD -m pip install --upgrade pip
$PYTHON_CMD -m pip install -r requirements.txt

# Test installation
echo "🧪 Testing installation..."
if $PYTHON_CMD -c "import pyaudio, websockets, pynput, pyautogui; print('✅ All imports successful')" 2>/dev/null; then
    echo "✅ Installation successful!"
else
    echo "❌ Some dependencies failed to install. Check the error messages above."
    exit 1
fi

echo
echo "🎯 Installation Complete!"
echo
echo "Next steps:"
echo "1. Start your SpeakToMe server: python start_server.py"
echo "2. Run the voice client: $PYTHON_CMD voice_client.py"
echo "3. Press Ctrl+Shift+W anywhere to start recording"
echo
echo "Configuration file: voice_client_config.json"
echo "Documentation: README.md"

# Platform-specific setup instructions
case $OS in
    "macOS")
        echo
        echo "🍎 macOS Setup Required:"
        echo "1. System Preferences > Security & Privacy > Privacy"
        echo "2. Grant Microphone access to Terminal and Python"
        echo "3. Grant Accessibility access to Terminal and Python"
        ;;
    "Linux")
        echo
        echo "🐧 Linux Setup:"
        echo "1. Add user to audio group: sudo usermod -a -G audio \$USER"
        echo "2. Logout and login again for group changes to take effect"
        echo "3. Test microphone access"
        ;;
    "Windows")
        echo
        echo "🪟 Windows Setup:"
        echo "1. Grant microphone permissions to Python"
        echo "2. Run as Administrator if hotkeys don't work"
        echo "3. Check Windows Defender settings if blocked"
        ;;
esac

echo
echo "Happy voice-to-texting! 🎉"
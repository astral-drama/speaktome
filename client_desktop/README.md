# SpeakToMe Desktop Voice Client

A cross-platform desktop client that captures voice input via global hotkeys and injects transcribed text into any active window.

## Features

- **🔥 Global Hotkeys**: Press `Ctrl+Shift+W` anywhere to start/stop recording
- **🎤 Cross-Platform Audio**: Works on macOS, Linux, and Windows
- **📝 Text Injection**: Sends transcribed text directly to the active window
- **⚡ Real-Time**: WebSocket connection to SpeakToMe server
- **⚙️ Configurable**: JSON configuration file for all settings
- **🔊 Audio Feedback**: Visual and audio feedback during recording

## Quick Start

### 1. Install Dependencies

**Create and activate virtual environment** (recommended):
```bash
# From the main speaktome directory
python3 -m venv .venv
source .venv/bin/activate

# Install Python dependencies
pip install --upgrade pip
pip install -r client_desktop/requirements.txt
```

**System audio libraries** (platform-specific):
```bash
# macOS: Install audio dependencies
brew install portaudio

# Linux: Install system audio libraries  
sudo apt-get install portaudio19-dev python3-pyaudio
sudo apt-get install xclip  # For clipboard support
# OR on CentOS/RHEL/Fedora:
sudo yum install portaudio-devel

# Windows: Usually works out of the box with pip
```

### 2. Start SpeakToMe Server

First, make sure your SpeakToMe server is running:

```bash
# In the main speaktome directory
python start_server.py
```

### 3. Run the Voice Client

```bash
# Activate virtual environment first
source .venv/bin/activate

# Navigate to desktop client directory
cd client_desktop

# Basic usage
PYTHONPATH=/home/seth/Software/dev/speaktome python client/voice_client_app.py

# Or use the GUI version
PYTHONPATH=/home/seth/Software/dev/speaktome python speaktome_client.py

# With custom server
PYTHONPATH=/home/seth/Software/dev/speaktome python client/voice_client_app.py --server ws://192.168.1.100:8000/ws/transcribe

# With custom hotkey
PYTHONPATH=/home/seth/Software/dev/speaktome python client/voice_client_app.py --hotkey "ctrl+alt+v"

# With config file  
PYTHONPATH=/home/seth/Software/dev/speaktome python client/voice_client_app.py --config my_config.json
```

## Usage

1. **Start the client**: Run `PYTHONPATH=/home/seth/Software/dev/speaktome python speaktome_client.py` (GUI) or `python client/voice_client_app.py` (CLI)
2. **Press hotkey**: Use `Ctrl+Shift+W` (or your configured hotkey) anywhere
3. **Record audio**: Speak while the recording indicator is active
4. **Stop recording**: Press the hotkey again or wait for auto-stop
5. **Get text**: Transcribed text appears in your active window via clipboard or primary selection

## Configuration

Edit `voice_client_config.json` to customize:

```json
{
    "server_url": "ws://localhost:8000/ws/transcribe",
    "model": "base",
    "hotkey": "ctrl+shift+w",
    "audio": {
        "sample_rate": 16000,
        "channels": 1,
        "chunk_size": 1024,
        "input_device": null
    },
    "text": {
        "add_space_after": true,
        "capitalize_first": true,
        "auto_punctuation": false
    },
    "logging": {
        "level": "INFO",
        "file": null
    }
}
```

### Configuration Options

- **server_url**: WebSocket URL of your SpeakToMe server
- **model**: Whisper model size (`tiny`, `base`, `small`, `medium`, `large`)
- **hotkey**: Global hotkey combination (e.g., `"ctrl+shift+w"`, `"alt+space"`)
- **audio.sample_rate**: Audio sample rate (16000 recommended for Whisper)
- **audio.input_device**: Specific audio input device (null for default)
- **text.add_space_after**: Add space after transcribed text
- **text.capitalize_first**: Capitalize first letter of transcription
- **logging.level**: Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`)

## Platform-Specific Setup

### macOS

```bash
# Install audio dependencies
brew install portaudio

# Grant accessibility permissions
# System Preferences > Security & Privacy > Privacy > Accessibility
# Add Terminal (or your terminal app) and Python

# For microphone access
# System Preferences > Security & Privacy > Privacy > Microphone
# Add Terminal and Python
```

### Linux

```bash
# Ubuntu/Debian
sudo apt-get install portaudio19-dev python3-pyaudio
sudo apt-get install xclip  # For clipboard support

# CentOS/RHEL/Fedora
sudo yum install portaudio-devel
sudo dnf install portaudio-devel

# Arch Linux
sudo pacman -S portaudio

# For X11 support (text injection)
sudo apt-get install python3-tk python3-dev
```

### Windows

```bash
# Usually works out of the box with pip
pip install -r requirements.txt

# If PyAudio fails to install:
# 1. Download wheel from: https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio
# 2. pip install PyAudio-0.2.11-cp39-cp39-win_amd64.whl (adjust for your Python version)

# For running in background as service
# Consider using pythonw.exe instead of python.exe
```

## Hotkey Combinations

Supported hotkey formats:

- `"ctrl+shift+w"` - Control + Shift + W
- `"alt+space"` - Alt + Space  
- `"cmd+shift+v"` - Command + Shift + V (macOS)
- `"ctrl+alt+t"` - Control + Alt + T
- `"shift+f1"` - Shift + F1

Available modifiers: `ctrl`, `shift`, `alt`, `cmd` (macOS only)
Available keys: Any letter, number, or function key

## Troubleshooting

### Audio Issues

```bash
# Test microphone access
python -c "import pyaudio; p = pyaudio.PyAudio(); print('Audio devices:', p.get_device_count())"

# List audio devices
python -c "
import pyaudio
p = pyaudio.PyAudio()
for i in range(p.get_device_count()):
    info = p.get_device_info_by_index(i)
    print(f'{i}: {info[\"name\"]} - Inputs: {info[\"maxInputChannels\"]}')
"

# Test specific device
python voice_client.py --config test_config.json
# Edit test_config.json to set "input_device": 2 (device index)
```

### Permission Issues

**macOS**:
- System Preferences > Security & Privacy > Privacy
- Grant permissions for Microphone and Accessibility
- Add Terminal and Python to allowed apps

**Linux**:
- Ensure user is in `audio` group: `sudo usermod -a -G audio $USER`
- For text injection: Install X11 development packages
- Check audio permissions: `ls -la /dev/snd/`

**Windows**:
- Run as Administrator if hotkeys don't work
- Check Windows Defender/Antivirus settings
- Ensure microphone permissions are granted to Python

### Connection Issues

```bash
# Test server connection
curl -f http://localhost:8000/health

# Test WebSocket connection
python -c "
import asyncio
import websockets

async def test():
    try:
        async with websockets.connect('ws://localhost:8000/ws/transcribe') as ws:
            print('✅ WebSocket connection successful')
    except Exception as e:
        print(f'❌ Connection failed: {e}')

asyncio.run(test())
"
```

### Text Injection Issues

- **macOS**: Grant Accessibility permissions to Terminal/Python
- **Linux**: Install `xclip` and X11 development packages  
- **Windows**: Run as Administrator or check antivirus settings

## Advanced Usage

### Running as Background Service

```bash
# Linux/macOS: Run in background
nohup python voice_client.py > voice_client.log 2>&1 &

# Windows: Use pythonw for no console
pythonw voice_client.py

# Create systemd service (Linux)
sudo tee /etc/systemd/system/speaktome-client.service << EOF
[Unit]
Description=SpeakToMe Voice Client
After=network.target

[Service]
Type=simple
User=yourusername
WorkingDirectory=/path/to/speaktome/client_desktop
ExecStart=/usr/bin/python3 voice_client.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable speaktome-client
sudo systemctl start speaktome-client
```

### Multiple Server Support

```json
{
    "servers": [
        {
            "name": "local",
            "url": "ws://localhost:8000/ws/transcribe",
            "model": "base"
        },
        {
            "name": "remote",
            "url": "ws://server.example.com:8000/ws/transcribe", 
            "model": "large"
        }
    ],
    "active_server": "local"
}
```

### Custom Hotkeys for Different Actions

```json
{
    "hotkeys": {
        "record": "ctrl+shift+w",
        "record_large": "ctrl+shift+l",
        "record_quick": "ctrl+shift+q"
    }
}
```

## Development

### Architecture

The client uses **Phase 3 functional architecture** matching the server design:

- **Result Monads**: Composable error handling without exceptions following mathematical laws (Left Identity, Right Identity, Associativity)
- **Event-Driven**: Decoupled communication via event bus
- **Dependency Injection**: Container-based service management
- **Composable Pipelines**: Functional audio processing stages
- **Immutable Data**: AudioData and ProcessingContext transformations
- **Pure Functions**: UI builders and data transformations extracted into composable, testable functions
- **Category Theory Patterns**: Mathematical coherence with associativity, identity, and composition laws
- **Functional Composition**: Large methods decomposed into chains of pure functions using `flat_map`

### Testing

Comprehensive test suite following server patterns:

```bash
# Ensure virtual environment is activated and PYTHONPATH is set
source .venv/bin/activate
export PYTHONPATH=/home/seth/Software/dev/speaktome

# Run all tests
python tests/run_tests.py

# Run specific test types
python tests/run_tests.py --type unit
python tests/run_tests.py --type integration
python tests/run_tests.py --type e2e

# Run property-based tests (mathematical properties verification)
pytest tests/property_based/ -v

# Run with coverage
python tests/run_tests.py --coverage

# Run linting and type checking
python tests/run_tests.py --quality
ruff check client/
mypy client/

# Using pytest directly
pytest tests/unit/                    # Unit tests
pytest -m integration                 # Integration tests
pytest -m "e2e and not slow"          # E2E tests (fast only)
pytest --cov=client --cov=shared      # With coverage
```

### Test Categories

- **Unit Tests**: Functional utilities, Result monads, pipeline stages
- **Integration Tests**: Provider interactions, event flows, component communication  
- **End-to-End Tests**: Complete workflows from hotkey to text injection
- **Property-Based Tests**: Mathematical laws and invariants (monad laws, function composition, UI determinism)

### Building Executable

```bash
# Install PyInstaller
pip install pyinstaller

# Build single executable
pyinstaller --onefile --windowed voice_client.py

# The executable will be in dist/voice_client
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure cross-platform compatibility
5. Submit a pull request

## License

This project is part of the SpeakToMe voice-to-text system. See the main project LICENSE file for details.

## Changelog

### v1.1.0
- **Functional Architecture**: Complete refactoring using Category Theory principles
- **Improved Text Injection**: Added X11 primary selection support (middle mouse paste)
- **Enhanced UI**: Functional composition patterns, reduced verbose dialogs
- **Property-Based Testing**: Mathematical verification of functional composition
- **Better Error Handling**: Result monad patterns throughout codebase
- **Threading Fixes**: Proper async event loop handling for global hotkeys
- **Code Quality**: Removed debugging cruft, extracted pure functions

### v1.0.0
- Initial release with cross-platform support
- Global hotkey integration  
- WebSocket client for SpeakToMe server
- Text injection into active windows
- JSON configuration support

---

**🎯 Ready to use!** Press `Ctrl+Shift+W` anywhere to start voice-to-text transcription!
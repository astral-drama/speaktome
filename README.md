# SpeakToMe Voice-to-Text Web Application

A modern web-based voice-to-text system built with **Phase 3 functional architecture**, featuring GPU-accelerated OpenAI Whisper transcription and real-time audio processing through a browser interface.

## Features

- **🌐 Web-Based Interface**: Modern chat-style web UI with real-time audio recording
- **🚀 GPU-Accelerated Transcription**: Uses RTX 4090 for fast Whisper inference
- **🔧 Phase 3 Functional Architecture**: Composable pipeline, Result monads, event-driven design
- **🎯 Batch Processing**: Reliable record-then-send approach for clean transcriptions
- **⚡ Real-Time Processing**: WebSocket-based audio streaming and response
- **🔄 Multiple Whisper Models**: Support for tiny, base, small, medium, and large models
- **🌍 Multi-Language Support**: Auto-detect or specify target languages

## Architecture

### Phase 3 Functional Design
- **Composable Pipeline**: Modular audio processing stages (validation → conversion → transcription)
- **Result Monads**: Functional error handling without exceptions
- **Event-Driven**: Async event bus for decoupled communication
- **Dependency Injection**: Clean dependency management with container
- **Immutable Data**: AudioData and ProcessingContext with functional transformations

### Technology Stack
- **Backend**: FastAPI with async WebSocket support
- **Frontend**: Vanilla JavaScript with WebRTC audio recording
- **Audio Processing**: FFmpeg for format conversion (WebM → WAV)
- **Transcription**: OpenAI Whisper with CUDA acceleration
- **Architecture**: Functional programming patterns with async/await

## Installation

### Prerequisites
- **GPU**: NVIDIA RTX 4090 (or CUDA-compatible GPU)
- **Python**: 3.8 or higher
- **System**: Linux (Ubuntu 20.04+ recommended)
- **FFmpeg**: For audio format conversion

### Setup

1. **Clone and navigate to project**:
   ```bash
   cd /home/seth/Software/dev/speaktome
   ```

2. **Activate virtual environment**:
   ```bash
   source .venv/bin/activate
   ```

3. **Dependencies should be installed, but if needed**:
   ```bash
   pip install openai-whisper torch torchvision torchaudio
   pip install fastapi uvicorn aiofiles
   ```

## Usage

### Starting the Server

```bash
# Start the Phase 3 server
python start_server.py

# Or run directly
python server/phase3_server.py
```

The server will start on `http://localhost:8000` by default.

### Web Interface

1. **Open browser**: Navigate to `http://localhost:8000`
2. **Allow microphone**: Grant microphone permissions when prompted
3. **Record audio**: Click the microphone button to start/stop recording
4. **Get transcription**: Audio is processed when recording stops (batch mode)

### Settings
- **Model Selection**: Choose from tiny, base, small, medium, large
- **Language**: Auto-detect or specify target language
- **Recording Mode**: Batch processing (recommended) or streaming
- **Auto-send**: Automatically process when recording stops

## API Endpoints

### REST API
- `GET /` - Web interface
- `GET /health` - Server health check  
- `GET /api/models` - Available Whisper models
- `POST /api/transcribe` - File upload transcription
- `GET /api/transcribe/{id}` - Get transcription result

### WebSocket
- `WS /ws/transcribe` - Real-time audio processing
  - Send: `{"type": "audio", "data": "base64-encoded-audio", "format": "webm"}`
  - Receive: `{"type": "transcription", "text": "...", "language": "en"}`

## Project Structure

```
speaktome/
├── server/
│   ├── phase3_server.py           # Main FastAPI server with Phase 3 architecture
│   ├── providers/
│   │   ├── whisper_provider.py    # Real Whisper transcription provider
│   │   └── transcription_provider.py # Provider interfaces
│   ├── pipeline/
│   │   └── audio_pipeline.py      # Composable processing pipeline
│   ├── functional/
│   │   └── result_monad.py        # Result monad implementation
│   ├── events/
│   │   └── event_bus.py           # Event-driven communication
│   ├── connection/
│   │   └── websocket_manager.py   # WebSocket connection management
│   ├── container/
│   │   └── dependency_container.py # Dependency injection
│   └── audio_processor.py         # Audio format conversion (FFmpeg)
├── client/
│   ├── index.html                 # Web interface
│   ├── js/
│   │   ├── app.js                # Main application controller
│   │   ├── audio-client.js       # WebRTC recording and WebSocket client
│   │   └── chat-interface.js     # Chat-style UI components
│   └── css/
│       └── styles.css            # Interface styling
├── tests/
│   ├── unit/                     # Unit tests for individual components
│   ├── integration/              # Integration tests for pipelines
│   └── e2e/                      # End-to-end realistic workflow tests
├── whisper_transcriber.py        # Core Whisper transcription class
├── start_server.py               # Server launcher with validation
└── README.md                     # This file
```

## Configuration

### Default Settings
- **Model**: base (good balance of speed/accuracy)
- **Language**: Auto-detect
- **Recording Mode**: Batch processing  
- **Port**: 8000
- **GPU**: Auto-detect CUDA

### Environment Variables
```bash
export WHISPER_MODEL=base           # Default model size
export WHISPER_DEVICE=cuda          # Force GPU/CPU
export SERVER_PORT=8000             # Server port
export LOG_LEVEL=INFO               # Logging level
```

## Performance

### GPU Performance (RTX 4090)
- **Base model**: ~0.1-0.3 seconds per transcription
- **Small model**: ~0.2-0.5 seconds per transcription  
- **Large model**: ~0.5-1.0 seconds per transcription

### Batch vs Streaming
- **Batch** (recommended): Single clean audio file, reliable conversion
- **Streaming**: Real-time chunks, may have format issues with some browsers

## Development

### Testing
```bash
# Run all tests
python -m pytest

# Run specific test types
python -m pytest tests/unit/              # Unit tests
python -m pytest tests/integration/       # Integration tests  
python -m pytest tests/e2e/              # End-to-end tests
```

### Code Style
- **Functional patterns**: Prefer pure functions, Result monads, immutable data
- **Async/await**: All I/O operations are async
- **Type hints**: Full type annotation throughout
- **Error handling**: Result monads instead of exceptions

### Adding New Components

1. **New pipeline stage**: Extend `PipelineStage` in `audio_pipeline.py`
2. **New transcription provider**: Implement `TranscriptionProvider` interface
3. **New events**: Add to event bus in `event_bus.py`
4. **New endpoints**: Add routes to `phase3_server.py`

## Troubleshooting

### Common Issues

**GPU not detected**:
```bash
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}, GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"None\"}')"
```

**Audio conversion fails**:
```bash
ffmpeg -version  # Check FFmpeg installation
```

**WebSocket connection issues**:
- Check firewall settings
- Verify port 8000 is available
- Try HTTPS for microphone permissions

**Microphone not working**:
- Grant browser microphone permissions
- Use HTTPS in production (required for microphone access)
- Check browser developer console for errors

### Debugging
```bash
# Enable debug logging
LOG_LEVEL=DEBUG python server/phase3_server.py

# Check server health
curl http://localhost:8000/health
```

## Production Deployment

### HTTPS Setup
For production, use HTTPS (required for microphone access):

```bash
# Using Caddy (example)
# Caddyfile:
your-domain.com {
    reverse_proxy localhost:8000
}
```

### Performance Tuning
- Use larger Whisper models for better accuracy
- Adjust worker count based on GPU memory
- Monitor GPU utilization and temperature

## Contributing

This project follows functional programming principles:

1. **Pure functions** where possible
2. **Result monads** for error handling  
3. **Immutable data structures**
4. **Composable pipeline architecture**
5. **Event-driven communication**

See the code structure and tests for examples of these patterns.

## License

This project uses OpenAI Whisper and various open-source libraries. Check individual component licenses for details.

---

**🎯 Ready to use!** Start the server with `python start_server.py` and open `http://localhost:8000` in your browser.
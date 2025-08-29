# SpeakToMe Voice-to-Text Web Server

A modern web-based voice transcription service built with **Phase 3 functional architecture**, featuring GPU-accelerated OpenAI Whisper transcription and real-time audio processing.

## 🚀 Quick Start

1. **Start the server**:
   ```bash
   source .venv/bin/activate
   python start_server.py
   ```

2. **Open web interface**: http://localhost:8000

3. **Record and transcribe**: Click microphone, speak, stop recording → get text!

## 🌟 Features

### Phase 3 Architecture
- **Functional Programming**: Result monads, immutable data, pure functions
- **Composable Pipeline**: Modular audio processing stages
- **Event-Driven**: Async event bus for decoupled communication
- **Dependency Injection**: Clean component management

### Server Capabilities
- **FastAPI + uvicorn** - High-performance async web server
- **WebSocket streaming** - Real-time voice-to-text with batch processing
- **REST API** - Upload audio files for batch transcription
- **GPU acceleration** - Optimized for RTX 4090 (0.1-0.3s per transcription)
- **Concurrent processing** - Handle multiple users simultaneously
- **Audio format support** - WebM, WAV, MP3, FLAC, M4A, OGG
- **Model selection** - Choose from tiny to large Whisper models
- **Multi-language** - Auto-detect or specify target language

### Web Interface
- **Modern chat UI** - Clean, responsive design
- **Real-time recording** - WebRTC-based audio capture
- **Batch processing** - Reliable record-then-send approach
- **Settings panel** - Configure models, language, recording mode
- **Progress feedback** - Visual indicators for recording and processing

## 🏗️ Architecture

### Backend Pipeline
```
Audio Input → Validation → Format Conversion → Whisper Transcription → Result
     ↓              ↓              ↓                    ↓            ↓
 WebSocket      AudioData      WebM→WAV          GPU Processing   Response
```

### Functional Components
- **Result Monads**: Error handling without exceptions
- **AudioData**: Immutable audio representation
- **ProcessingContext**: Request metadata and metrics
- **Event Bus**: Async communication between components
- **Provider System**: Pluggable transcription backends

## 📊 API Reference

### WebSocket Endpoints
```javascript
// Connect to real-time transcription
ws://localhost:8000/ws/transcribe

// Send audio data
{
  "type": "audio",
  "data": "base64-encoded-webm-audio",
  "format": "webm",
  "model": "base",
  "language": "en"
}

// Receive transcription
{
  "type": "transcription", 
  "text": "Your transcribed speech",
  "language": "en",
  "processing_time": 0.234,
  "timestamp": 1640995200.123
}
```

### REST API
```bash
# Get server health
GET /health

# List available models  
GET /api/models

# Upload file for transcription
POST /api/transcribe
Content-Type: multipart/form-data
- file: audio file
- model: whisper model (optional)
- language: target language (optional)

# Get transcription result
GET /api/transcribe/{request_id}
```

## ⚙️ Configuration

### Environment Variables
```bash
export WHISPER_MODEL=base           # Default model
export WHISPER_DEVICE=cuda          # Force GPU/CPU
export SERVER_PORT=8000             # Server port  
export LOG_LEVEL=INFO               # Logging verbosity
export MAX_WORKERS=2                # Transcription workers
```

### Model Performance (RTX 4090)
- **tiny**: ~39MB, ~0.05s processing, lower accuracy
- **base**: ~74MB, ~0.1-0.3s processing, good balance ⭐
- **small**: ~244MB, ~0.2-0.5s processing, better accuracy
- **medium**: ~769MB, ~0.3-0.8s processing, high accuracy
- **large**: ~1550MB, ~0.5-1.0s processing, best accuracy

## 🔧 Development

### Project Structure
```
server/
├── phase3_server.py           # Main FastAPI app with Phase 3 integration
├── providers/
│   ├── whisper_provider.py    # Real Whisper transcription implementation
│   └── transcription_provider.py # Provider interfaces and contracts
├── pipeline/
│   └── audio_pipeline.py      # Composable processing pipeline
├── functional/
│   └── result_monad.py        # Functional error handling
├── events/
│   └── event_bus.py           # Event-driven communication
├── connection/
│   └── websocket_manager.py   # WebSocket lifecycle management
├── container/
│   └── dependency_container.py # Dependency injection system
└── audio_processor.py         # Audio format conversion with FFmpeg
```

### Running Tests
```bash
# All tests
python -m pytest

# Specific test categories
python -m pytest tests/unit/        # Unit tests
python -m pytest tests/integration/ # Integration tests
python -m pytest tests/e2e/         # End-to-end tests
```

### Adding New Features

1. **New Pipeline Stage**: Extend `PipelineStage` in `audio_pipeline.py`
2. **New Provider**: Implement `TranscriptionProvider` interface
3. **New Events**: Add to event bus for async communication
4. **New Endpoints**: Add routes to `phase3_server.py`

## 🐛 Troubleshooting

### Common Issues

**Server won't start**:
```bash
# Check dependencies
python start_server.py

# Check port availability
netstat -tuln | grep 8000
```

**GPU not working**:
```bash
# Verify CUDA setup
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}, GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"None\"}')"
```

**Audio conversion fails**:
```bash
# Check FFmpeg
ffmpeg -version
```

**WebSocket connection issues**:
- Check browser console for errors
- Verify firewall allows port 8000
- For microphone access, use HTTPS in production

### Debug Mode
```bash
LOG_LEVEL=DEBUG python server/phase3_server.py
```

## 🌐 Production Deployment

### HTTPS Setup (Required for Microphone)
```bash
# Using Caddy
your-domain.com {
    reverse_proxy localhost:8000
}

# Using nginx
server {
    listen 443 ssl;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

### Performance Tuning
- **GPU Memory**: Monitor with `nvidia-smi`
- **Worker Count**: Adjust based on concurrent users
- **Model Selection**: Balance accuracy vs speed for your use case
- **Batch Size**: Process multiple requests together for efficiency

## 📈 Monitoring

### Health Checks
```bash
curl http://localhost:8000/health
```

### Metrics
The server exposes processing metrics:
- Request count and success rate
- Average processing time per model
- GPU utilization and memory usage
- Active WebSocket connections

### Logging
```bash
# Enable structured logging
LOG_LEVEL=INFO python server/phase3_server.py

# Log files contain:
# - Request/response timing
# - Audio processing pipeline stages
# - GPU utilization metrics
# - Error details with stack traces
```

---

**🎯 Ready for production!** This web server provides reliable, GPU-accelerated voice transcription with a modern functional architecture.
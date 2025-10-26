# Text-to-Speech (TTS) Feature

High-quality neural text-to-speech synthesis using Coqui TTS with GPU acceleration.

## Overview

The TTS feature mirrors the STT (Speech-to-Text) architecture with:
- **Functional pipeline architecture**: Composable stages for text validation, synthesis, and post-processing
- **Event-driven**: EventBus publishes TextSubmittedEvent, SynthesisCompletedEvent, etc.
- **Result monads**: Clean error handling with Success/Failure
- **GPU-accelerated**: Runs Coqui TTS on NVIDIA 4090
- **REST + WebSocket APIs**: Both synchronous and real-time streaming

## Architecture

### Provider Layer
- **`server/providers/tts_provider.py`**: Abstract TTS provider interface
- **`server/providers/coqui_tts_provider.py`**: Coqui TTS implementation with GPU support

### Pipeline Stages
Located in `server/pipeline/tts_pipeline.py`:
1. **TextValidationStage**: Validates input text (length, encoding)
2. **TextPreprocessingStage**: Normalizes whitespace, removes invalid chars
3. **SynthesisStage**: Generates audio using TTS provider
4. **AudioPostProcessingStage**: Post-processes synthesized audio

### Events
Located in `server/events/event_bus.py`:
- `TextSubmittedEvent`: Fired when text is submitted for synthesis
- `SynthesisStartedEvent`: Fired when synthesis begins
- `SynthesisCompletedEvent`: Fired when synthesis completes
- `SynthesisFailedEvent`: Fired when synthesis fails

## API Endpoints

### REST API

#### 1. Synthesize Speech
```http
POST /api/synthesize
Content-Type: application/json

{
  "text": "Hello, this is a test",
  "voice": "default",
  "language": "en",
  "speed": 1.0,
  "output_format": "wav"
}
```

**Response:**
```json
{
  "id": "uuid",
  "status": "processing"
}
```

#### 2. Get Synthesis Result
```http
GET /api/synthesize/{request_id}
```

**Response (completed):**
```json
{
  "id": "uuid",
  "status": "completed",
  "audio_data": "base64_encoded_audio",
  "audio_format": "wav",
  "processing_time": 2.5,
  "error": null
}
```

#### 3. Get Available Voices
```http
GET /api/voices
```

**Response:**
```json
[
  {
    "name": "tts_models/en/ljspeech/tacotron2-DDC",
    "language": "en",
    "description": "English female voice (LJSpeech)"
  }
]
```

### WebSocket API

#### Connect
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/synthesize');
```

#### Send Text for Synthesis
```javascript
ws.send(JSON.stringify({
  type: "text",
  text: "Hello, this is a test",
  voice: "default",
  speed: 1.0,
  format: "wav"
}));
```

#### Receive Audio
```javascript
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);

  if (data.type === "audio" && data.status === "completed") {
    const audioBytes = atob(data.data); // Decode base64
    const audioBlob = new Blob([audioBytes], { type: 'audio/wav' });
    // Play or process audio...
  }
};
```

## Installation

### 1. Install TTS Library
```bash
pip install TTS>=0.22.0
```

The TTS library is already added to `requirements.txt`.

### 2. Verify GPU Support
```python
import torch
print(f"CUDA available: {torch.cuda.is_available()}")
print(f"GPU: {torch.cuda.get_device_name(0)}")
```

### 3. Start Server
```bash
python start_server.py
```

The server will automatically:
- Initialize Coqui TTS on GPU (CUDA)
- Load default voice model
- Enable TTS endpoints

## Usage Examples

### Python (REST API)
```python
import requests
import base64

# Submit synthesis request
response = requests.post('http://localhost:8000/api/synthesize', json={
    "text": "Hello world",
    "voice": "default",
    "speed": 1.0
})

request_id = response.json()['id']

# Poll for result
import time
while True:
    result = requests.get(f'http://localhost:8000/api/synthesize/{request_id}')
    data = result.json()

    if data['status'] == 'completed':
        # Decode and save audio
        audio_bytes = base64.b64decode(data['audio_data'])
        with open('output.wav', 'wb') as f:
            f.write(audio_bytes)
        break

    time.sleep(0.5)
```

### JavaScript (WebSocket)
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/synthesize');

ws.onopen = () => {
  ws.send(JSON.stringify({
    type: "text",
    text: "Hello from JavaScript!",
    voice: "default"
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);

  if (data.type === "audio" && data.status === "completed") {
    // Decode base64 audio
    const audioData = atob(data.data);
    const audioArray = new Uint8Array(audioData.length);
    for (let i = 0; i < audioData.length; i++) {
      audioArray[i] = audioData.charCodeAt(i);
    }

    // Create audio blob and play
    const audioBlob = new Blob([audioArray], { type: 'audio/wav' });
    const audioUrl = URL.createObjectURL(audioBlob);
    const audio = new Audio(audioUrl);
    audio.play();
  }
};
```

### Test Script
```bash
python test_tts.py
```

This will:
- Check server health
- List available voices
- Synthesize test text
- Save audio to `test_output.wav`

## Configuration

### Change Voice Model
Edit `server/phase3_server.py`:
```python
tts_provider = CoquiTTSProvider(
    default_voice="tts_models/en/vctk/vits",  # Multi-speaker model
    device="cuda",
    max_workers=2
)
```

### Available Models
- `tts_models/en/ljspeech/tacotron2-DDC` - Default, female voice
- `tts_models/en/ljspeech/vits` - VITS-based, female voice
- `tts_models/en/vctk/vits` - Multi-speaker, various voices

See [Coqui TTS models](https://github.com/coqui-ai/TTS#released-models) for full list.

### Adjust GPU Settings
```python
tts_provider = CoquiTTSProvider(
    device="cuda",      # Use "cpu" for CPU-only
    max_workers=2       # Concurrent synthesis tasks
)
```

## Performance

With NVIDIA 4090:
- **Initialization**: ~5-10 seconds (model loading)
- **Synthesis speed**: ~1-3 seconds for 20-30 words
- **GPU memory**: ~2-4 GB (varies by model)

## Troubleshooting

### TTS Not Available
If you see "TTS service not available":
1. Check server logs for initialization errors
2. Verify CUDA is available: `torch.cuda.is_available()`
3. Ensure TTS library is installed: `pip install TTS`

### CUDA Out of Memory
Reduce batch size or switch to CPU:
```python
tts_provider = CoquiTTSProvider(device="cpu")
```

### Slow Synthesis
- Verify GPU is being used (check logs for "CUDA available")
- Try a faster model (e.g., VITS vs Tacotron2)
- Reduce max_workers if GPU memory is constrained

## Symmetry with STT

The TTS implementation mirrors the STT architecture:

| Feature | STT (Speech-to-Text) | TTS (Text-to-Speech) |
|---------|---------------------|---------------------|
| Input | Audio bytes | Text string |
| Output | Text string | Audio bytes |
| Provider | WhisperTranscriptionProvider | CoquiTTSProvider |
| Pipeline | AudioData → Text | TextData → AudioData |
| REST API | POST /api/transcribe | POST /api/synthesize |
| WebSocket | /ws/transcribe | /ws/synthesize |
| Events | TranscriptionCompletedEvent | SynthesisCompletedEvent |

## Next Steps

### Potential Enhancements
1. **Voice cloning**: Support custom voice models
2. **Streaming synthesis**: Generate audio in chunks
3. **Multiple languages**: Add non-English voice models
4. **Emotion control**: Adjust pitch, tone, emphasis
5. **SSML support**: Rich text-to-speech markup
6. **Caching**: Cache frequently synthesized phrases

### Integration Ideas
- Desktop client: Add TTS playback button
- Web client: Real-time TTS preview
- Voice assistant: Combine STT + LLM + TTS pipeline

## References

- [Coqui TTS GitHub](https://github.com/coqui-ai/TTS)
- [Coqui TTS Documentation](https://tts.readthedocs.io/)
- [Available Models](https://github.com/coqui-ai/TTS#released-models)

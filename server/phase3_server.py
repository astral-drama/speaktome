#!/usr/bin/env python3

"""
Phase 3 SpeakToMe Server

FastAPI server using the Phase 3 functional architecture:
- Composable audio processing pipeline
- Event-driven architecture  
- Result monad error handling
- Dependency injection container
"""

import asyncio
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Union, Any
import tempfile
import base64

from fastapi import FastAPI, File, UploadFile, HTTPException, WebSocket, WebSocketDisconnect, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import aiofiles
import uvicorn

# Phase 3 imports
from server.container import DependencyContainer, get_container
from server.events import (
    EventBus, get_event_bus, AudioUploadedEvent, TranscriptionCompletedEvent,
    TextSubmittedEvent, SynthesisCompletedEvent
)
from server.pipeline import (
    AudioData, ProcessingContext, create_default_pipeline, create_fast_pipeline, create_quality_pipeline
)
from server.pipeline.tts_pipeline import (
    TextData, TTSContext, create_default_tts_pipeline, create_fast_tts_pipeline, create_quality_tts_pipeline
)
from server.connection import WebSocketConnectionManager
# Routing components removed - WebSocket handling now integrated directly
from server.validation import create_audio_validator
from server.functional.result_monad import Result, Success, Failure
from server.status import get_server_status_provider

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
)
logger = logging.getLogger(__name__)

# Pydantic models for API
class TranscriptionRequest(BaseModel):
    model: str = Field(default="base", description="Pipeline model to use")
    language: Optional[str] = Field(default=None, description="Language code (auto-detect if None)")
    
class TranscriptionResponse(BaseModel):
    id: str
    status: str
    text: Optional[str] = None
    language: Optional[str] = None
    processing_time: Optional[float] = None
    error: Optional[str] = None

class ServerStatus(BaseModel):
    status: str
    uptime: float
    pipeline_type: str
    loaded_models: List[str]
    active_connections: int
    event_bus_status: str

class ModelInfo(BaseModel):
    name: str
    pipeline_type: str
    description: str

# TTS Pydantic models
class SynthesisRequest(BaseModel):
    text: str = Field(..., description="Text to synthesize")
    voice: str = Field(default="default", description="Voice to use")
    language: Optional[str] = Field(default=None, description="Language code")
    speed: float = Field(default=1.0, description="Speech speed (0.5-2.0)")
    output_format: str = Field(default="wav", description="Audio format (wav, mp3)")

class SynthesisResponse(BaseModel):
    id: str
    status: str
    audio_data: Optional[str] = None  # Base64 encoded audio
    audio_format: Optional[str] = None
    duration: Optional[float] = None
    processing_time: Optional[float] = None
    error: Optional[str] = None

class VoiceInfo(BaseModel):
    name: str
    language: str
    description: Optional[str] = None

# Global configuration
AVAILABLE_MODELS = ["base", "small", "medium"]
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
SUPPORTED_FORMATS = ["wav", "mp3", "flac", "webm"]
TEMP_DIR = "/tmp/whisper_phase3"

# Ensure temp directory exists
Path(TEMP_DIR).mkdir(exist_ok=True)

# Create FastAPI app
app = FastAPI(
    title="Whisper Voice-to-Text Server (Phase 3)",
    description="Functional, composable voice transcription with event-driven architecture",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
app_start_time = time.time()
active_transcriptions: Dict[str, Dict[str, Any]] = {}

# Phase 3 components (initialized at startup)
container = None
event_bus = None
websocket_manager = None
audio_validator = None
pipeline = None
tts_pipeline = None
tts_provider = None
status_provider = None

@app.on_event("startup")
async def startup_event():
    """Initialize Phase 3 architecture components"""
    global container, event_bus, websocket_manager, audio_validator, pipeline, tts_pipeline, tts_provider, status_provider

    logger.info("🚀 Starting Whisper Server with Phase 3 Architecture")

    # Initialize dependency injection container
    container = DependencyContainer()

    # Initialize event bus
    event_bus = EventBus()
    await event_bus.start()
    logger.info("✅ Event bus started")

    # Initialize WebSocket manager
    websocket_manager = WebSocketConnectionManager()
    logger.info("✅ WebSocket manager initialized")

    # Initialize audio validator
    audio_validator = create_audio_validator(max_size_mb=10.0)
    container.register_instance(type(audio_validator), audio_validator)
    logger.info("✅ Audio validator configured")

    # Initialize STT pipeline with real Whisper transcription
    from server.providers.whisper_provider import WhisperTranscriptionProvider
    provider = WhisperTranscriptionProvider(default_model="medium", max_workers=2)
    await provider.initialize()
    pipeline = create_default_pipeline(provider)
    logger.info("✅ STT audio processing pipeline initialized")

    # Initialize TTS pipeline with Coqui TTS
    # Using VITS model for better naturalness and contraction handling
    from server.providers.coqui_tts_provider import CoquiTTSProvider
    tts_provider = CoquiTTSProvider(
        default_voice="tts_models/en/ljspeech/vits",
        device="cuda",
        max_workers=2
    )
    tts_init_result = await tts_provider.initialize()
    if tts_init_result.is_success():
        tts_pipeline = create_default_tts_pipeline(tts_provider)
        logger.info("✅ TTS processing pipeline initialized")
    else:
        logger.error(f"❌ TTS initialization failed: {tts_init_result.get_error()}")
        logger.warning("⚠️  TTS endpoints will not be available")

    # Initialize status provider
    status_provider = get_server_status_provider()
    logger.info("✅ Status provider initialized")
    
    # Mount client directory to serve CSS, JS, and other static files
    client_dir = Path(__file__).parent.parent / "client"
    if client_dir.exists():
        # Mount specific subdirectories so they don't conflict with API routes
        css_dir = client_dir / "css" 
        js_dir = client_dir / "js"
        if css_dir.exists():
            app.mount("/css", StaticFiles(directory=str(css_dir)), name="css")
        if js_dir.exists():
            app.mount("/js", StaticFiles(directory=str(js_dir)), name="js")
        logger.info(f"✅ Static files mounted: {client_dir}")
    
    logger.info("🎉 Phase 3 server startup complete!")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up Phase 3 components"""
    logger.info("🛑 Shutting down Phase 3 server...")

    if tts_provider:
        await tts_provider.shutdown()
        logger.info("✅ TTS provider shutdown")

    if websocket_manager:
        await websocket_manager.shutdown()
        logger.info("✅ WebSocket manager shutdown")

    if event_bus:
        await event_bus.stop()
        logger.info("✅ Event bus stopped")

    if container:
        await container.dispose()
        logger.info("✅ Dependency container disposed")

    logger.info("👋 Phase 3 server shutdown complete")

async def save_uploaded_file(upload_file: UploadFile) -> Result[str, str]:
    """Save uploaded file with functional error handling"""
    try:
        # Validate file size
        if upload_file.size and upload_file.size > MAX_FILE_SIZE:
            return Failure(f"File too large. Maximum size: {MAX_FILE_SIZE / (1024*1024):.1f}MB")
        
        # Check file extension
        file_extension = Path(upload_file.filename).suffix.lower().lstrip('.')
        if file_extension not in SUPPORTED_FORMATS:
            return Failure(f"Unsupported file format. Supported: {', '.join(SUPPORTED_FORMATS)}")
        
        # Create unique filename
        unique_filename = f"{uuid.uuid4()}.{file_extension}"
        file_path = Path(TEMP_DIR) / unique_filename
        
        # Save file
        content = await upload_file.read()
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)
        
        logger.info(f"💾 Saved uploaded file: {file_path} ({len(content)} bytes)")
        return Success(str(file_path))
        
    except Exception as e:
        logger.error(f"❌ Error saving file: {e}")
        return Failure(f"Failed to save file: {str(e)}")

# REST API Endpoints

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serve main client interface"""
    client_file = Path(__file__).parent.parent / "client" / "index.html"
    if client_file.exists():
        async with aiofiles.open(client_file, "r") as f:
            content = await f.read()
        return content
    else:
        return """
        <html>
            <head><title>Whisper Phase 3 Server</title></head>
            <body>
                <h1>🎤 Whisper Voice-to-Text Server</h1>
                <h2>Phase 3: Functional Architecture</h2>
                <p>Client interface not found. Please check the client directory.</p>
                <p><a href="/docs">📖 API Documentation</a></p>
            </body>
        </html>
        """

@app.get("/api/status", response_model=ServerStatus)
async def get_server_status():
    """Get server status using Phase 3 components"""
    connection_count = websocket_manager.get_connection_count() if websocket_manager else 0
    
    return ServerStatus(
        status="running",
        uptime=time.time() - app_start_time,
        pipeline_type="composable_functional",
        loaded_models=AVAILABLE_MODELS,
        active_connections=connection_count,
        event_bus_status="running" if event_bus else "stopped"
    )

@app.get("/api/models", response_model=List[ModelInfo])
async def get_available_models():
    """Get available pipeline models"""
    model_info = {
        "base": {"pipeline_type": "default", "description": "Balanced pipeline with all stages"},
        "small": {"pipeline_type": "fast", "description": "Fast pipeline with minimal processing"},
        "medium": {"pipeline_type": "quality", "description": "High-quality pipeline with noise reduction"}
    }
    
    return [
        ModelInfo(
            name=model,
            pipeline_type=info["pipeline_type"],
            description=info["description"]
        )
        for model, info in model_info.items()
    ]

@app.post("/api/transcribe", response_model=TranscriptionResponse) 
async def transcribe_audio(
    file: UploadFile = File(...),
    model: str = Form("base"),
    language: Optional[str] = Form(None)
):
    """Process audio file through Phase 3 pipeline"""
    
    # Validate model first
    if model not in AVAILABLE_MODELS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid model. Available models: {', '.join(AVAILABLE_MODELS)}"
        )
    
    # Save uploaded file
    file_result = await save_uploaded_file(file)
    if file_result.is_failure():
        raise HTTPException(status_code=400, detail=file_result.get_error())
    
    file_path = file_result.get_value()
    request_id = str(uuid.uuid4())
    
    try:
        # Fire upload event
        upload_event = AudioUploadedEvent.create(
            request_id=request_id,
            file_path=file_path,
            file_size=file.size or 0,
            client_id=request_id
        )
        await event_bus.publish(upload_event)
        
        # Create audio data
        async with aiofiles.open(file_path, "rb") as f:
            audio_bytes = await f.read()
        
        audio_data = AudioData(
            data=audio_bytes,
            format=Path(file.filename).suffix.lower().lstrip('.'),
            sample_rate=16000  # Default, would be detected in real implementation
        )
        
        # Create processing context
        context = ProcessingContext(
            request_id=request_id,
            client_id=request_id,
            model=model,
            language=language
        )
        
        # Store request info
        active_transcriptions[request_id] = {
            'status': 'processing',
            'start_time': time.time(),
            'model': model,
            'file_path': file_path
        }
        
        # Process through pipeline asynchronously
        asyncio.create_task(process_audio_async(request_id, audio_data, context))
        
        return TranscriptionResponse(
            id=request_id,
            status="processing"
        )
        
    except Exception as e:
        logger.error(f"❌ Error in transcribe_audio: {e}")
        
        # Cleanup file
        try:
            Path(file_path).unlink(missing_ok=True)
        except:
            pass
            
        raise HTTPException(status_code=500, detail=str(e))

async def process_audio_async(request_id: str, audio_data: AudioData, context: ProcessingContext):
    """Process audio through pipeline asynchronously"""
    try:
        # Process through pipeline
        result = await pipeline.process(audio_data, context)
        
        if result.is_success():
            processed_audio = result.get_value()
            transcription_text = processed_audio.metadata.get("transcription_text", "")
            processing_time = time.time() - active_transcriptions[request_id]['start_time']
            
            # Update transcription status
            active_transcriptions[request_id].update({
                'status': 'completed',
                'text': transcription_text,
                'processing_time': processing_time
            })
            
            # Fire completion event
            completion_event = TranscriptionCompletedEvent.create(
                request_id=request_id,
                text=transcription_text,
                language=context.language or "en",
                processing_time=processing_time,
                client_id=context.client_id
            )
            await event_bus.publish(completion_event)
            
        else:
            # Handle failure
            error_message = result.get_error()
            active_transcriptions[request_id].update({
                'status': 'failed',
                'error': error_message
            })
            
    except Exception as e:
        logger.error(f"❌ Error processing audio {request_id}: {e}")
        active_transcriptions[request_id].update({
            'status': 'failed',
            'error': str(e)
        })
    
    finally:
        # Cleanup file
        file_path = active_transcriptions[request_id].get('file_path')
        if file_path:
            try:
                Path(file_path).unlink(missing_ok=True)
            except:
                pass

@app.get("/api/transcribe/{request_id}", response_model=TranscriptionResponse)
async def get_transcription_result(request_id: str):
    """Get transcription result by request ID"""

    if request_id not in active_transcriptions:
        raise HTTPException(status_code=404, detail="Transcription request not found")

    transcription = active_transcriptions[request_id]

    return TranscriptionResponse(
        id=request_id,
        status=transcription['status'],
        text=transcription.get('text'),
        language=transcription.get('language', 'en'),
        processing_time=transcription.get('processing_time'),
        error=transcription.get('error')
    )

# TTS API Endpoints

# Global state for TTS
active_syntheses: Dict[str, Dict[str, Any]] = {}

@app.post("/api/synthesize", response_model=SynthesisResponse)
async def synthesize_speech(request: SynthesisRequest):
    """Synthesize speech from text through TTS pipeline"""

    if not tts_pipeline:
        raise HTTPException(status_code=503, detail="TTS service not available")

    request_id = str(uuid.uuid4())

    try:
        # Fire text submitted event
        submit_event = TextSubmittedEvent.create(
            request_id=request_id,
            text=request.text,
            voice=request.voice,
            client_id=request_id
        )
        await event_bus.publish(submit_event)

        # Create text data
        text_data = TextData(
            text=request.text,
            language=request.language
        )

        # Create TTS context
        context = TTSContext(
            request_id=request_id,
            client_id=request_id,
            voice=request.voice,
            speed=request.speed,
            output_format=request.output_format
        )

        # Store request info
        active_syntheses[request_id] = {
            'status': 'processing',
            'start_time': time.time(),
            'voice': request.voice
        }

        # Process through pipeline asynchronously
        asyncio.create_task(process_synthesis_async(request_id, text_data, context))

        return SynthesisResponse(
            id=request_id,
            status="processing"
        )

    except Exception as e:
        logger.error(f"❌ Error in synthesize_speech: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def process_synthesis_async(request_id: str, text_data: TextData, context: TTSContext):
    """Process synthesis through pipeline asynchronously"""
    try:
        # Process through TTS pipeline
        result = await tts_pipeline.process(text_data, context)

        if result.is_success():
            audio_data = result.get_value()
            processing_time = time.time() - active_syntheses[request_id]['start_time']

            # Encode audio data to base64
            audio_b64 = base64.b64encode(audio_data.data).decode('utf-8')

            # Update synthesis status
            active_syntheses[request_id].update({
                'status': 'completed',
                'audio_data': audio_b64,
                'audio_format': audio_data.format,
                'sample_rate': audio_data.sample_rate,
                'processing_time': processing_time
            })

            # Fire completion event
            completion_event = SynthesisCompletedEvent.create(
                request_id=request_id,
                audio_size=len(audio_data.data),
                duration=audio_data.metadata.get('duration', 0.0),
                processing_time=processing_time,
                client_id=context.client_id
            )
            await event_bus.publish(completion_event)

        else:
            # Handle failure
            error_message = result.get_error()
            active_syntheses[request_id].update({
                'status': 'failed',
                'error': error_message
            })

    except Exception as e:
        logger.error(f"❌ Error processing synthesis {request_id}: {e}")
        active_syntheses[request_id].update({
            'status': 'failed',
            'error': str(e)
        })

@app.get("/api/synthesize/{request_id}", response_model=SynthesisResponse)
async def get_synthesis_result(request_id: str):
    """Get synthesis result by request ID"""

    if request_id not in active_syntheses:
        raise HTTPException(status_code=404, detail="Synthesis request not found")

    synthesis = active_syntheses[request_id]

    return SynthesisResponse(
        id=request_id,
        status=synthesis['status'],
        audio_data=synthesis.get('audio_data'),
        audio_format=synthesis.get('audio_format'),
        processing_time=synthesis.get('processing_time'),
        error=synthesis.get('error')
    )

@app.get("/api/voices", response_model=List[VoiceInfo])
async def get_available_voices():
    """Get available TTS voices"""

    if not tts_provider:
        raise HTTPException(status_code=503, detail="TTS service not available")

    voices_result = await tts_provider.get_available_voices()

    if voices_result.is_failure():
        raise HTTPException(status_code=500, detail=voices_result.get_error())

    voices = voices_result.get_value()

    return [
        VoiceInfo(
            name=voice.name,
            language=voice.language,
            description=voice.description
        )
        for voice in voices
    ]

# WebSocket endpoints using Phase 3 WebSocket manager

@app.websocket("/ws/transcribe")
async def websocket_transcribe(websocket: WebSocket):
    """WebSocket endpoint for real-time transcription"""
    logger.info(f"🔌 WebSocket connection attempt from {websocket.client}")
    
    try:
        await websocket.accept()
        client_id = str(uuid.uuid4())
        
        logger.info(f"🔌 WebSocket client {client_id} connected successfully")
    except Exception as e:
        logger.error(f"❌ WebSocket accept failed: {e}")
        return
    
    try:
        # Send welcome message that client expects
        await websocket.send_json({
            "type": "connection",
            "status": "connected", 
            "client_id": client_id,
            "message": "Ready for transcription"
        })
        
        # Handle messages
        while True:
            try:
                data = await websocket.receive_json()
                message_type = data.get("type", "")
                
                if message_type == "config":
                    # Handle configuration
                    await websocket.send_json({
                        "type": "config",
                        "status": "configured",
                        "model": data.get("model", "base"),
                        "language": data.get("language")
                    })
                    
                elif message_type == "audio":
                    # Handle audio data through Phase 3 pipeline
                    await _process_websocket_audio(websocket, data, client_id)
                    
                elif message_type == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": time.time()
                    })
                    
            except Exception as e:
                logger.error(f"❌ WebSocket message error: {e}")
                break
                
    except Exception as e:
        logger.error(f"❌ WebSocket connection error: {e}")
    finally:
        logger.info(f"🔌 WebSocket client {client_id} disconnected")

async def _process_websocket_audio(websocket: WebSocket, data: dict, client_id: str):
    """Process WebSocket audio through Phase 3 pipeline"""
    try:
        # Extract audio data (base64 encoded)
        audio_data_b64 = data.get("data", "")
        audio_format = data.get("format", "webm")
        model = data.get("model", "base")
        
        if not audio_data_b64:
            await websocket.send_json({
                "type": "error",
                "message": "No audio data provided"
            })
            return
            
        # Decode base64 audio data
        import base64
        try:
            audio_bytes = base64.b64decode(audio_data_b64)
        except Exception as e:
            await websocket.send_json({
                "type": "error", 
                "message": f"Invalid audio data: {str(e)}"
            })
            return
            
        # Create AudioData object for Phase 3 pipeline
        audio_data = AudioData(
            data=audio_bytes,
            format=audio_format,
            sample_rate=16000  # Default sample rate
        )
        
        # Create processing context
        context = ProcessingContext(
            request_id=str(uuid.uuid4()),
            client_id=client_id,
            model=model,
            language=data.get("language")
        )
        
        start_time = time.time()
        
        # Process through Phase 3 pipeline
        result = await pipeline.process(audio_data, context)
        
        processing_time = time.time() - start_time
        
        if result.is_success():
            processed_audio = result.get_value()
            transcription_text = processed_audio.metadata.get("transcription_text", "")
            
            # Fire completion event
            completion_event = TranscriptionCompletedEvent.create(
                request_id=context.request_id,
                text=transcription_text,
                language=context.language or "en",
                processing_time=processing_time,
                client_id=client_id
            )
            await event_bus.publish(completion_event)
            
            # Send successful transcription response
            await websocket.send_json({
                "type": "transcription",
                "status": "completed",
                "text": transcription_text,
                "language": context.language or "en",
                "processing_time": processing_time,
                "timestamp": time.time()
            })
            
        else:
            # Handle pipeline failure
            error_message = result.get_error()
            logger.error(f"❌ Pipeline failed for WebSocket audio: {error_message}")
            
            await websocket.send_json({
                "type": "transcription",
                "status": "failed", 
                "error": error_message,
                "processing_time": processing_time
            })
            
    except Exception as e:
        logger.error(f"❌ WebSocket audio processing error: {e}")
        await websocket.send_json({
            "type": "error",
            "message": f"Audio processing failed: {str(e)}"
        })

@app.websocket("/ws/synthesize")
async def websocket_synthesize(websocket: WebSocket):
    """WebSocket endpoint for real-time TTS synthesis"""
    logger.info(f"🔌 TTS WebSocket connection attempt from {websocket.client}")

    if not tts_pipeline:
        logger.error("❌ TTS pipeline not available")
        await websocket.close(code=1011, reason="TTS service not available")
        return

    try:
        await websocket.accept()
        client_id = str(uuid.uuid4())

        logger.info(f"🔌 TTS WebSocket client {client_id} connected successfully")
    except Exception as e:
        logger.error(f"❌ TTS WebSocket accept failed: {e}")
        return

    try:
        # Send welcome message
        await websocket.send_json({
            "type": "connection",
            "status": "connected",
            "client_id": client_id,
            "message": "Ready for text-to-speech synthesis"
        })

        # Handle messages
        while True:
            try:
                data = await websocket.receive_json()
                message_type = data.get("type", "")

                if message_type == "config":
                    # Handle configuration
                    await websocket.send_json({
                        "type": "config",
                        "status": "configured",
                        "voice": data.get("voice", "default"),
                        "speed": data.get("speed", 1.0)
                    })

                elif message_type == "text":
                    # Handle text synthesis
                    await _process_websocket_synthesis(websocket, data, client_id)

                elif message_type == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": time.time()
                    })

            except Exception as e:
                logger.error(f"❌ TTS WebSocket message error: {e}")
                break

    except Exception as e:
        logger.error(f"❌ TTS WebSocket connection error: {e}")
    finally:
        logger.info(f"🔌 TTS WebSocket client {client_id} disconnected")

async def _process_websocket_synthesis(websocket: WebSocket, data: dict, client_id: str):
    """Process WebSocket text synthesis through TTS pipeline"""
    try:
        # Extract text data
        text = data.get("text", "")
        voice = data.get("voice", "default")
        speed = data.get("speed", 1.0)
        output_format = data.get("format", "wav")

        if not text or not text.strip():
            await websocket.send_json({
                "type": "error",
                "message": "No text provided"
            })
            return

        # Create TextData object for TTS pipeline
        text_data = TextData(
            text=text,
            language=data.get("language")
        )

        # Create TTS context
        context = TTSContext(
            request_id=str(uuid.uuid4()),
            client_id=client_id,
            voice=voice,
            speed=speed,
            output_format=output_format
        )

        start_time = time.time()

        # Fire text submitted event
        submit_event = TextSubmittedEvent.create(
            request_id=context.request_id,
            text=text,
            voice=voice,
            client_id=client_id
        )
        await event_bus.publish(submit_event)

        # Process through TTS pipeline
        result = await tts_pipeline.process(text_data, context)

        processing_time = time.time() - start_time

        if result.is_success():
            audio_data = result.get_value()

            # Encode audio to base64
            audio_b64 = base64.b64encode(audio_data.data).decode('utf-8')

            # Fire completion event
            completion_event = SynthesisCompletedEvent.create(
                request_id=context.request_id,
                audio_size=len(audio_data.data),
                duration=audio_data.metadata.get('duration', 0.0),
                processing_time=processing_time,
                client_id=client_id
            )
            await event_bus.publish(completion_event)

            # Send successful synthesis response
            await websocket.send_json({
                "type": "audio",
                "status": "completed",
                "data": audio_b64,
                "format": audio_data.format,
                "sample_rate": audio_data.sample_rate,
                "processing_time": processing_time,
                "timestamp": time.time()
            })

        else:
            # Handle pipeline failure
            error_message = result.get_error()
            logger.error(f"❌ TTS Pipeline failed for WebSocket text: {error_message}")

            await websocket.send_json({
                "type": "audio",
                "status": "failed",
                "error": error_message,
                "processing_time": processing_time
            })

    except Exception as e:
        logger.error(f"❌ WebSocket synthesis processing error: {e}")
        await websocket.send_json({
            "type": "error",
            "message": f"Synthesis processing failed: {str(e)}"
        })

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "architecture": "phase3_functional",
        "components": {
            "event_bus": "running" if event_bus else "stopped",
            "websocket_manager": "initialized" if websocket_manager else "not_initialized",
            "stt_pipeline": "ready" if pipeline else "not_ready",
            "tts_pipeline": "ready" if tts_pipeline else "not_ready",
            "tts_provider": "initialized" if tts_provider else "not_initialized"
        }
    }

def main():
    """Main entry point for Phase 3 server"""
    logger.info("🎤 Starting Whisper Phase 3 Server")
    logger.info("Architecture: Functional, Composable, Event-Driven")
    
    uvicorn.run(
        app,  # Pass the app directly instead of string
        host="0.0.0.0",  # Allow external connections from your MacBook
        port=8000,
        reload=False,  # Disable reload for stability
        log_level="info"
    )

if __name__ == "__main__":
    main()
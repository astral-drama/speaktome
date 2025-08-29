// Audio client for WebRTC recording and WebSocket communication

class AudioClient {
    constructor() {
        this.websocket = null;
        this.mediaRecorder = null;
        this.audioStream = null;
        this.audioContext = null;
        this.analyser = null;
        this.dataArray = null;
        this.animationFrame = null;
        
        // Recording state
        this.isRecording = false;
        this.isConnected = false;
        this.recordedChunks = [];
        
        // Settings
        this.settings = {
            model: 'base',
            language: null,
            recordingMode: 'batch', // 'streaming' or 'batch' 
            autoSend: true
        };
        
        // Event emitter
        this.events = Utils.createEventEmitter();
        
        // Initialize
        this.init();
    }

    async init() {
        // Check browser support
        const support = Utils.checkBrowserSupport();
        if (!support.supported) {
            console.warn('Browser support issues:', support.missing);
            // For testing - allow connection even without getUserMedia
            // Just disable recording functionality
            if (support.missing.includes('getUserMedia')) {
                console.warn('Microphone access not available - recording disabled');
            } else {
                this.events.emit('error', {
                    message: `Browser not supported. Missing: ${support.missing.join(', ')}`,
                    code: 'BROWSER_NOT_SUPPORTED'
                });
                return;
            }
        }

        // Load settings from storage
        this.loadSettings();
        
        // Connect to WebSocket
        await this.connect();
    }

    loadSettings() {
        const savedSettings = Utils.storage.get('whisper-settings', {});
        this.settings = { ...this.settings, ...savedSettings };
    }

    saveSettings() {
        Utils.storage.set('whisper-settings', this.settings);
    }

    async connect() {
        try {
            const wsUrl = Utils.getWebSocketUrl('/ws/transcribe');
            console.log('Connecting to WebSocket:', wsUrl);
            
            this.websocket = new WebSocket(wsUrl);
            
            this.websocket.onopen = () => {
                console.log('WebSocket connected');
                this.isConnected = true;
                this.events.emit('connected');
                this.sendConfig();
            };
            
            this.websocket.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleWebSocketMessage(data);
                } catch (error) {
                    console.error('Error parsing WebSocket message:', error);
                }
            };
            
            this.websocket.onclose = (event) => {
                console.log('WebSocket disconnected:', event.code, event.reason);
                this.isConnected = false;
                this.events.emit('disconnected', { code: event.code, reason: event.reason });
                
                // Attempt to reconnect if not intentional
                if (event.code !== 1000) {
                    setTimeout(() => this.reconnect(), 5000);
                }
            };
            
            this.websocket.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.events.emit('error', { 
                    message: 'WebSocket connection failed',
                    code: 'WEBSOCKET_ERROR'
                });
            };
            
        } catch (error) {
            console.error('Error connecting to WebSocket:', error);
            this.events.emit('error', { 
                message: 'Failed to connect to server',
                code: 'CONNECTION_FAILED'
            });
        }
    }

    async reconnect() {
        if (this.isConnected) return;
        
        console.log('Attempting to reconnect...');
        this.events.emit('reconnecting');
        
        await Utils.retry(
            () => this.connect(),
            {
                retries: 5,
                delay: 1000,
                backoff: 2,
                onRetry: (error, attempt, waitTime) => {
                    console.log(`Reconnection attempt ${attempt} in ${waitTime}ms`);
                }
            }
        );
    }

    disconnect() {
        if (this.websocket) {
            this.websocket.close(1000, 'Client disconnect');
            this.websocket = null;
        }
        
        this.stopRecording();
        this.isConnected = false;
    }

    sendConfig() {
        if (!this.isConnected || !this.websocket) return;
        
        this.websocket.send(JSON.stringify({
            type: 'config',
            model: this.settings.model,
            language: this.settings.language
        }));
    }

    handleWebSocketMessage(data) {
        switch (data.type) {
            case 'connection':
                this.events.emit('connection', data);
                break;
                
            case 'config':
                this.events.emit('config', data);
                break;
                
            case 'transcription':
                this.events.emit('transcription', {
                    text: data.text,
                    language: data.language,
                    processingTime: data.processing_time,
                    timestamp: data.timestamp
                });
                break;
                
            case 'error':
                this.events.emit('error', {
                    message: data.message,
                    code: 'SERVER_ERROR'
                });
                break;
                
            case 'pong':
                // Handle ping/pong for keep-alive
                break;
                
            default:
                console.warn('Unknown message type:', data.type);
        }
    }

    async requestMicrophoneAccess() {
        try {
            const permission = await Utils.requestMicrophonePermission();
            if (!permission.granted) {
                throw new Error(permission.error || 'Microphone access denied');
            }
            
            this.audioStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    sampleRate: 16000
                }
            });
            
            this.setupAudioAnalysis();
            this.events.emit('microphoneReady');
            
            return true;
        } catch (error) {
            console.error('Microphone access error:', error);
            this.events.emit('error', {
                message: `Microphone access failed: ${error.message}`,
                code: 'MICROPHONE_ACCESS_DENIED'
            });
            return false;
        }
    }

    setupAudioAnalysis() {
        if (!this.audioStream) return;
        
        try {
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const source = this.audioContext.createMediaStreamSource(this.audioStream);
            
            this.analyser = this.audioContext.createAnalyser();
            this.analyser.fftSize = 256;
            this.analyser.smoothingTimeConstant = 0.8;
            
            source.connect(this.analyser);
            
            this.dataArray = new Uint8Array(this.analyser.frequencyBinCount);
            
            // Start audio level monitoring
            this.updateAudioLevel();
            
        } catch (error) {
            console.error('Error setting up audio analysis:', error);
        }
    }

    updateAudioLevel() {
        if (!this.analyser || !this.dataArray) return;
        
        this.analyser.getByteFrequencyData(this.dataArray);
        const level = Utils.getAudioLevel(this.dataArray);
        
        this.events.emit('audioLevel', level);
        
        if (this.isRecording || this.audioStream) {
            this.animationFrame = requestAnimationFrame(() => this.updateAudioLevel());
        }
    }

    async startRecording() {
        if (this.isRecording) return false;
        
        // Request microphone access if not already available
        if (!this.audioStream) {
            const hasAccess = await this.requestMicrophoneAccess();
            if (!hasAccess) return false;
        }
        
        try {
            // Resume audio context if needed
            if (this.audioContext && this.audioContext.state === 'suspended') {
                await this.audioContext.resume();
            }
            
            // Setup MediaRecorder
            const options = {
                mimeType: this.getSupportedMimeType(),
                bitsPerSecond: 128000
            };
            
            this.mediaRecorder = new MediaRecorder(this.audioStream, options);
            this.recordedChunks = [];
            
            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data && event.data.size > 0) {
                    this.recordedChunks.push(event.data);
                    
                    // For streaming mode, send data immediately
                    if (this.settings.recordingMode === 'streaming') {
                        this.sendAudioChunk(event.data);
                    }
                }
            };
            
            this.mediaRecorder.onstop = () => {
                console.log('Recording stopped');
                
                // For batch mode, send all data when recording stops
                if (this.settings.recordingMode === 'batch' && this.recordedChunks.length > 0) {
                    console.log(`Batch mode: Processing ${this.recordedChunks.length} audio chunks`);
                    const audioBlob = new Blob(this.recordedChunks, { 
                        type: this.mediaRecorder.mimeType 
                    });
                    console.log(`Sending complete audio file: ${(audioBlob.size / 1024).toFixed(1)} KB`);
                    this.sendAudioFile(audioBlob);
                }
                
                this.events.emit('recordingStopped');
            };
            
            this.mediaRecorder.onerror = (error) => {
                console.error('MediaRecorder error:', error);
                this.events.emit('error', {
                    message: 'Recording error occurred',
                    code: 'RECORDING_ERROR'
                });
            };
            
            // Start recording
            const timeslice = this.settings.recordingMode === 'streaming' ? 1000 : undefined;
            this.mediaRecorder.start(timeslice);
            
            this.isRecording = true;
            this.events.emit('recordingStarted');
            
            return true;
            
        } catch (error) {
            console.error('Error starting recording:', error);
            this.events.emit('error', {
                message: `Failed to start recording: ${error.message}`,
                code: 'RECORDING_START_FAILED'
            });
            return false;
        }
    }

    stopRecording() {
        if (!this.isRecording || !this.mediaRecorder) return false;
        
        try {
            this.mediaRecorder.stop();
            this.isRecording = false;
            return true;
        } catch (error) {
            console.error('Error stopping recording:', error);
            this.isRecording = false;
            return false;
        }
    }

    getSupportedMimeType() {
        const types = [
            'audio/webm;codecs=opus',
            'audio/webm',
            'audio/ogg;codecs=opus',
            'audio/ogg',
            'audio/wav',
            'audio/mp4'
        ];
        
        for (const type of types) {
            if (MediaRecorder.isTypeSupported(type)) {
                return type;
            }
        }
        
        return 'audio/webm'; // Fallback
    }

    async sendAudioChunk(audioBlob) {
        if (!this.isConnected || !this.websocket) return;
        
        try {
            const base64Data = await this.blobToBase64(audioBlob);
            const format = this.getFormatFromMimeType(audioBlob.type || this.mediaRecorder.mimeType);
            
            this.websocket.send(JSON.stringify({
                type: 'audio',
                data: base64Data,
                format: format,
                model: this.settings.model,
                language: this.settings.language
            }));
            
        } catch (error) {
            console.error('Error sending audio chunk:', error);
            this.events.emit('error', {
                message: 'Failed to send audio data',
                code: 'SEND_AUDIO_FAILED'
            });
        }
    }

    async sendAudioFile(audioBlob) {
        if (this.settings.recordingMode === 'streaming') {
            // Already sent in chunks
            return;
        }
        
        await this.sendAudioChunk(audioBlob);
    }

    async blobToBase64(blob) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onloadend = () => {
                const base64 = reader.result.split(',')[1]; // Remove data URL prefix
                resolve(base64);
            };
            reader.onerror = reject;
            reader.readAsDataURL(blob);
        });
    }

    getFormatFromMimeType(mimeType) {
        if (mimeType.includes('webm')) return 'webm';
        if (mimeType.includes('ogg')) return 'ogg';
        if (mimeType.includes('wav')) return 'wav';
        if (mimeType.includes('mp4')) return 'mp4';
        return 'webm'; // Default
    }

    async uploadFile(file) {
        const validation = Utils.validateAudioFile(file);
        if (!validation.valid) {
            this.events.emit('error', {
                message: validation.error,
                code: 'FILE_VALIDATION_FAILED'
            });
            return;
        }
        
        try {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('model', this.settings.model);
            if (this.settings.language) {
                formData.append('language', this.settings.language);
            }
            
            this.events.emit('uploadStarted', { fileName: file.name, fileSize: file.size });
            
            const response = await fetch('/api/transcribe', {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Upload failed');
            }
            
            const result = await response.json();
            this.events.emit('uploadCompleted', result);
            
            // Poll for result
            this.pollForResult(result.id);
            
        } catch (error) {
            console.error('Upload error:', error);
            this.events.emit('error', {
                message: `Upload failed: ${error.message}`,
                code: 'UPLOAD_FAILED'
            });
        }
    }

    async pollForResult(requestId, maxAttempts = 60) {
        let attempts = 0;
        
        const poll = async () => {
            try {
                attempts++;
                const response = await fetch(`/api/transcribe/${requestId}`);
                
                if (!response.ok) {
                    throw new Error('Failed to get transcription result');
                }
                
                const result = await response.json();
                
                if (result.status === 'completed') {
                    this.events.emit('transcription', {
                        text: result.text,
                        language: result.language,
                        processingTime: result.processing_time
                    });
                } else if (result.status === 'failed') {
                    this.events.emit('error', {
                        message: result.error || 'Transcription failed',
                        code: 'TRANSCRIPTION_FAILED'
                    });
                } else if (attempts < maxAttempts) {
                    // Still processing, poll again
                    setTimeout(poll, 1000);
                } else {
                    // Timeout
                    this.events.emit('error', {
                        message: 'Transcription timeout',
                        code: 'TRANSCRIPTION_TIMEOUT'
                    });
                }
                
            } catch (error) {
                console.error('Polling error:', error);
                this.events.emit('error', {
                    message: 'Failed to get transcription result',
                    code: 'POLLING_FAILED'
                });
            }
        };
        
        poll();
    }

    updateSettings(newSettings) {
        this.settings = { ...this.settings, ...newSettings };
        this.saveSettings();
        
        // Send updated config to server
        if (this.isConnected) {
            this.sendConfig();
        }
        
        this.events.emit('settingsUpdated', this.settings);
    }

    getSettings() {
        return { ...this.settings };
    }

    cleanup() {
        // Stop recording
        this.stopRecording();
        
        // Cancel animation frame
        if (this.animationFrame) {
            cancelAnimationFrame(this.animationFrame);
        }
        
        // Close audio stream
        if (this.audioStream) {
            this.audioStream.getTracks().forEach(track => track.stop());
            this.audioStream = null;
        }
        
        // Close audio context
        if (this.audioContext && this.audioContext.state !== 'closed') {
            this.audioContext.close();
            this.audioContext = null;
        }
        
        // Close WebSocket
        this.disconnect();
    }

    // Event handling methods
    on(event, callback) {
        this.events.on(event, callback);
    }

    off(event, callback) {
        this.events.off(event, callback);
    }
}

// Export for use in other modules
window.AudioClient = AudioClient;
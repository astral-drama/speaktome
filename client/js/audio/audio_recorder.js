// Audio Recording Module - Focused on microphone access and recording

class AudioRecorder {
    constructor() {
        this.mediaRecorder = null;
        this.audioStream = null;
        this.audioContext = null;
        this.analyser = null;
        this.dataArray = null;
        this.animationFrame = null;
        
        // Recording state
        this.isRecording = false;
        this.recordedChunks = [];
        
        // Event emitter
        this.events = Utils.createEventEmitter();
        
        // Recording settings
        this.recordingSettings = {
            echoCancellation: true,
            noiseSuppression: true,
            sampleRate: 16000
        };
    }
    
    async requestMicrophoneAccess() {
        try {
            const permission = await Utils.requestMicrophonePermission();
            if (!permission.granted) {
                throw new Error(permission.error || 'Microphone access denied');
            }
            
            this.audioStream = await navigator.mediaDevices.getUserMedia({
                audio: this.recordingSettings
            });
            
            this.setupAudioAnalysis();
            this.events.emit('microphoneReady');
            
            return { success: true };
            
        } catch (error) {
            const errorResult = {
                success: false,
                error: error.message,
                code: 'MICROPHONE_ACCESS_DENIED'
            };
            
            this.events.emit('error', errorResult);
            return errorResult;
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
            this.events.emit('error', {
                success: false,
                error: error.message,
                code: 'AUDIO_ANALYSIS_FAILED'
            });
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
    
    async startRecording(options = {}) {
        if (this.isRecording) {
            return { success: false, error: 'Already recording' };
        }
        
        // Request microphone access if not already available
        if (!this.audioStream) {
            const accessResult = await this.requestMicrophoneAccess();
            if (!accessResult.success) return accessResult;
        }
        
        try {
            // Resume audio context if needed
            if (this.audioContext && this.audioContext.state === 'suspended') {
                await this.audioContext.resume();
            }
            
            // Setup MediaRecorder
            const mediaRecorderOptions = {
                mimeType: this.getSupportedMimeType(),
                bitsPerSecond: options.bitsPerSecond || 128000
            };
            
            this.mediaRecorder = new MediaRecorder(this.audioStream, mediaRecorderOptions);
            this.recordedChunks = [];
            
            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data && event.data.size > 0) {
                    this.recordedChunks.push(event.data);
                    this.events.emit('audioData', {
                        data: event.data,
                        chunks: this.recordedChunks.length
                    });
                }
            };
            
            this.mediaRecorder.onstop = () => {
                this.events.emit('recordingStopped', {
                    chunks: this.recordedChunks,
                    duration: this.getRecordingDuration()
                });
            };
            
            this.mediaRecorder.onerror = (error) => {
                this.events.emit('error', {
                    success: false,
                    error: 'Recording error occurred',
                    code: 'RECORDING_ERROR',
                    details: error
                });
            };
            
            // Start recording
            const timeslice = options.timeslice || undefined;
            this.mediaRecorder.start(timeslice);
            
            this.isRecording = true;
            this.recordingStartTime = Date.now();
            this.events.emit('recordingStarted');
            
            return { success: true };
            
        } catch (error) {
            return {
                success: false,
                error: `Failed to start recording: ${error.message}`,
                code: 'RECORDING_START_FAILED'
            };
        }
    }
    
    stopRecording() {
        if (!this.isRecording || !this.mediaRecorder) {
            return { success: false, error: 'Not recording' };
        }
        
        try {
            this.mediaRecorder.stop();
            this.isRecording = false;
            return { success: true };
        } catch (error) {
            this.isRecording = false;
            return {
                success: false,
                error: `Failed to stop recording: ${error.message}`,
                code: 'RECORDING_STOP_FAILED'
            };
        }
    }
    
    getRecordingBlob() {
        if (this.recordedChunks.length === 0) {
            return null;
        }
        
        return new Blob(this.recordedChunks, { 
            type: this.mediaRecorder ? this.mediaRecorder.mimeType : 'audio/webm' 
        });
    }
    
    getRecordingDuration() {
        return this.recordingStartTime ? Date.now() - this.recordingStartTime : 0;
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
    
    cleanup() {
        // Stop recording
        this.stopRecording();
        
        // Cancel animation frame
        if (this.animationFrame) {
            cancelAnimationFrame(this.animationFrame);
            this.animationFrame = null;
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
        
        // Clear data
        this.recordedChunks = [];
        this.dataArray = null;
        this.analyser = null;
        this.mediaRecorder = null;
    }
    
    // Event handling
    on(event, callback) {
        this.events.on(event, callback);
    }
    
    off(event, callback) {
        this.events.off(event, callback);
    }
    
    // Configuration
    updateRecordingSettings(settings) {
        this.recordingSettings = { ...this.recordingSettings, ...settings };
    }
    
    getRecordingSettings() {
        return { ...this.recordingSettings };
    }
}

// Export for use in other modules
window.AudioRecorder = AudioRecorder;
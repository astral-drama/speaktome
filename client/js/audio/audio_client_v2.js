// Audio Client V2 - Composed from focused modules

class AudioClientV2 {
    constructor() {
        // Initialize focused modules
        this.recorder = new AudioRecorder();
        this.websocket = new WebSocketClient();
        this.uploader = new FileUploader();
        
        // Settings
        this.settings = {
            model: 'base',
            language: null,
            recordingMode: 'streaming', // 'streaming' or 'batch'
            autoSend: true
        };
        
        // State
        this.isRecording = false;
        this.isConnected = false;
        
        // Event emitter for the composed client
        this.events = Utils.createEventEmitter();
        
        // Initialize
        this.init();
    }
    
    init() {
        // Check browser support
        const support = Utils.checkBrowserSupport();
        if (!support.supported) {
            this.events.emit('error', {
                message: `Browser not supported. Missing: ${support.missing.join(', ')}`,
                code: 'BROWSER_NOT_SUPPORTED'
            });
            return;
        }
        
        // Load settings from storage
        this.loadSettings();
        
        // Setup event forwarding and coordination
        this.setupEventHandling();
        
        // Connect to WebSocket
        this.connect();
    }
    
    setupEventHandling() {
        // WebSocket events
        this.websocket.on('connected', () => {
            this.isConnected = true;
            this.events.emit('connected');
            this.sendConfig();
        });
        
        this.websocket.on('disconnected', (data) => {
            this.isConnected = false;
            this.events.emit('disconnected', data);
        });
        
        this.websocket.on('reconnecting', (data) => {
            this.events.emit('reconnecting', data);
        });
        
        this.websocket.on('transcription', (data) => {
            this.events.emit('transcription', data);
        });
        
        this.websocket.on('error', (error) => {
            this.events.emit('error', error);
        });
        
        // Recorder events
        this.recorder.on('microphoneReady', () => {
            this.events.emit('microphoneReady');
        });
        
        this.recorder.on('recordingStarted', () => {
            this.isRecording = true;
            this.events.emit('recordingStarted');
        });
        
        this.recorder.on('recordingStopped', (data) => {
            this.isRecording = false;
            this.events.emit('recordingStopped');
            
            // Handle recorded data based on mode
            if (this.settings.recordingMode === 'batch' && data.chunks.length > 0) {
                this.handleBatchRecording(data);
            }
        });
        
        this.recorder.on('audioData', (data) => {
            // Handle streaming data
            if (this.settings.recordingMode === 'streaming' && this.settings.autoSend) {
                this.handleStreamingAudio(data.data);
            }
        });
        
        this.recorder.on('audioLevel', (level) => {
            this.events.emit('audioLevel', level);
        });
        
        this.recorder.on('error', (error) => {
            this.events.emit('error', error);
        });
        
        // Uploader events
        this.uploader.on('uploadStarted', (data) => {
            this.events.emit('uploadStarted', data);
        });
        
        this.uploader.on('uploadCompleted', (data) => {
            this.events.emit('uploadCompleted', data);
        });
        
        this.uploader.on('transcription', (data) => {
            this.events.emit('transcription', data);
        });
        
        this.uploader.on('error', (error) => {
            this.events.emit('error', error);
        });
    }
    
    async connect() {
        return this.websocket.connect('/ws/transcribe');
    }
    
    async disconnect() {
        this.stopRecording();
        return this.websocket.disconnect();
    }
    
    sendConfig() {
        if (!this.isConnected) return { success: false, error: 'Not connected' };
        
        return this.websocket.sendConfig(this.settings.model, this.settings.language);
    }
    
    async requestMicrophoneAccess() {
        return this.recorder.requestMicrophoneAccess();
    }
    
    async startRecording() {
        if (!this.isConnected) {
            return { success: false, error: 'Not connected to server' };
        }
        
        const options = {
            timeslice: this.settings.recordingMode === 'streaming' ? 1000 : undefined,
            bitsPerSecond: 128000
        };
        
        return this.recorder.startRecording(options);
    }
    
    stopRecording() {
        return this.recorder.stopRecording();
    }
    
    async handleStreamingAudio(audioBlob) {
        try {
            const base64Data = await this.blobToBase64(audioBlob);
            const format = this.getFormatFromMimeType(audioBlob.type || this.recorder.getSupportedMimeType());
            
            return this.websocket.sendAudio(base64Data, format, this.settings.model, this.settings.language);
        } catch (error) {
            this.events.emit('error', {
                code: 'SEND_AUDIO_FAILED',
                error: 'Failed to send streaming audio',
                details: error.message
            });
            return { success: false, error: error.message };
        }
    }
    
    async handleBatchRecording(recordingData) {
        const audioBlob = this.recorder.getRecordingBlob();
        if (!audioBlob) return;
        
        if (this.isConnected) {
            // Send via WebSocket for faster processing
            return this.handleStreamingAudio(audioBlob);
        } else {
            // Fallback to HTTP upload
            const file = this.uploader.createFileFromBlob(
                audioBlob, 
                `recording_${Date.now()}.webm`, 
                audioBlob.type
            );
            
            return this.uploader.uploadAndWaitForResult(file, {
                model: this.settings.model,
                language: this.settings.language
            });
        }
    }
    
    async uploadFile(file) {
        return this.uploader.uploadAndWaitForResult(file, {
            model: this.settings.model,
            language: this.settings.language
        });
    }
    
    // Utility methods
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
    
    // Settings management
    loadSettings() {
        const savedSettings = Utils.storage.get('whisper-settings', {});
        this.settings = { ...this.settings, ...savedSettings };
    }
    
    saveSettings() {
        Utils.storage.set('whisper-settings', this.settings);
    }
    
    updateSettings(newSettings) {
        this.settings = { ...this.settings, ...newSettings };
        this.saveSettings();
        
        // Update individual modules
        if (newSettings.maxFileSize) {
            this.uploader.updateUploadSettings({ 
                maxFileSize: newSettings.maxFileSize * 1024 * 1024 
            });
        }
        
        // Send updated config to server
        if (this.isConnected) {
            this.sendConfig();
        }
        
        this.events.emit('settingsUpdated', this.settings);
    }
    
    getSettings() {
        return { ...this.settings };
    }
    
    // Status and info
    getConnectionState() {
        return {
            ...this.websocket.getConnectionState(),
            isRecording: this.isRecording
        };
    }
    
    getRecordingInfo() {
        return {
            isRecording: this.isRecording,
            settings: this.recorder.getRecordingSettings(),
            supportedMimeType: this.recorder.getSupportedMimeType(),
            recordingDuration: this.recorder.getRecordingDuration()
        };
    }
    
    getUploadInfo() {
        return {
            settings: this.uploader.getUploadSettings(),
            supportedFormats: this.uploader.getSupportedFormats(),
            maxFileSize: this.uploader.getMaxFileSize()
        };
    }
    
    // Event handling
    on(event, callback) {
        this.events.on(event, callback);
    }
    
    off(event, callback) {
        this.events.off(event, callback);
    }
    
    // Cleanup
    cleanup() {
        this.recorder.cleanup();
        this.websocket.cleanup();
        this.isRecording = false;
        this.isConnected = false;
    }
}

// Export for use in other modules
window.AudioClientV2 = AudioClientV2;
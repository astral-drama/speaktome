// Main application controller

class WhisperApp {
    constructor() {
        // Core components
        this.audioClient = null;
        this.chatInterface = null;
        
        // DOM elements
        this.elements = {};
        
        // State
        this.isRecording = false;
        this.isConnected = false;
        
        // Initialize
        this.init();
    }

    init() {
        // Wait for DOM to be ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.setup());
        } else {
            this.setup();
        }
    }

    setup() {
        // Get DOM elements
        this.cacheElements();
        
        // Initialize components
        this.initializeComponents();
        
        // Setup event listeners
        this.setupEventListeners();
        
        // Setup modals
        this.setupModals();
        
        // Initialize UI state
        this.updateUI();
        
        console.log('Whisper Voice-to-Text App initialized');
    }

    cacheElements() {
        this.elements = {
            // Connection status
            connectionStatus: document.getElementById('connectionStatus'),
            
            // Chat
            chatMessages: document.getElementById('chatMessages'),
            
            // Recording controls
            recordingStatus: document.getElementById('recordingStatus'),
            audioLevel: document.getElementById('audioLevel'),
            recordBtn: document.getElementById('recordBtn'),
            uploadBtn: document.getElementById('uploadBtn'),
            clearBtn: document.getElementById('clearBtn'),
            
            // Settings
            settingsBtn: document.getElementById('settingsBtn'),
            settingsModal: document.getElementById('settingsModal'),
            closeSettings: document.getElementById('closeSettings'),
            modelSelect: document.getElementById('modelSelect'),
            languageSelect: document.getElementById('languageSelect'),
            recordingMode: document.getElementById('recordingMode'),
            autoSend: document.getElementById('autoSend'),
            resetSettings: document.getElementById('resetSettings'),
            saveSettings: document.getElementById('saveSettings'),
            
            // Upload
            uploadModal: document.getElementById('uploadModal'),
            closeUpload: document.getElementById('closeUpload'),
            uploadArea: document.getElementById('uploadArea'),
            browseBtn: document.getElementById('browseBtn'),
            fileInput: document.getElementById('fileInput'),
            uploadProgress: document.getElementById('uploadProgress'),
            progressFill: document.getElementById('progressFill'),
            progressText: document.getElementById('progressText'),
            progressPercent: document.getElementById('progressPercent'),
            
            // Toasts
            errorToast: document.getElementById('errorToast'),
            successToast: document.getElementById('successToast'),
            closeError: document.getElementById('closeError'),
            closeSuccess: document.getElementById('closeSuccess'),
        };
    }

    initializeComponents() {
        // Initialize chat interface
        this.chatInterface = new ChatInterface(this.elements.chatMessages);
        
        // Initialize audio client
        this.audioClient = new AudioClient();
        
        // Setup audio client event listeners
        this.setupAudioClientEvents();
        
        // Load and apply saved settings
        this.loadSettings();
    }

    setupAudioClientEvents() {
        // Connection events
        this.audioClient.on('connected', () => {
            this.isConnected = true;
            this.updateConnectionStatus('connected');
            this.chatInterface.addConnectionMessage('connected');
            this.updateUI();
        });
        
        this.audioClient.on('disconnected', (data) => {
            this.isConnected = false;
            this.updateConnectionStatus('disconnected');
            this.chatInterface.addConnectionMessage('disconnected');
            this.updateUI();
        });
        
        this.audioClient.on('reconnecting', () => {
            this.updateConnectionStatus('connecting');
            this.chatInterface.addConnectionMessage('reconnecting');
        });
        
        // Recording events
        this.audioClient.on('microphoneReady', () => {
            this.elements.recordBtn.disabled = false;
            this.updateRecordingStatus('Ready to record');
        });
        
        this.audioClient.on('recordingStarted', () => {
            this.isRecording = true;
            this.chatInterface.addRecordingStartMessage();
            this.updateUI();
        });
        
        this.audioClient.on('recordingStopped', () => {
            this.isRecording = false;
            this.chatInterface.addRecordingStopMessage();
            this.updateUI();
        });
        
        // Audio level updates
        this.audioClient.on('audioLevel', (level) => {
            this.updateAudioLevel(level);
        });
        
        // Transcription results
        this.audioClient.on('transcription', (data) => {
            this.chatInterface.addTranscription(data.text, {
                language: data.language,
                processingTime: data.processingTime
            });
        });
        
        // Upload events
        this.audioClient.on('uploadStarted', (data) => {
            this.showUploadProgress();
            this.updateUploadProgress(0, `Uploading ${data.fileName}...`);
        });
        
        this.audioClient.on('uploadCompleted', (data) => {
            this.updateUploadProgress(100, 'Processing...');
        });
        
        // Error handling
        this.audioClient.on('error', (error) => {
            console.error('Audio client error:', error);
            Utils.showToast(error.message, 'error');
            
            // Update UI based on error type
            if (error.code === 'MICROPHONE_ACCESS_DENIED') {
                this.updateRecordingStatus('Microphone access denied');
                this.elements.recordBtn.disabled = true;
            }
        });
    }

    setupEventListeners() {
        // Record button
        this.elements.recordBtn.addEventListener('click', () => {
            this.toggleRecording();
        });
        
        // Upload button
        this.elements.uploadBtn.addEventListener('click', () => {
            this.showModal('uploadModal');
        });
        
        // Clear button
        this.elements.clearBtn.addEventListener('click', () => {
            if (confirm('Clear all messages?')) {
                this.chatInterface.clearMessages();
            }
        });
        
        // Settings button
        this.elements.settingsBtn.addEventListener('click', () => {
            this.showModal('settingsModal');
        });
        
        // File input
        this.elements.fileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                this.handleFileUpload(e.target.files[0]);
            }
        });
        
        // Browse button
        this.elements.browseBtn.addEventListener('click', () => {
            this.elements.fileInput.click();
        });
        
        // Drag and drop
        this.setupDragAndDrop();
        
        // Settings form
        this.elements.saveSettings.addEventListener('click', () => {
            this.saveSettings();
        });
        
        this.elements.resetSettings.addEventListener('click', () => {
            this.resetSettings();
        });
        
        // Toast close buttons
        this.elements.closeError.addEventListener('click', () => {
            this.elements.errorToast.style.display = 'none';
        });
        
        this.elements.closeSuccess.addEventListener('click', () => {
            this.elements.successToast.style.display = 'none';
        });
        
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            // Space bar to toggle recording (when not typing)
            if (e.code === 'Space' && !this.isTyping(e.target)) {
                e.preventDefault();
                this.toggleRecording();
            }
            
            // Escape to close modals
            if (e.key === 'Escape') {
                this.hideAllModals();
            }
        });
    }

    setupModals() {
        // Close buttons
        this.elements.closeSettings.addEventListener('click', () => {
            this.hideModal('settingsModal');
        });
        
        this.elements.closeUpload.addEventListener('click', () => {
            this.hideModal('uploadModal');
        });
        
        // Click outside to close
        [this.elements.settingsModal, this.elements.uploadModal].forEach(modal => {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    this.hideModal(modal.id);
                }
            });
        });
    }

    setupDragAndDrop() {
        const uploadArea = this.elements.uploadArea;
        
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            uploadArea.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
            });
        });
        
        ['dragenter', 'dragover'].forEach(eventName => {
            uploadArea.addEventListener(eventName, () => {
                uploadArea.classList.add('drag-over');
            });
        });
        
        ['dragleave', 'drop'].forEach(eventName => {
            uploadArea.addEventListener(eventName, () => {
                uploadArea.classList.remove('drag-over');
            });
        });
        
        uploadArea.addEventListener('drop', (e) => {
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                this.handleFileUpload(files[0]);
            }
        });
    }

    async toggleRecording() {
        if (!this.isConnected) {
            Utils.showToast('Not connected to server', 'error');
            return;
        }
        
        if (this.isRecording) {
            // Stop recording
            const stopped = this.audioClient.stopRecording();
            if (stopped) {
                this.updateRecordingStatus('Processing...');
            }
        } else {
            // Start recording
            this.updateRecordingStatus('Starting...');
            const started = await this.audioClient.startRecording();
            if (started) {
                this.updateRecordingStatus('Recording... Press again to stop');
            } else {
                this.updateRecordingStatus('Failed to start recording');
            }
        }
    }

    async handleFileUpload(file) {
        this.hideModal('uploadModal');
        await this.audioClient.uploadFile(file);
    }

    updateConnectionStatus(status) {
        const statusElement = this.elements.connectionStatus;
        const indicator = statusElement.querySelector('.status-indicator');
        const text = statusElement.querySelector('span');
        
        // Remove all status classes
        indicator.className = 'status-indicator';
        
        const statusConfig = {
            connecting: { class: 'connecting', text: 'Connecting...' },
            connected: { class: 'connected', text: 'Connected' },
            disconnected: { class: 'disconnected', text: 'Disconnected' }
        };
        
        const config = statusConfig[status] || statusConfig.disconnected;
        indicator.classList.add(config.class);
        text.textContent = config.text;
    }

    updateRecordingStatus(text) {
        const statusText = this.elements.recordingStatus.querySelector('.status-text');
        statusText.textContent = text;
    }

    updateAudioLevel(level) {
        this.elements.audioLevel.style.width = `${level * 100}%`;
    }

    updateUI() {
        // Update record button
        const recordBtn = this.elements.recordBtn;
        const icon = recordBtn.querySelector('i');
        const text = recordBtn.querySelector('span');
        
        if (this.isRecording) {
            recordBtn.classList.add('recording');
            icon.className = 'fas fa-stop';
            text.textContent = 'Stop Recording';
        } else {
            recordBtn.classList.remove('recording');
            icon.className = 'fas fa-microphone';
            text.textContent = 'Start Recording';
        }
        
        // Enable/disable controls based on connection
        recordBtn.disabled = !this.isConnected;
        this.elements.uploadBtn.disabled = !this.isConnected;
    }

    loadSettings() {
        const settings = this.audioClient.getSettings();
        
        this.elements.modelSelect.value = settings.model;
        this.elements.languageSelect.value = settings.language || '';
        this.elements.recordingMode.value = settings.recordingMode;
        this.elements.autoSend.checked = settings.autoSend;
    }

    saveSettings() {
        const settings = {
            model: this.elements.modelSelect.value,
            language: this.elements.languageSelect.value || null,
            recordingMode: this.elements.recordingMode.value,
            autoSend: this.elements.autoSend.checked
        };
        
        this.audioClient.updateSettings(settings);
        this.hideModal('settingsModal');
        Utils.showToast('Settings saved', 'success', 2000);
    }

    resetSettings() {
        if (confirm('Reset all settings to defaults?')) {
            const defaultSettings = {
                model: 'base',
                language: null,
                recordingMode: 'batch',
                autoSend: true
            };
            
            this.audioClient.updateSettings(defaultSettings);
            this.loadSettings();
            Utils.showToast('Settings reset to defaults', 'success', 2000);
        }
    }

    showModal(modalId) {
        const modal = document.getElementById(modalId);
        modal.classList.add('active');
        modal.style.display = 'flex';
        
        // Focus first input if available
        const firstInput = modal.querySelector('input, select, textarea');
        if (firstInput) {
            setTimeout(() => firstInput.focus(), 100);
        }
    }

    hideModal(modalId) {
        const modal = document.getElementById(modalId);
        modal.classList.remove('active');
        modal.style.display = 'none';
        
        // Hide upload progress if it's the upload modal
        if (modalId === 'uploadModal') {
            this.hideUploadProgress();
        }
    }

    hideAllModals() {
        [this.elements.settingsModal, this.elements.uploadModal].forEach(modal => {
            this.hideModal(modal.id);
        });
    }

    showUploadProgress() {
        this.elements.uploadProgress.style.display = 'block';
    }

    hideUploadProgress() {
        this.elements.uploadProgress.style.display = 'none';
        this.elements.progressFill.style.width = '0%';
        this.elements.fileInput.value = ''; // Reset file input
    }

    updateUploadProgress(percent, text) {
        this.elements.progressFill.style.width = `${percent}%`;
        this.elements.progressText.textContent = text;
        this.elements.progressPercent.textContent = `${percent}%`;
    }

    isTyping(element) {
        const typingElements = ['INPUT', 'TEXTAREA', 'SELECT'];
        return typingElements.includes(element.tagName) || 
               element.contentEditable === 'true';
    }

    cleanup() {
        if (this.audioClient) {
            this.audioClient.cleanup();
        }
    }
}

// Initialize app when page loads
let app;

document.addEventListener('DOMContentLoaded', () => {
    app = new WhisperApp();
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (app) {
        app.cleanup();
    }
});

// Handle page visibility changes
document.addEventListener('visibilitychange', () => {
    if (document.hidden && app && app.isRecording) {
        // Stop recording when page becomes hidden
        app.toggleRecording();
    }
});

// Export for debugging
window.WhisperApp = WhisperApp;
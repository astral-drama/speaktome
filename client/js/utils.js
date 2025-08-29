// Utility functions for the Whisper Voice-to-Text client

class Utils {
    /**
     * Format timestamp to readable time
     */
    static formatTime(timestamp) {
        const date = new Date(timestamp || Date.now());
        return date.toLocaleTimeString([], { 
            hour: '2-digit', 
            minute: '2-digit',
            second: '2-digit'
        });
    }

    /**
     * Format duration in seconds to readable string
     */
    static formatDuration(seconds) {
        if (seconds < 1) return '< 1s';
        if (seconds < 60) return `${Math.round(seconds)}s`;
        
        const minutes = Math.floor(seconds / 60);
        const remainingSeconds = Math.round(seconds % 60);
        return `${minutes}m ${remainingSeconds}s`;
    }

    /**
     * Format file size to readable string
     */
    static formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        
        return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
    }

    /**
     * Debounce function calls
     */
    static debounce(func, wait, immediate = false) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                timeout = null;
                if (!immediate) func.apply(this, args);
            };
            
            const callNow = immediate && !timeout;
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
            
            if (callNow) func.apply(this, args);
        };
    }

    /**
     * Throttle function calls
     */
    static throttle(func, limit) {
        let inThrottle;
        return function executedFunction(...args) {
            if (!inThrottle) {
                func.apply(this, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    }

    /**
     * Generate unique ID
     */
    static generateId() {
        return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    }

    /**
     * Validate audio file
     */
    static validateAudioFile(file) {
        const supportedTypes = [
            'audio/wav', 'audio/wave', 'audio/x-wav',
            'audio/mpeg', 'audio/mp3',
            'audio/flac',
            'audio/m4a', 'audio/x-m4a',
            'audio/webm',
            'audio/ogg'
        ];

        const maxSize = 50 * 1024 * 1024; // 50MB

        if (!file) {
            return { valid: false, error: 'No file selected' };
        }

        if (file.size > maxSize) {
            return { 
                valid: false, 
                error: `File too large. Maximum size is ${this.formatFileSize(maxSize)}` 
            };
        }

        if (!supportedTypes.includes(file.type)) {
            return { 
                valid: false, 
                error: 'Unsupported file format. Supported formats: MP3, WAV, FLAC, M4A, WebM, OGG' 
            };
        }

        return { valid: true };
    }

    /**
     * Show toast notification
     */
    static showToast(message, type = 'info', duration = 5000) {
        const toast = type === 'error' 
            ? document.getElementById('errorToast')
            : document.getElementById('successToast');
        
        const messageElement = type === 'error'
            ? document.getElementById('errorMessage')
            : document.getElementById('successMessage');

        messageElement.textContent = message;
        toast.style.display = 'flex';

        // Auto-hide after duration
        setTimeout(() => {
            toast.style.display = 'none';
        }, duration);
    }

    /**
     * Show loading overlay
     */
    static showLoading(text = 'Processing...') {
        const overlay = document.getElementById('loadingOverlay');
        const loadingText = document.getElementById('loadingText');
        
        loadingText.textContent = text;
        overlay.style.display = 'flex';
    }

    /**
     * Hide loading overlay
     */
    static hideLoading() {
        const overlay = document.getElementById('loadingOverlay');
        overlay.style.display = 'none';
    }

    /**
     * Escape HTML to prevent XSS
     */
    static escapeHtml(unsafe) {
        return unsafe
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    /**
     * Get audio level from audio data
     */
    static getAudioLevel(audioData) {
        if (!audioData || audioData.length === 0) return 0;

        let sum = 0;
        for (let i = 0; i < audioData.length; i++) {
            sum += audioData[i] * audioData[i];
        }
        
        const rms = Math.sqrt(sum / audioData.length);
        return Math.min(1, rms * 10); // Normalize and amplify
    }

    /**
     * Check if browser supports required features
     */
    static checkBrowserSupport() {
        const support = {
            mediaRecorder: typeof MediaRecorder !== 'undefined',
            webSockets: typeof WebSocket !== 'undefined',
            getUserMedia: !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia),
            audioContext: typeof AudioContext !== 'undefined' || typeof webkitAudioContext !== 'undefined'
        };

        const unsupported = Object.keys(support).filter(key => !support[key]);
        
        return {
            supported: unsupported.length === 0,
            missing: unsupported,
            details: support
        };
    }

    /**
     * Get WebSocket URL based on current location
     */
    static getWebSocketUrl(path = '') {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.host;
        return `${protocol}//${host}${path}`;
    }

    /**
     * Local storage helpers
     */
    static storage = {
        get(key, defaultValue = null) {
            try {
                const item = localStorage.getItem(key);
                return item ? JSON.parse(item) : defaultValue;
            } catch (e) {
                console.warn('Error reading from localStorage:', e);
                return defaultValue;
            }
        },

        set(key, value) {
            try {
                localStorage.setItem(key, JSON.stringify(value));
                return true;
            } catch (e) {
                console.warn('Error writing to localStorage:', e);
                return false;
            }
        },

        remove(key) {
            try {
                localStorage.removeItem(key);
                return true;
            } catch (e) {
                console.warn('Error removing from localStorage:', e);
                return false;
            }
        }
    };

    /**
     * Event emitter for custom events
     */
    static createEventEmitter() {
        const events = {};
        
        return {
            on(event, callback) {
                if (!events[event]) events[event] = [];
                events[event].push(callback);
            },

            off(event, callback) {
                if (!events[event]) return;
                events[event] = events[event].filter(cb => cb !== callback);
            },

            emit(event, data) {
                if (!events[event]) return;
                events[event].forEach(callback => {
                    try {
                        callback(data);
                    } catch (e) {
                        console.error('Event callback error:', e);
                    }
                });
            }
        };
    }

    /**
     * Request permission for microphone access
     */
    static async requestMicrophonePermission() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ 
                audio: true 
            });
            
            // Stop the stream immediately - we just wanted permission
            stream.getTracks().forEach(track => track.stop());
            
            return { granted: true };
        } catch (error) {
            return { 
                granted: false, 
                error: error.message,
                code: error.name
            };
        }
    }

    /**
     * Copy text to clipboard
     */
    static async copyToClipboard(text) {
        try {
            if (navigator.clipboard && navigator.clipboard.writeText) {
                await navigator.clipboard.writeText(text);
                return { success: true };
            } else {
                // Fallback for older browsers
                const textArea = document.createElement('textarea');
                textArea.value = text;
                document.body.appendChild(textArea);
                textArea.select();
                document.execCommand('copy');
                document.body.removeChild(textArea);
                return { success: true };
            }
        } catch (error) {
            return { success: false, error: error.message };
        }
    }

    /**
     * Download text as file
     */
    static downloadTextAsFile(text, filename = 'transcription.txt') {
        const blob = new Blob([text], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        
        URL.revokeObjectURL(url);
    }

    /**
     * Retry function with exponential backoff
     */
    static async retry(fn, options = {}) {
        const {
            retries = 3,
            delay = 1000,
            backoff = 2,
            onRetry = () => {}
        } = options;

        let lastError;

        for (let i = 0; i <= retries; i++) {
            try {
                return await fn();
            } catch (error) {
                lastError = error;
                
                if (i === retries) {
                    throw error;
                }

                const waitTime = delay * Math.pow(backoff, i);
                onRetry(error, i + 1, waitTime);
                
                await new Promise(resolve => setTimeout(resolve, waitTime));
            }
        }

        throw lastError;
    }
}

// Export for use in other modules
window.Utils = Utils;
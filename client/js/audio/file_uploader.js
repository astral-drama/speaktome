// File Upload Module - Focused on file validation and uploading

class FileUploader {
    constructor() {
        // Upload settings
        this.uploadSettings = {
            maxFileSize: 50 * 1024 * 1024, // 50MB
            supportedFormats: [
                'audio/wav', 'audio/wave', 'audio/x-wav',
                'audio/mpeg', 'audio/mp3',
                'audio/flac',
                'audio/m4a', 'audio/x-m4a',
                'audio/webm',
                'audio/ogg'
            ],
            endpoint: '/api/transcribe'
        };
        
        // Event emitter
        this.events = Utils.createEventEmitter();
    }
    
    validateFile(file) {
        return Utils.validateAudioFile(file);
    }
    
    async uploadFile(file, options = {}) {
        // Validate file first
        const validation = this.validateFile(file);
        if (!validation.valid) {
            const error = {
                success: false,
                error: validation.error,
                code: 'FILE_VALIDATION_FAILED'
            };
            this.events.emit('error', error);
            return error;
        }
        
        try {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('model', options.model || 'base');
            
            if (options.language) {
                formData.append('language', options.language);
            }
            
            this.events.emit('uploadStarted', { 
                fileName: file.name, 
                fileSize: file.size 
            });
            
            const response = await fetch(this.uploadSettings.endpoint, {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Upload failed');
            }
            
            const result = await response.json();
            this.events.emit('uploadCompleted', result);
            
            return {
                success: true,
                requestId: result.id,
                status: result.status
            };
            
        } catch (error) {
            const errorResult = {
                success: false,
                error: `Upload failed: ${error.message}`,
                code: 'UPLOAD_FAILED'
            };
            
            this.events.emit('error', errorResult);
            return errorResult;
        }
    }
    
    async pollForResult(requestId, options = {}) {
        const maxAttempts = options.maxAttempts || 60;
        const pollInterval = options.pollInterval || 1000;
        
        let attempts = 0;
        
        const poll = async () => {
            try {
                attempts++;
                const response = await fetch(`${this.uploadSettings.endpoint}/${requestId}`);
                
                if (!response.ok) {
                    throw new Error('Failed to get transcription result');
                }
                
                const result = await response.json();
                
                if (result.status === 'completed') {
                    this.events.emit('transcription', {
                        text: result.text,
                        language: result.language,
                        processingTime: result.processing_time,
                        requestId: requestId
                    });
                    
                    return {
                        success: true,
                        result: result
                    };
                } else if (result.status === 'failed') {
                    const error = {
                        success: false,
                        error: result.error || 'Transcription failed',
                        code: 'TRANSCRIPTION_FAILED',
                        requestId: requestId
                    };
                    
                    this.events.emit('error', error);
                    return error;
                } else if (attempts < maxAttempts) {
                    // Still processing, poll again
                    this.events.emit('polling', {
                        requestId: requestId,
                        attempt: attempts,
                        status: result.status
                    });
                    
                    setTimeout(poll, pollInterval);
                } else {
                    // Timeout
                    const error = {
                        success: false,
                        error: 'Transcription timeout',
                        code: 'TRANSCRIPTION_TIMEOUT',
                        requestId: requestId
                    };
                    
                    this.events.emit('error', error);
                    return error;
                }
                
            } catch (error) {
                const errorResult = {
                    success: false,
                    error: 'Failed to get transcription result',
                    code: 'POLLING_FAILED',
                    requestId: requestId,
                    details: error.message
                };
                
                this.events.emit('error', errorResult);
                return errorResult;
            }
        };
        
        return poll();
    }
    
    async uploadAndWaitForResult(file, options = {}) {
        const uploadResult = await this.uploadFile(file, options);
        
        if (!uploadResult.success) {
            return uploadResult;
        }
        
        return this.pollForResult(uploadResult.requestId, options);
    }
    
    async cancelRequest(requestId) {
        try {
            const response = await fetch(`${this.uploadSettings.endpoint}/${requestId}`, {
                method: 'DELETE'
            });
            
            if (!response.ok) {
                throw new Error('Failed to cancel request');
            }
            
            const result = await response.json();
            this.events.emit('requestCancelled', { requestId: requestId });
            
            return {
                success: true,
                message: result.message
            };
            
        } catch (error) {
            return {
                success: false,
                error: `Cancel failed: ${error.message}`,
                code: 'CANCEL_FAILED'
            };
        }
    }
    
    // File handling utilities
    createFileFromBlob(blob, filename, type) {
        return new File([blob], filename, { type: type });
    }
    
    getFileInfo(file) {
        return {
            name: file.name,
            size: file.size,
            type: file.type,
            lastModified: file.lastModified,
            sizeFormatted: Utils.formatFileSize(file.size)
        };
    }
    
    // Configuration methods
    updateUploadSettings(settings) {
        this.uploadSettings = { ...this.uploadSettings, ...settings };
    }
    
    getUploadSettings() {
        return { ...this.uploadSettings };
    }
    
    getSupportedFormats() {
        return [...this.uploadSettings.supportedFormats];
    }
    
    getMaxFileSize() {
        return this.uploadSettings.maxFileSize;
    }
    
    // Event handling
    on(event, callback) {
        this.events.on(event, callback);
    }
    
    off(event, callback) {
        this.events.off(event, callback);
    }
}

// Export for use in other modules
window.FileUploader = FileUploader;
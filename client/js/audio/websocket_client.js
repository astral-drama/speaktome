// WebSocket Client Module - Focused on WebSocket communication

class WebSocketClient {
    constructor() {
        this.websocket = null;
        this.isConnected = false;
        
        // Connection settings
        this.connectionSettings = {
            reconnectAttempts: 5,
            reconnectDelay: 1000,
            reconnectBackoff: 2,
            keepAliveInterval: 30000
        };
        
        // State
        this.currentAttempt = 0;
        this.keepAliveTimer = null;
        
        // Event emitter
        this.events = Utils.createEventEmitter();
    }
    
    async connect(endpoint = '/ws/transcribe') {
        try {
            const wsUrl = Utils.getWebSocketUrl(endpoint);
            console.log('Connecting to WebSocket:', wsUrl);
            
            this.websocket = new WebSocket(wsUrl);
            
            this.websocket.onopen = () => {
                console.log('WebSocket connected');
                this.isConnected = true;
                this.currentAttempt = 0;
                this.events.emit('connected');
                this.startKeepAlive();
            };
            
            this.websocket.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleMessage(data);
                } catch (error) {
                    console.error('Error parsing WebSocket message:', error);
                    this.events.emit('error', {
                        code: 'MESSAGE_PARSE_ERROR',
                        error: error.message
                    });
                }
            };
            
            this.websocket.onclose = (event) => {
                console.log('WebSocket disconnected:', event.code, event.reason);
                this.isConnected = false;
                this.stopKeepAlive();
                
                this.events.emit('disconnected', { 
                    code: event.code, 
                    reason: event.reason 
                });
                
                // Attempt to reconnect if not intentional
                if (event.code !== 1000 && this.shouldReconnect()) {
                    this.scheduleReconnect();
                }
            };
            
            this.websocket.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.events.emit('error', { 
                    code: 'WEBSOCKET_ERROR',
                    error: 'WebSocket connection failed'
                });
            };
            
            return { success: true };
            
        } catch (error) {
            console.error('Error connecting to WebSocket:', error);
            return {
                success: false,
                error: 'Failed to connect to server',
                code: 'CONNECTION_FAILED'
            };
        }
    }
    
    async disconnect() {
        if (this.websocket) {
            this.stopKeepAlive();
            this.websocket.close(1000, 'Client disconnect');
            this.websocket = null;
        }
        
        this.isConnected = false;
    }
    
    send(message) {
        if (!this.isConnected || !this.websocket) {
            return {
                success: false,
                error: 'Not connected to server',
                code: 'NOT_CONNECTED'
            };
        }
        
        try {
            const messageStr = typeof message === 'string' ? message : JSON.stringify(message);
            this.websocket.send(messageStr);
            return { success: true };
        } catch (error) {
            return {
                success: false,
                error: `Failed to send message: ${error.message}`,
                code: 'SEND_FAILED'
            };
        }
    }
    
    sendConfig(model, language) {
        return this.send({
            type: 'config',
            model: model,
            language: language
        });
    }
    
    sendAudio(audioData, format, model, language) {
        return this.send({
            type: 'audio',
            data: audioData,
            format: format,
            model: model,
            language: language
        });
    }
    
    sendPing() {
        return this.send({
            type: 'ping',
            timestamp: Date.now()
        });
    }
    
    handleMessage(data) {
        const messageType = data.type;
        
        switch (messageType) {
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
                    code: 'SERVER_ERROR',
                    error: data.message
                });
                break;
                
            case 'pong':
                this.events.emit('pong', data);
                break;
                
            default:
                console.warn('Unknown message type:', messageType);
                this.events.emit('unknownMessage', data);
        }
    }
    
    shouldReconnect() {
        return this.currentAttempt < this.connectionSettings.reconnectAttempts;
    }
    
    scheduleReconnect() {
        this.currentAttempt++;
        const delay = this.connectionSettings.reconnectDelay * 
                     Math.pow(this.connectionSettings.reconnectBackoff, this.currentAttempt - 1);
        
        console.log(`Reconnect attempt ${this.currentAttempt} in ${delay}ms`);
        this.events.emit('reconnecting', { 
            attempt: this.currentAttempt, 
            delay: delay 
        });
        
        setTimeout(() => {
            if (!this.isConnected) {
                this.connect();
            }
        }, delay);
    }
    
    startKeepAlive() {
        if (this.keepAliveTimer) {
            clearInterval(this.keepAliveTimer);
        }
        
        this.keepAliveTimer = setInterval(() => {
            if (this.isConnected) {
                this.sendPing();
            }
        }, this.connectionSettings.keepAliveInterval);
    }
    
    stopKeepAlive() {
        if (this.keepAliveTimer) {
            clearInterval(this.keepAliveTimer);
            this.keepAliveTimer = null;
        }
    }
    
    // Configuration methods
    updateConnectionSettings(settings) {
        this.connectionSettings = { ...this.connectionSettings, ...settings };
    }
    
    getConnectionSettings() {
        return { ...this.connectionSettings };
    }
    
    getConnectionState() {
        return {
            isConnected: this.isConnected,
            readyState: this.websocket ? this.websocket.readyState : WebSocket.CLOSED,
            currentAttempt: this.currentAttempt
        };
    }
    
    // Event handling
    on(event, callback) {
        this.events.on(event, callback);
    }
    
    off(event, callback) {
        this.events.off(event, callback);
    }
    
    cleanup() {
        this.disconnect();
        this.stopKeepAlive();
        this.currentAttempt = 0;
    }
}

// Export for use in other modules
window.WebSocketClient = WebSocketClient;
// TTS Client - Handles text-to-speech synthesis

class TTSClient {
    constructor() {
        this.baseUrl = window.location.origin;
        this.wsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`;
        this.ws = null;
        this.isConnected = false;
        this.currentAudioBlob = null;
        this.currentAudio = null;

        // Event callbacks
        this.onVoicesLoaded = null;
        this.onSynthesisStart = null;
        this.onSynthesisComplete = null;
        this.onSynthesisError = null;
        this.onAudioPlay = null;
        this.onAudioEnd = null;

        // Available voices
        this.voices = [];
    }

    // Initialize TTS client
    async initialize() {
        console.log('🎤 Initializing TTS Client');

        try {
            // Load available voices
            await this.loadVoices();

            // Connect WebSocket for real-time synthesis
            this.connectWebSocket();

            console.log('✅ TTS Client initialized');
            return true;
        } catch (error) {
            console.error('❌ TTS Client initialization failed:', error);
            return false;
        }
    }

    // Load available voices from server
    async loadVoices() {
        try {
            const response = await fetch(`${this.baseUrl}/api/voices`);

            if (!response.ok) {
                throw new Error(`Failed to load voices: ${response.statusText}`);
            }

            this.voices = await response.json();
            console.log(`📋 Loaded ${this.voices.length} voices`);

            if (this.onVoicesLoaded) {
                this.onVoicesLoaded(this.voices);
            }

            return this.voices;
        } catch (error) {
            console.error('❌ Error loading voices:', error);
            throw error;
        }
    }

    // Connect WebSocket for streaming TTS
    connectWebSocket() {
        try {
            this.ws = new WebSocket(`${this.wsUrl}/ws/synthesize`);

            this.ws.onopen = () => {
                console.log('🔌 TTS WebSocket connected');
                this.isConnected = true;
            };

            this.ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this.handleWebSocketMessage(data);
            };

            this.ws.onerror = (error) => {
                console.error('❌ TTS WebSocket error:', error);
                this.isConnected = false;
            };

            this.ws.onclose = () => {
                console.log('🔌 TTS WebSocket disconnected');
                this.isConnected = false;

                // Attempt reconnection after 3 seconds
                setTimeout(() => {
                    if (!this.isConnected) {
                        console.log('🔄 Attempting TTS WebSocket reconnection...');
                        this.connectWebSocket();
                    }
                }, 3000);
            };
        } catch (error) {
            console.error('❌ Error connecting TTS WebSocket:', error);
        }
    }

    // Handle WebSocket messages
    handleWebSocketMessage(data) {
        console.log('📨 TTS WebSocket message:', data.type);

        switch (data.type) {
            case 'connection':
                console.log('✅ TTS WebSocket connection confirmed');
                break;

            case 'audio':
                if (data.status === 'completed') {
                    console.log('✅ TTS synthesis completed via WebSocket');
                    this.handleSynthesisComplete(data);
                } else if (data.status === 'failed') {
                    console.error('❌ TTS synthesis failed:', data.error);
                    if (this.onSynthesisError) {
                        this.onSynthesisError(data.error);
                    }
                }
                break;

            case 'error':
                console.error('❌ TTS WebSocket error:', data.message);
                if (this.onSynthesisError) {
                    this.onSynthesisError(data.message);
                }
                break;
        }
    }

    // Synthesize speech using REST API
    async synthesizeSpeech(text, voice = 'default', speed = 1.0, format = 'wav') {
        try {
            console.log(`🎵 Synthesizing speech: "${text.substring(0, 50)}..."`);

            if (this.onSynthesisStart) {
                this.onSynthesisStart();
            }

            // Submit synthesis request
            const response = await fetch(`${this.baseUrl}/api/synthesize`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    text: text,
                    voice: voice,
                    speed: speed,
                    output_format: format
                })
            });

            if (!response.ok) {
                throw new Error(`Synthesis request failed: ${response.statusText}`);
            }

            const result = await response.json();
            const requestId = result.id;

            console.log(`📝 Synthesis request submitted: ${requestId}`);

            // Poll for result
            return await this.pollSynthesisResult(requestId);

        } catch (error) {
            console.error('❌ Synthesis error:', error);
            if (this.onSynthesisError) {
                this.onSynthesisError(error.message);
            }
            throw error;
        }
    }

    // Poll for synthesis result
    async pollSynthesisResult(requestId, maxAttempts = 30) {
        for (let attempt = 0; attempt < maxAttempts; attempt++) {
            await new Promise(resolve => setTimeout(resolve, 1000));

            try {
                const response = await fetch(`${this.baseUrl}/api/synthesize/${requestId}`);

                if (!response.ok) {
                    throw new Error(`Failed to get synthesis result: ${response.statusText}`);
                }

                const result = await response.json();

                if (result.status === 'completed') {
                    console.log('✅ Synthesis completed');
                    this.handleSynthesisComplete(result);
                    return result;
                } else if (result.status === 'failed') {
                    throw new Error(result.error || 'Synthesis failed');
                }

                console.log(`⏳ Polling attempt ${attempt + 1}/${maxAttempts}...`);

            } catch (error) {
                console.error('❌ Polling error:', error);
                throw error;
            }
        }

        throw new Error('Synthesis timeout');
    }

    // Synthesize speech using WebSocket (faster for real-time)
    synthesizeSpeechWebSocket(text, voice = 'default', speed = 1.0, format = 'wav') {
        if (!this.isConnected) {
            throw new Error('TTS WebSocket not connected');
        }

        console.log(`🎵 Synthesizing speech via WebSocket: "${text.substring(0, 50)}..."`);

        if (this.onSynthesisStart) {
            this.onSynthesisStart();
        }

        this.ws.send(JSON.stringify({
            type: 'text',
            text: text,
            voice: voice,
            speed: speed,
            format: format
        }));
    }

    // Handle synthesis completion
    handleSynthesisComplete(result) {
        // Decode base64 audio data
        const audioData = atob(result.data);
        const audioArray = new Uint8Array(audioData.length);
        for (let i = 0; i < audioData.length; i++) {
            audioArray[i] = audioData.charCodeAt(i);
        }

        // Create audio blob
        this.currentAudioBlob = new Blob([audioArray], { type: 'audio/wav' });

        console.log(`💾 Audio blob created: ${this.currentAudioBlob.size} bytes`);

        if (this.onSynthesisComplete) {
            this.onSynthesisComplete(this.currentAudioBlob, result);
        }
    }

    // Play synthesized audio
    playAudio() {
        if (!this.currentAudioBlob) {
            console.error('❌ No audio to play');
            return;
        }

        // Stop any currently playing audio
        this.stopAudio();

        // Create audio element
        const audioUrl = URL.createObjectURL(this.currentAudioBlob);
        this.currentAudio = new Audio(audioUrl);

        this.currentAudio.onplay = () => {
            console.log('▶️  Audio playing');
            if (this.onAudioPlay) {
                this.onAudioPlay();
            }
        };

        this.currentAudio.onended = () => {
            console.log('⏹️  Audio ended');
            URL.revokeObjectURL(audioUrl);
            if (this.onAudioEnd) {
                this.onAudioEnd();
            }
        };

        this.currentAudio.onerror = (error) => {
            console.error('❌ Audio playback error:', error);
            URL.revokeObjectURL(audioUrl);
        };

        this.currentAudio.play();
    }

    // Stop audio playback
    stopAudio() {
        if (this.currentAudio) {
            this.currentAudio.pause();
            this.currentAudio.currentTime = 0;
            this.currentAudio = null;
        }
    }

    // Download audio file
    downloadAudio(filename = 'synthesized_speech.wav') {
        if (!this.currentAudioBlob) {
            console.error('❌ No audio to download');
            return;
        }

        const url = URL.createObjectURL(this.currentAudioBlob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        console.log(`💾 Audio downloaded: ${filename}`);
    }

    // Disconnect WebSocket
    disconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
            this.isConnected = false;
        }

        this.stopAudio();
    }
}

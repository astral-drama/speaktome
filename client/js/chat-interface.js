// Chat interface for displaying messages and managing conversation

class ChatInterface {
    constructor(chatMessagesElement) {
        this.chatMessages = chatMessagesElement;
        this.messages = [];
        this.autoScroll = true;
        
        // Initialize
        this.init();
    }

    init() {
        // Set initial welcome time
        const welcomeTime = document.getElementById('welcomeTime');
        if (welcomeTime) {
            welcomeTime.textContent = Utils.formatTime();
        }
        
        // Setup scroll detection for auto-scroll
        this.chatMessages.addEventListener('scroll', () => {
            const { scrollTop, scrollHeight, clientHeight } = this.chatMessages;
            this.autoScroll = scrollTop + clientHeight >= scrollHeight - 5;
        });
    }

    addMessage(type, content, metadata = {}) {
        const message = {
            id: Utils.generateId(),
            type,
            content,
            timestamp: Date.now(),
            ...metadata
        };

        this.messages.push(message);
        this.renderMessage(message);
        
        if (this.autoScroll) {
            this.scrollToBottom();
        }
        
        return message.id;
    }

    renderMessage(message) {
        const messageElement = this.createMessageElement(message);
        this.chatMessages.appendChild(messageElement);
        
        // Animate message appearance
        requestAnimationFrame(() => {
            messageElement.style.opacity = '1';
            messageElement.style.transform = 'translateY(0)';
        });
    }

    createMessageElement(message) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${message.type}`;
        messageDiv.dataset.messageId = message.id;
        messageDiv.style.opacity = '0';
        messageDiv.style.transform = 'translateY(10px)';
        messageDiv.style.transition = 'all 0.3s ease-out';

        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        // Create content based on message type
        if (message.type === 'transcription') {
            contentDiv.appendChild(this.createTranscriptionContent(message));
        } else if (message.type === 'tts') {
            contentDiv.appendChild(this.createTTSContent(message));
        } else {
            const p = document.createElement('p');
            p.textContent = message.content;
            contentDiv.appendChild(p);
        }
        
        const timeDiv = document.createElement('div');
        timeDiv.className = 'message-time';
        
        const timeSpan = document.createElement('span');
        timeSpan.textContent = Utils.formatTime(message.timestamp);
        timeDiv.appendChild(timeSpan);
        
        // Add metadata info if available
        if (message.language || message.processingTime) {
            const metadataSpan = document.createElement('span');
            metadataSpan.className = 'message-metadata';
            
            const parts = [];
            if (message.language && message.language !== 'unknown') {
                parts.push(`Language: ${message.language.toUpperCase()}`);
            }
            if (message.processingTime) {
                parts.push(`Processed in ${Utils.formatDuration(message.processingTime)}`);
            }
            
            metadataSpan.textContent = parts.join(' • ');
            timeDiv.appendChild(metadataSpan);
        }
        
        messageDiv.appendChild(contentDiv);
        messageDiv.appendChild(timeDiv);
        
        return messageDiv;
    }

    createTranscriptionContent(message) {
        const container = document.createElement('div');
        
        const textP = document.createElement('p');
        textP.textContent = message.content;
        textP.className = 'transcription-text';
        container.appendChild(textP);
        
        // Add action buttons
        const actionsDiv = document.createElement('div');
        actionsDiv.className = 'message-actions';
        
        // Copy button
        const copyBtn = document.createElement('button');
        copyBtn.className = 'btn-action';
        copyBtn.innerHTML = '<i class="fas fa-copy"></i>';
        copyBtn.title = 'Copy to clipboard';
        copyBtn.onclick = () => this.copyText(message.content);
        
        // Edit button (for corrections)
        const editBtn = document.createElement('button');
        editBtn.className = 'btn-action';
        editBtn.innerHTML = '<i class="fas fa-edit"></i>';
        editBtn.title = 'Edit transcription';
        editBtn.onclick = () => this.editMessage(message.id);
        
        actionsDiv.appendChild(copyBtn);
        actionsDiv.appendChild(editBtn);
        
        container.appendChild(actionsDiv);
        
        return container;
    }

    createTTSContent(message) {
        const container = document.createElement('div');

        // Add header with icon
        const headerDiv = document.createElement('div');
        headerDiv.className = 'message-header';

        const icon = document.createElement('i');
        icon.className = 'fas fa-volume-up';
        headerDiv.appendChild(icon);

        const label = document.createElement('span');
        label.className = 'message-label';
        label.textContent = 'Text-to-Speech';
        headerDiv.appendChild(label);

        container.appendChild(headerDiv);

        // Add text content
        const textP = document.createElement('p');
        textP.textContent = message.content;
        textP.className = 'transcription-text';
        container.appendChild(textP);

        // Add metadata if available
        if (message.voice) {
            const metaDiv = document.createElement('div');
            metaDiv.className = 'tts-meta';
            metaDiv.style.cssText = 'font-size: 0.813rem; color: #6b7280; margin-top: 0.5rem;';
            metaDiv.innerHTML = `<i class="fas fa-user"></i> Voice: ${message.voice}`;
            container.appendChild(metaDiv);
        }

        // Add action buttons
        const actionsDiv = document.createElement('div');
        actionsDiv.className = 'message-actions';

        // Copy button
        const copyBtn = document.createElement('button');
        copyBtn.className = 'btn-action';
        copyBtn.innerHTML = '<i class="fas fa-copy"></i>';
        copyBtn.title = 'Copy to clipboard';
        copyBtn.onclick = () => this.copyText(message.content);

        actionsDiv.appendChild(copyBtn);
        container.appendChild(actionsDiv);

        return container;
    }

    async copyText(text) {
        const result = await Utils.copyToClipboard(text);
        if (result.success) {
            Utils.showToast('Text copied to clipboard', 'success', 2000);
        } else {
            Utils.showToast('Failed to copy text', 'error');
        }
    }

    editMessage(messageId) {
        const messageElement = this.chatMessages.querySelector(`[data-message-id="${messageId}"]`);
        const message = this.messages.find(m => m.id === messageId);
        
        if (!messageElement || !message) return;
        
        const textElement = messageElement.querySelector('.transcription-text');
        if (!textElement) return;
        
        // Create textarea for editing
        const textarea = document.createElement('textarea');
        textarea.className = 'edit-textarea';
        textarea.value = message.content;
        textarea.style.cssText = `
            width: 100%;
            min-height: 60px;
            padding: 0.5rem;
            border: 2px solid #4f46e5;
            border-radius: 4px;
            font-family: inherit;
            font-size: inherit;
            resize: vertical;
        `;
        
        // Create save/cancel buttons
        const buttonsDiv = document.createElement('div');
        buttonsDiv.className = 'edit-buttons';
        buttonsDiv.style.cssText = 'margin-top: 0.5rem; display: flex; gap: 0.5rem;';
        
        const saveBtn = document.createElement('button');
        saveBtn.className = 'btn btn-primary';
        saveBtn.textContent = 'Save';
        saveBtn.style.cssText = 'padding: 0.25rem 0.75rem; font-size: 0.75rem;';
        
        const cancelBtn = document.createElement('button');
        cancelBtn.className = 'btn btn-secondary';
        cancelBtn.textContent = 'Cancel';
        cancelBtn.style.cssText = 'padding: 0.25rem 0.75rem; font-size: 0.75rem;';
        
        buttonsDiv.appendChild(saveBtn);
        buttonsDiv.appendChild(cancelBtn);
        
        // Replace text with editor
        const originalContent = textElement.innerHTML;
        textElement.innerHTML = '';
        textElement.appendChild(textarea);
        textElement.appendChild(buttonsDiv);
        
        textarea.focus();
        textarea.select();
        
        // Handle save
        saveBtn.onclick = () => {
            const newText = textarea.value.trim();
            if (newText && newText !== message.content) {
                message.content = newText;
                textElement.innerHTML = newText;
                Utils.showToast('Transcription updated', 'success', 2000);
            } else {
                textElement.innerHTML = originalContent;
            }
        };
        
        // Handle cancel
        cancelBtn.onclick = () => {
            textElement.innerHTML = originalContent;
        };
        
        // Handle Escape key
        textarea.onkeydown = (e) => {
            if (e.key === 'Escape') {
                cancelBtn.click();
            } else if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                saveBtn.click();
            }
        };
    }

    addUserMessage(text) {
        return this.addMessage('user', text);
    }

    addSystemMessage(text) {
        return this.addMessage('system', text);
    }

    addTranscription(text, metadata = {}) {
        return this.addMessage('transcription', text, metadata);
    }

    addErrorMessage(text, error = null) {
        const content = error ? `${text}: ${error}` : text;
        return this.addMessage('error', content);
    }

    addRecordingStartMessage() {
        return this.addSystemMessage('🎤 Recording started... Speak now.');
    }

    addRecordingStopMessage() {
        return this.addSystemMessage('⏹️ Recording stopped. Processing audio...');
    }

    addTTSMessage(text, metadata = {}) {
        return this.addMessage('tts', text, metadata);
    }

    addConnectionMessage(status) {
        const messages = {
            connecting: '🔗 Connecting to server...',
            connected: '✅ Connected to server. Ready for transcription.',
            disconnected: '❌ Disconnected from server. Attempting to reconnect...',
            reconnecting: '🔄 Reconnecting to server...'
        };

        return this.addSystemMessage(messages[status] || `Status: ${status}`);
    }

    updateMessage(messageId, newContent, metadata = {}) {
        const message = this.messages.find(m => m.id === messageId);
        if (!message) return false;
        
        message.content = newContent;
        Object.assign(message, metadata);
        
        const messageElement = this.chatMessages.querySelector(`[data-message-id="${messageId}"]`);
        if (messageElement) {
            // Re-render the message
            const newElement = this.createMessageElement(message);
            messageElement.parentNode.replaceChild(newElement, messageElement);
        }
        
        return true;
    }

    removeMessage(messageId) {
        const messageIndex = this.messages.findIndex(m => m.id === messageId);
        if (messageIndex === -1) return false;
        
        this.messages.splice(messageIndex, 1);
        
        const messageElement = this.chatMessages.querySelector(`[data-message-id="${messageId}"]`);
        if (messageElement) {
            messageElement.style.opacity = '0';
            messageElement.style.transform = 'translateY(-10px)';
            
            setTimeout(() => {
                messageElement.remove();
            }, 300);
        }
        
        return true;
    }

    clearMessages() {
        // Animate out all messages
        const messageElements = this.chatMessages.querySelectorAll('.message');
        messageElements.forEach((element, index) => {
            setTimeout(() => {
                element.style.opacity = '0';
                element.style.transform = 'translateY(-10px)';
            }, index * 50);
        });
        
        // Clear after animation
        setTimeout(() => {
            this.chatMessages.innerHTML = '';
            this.messages = [];
            
            // Add welcome message back
            this.addSystemMessage('Chat cleared. Ready for new transcriptions.');
        }, messageElements.length * 50 + 300);
    }

    scrollToBottom(smooth = true) {
        const scrollOptions = {
            top: this.chatMessages.scrollHeight,
            behavior: smooth ? 'smooth' : 'auto'
        };
        
        this.chatMessages.scrollTo(scrollOptions);
    }

    exportChat() {
        const chatText = this.messages
            .map(message => {
                const time = Utils.formatTime(message.timestamp);
                const type = message.type.charAt(0).toUpperCase() + message.type.slice(1);
                
                let content = `[${time}] ${type}: ${message.content}`;
                
                if (message.language && message.language !== 'unknown') {
                    content += ` (Language: ${message.language.toUpperCase()})`;
                }
                
                if (message.processingTime) {
                    content += ` (Processed in ${Utils.formatDuration(message.processingTime)})`;
                }
                
                return content;
            })
            .join('\n\n');
        
        const timestamp = new Date().toISOString().split('T')[0];
        Utils.downloadTextAsFile(chatText, `whisper-transcription-${timestamp}.txt`);
    }

    getTranscriptionText() {
        return this.messages
            .filter(message => message.type === 'transcription')
            .map(message => message.content)
            .join(' ');
    }

    getMessageCount() {
        return this.messages.length;
    }

    getLastMessage() {
        return this.messages[this.messages.length - 1] || null;
    }

    searchMessages(query) {
        const lowercaseQuery = query.toLowerCase();
        return this.messages.filter(message =>
            message.content.toLowerCase().includes(lowercaseQuery)
        );
    }

    highlightText(query) {
        if (!query.trim()) return;
        
        const regex = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
        
        this.chatMessages.querySelectorAll('.message-content p, .transcription-text').forEach(element => {
            if (element.textContent.toLowerCase().includes(query.toLowerCase())) {
                element.innerHTML = element.textContent.replace(regex, '<mark>$1</mark>');
            }
        });
    }

    clearHighlights() {
        this.chatMessages.querySelectorAll('mark').forEach(mark => {
            const parent = mark.parentNode;
            parent.replaceChild(document.createTextNode(mark.textContent), mark);
            parent.normalize();
        });
    }
}

// Export for use in other modules
window.ChatInterface = ChatInterface;
// Socket.IO connection
const socket = io();

// Global variables
let currentUserId = null;
let currentUsername = null;
let typingTimeout = null;
let currentCall = null;

// DOM Elements
let messagesArea, messageInput, sendBtn, fileInput, searchInput, usersList;
let chatHeader, inputArea, typingIndicator, headerUsername, headerAvatar, userStatus;
let audioCallBtn, videoCallBtn;

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Initialize DOM elements
    messagesArea = document.getElementById('messagesArea');
    messageInput = document.getElementById('messageInput');
    sendBtn = document.getElementById('sendBtn');
    fileInput = document.getElementById('fileInput');
    searchInput = document.getElementById('searchInput');
    usersList = document.getElementById('usersList');
    chatHeader = document.getElementById('chatHeader');
    inputArea = document.getElementById('inputArea');
    typingIndicator = document.getElementById('typingIndicator');
    headerUsername = document.getElementById('headerUsername');
    headerAvatar = document.getElementById('headerAvatar');
    userStatus = document.getElementById('userStatus');
    audioCallBtn = document.getElementById('audioCallBtn');
    videoCallBtn = document.getElementById('videoCallBtn');
    
    // Add event listeners
    if (sendBtn) sendBtn.addEventListener('click', sendMessage);
    if (messageInput) messageInput.addEventListener('keypress', handleMessageKeypress);
    if (fileInput) fileInput.addEventListener('change', handleFileUpload);
    if (searchInput) searchInput.addEventListener('input', handleSearch);
    if (audioCallBtn) audioCallBtn.addEventListener('click', () => initiateCall('audio'));
    if (videoCallBtn) videoCallBtn.addEventListener('click', () => initiateCall('video'));
    
    // Load all users
    loadUsers();
    
    // Setup socket events
    setupSocketEvents();
});

// Load all users and their chats
function loadUsers() {
    if (!usersList) return;
    
    const userItems = document.querySelectorAll('.user-item');
    userItems.forEach(item => {
        item.addEventListener('click', function() {
            selectUser(this);
        });
    });
}

// Select a user to chat with
function selectUser(userElement) {
    // Remove active class from all users
    document.querySelectorAll('.user-item').forEach(item => {
        item.classList.remove('active');
    });
    
    // Add active class to selected user
    userElement.classList.add('active');
    
    // Get user details
    currentUserId = userElement.dataset.userId;
    currentUsername = userElement.dataset.username;
    
    // Update header
    if (chatHeader) chatHeader.style.display = 'flex';
    if (inputArea) inputArea.style.display = 'flex';
    if (headerUsername) headerUsername.textContent = currentUsername;
    if (headerAvatar) headerAvatar.textContent = currentUsername.charAt(0).toUpperCase();
    
    // Load messages for this user
    loadMessages(currentUserId);
    
    // Join room for this user
    socket.emit('join_room', { room: `user_${currentUserId}` });
}

// Load messages from server
function loadMessages(userId) {
    fetch(`/get_messages/${userId}`)
        .then(response => response.json())
        .then(messages => {
            displayMessages(messages);
        })
        .catch(error => console.error('Error loading messages:', error));
}

// Display messages in chat area
function displayMessages(messages) {
    if (!messagesArea) return;
    
    messagesArea.innerHTML = '';
    
    if (messages.length === 0) {
        messagesArea.innerHTML = `
            <div class="text-center text-muted" style="margin-top: 50%;">
                <i class="fas fa-comments" style="font-size: 50px; margin-bottom: 20px;"></i>
                <p>No messages yet. Start chatting!</p>
            </div>
        `;
        return;
    }
    
    messages.forEach(message => {
        // FIX: Use window.CURRENT_USER_ID set by Jinja2 in the template
        const isSent = message.sender_id == window.CURRENT_USER_ID;
        
        const messageDiv = createMessageElement(message, isSent);
        messagesArea.appendChild(messageDiv);
    });
    
    // Scroll to bottom
    messagesArea.scrollTop = messagesArea.scrollHeight;
}

// Create message element
function createMessageElement(message, isSent) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${isSent ? 'sent' : 'received'}`;
    messageDiv.dataset.messageId = message.id;
    
    let contentHtml = '';
    
    switch(message.message_type) {
        case 'text':
            contentHtml = `<div class="message-text">${escapeHtml(message.content)}</div>`;
            break;
        case 'image':
            contentHtml = `
                <img src="${message.file_url}" class="message-image" onclick="window.open(this.src)" alt="Image">
            `;
            break;
        case 'video':
            contentHtml = `
                <video controls class="message-file">
                    <source src="${message.file_url}">
                </video>
            `;
            break;
        case 'audio':
            contentHtml = `
                <audio controls class="message-audio">
                    <source src="${message.file_url}">
                </audio>
            `;
            break;
        case 'file':
            contentHtml = `
                <a href="${message.file_url}" download class="btn-download">
                    <i class="fas fa-download"></i> Download File
                </a>
            `;
            break;
        default:
            contentHtml = `<div class="message-text">${escapeHtml(message.content)}</div>`;
    }
    
    messageDiv.innerHTML = `
        <div class="message-bubble">
            ${contentHtml}
            <div class="message-time">
                ${message.timestamp}
                ${isSent ? '<i class="fas fa-check-double" style="margin-left: 5px;"></i>' : ''}
            </div>
            ${!isSent ? `<div class="message-status">
                <i class="fas fa-eye" style="font-size: 10px;"></i> 
                ${message.is_read ? 'Read' : 'Delivered'}
            </div>` : ''}
        </div>
    `;
    
    return messageDiv;
}

// Send message function
function sendMessage() {
    if (!messageInput || !currentUserId) return;
    
    const content = messageInput.value.trim();
    if (!content) return;
    
    const formData = new FormData();
    formData.append('receiver_id', currentUserId);
    formData.append('content', content);
    formData.append('message_type', 'text');
    
    fetch('/send_message', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            messageInput.value = '';
            loadMessages(currentUserId);
        }
    })
    .catch(error => console.error('Error sending message:', error));
}

// Handle message input keypress
function handleMessageKeypress(e) {
    if (e.key === 'Enter') {
        sendMessage();
    }
    
    // Send typing indicator
    if (currentUserId) {
        socket.emit('typing', {
            receiver_id: currentUserId,
            is_typing: true
        });
        
        clearTimeout(typingTimeout);
        typingTimeout = setTimeout(() => {
            socket.emit('typing', {
                receiver_id: currentUserId,
                is_typing: false
            });
        }, 1000);
    }
}

// Handle file upload
function handleFileUpload(e) {
    const file = e.target.files[0];
    if (!file || !currentUserId) return;
    
    // Show loading indicator
    showNotification('Uploading file...', 'info');
    
    const formData = new FormData();
    formData.append('receiver_id', currentUserId);
    formData.append('file', file);
    
    fetch('/upload_file', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification('File uploaded successfully!', 'success');
            loadMessages(currentUserId);
            fileInput.value = ''; // Clear file input
        }
    })
    .catch(error => {
        console.error('Error uploading file:', error);
        showNotification('Error uploading file!', 'error');
    });
}

// Handle search functionality
function handleSearch(e) {
    const searchTerm = e.target.value.toLowerCase();
    const userItems = document.querySelectorAll('.user-item');
    
    userItems.forEach(item => {
        const username = item.dataset.username.toLowerCase();
        if (username.includes(searchTerm)) {
            item.style.display = 'flex';
        } else {
            item.style.display = 'none';
        }
    });
}

// Initiate audio/video call
function initiateCall(callType) {
    if (!currentUserId) return;
    
    // Open call window
    const callWindow = window.open(
        `/call/${currentUserId}?type=${callType}`, 
        '_blank', 
        'width=800,height=600,toolbar=no,menubar=no,location=no'
    );
    
    // Call API to initiate call record
    fetch('/call/initiate', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            receiver_id: currentUserId,
            call_type: callType
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            console.log('Call initiated:', data.call_id);
        }
    });
}

// Setup Socket.IO events
function setupSocketEvents() {
    // New message received
    socket.on('new_message', (data) => {
        if (data.sender_id == currentUserId || data.receiver_id == currentUserId ||
            data.sender_id == window.CURRENT_USER_ID || data.receiver_id == window.CURRENT_USER_ID) {
            if (currentUserId) loadMessages(currentUserId);
            playNotificationSound();
        }
        
        // Update unread count in sidebar
        updateUnreadCount(data.sender_id);
    });
    
    // User typing indicator
    socket.on('user_typing', (data) => {
        if (data.sender_id == currentUserId && data.is_typing) {
            typingIndicator.textContent = `${data.sender_name} is typing...`;
            typingIndicator.style.display = 'block';
            
            setTimeout(() => {
                typingIndicator.style.display = 'none';
            }, 2000);
        }
    });
    
    // User status update
    socket.on('user_status', (data) => {
        if (data.user_id == currentUserId) {
            userStatus.textContent = data.status === 'online' ? 'Online' : 'Offline';
            updateUserStatusInSidebar(data.user_id, data.status);
        }
    });
    
    // User online
    socket.on('user_online', (data) => {
        updateUserStatusInSidebar(data.user_id, 'online');
        showNotification(`${data.username} came online`, 'info');
    });
    
    // User offline
    socket.on('user_offline', (data) => {
        updateUserStatusInSidebar(data.user_id, 'offline');
        showNotification(`${data.username} went offline`, 'info');
    });
    
    // Incoming call
    socket.on('incoming_call', (data) => {
        showIncomingCallNotification(data);
    });
    
    // Call status update
    socket.on('call_status_update', (data) => {
        console.log('Call status update:', data);
    });
}

// Update unread message count
function updateUnreadCount(senderId) {
    // FIX: Don't show unread badge for the chat that is currently open
    if (senderId == currentUserId) return;
    const userItem = document.querySelector(`.user-item[data-user-id="${senderId}"]`);
    if (userItem) {
        const badge = userItem.querySelector('.badge');
        if (badge) {
            let count = parseInt(badge.textContent) || 0;
            count++;
            badge.textContent = count;
            badge.style.display = 'inline-block';
        } else {
            const timeDiv = userItem.querySelector('.user-time');
            const badge = document.createElement('span');
            badge.className = 'badge bg-success';
            badge.textContent = '1';
            timeDiv.appendChild(badge);
        }
    }
}

// Update user status in sidebar
function updateUserStatusInSidebar(userId, status) {
    const userItem = document.querySelector(`.user-item[data-user-id="${userId}"]`);
    if (userItem) {
        const statusDot = userItem.querySelector('.status-dot');
        if (statusDot) {
            statusDot.className = `status-dot ${status}`;
        } else {
            const avatar = userItem.querySelector('.user-avatar');
            const dot = document.createElement('div');
            dot.className = `status-dot ${status}`;
            avatar.appendChild(dot);
        }
    }
}

// Play notification sound
function playNotificationSound() {
    const audio = new Audio('/static/notification.mp3');
    audio.play().catch(e => console.log('Audio play failed:', e));
}

// Show notification
function showNotification(message, type = 'info') {
    // Create toast notification
    const toast = document.createElement('div');
    toast.className = `toast-notification ${type}`;
    toast.innerHTML = `
        <div class="toast-content">
            <i class="fas ${type === 'success' ? 'fa-check-circle' : type === 'error' ? 'fa-exclamation-circle' : 'fa-info-circle'}"></i>
            <span>${message}</span>
        </div>
    `;
    
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.classList.add('show');
    }, 100);
    
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => {
            toast.remove();
        }, 300);
    }, 3000);
}

// Show incoming call notification
function showIncomingCallNotification(data) {
    const notification = document.createElement('div');
    notification.className = 'incoming-call-notification';
    notification.innerHTML = `
        <div class="call-notification-content">
            <div class="caller-info">
                <div class="caller-avatar">${data.caller_name.charAt(0).toUpperCase()}</div>
                <div class="caller-details">
                    <h4>${data.caller_name}</h4>
                    <p>Incoming ${data.call_type} call...</p>
                </div>
            </div>
            <div class="call-actions">
                <button class="accept-call" data-call-id="${data.call_id}" data-caller-id="${data.caller_id}" data-call-type="${data.call_type}">
                    <i class="fas fa-phone"></i> Accept
                </button>
                <button class="reject-call" data-call-id="${data.call_id}">
                    <i class="fas fa-phone-slash"></i> Reject
                </button>
            </div>
        </div>
    `;
    
    document.body.appendChild(notification);
    
    // Add event listeners
    notification.querySelector('.accept-call').addEventListener('click', () => {
        acceptCall(data);
        notification.remove();
    });
    
    notification.querySelector('.reject-call').addEventListener('click', () => {
        rejectCall(data.call_id);
        notification.remove();
    });
    
    // Auto remove after 30 seconds
    setTimeout(() => {
        if (notification.parentNode) {
            notification.remove();
        }
    }, 30000);
}

// Accept incoming call
function acceptCall(data) {
    window.open(`/call/${data.caller_id}?type=${data.call_type}&call_id=${data.call_id}`, '_blank', 'width=800,height=600');
    
    // Update call status
    fetch('/call/update_status', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            call_id: data.call_id,
            status: 'answered'
        })
    });
}

// Reject incoming call
function rejectCall(callId) {
    fetch('/call/update_status', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            call_id: callId,
            status: 'rejected'
        })
    });
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Load call history
function loadCallHistory() {
    fetch('/call_history')
        .then(response => response.json())
        .then(calls => {
            displayCallHistory(calls);
        })
        .catch(error => console.error('Error loading call history:', error));
}

// Display call history
function displayCallHistory(calls) {
    const historyContainer = document.getElementById('callHistory');
    if (!historyContainer) return;
    
    historyContainer.innerHTML = '';
    calls.forEach(call => {
        const callElement = document.createElement('div');
        callElement.className = 'call-history-item';
        callElement.innerHTML = `
            <div class="call-icon">
                <i class="fas ${call.call_type === 'video' ? 'fa-video' : 'fa-phone'}"></i>
            </div>
            <div class="call-details">
                <div class="call-user">${call.other_user}</div>
                <div class="call-info">
                    ${call.call_status === 'answered' ? 
                        `<span class="text-success">Duration: ${formatDuration(call.duration)}</span>` : 
                        `<span class="text-danger">${call.call_status}</span>`
                    }
                </div>
                <div class="call-time">${call.start_time}</div>
            </div>
        `;
        historyContainer.appendChild(callElement);
    });
}

// Format duration
function formatDuration(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

// Delete message
function deleteMessage(messageId) {
    if (confirm('Are you sure you want to delete this message?')) {
        fetch(`/delete_message/${messageId}`, {
            method: 'DELETE'
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                loadMessages(currentUserId);
                showNotification('Message deleted successfully', 'success');
            }
        })
        .catch(error => console.error('Error deleting message:', error));
    }
}

// Export functions for global use
window.selectUser = selectUser;
window.loadMessages = loadMessages;
window.sendMessage = sendMessage;
window.initiateCall = initiateCall;
window.deleteMessage = deleteMessage;
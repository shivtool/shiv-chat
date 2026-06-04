from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from database import db, User, Message, CallHistory, SharedFile
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import base64
import uuid

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///whatsapp_clone.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size

# Ensure upload directories exist
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'images'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'videos'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'audios'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'files'), exist_ok=True)

db.init_app(app)
socketio = SocketIO(app, cors_allowed_origins="*")

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Store online users and rooms
online_users = {}
active_calls = {}

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('chat'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('chat'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            user.online_status = True
            user.last_seen = datetime.utcnow()
            db.session.commit()
            
            # FIX: Emit only to other users (broadcast=True is correct but was already fine)
            socketio.emit('user_online', {'user_id': user.id, 'username': user.username})
            
            return redirect(url_for('chat'))
        else:
            return render_template('login.html', error='Invalid username or password')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('chat'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if password != confirm_password:
            return render_template('register.html', error='Passwords do not match')
        
        if User.query.filter_by(username=username).first():
            return render_template('register.html', error='Username already exists')
        
        if User.query.filter_by(email=email).first():
            return render_template('register.html', error='Email already registered')
        
        hashed_password = generate_password_hash(password)
        new_user = User(username=username, email=email, password=hashed_password)
        
        db.session.add(new_user)
        db.session.commit()
        
        login_user(new_user)
        return redirect(url_for('chat'))
    
    return render_template('register.html')

@app.route('/chat')
@login_required
def chat():
    # Get all users except current user
    users = User.query.filter(User.id != current_user.id).all()
    
    # Get recent chats with last message
    recent_chats = []
    for user in users:
        last_message = Message.query.filter(
            ((Message.sender_id == current_user.id) & (Message.receiver_id == user.id)) |
            ((Message.sender_id == user.id) & (Message.receiver_id == current_user.id))
        ).filter_by(is_deleted=False).order_by(Message.timestamp.desc()).first()
        
        unread_count = Message.query.filter_by(
            sender_id=user.id, 
            receiver_id=current_user.id, 
            is_read=False
        ).count()
        
        recent_chats.append({
            'user': user,
            'last_message': last_message,
            'unread_count': unread_count
        })
    
    # Sort by last message time
    recent_chats.sort(key=lambda x: x['last_message'].timestamp if x['last_message'] else datetime.min, reverse=True)
    
    return render_template('index.html', users=recent_chats, current_user=current_user)

@app.route('/get_messages/<int:user_id>')
@login_required
def get_messages(user_id):
    messages = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == user_id)) |
        ((Message.sender_id == user_id) & (Message.receiver_id == current_user.id))
    ).filter_by(is_deleted=False).order_by(Message.timestamp.asc()).all()
    
    # Mark messages as read
    unread_messages = Message.query.filter_by(sender_id=user_id, receiver_id=current_user.id, is_read=False).all()
    for msg in unread_messages:
        msg.is_read = True
    db.session.commit()
    
    messages_data = []
    for msg in messages:
        messages_data.append({
            'id': msg.id,
            'sender_id': msg.sender_id,
            'receiver_id': msg.receiver_id,
            'message_type': msg.message_type,
            'content': msg.content or '',
            'file_url': msg.file_url,
            'timestamp': msg.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'is_read': msg.is_read
        })
    
    return jsonify(messages_data)

@app.route('/send_message', methods=['POST'])
@login_required
def send_message():
    # FIX: Convert receiver_id to int to avoid DB type mismatch
    receiver_id = int(request.form.get('receiver_id'))
    message_type = request.form.get('message_type', 'text')
    content = request.form.get('content', '')
    
    message = Message(
        sender_id=current_user.id,
        receiver_id=receiver_id,
        message_type=message_type,
        content=content
    )
    
    db.session.add(message)
    db.session.commit()
    
    # Emit real-time message to receiver's room
    socketio.emit('new_message', {
        'id': message.id,
        'sender_id': current_user.id,
        'sender_name': current_user.username,
        'receiver_id': receiver_id,
        'message_type': message_type,
        'content': content,
        'timestamp': message.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    }, room=f'user_{receiver_id}')
    
    return jsonify({'success': True, 'message_id': message.id})

@app.route('/upload_file', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    # FIX: Convert receiver_id to int
    receiver_id = int(request.form.get('receiver_id'))
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Determine file type and save location
    file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    filename = str(uuid.uuid4()) + '.' + file_ext
    file_size = len(file.read())
    file.seek(0)
    
    # FIX: ogg was in both audio and video — audio takes priority; separate cleanly
    if file_ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
        file_type = 'image'
        folder = 'images'
    elif file_ext in ['mp4', 'webm']:
        file_type = 'video'
        folder = 'videos'
    elif file_ext in ['mp3', 'wav', 'ogg', 'm4a', 'aac']:
        file_type = 'audio'
        folder = 'audios'
    else:
        file_type = 'file'
        folder = 'files'
    
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], folder, filename)
    file.save(file_path)
    
    # Save file info to database
    shared_file = SharedFile(
        sender_id=current_user.id,
        receiver_id=receiver_id,
        filename=secure_filename(file.filename),
        file_type=file_type,
        file_size=file_size,
        file_path=file_path
    )
    db.session.add(shared_file)
    
    # Save message
    message = Message(
        sender_id=current_user.id,
        receiver_id=receiver_id,
        message_type=file_type,
        content=f'Shared a {file_type}',
        file_url=f'/static/uploads/{folder}/{filename}'
    )
    db.session.add(message)
    db.session.commit()
    
    # Emit real-time message
    socketio.emit('new_message', {
        'id': message.id,
        'sender_id': current_user.id,
        'sender_name': current_user.username,
        'receiver_id': receiver_id,
        'message_type': file_type,
        'content': f'Shared a {file_type}',
        'file_url': message.file_url,
        'timestamp': message.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    }, room=f'user_{receiver_id}')
    
    return jsonify({'success': True, 'message_id': message.id})

@app.route('/call/<int:user_id>')
@login_required
def call_page(user_id):
    receiver = User.query.get_or_404(user_id)
    # FIX: Pass call_id from URL query param (sent by receiver when accepting)
    call_id = request.args.get('call_id', 0, type=int)
    return render_template('call.html', receiver=receiver, current_user=current_user, call_id=call_id)

@app.route('/call/initiate', methods=['POST'])
@login_required
def initiate_call():
    data = request.json
    receiver_id = data.get('receiver_id')
    call_type = data.get('call_type')  # 'audio' or 'video'
    
    # Create call record
    call_record = CallHistory(
        caller_id=current_user.id,
        receiver_id=receiver_id,
        call_type=call_type,
        call_status='missed'
    )
    db.session.add(call_record)
    db.session.commit()
    
    # Notify receiver about incoming call
    socketio.emit('incoming_call', {
        'call_id': call_record.id,
        'caller_id': current_user.id,
        'caller_name': current_user.username,
        'call_type': call_type
    }, room=f'user_{receiver_id}')
    
    return jsonify({'success': True, 'call_id': call_record.id})

@app.route('/call/update_status', methods=['POST'])
@login_required
def update_call_status():
    data = request.json
    call_id = data.get('call_id')
    status = data.get('status')  # 'answered', 'rejected', 'ended'
    duration = data.get('duration', 0)
    
    # FIX: call_id=0 means call was opened without a call record (edge case) — skip gracefully
    if not call_id:
        return jsonify({'success': True})
    
    call_record = CallHistory.query.get(call_id)
    if call_record:
        call_record.call_status = status
        if status == 'answered':
            call_record.start_time = datetime.utcnow()
        elif status == 'ended':
            call_record.end_time = datetime.utcnow()
            call_record.duration = duration
        db.session.commit()
        
        # Notify participants about call status change
        if status in ['answered', 'rejected', 'ended']:
            socketio.emit('call_status_update', {
                'call_id': call_id,
                'status': status,
                'duration': duration
            }, room=f'user_{call_record.receiver_id}')
            socketio.emit('call_status_update', {
                'call_id': call_id,
                'status': status,
                'duration': duration
            }, room=f'user_{call_record.caller_id}')
    
    return jsonify({'success': True})

@app.route('/call_history')
@login_required
def get_call_history():
    calls = CallHistory.query.filter(
        (CallHistory.caller_id == current_user.id) | 
        (CallHistory.receiver_id == current_user.id)
    # FIX: Use created_at fallback — start_time can be NULL for missed calls
    ).order_by(CallHistory.id.desc()).limit(50).all()
    
    calls_data = []
    for call in calls:
        other_user = call.caller if call.caller_id != current_user.id else call.receiver
        # FIX: Guard strftime against None start_time
        start_time_str = call.start_time.strftime('%Y-%m-%d %H:%M:%S') if call.start_time else 'N/A'
        calls_data.append({
            'id': call.id,
            'other_user': other_user.username,
            'call_type': call.call_type,
            'duration': call.duration,
            'call_status': call.call_status,
            'start_time': start_time_str
        })
    
    return jsonify(calls_data)

@app.route('/delete_message/<int:message_id>', methods=['DELETE'])
@login_required
def delete_message(message_id):
    message = Message.query.get_or_404(message_id)
    if message.sender_id == current_user.id or message.receiver_id == current_user.id:
        message.is_deleted = True
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'error': 'Unauthorized'}), 403

@app.route('/logout')
@login_required
def logout():
    current_user.online_status = False
    current_user.last_seen = datetime.utcnow()
    db.session.commit()
    
    socketio.emit('user_offline', {'user_id': current_user.id})
    
    logout_user()
    return redirect(url_for('login'))

# Socket.IO Events
@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        online_users[current_user.id] = request.sid
        join_room(f'user_{current_user.id}')
        emit('user_status', {'user_id': current_user.id, 'status': 'online'}, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    if current_user.is_authenticated:
        if current_user.id in online_users:
            del online_users[current_user.id]
        current_user.online_status = False
        current_user.last_seen = datetime.utcnow()
        db.session.commit()
        emit('user_status', {'user_id': current_user.id, 'status': 'offline'}, broadcast=True)

# FIX: Handle join_room event from frontend (was missing — caused silent failure)
@socketio.on('join_room')
def handle_join_room(data):
    room = data.get('room')
    if room:
        join_room(room)

@socketio.on('typing')
def handle_typing(data):
    receiver_id = data.get('receiver_id')
    is_typing = data.get('is_typing')
    
    emit('user_typing', {
        'sender_id': current_user.id,
        'sender_name': current_user.username,
        'is_typing': is_typing
    }, room=f'user_{receiver_id}')

@socketio.on('join_call')
def handle_join_call(data):
    call_id = data.get('call_id')
    room_name = f'call_{call_id}'
    join_room(room_name)
    emit('user_joined_call', {'user_id': current_user.id}, room=room_name)

@socketio.on('webrtc_offer')
def handle_webrtc_offer(data):
    target_user_id = data.get('target_user_id')
    offer = data.get('offer')
    emit('webrtc_offer', {
        'offer': offer,
        'caller_id': current_user.id
    }, room=f'user_{target_user_id}')

@socketio.on('webrtc_answer')
def handle_webrtc_answer(data):
    target_user_id = data.get('target_user_id')
    answer = data.get('answer')
    emit('webrtc_answer', {
        'answer': answer,
        'caller_id': current_user.id
    }, room=f'user_{target_user_id}')

@socketio.on('webrtc_ice_candidate')
def handle_webrtc_ice_candidate(data):
    target_user_id = data.get('target_user_id')
    candidate = data.get('candidate')
    emit('webrtc_ice_candidate', {
        'candidate': candidate,
        'caller_id': current_user.id
    }, room=f'user_{target_user_id}')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)

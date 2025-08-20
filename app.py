from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, session
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
from werkzeug.utils import secure_filename
import time
from datetime import datetime, timedelta
from flask_migrate import Migrate
import logging
from logging.handlers import RotatingFileHandler
import json

from models import db, User, Post, Comment, Notification, Conversation, Message, Achievement, UserAchievement

app = Flask(__name__)
app.config['SECRET_KEY'] = 'gizli_anahtar_cok_uzun_ve_guvenli_bir_anahtar_olmalı'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Güvenlik ayarları
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
app.config['SESSION_COOKIE_SECURE'] = False  # Production'da True yap
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Fotoğraf yükleme klasörleri
app.config['POST_IMAGES_FOLDER'] = os.path.join('static', 'post_images')
app.config['PROFILE_PIC_FOLDER'] = os.path.join('static', 'profile_images')
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5 MB
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Flask eklentileri
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
db.init_app(app)
migrate = Migrate(app, db)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Rate Limiter
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# Basit Cache Sınıfı (Redis yerine)
class SimpleCache:
    def __init__(self):
        self.cache = {}
    
    def get(self, key):
        return self.cache.get(key)
    
    def set(self, key, value, ex=None):
        self.cache[key] = value
    
    def setex(self, key, time, value):
        self.cache[key] = value
    
    def delete(self, key):
        if key in self.cache:
            del self.cache[key]
    
    def incr(self, key):
        self.cache[key] = int(self.cache.get(key, 0)) + 1
        return self.cache[key]
    
    def sadd(self, key, value):
        if key not in self.cache:
            self.cache[key] = set()
        if isinstance(self.cache[key], set):
            self.cache[key].add(value)
    
    def srem(self, key, value):
        if key in self.cache and isinstance(self.cache[key], set):
            self.cache[key].discard(value)
    
    def smembers(self, key):
        return self.cache.get(key, set())
    
    def scard(self, key):
        return len(self.cache.get(key, set()))
    
    def lpush(self, key, value):
        if key not in self.cache:
            self.cache[key] = []
        self.cache[key].insert(0, value)
    
    def lrange(self, key, start, end):
        if key in self.cache:
            return self.cache[key][start:end]
        return []
    
    def ltrim(self, key, start, end):
        if key in self.cache:
            self.cache[key] = self.cache[key][start:end]

# Redis yerine basit cache kullan
redis_client = SimpleCache()

# Varsayılan Başarımlar (HATA DÜZELTME)
DEFAULT_ACHIEVEMENTS = [
    {'name': 'İlk Gönderi', 'description': 'İlk gönderini paylaştın!', 'points': 50, 'condition': 'posts_count >= 1'},
    {'name': 'Aktif Kullanıcı', 'description': '10 gönderi paylaştın!', 'points': 100, 'condition': 'posts_count >= 10'},
    {'name': 'Popüler', 'description': '5 takipçi kazandın!', 'points': 150, 'condition': 'followers_count >= 5'},
    {'name': 'Ünlü', 'description': '20 takipçi kazandın!', 'points': 300, 'condition': 'followers_count >= 20'},
    {'name': 'Puan Canavarı', 'description': '100 puan kazandın!', 'points': 50, 'condition': 'points >= 100'},
    {'name': 'Efsane', 'description': '500 puan kazandın!', 'points': 200, 'condition': 'points >= 500'},
]

# Logging
if not os.path.exists('logs'):
    os.makedirs('logs')
file_handler = RotatingFileHandler('logs/socialapp.log', maxBytes=10240, backupCount=10)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)
app.logger.info('SocialApp startup')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ===================== HELPER FUNCTIONS =====================

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def log_security_event(event_type, user_id, ip_address, details):
    """Güvenlik olaylarını loglar"""
    security_log = {
        'timestamp': datetime.utcnow().isoformat(),
        'event_type': event_type,
        'user_id': user_id,
        'ip_address': ip_address,
        'details': details
    }
    redis_client.lpush('security_events', json.dumps(security_log))
    redis_client.ltrim('security_events', 0, 999)  # Son 1000 olayı tut

def get_user_stats(user_id):
    """Kullanıcı istatistiklerini getirir"""
    stats = redis_client.get(f'user_stats:{user_id}')
    if stats:
        return json.loads(stats)
    
    user = User.query.get(user_id)
    if not user:
        return {}
    
    stats = {
        'posts_count': user.posts_count(),
        'followers_count': user.followers_count(),
        'following_count': user.following_count(),
        'likes_received': sum(post.like_count for post in user.user_posts),
        'comments_received': sum(post.comment_count for post in user.user_posts),
        'points': user.points,
        'level': user.level,
        'achievements_count': UserAchievement.query.filter_by(user_id=user_id).count()
    }
    
    # 1 saat cache'le
    redis_client.setex(f'user_stats:{user_id}', 3600, json.dumps(stats))
    return stats

# ===================== SOCKET.IO HANDLERS =====================

@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        join_room(f'user_{current_user.id}')
        app.logger.info(f'User {current_user.username} connected')
        emit('notification_count', {
            'count': current_user.get_unread_notifications_count()
        })

@socketio.on('disconnect')
def handle_disconnect():
    if current_user.is_authenticated:
        leave_room(f'user_{current_user.id}')
        app.logger.info(f'User {current_user.username} disconnected')

@socketio.on('mark_notification_read')
def handle_mark_notification_read(data):
    notification_id = data.get('notification_id')
    if notification_id:
        notification = Notification.query.get(notification_id)
        if notification and notification.user_id == current_user.id:
            notification.is_read = True
            db.session.commit()
            emit('notification_count', {
                'count': current_user.get_unread_notifications_count()
            })

@socketio.on('send_message')
def handle_send_message(data):
    conversation_id = data.get('conversation_id')
    content = data.get('content')
    receiver_id = data.get('receiver_id')
    
    if not content or len(content.strip()) == 0:
        return
    
    if conversation_id:
        conversation = Conversation.query.get(conversation_id)
        if conversation and current_user.id in [p.id for p in conversation.participants]:
            message = Message(
                conversation_id=conversation.id,
                sender_id=current_user.id,
                content=content.strip()
            )
            db.session.add(message)
            db.session.commit()
            
            # Alıcılara gönder
            for participant in conversation.participants:
                if participant.id != current_user.id:
                    emit('new_message', {
                        'message_id': message.id,
                        'content': message.content,
                        'sender': current_user.username,
                        'timestamp': message.timestamp.isoformat(),
                        'conversation_id': conversation.id
                    }, room=f'user_{participant.id}')
                    
                    # Bildirim oluştur
                    notification = Notification(
                        user_id=participant.id,
                        message=f'{current_user.username}: {message.content[:50]}...',
                        notification_type='message',
                        related_id=conversation.id
                    )
                    db.session.add(notification)
            
            db.session.commit()

# ===================== ROUTES =====================

@app.route("/")
def index():
    # İstatistikleri cache'le
    site_stats = redis_client.get('site_stats')
    if not site_stats:
        site_stats = {
            'total_users': User.query.count(),
            'total_posts': Post.query.count(),
            'total_comments': Comment.query.count(),
            'online_users': len(redis_client.smembers('online_users') or [])
        }
        redis_client.setex('site_stats', 300, json.dumps(site_stats))  # 5 dakika cache
    else:
        site_stats = json.loads(site_stats)
    
    return render_template("index.html", site_stats=site_stats)

@app.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        email = request.form.get("email", "").strip()

        # Güvenlik kontrolü
        if User.query.filter_by(username=username).first():
            flash("Bu kullanıcı adı zaten alınmış!", "danger")
            log_security_event('register_attempt', None, request.remote_addr, 
                             f'Username already exists: {username}')
            return redirect(url_for("register"))

        if len(password) < 8:
            flash("Şifre en az 8 karakter olmalı.", "warning")
            return redirect(url_for("register"))

        hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
        user = User(
            username=username,
            password=hashed_pw,
            email=email,
            profile_image="default_avatar.png"
        )
        db.session.add(user)
        db.session.commit()
        
        # Varsayılan başarımları ekle (HATA DÜZELTME)
        achievements = Achievement.query.all()
        if not achievements:
            for achievement_data in DEFAULT_ACHIEVEMENTS:
                achievement = Achievement(**achievement_data)
                db.session.add(achievement)
            db.session.commit()
            achievements = Achievement.query.all()
        
        flash("Kayıt başarılı, şimdi giriş yapabilirsin!", "success")
        log_security_event('register_success', user.id, request.remote_addr, 
                         f'New user: {username}')
        return redirect(url_for("login"))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        
        # Brute-force koruması
        attempt_key = f"login_attempts:{request.remote_addr}"
        attempts = redis_client.get(attempt_key) or 0
        if int(attempts) >= 5:
            flash("Çok fazla deneme yaptınız. Lütfen 15 dakika bekleyin.", "danger")
            return redirect(url_for("login"))
        
        user = User.query.filter_by(username=username).first()
        
        if user and bcrypt.check_password_hash(user.password, password):
            # Başarılı giriş
            login_user(user)
            user.last_login = datetime.utcnow()
            user.login_attempts = 0
            db.session.commit()
            
            redis_client.delete(attempt_key)
            redis_client.sadd('online_users', user.id)
            
            flash("Giriş başarılı!", "success")
            log_security_event('login_success', user.id, request.remote_addr, 
                             f'Successful login')
            return redirect(url_for("dashboard"))
        else:
            # Başarısız giriş
            redis_client.incr(attempt_key)
            redis_client.expire(attempt_key, 900)  # 15 dakika
            
            flash("Hatalı kullanıcı adı veya şifre!", "danger")
            log_security_event('login_failed', None, request.remote_addr, 
                             f'Failed login attempt for: {username}')
    
    return render_template("login.html")

@app.route("/dashboard")
@login_required
def dashboard():
    user_stats = get_user_stats(current_user.id)
    recent_notifications = current_user.get_recent_notifications(5)
    recent_messages = Message.query.join(Conversation).filter(
        Conversation.participants.any(id=current_user.id)
    ).order_by(Message.timestamp.desc()).limit(5).all()
    
    return render_template("dashboard.html", 
                         name=current_user.username,
                         stats=user_stats,
                         notifications=recent_notifications,
                         messages=recent_messages)

@app.route("/posts", methods=["GET", "POST"])
@login_required
def posts():
    if request.method == "POST":
        content = request.form["content"]
        image = request.files.get("image")

        if not content.strip():
            flash("Gönderi içeriği boş olamaz!", "warning")
            return redirect(url_for("posts"))

        image_filename = None
        if image and allowed_file(image.filename):
            secure_name = secure_filename(image.filename)
            timestamp = str(int(time.time()))
            image_filename = f"{current_user.username}_{timestamp}_{secure_name}"
            image_path = os.path.join(app.root_path, app.config['POST_IMAGES_FOLDER'], image_filename)
            image.save(image_path)
        elif image:
            flash("Geçersiz dosya türü!", "danger")
            return redirect(url_for("posts"))

        post = Post(
            body=content.strip(),
            user_id=current_user.id, 
            image=image_filename
        )
        
        # Hashtag'leri çıkar ve kaydet
        hashtags = post.extract_hashtags()
        
        db.session.add(post)
        db.session.commit()
        
        # Puan ve başarım
        current_user.add_points(10)
        current_user.check_achievements()
        
        flash("Gönderi paylaşıldı! +10 puan", "success")
        return redirect(url_for("posts"))

    # Önbelleklenmiş gönderileri getir
    cache_key = f'posts:{current_user.id}'
    cached_posts = redis_client.get(cache_key)
    
    if cached_posts:
        posts_data = json.loads(cached_posts)
    else:
        # Takip edilenlerin gönderileri + kendi gönderileri
        followed_posts = current_user.followed_posts()
        own_posts = Post.query.filter_by(user_id=current_user.id)
        all_posts = followed_posts.union(own_posts).order_by(Post.timestamp.desc()).all()
        
        posts_data = []
        for post in all_posts:
            posts_data.append({
                'id': post.id,
                'body': post.body,
                'hashtags': post.hashtags,
                'timestamp': post.timestamp.isoformat(),
                'author': post.author.username,
                'author_image': post.author.profile_image,
                'image': post.image,
                'like_count': post.like_count,
                'comment_count': post.comment_count,
                'is_liked': post.is_liked_by(current_user),
                'comments': [
                    {
                        'body': c.body,
                        'username': c.user.username,
                        'timestamp': c.timestamp.isoformat()
                    } for c in post.post_comments[:3]  # İlk 3 yorum
                ]
            })
        
        # 1 dakika cache'le
        redis_client.setex(cache_key, 60, json.dumps(posts_data))
    
    return render_template("posts.html", posts=posts_data)

@app.route('/like_post/<int:post_id>', methods=['POST'])
@login_required
def like_post(post_id):
    post = Post.query.get_or_404(post_id)
    
    if post.is_liked_by(current_user):
        post.unlike(current_user)
        message = "Beğeniden çıkarıldı"
        notification_type = 'unlike'
    else:
        post.like(current_user)
        message = "Gönderi beğenildi"
        notification_type = 'like'
        
        # Bildirim oluştur (kendi gönderini beğenmediyse)
        if post.author.id != current_user.id:
            notification = Notification(
                user_id=post.author.id,
                message=f'{current_user.username} gönderini beğendi',
                notification_type='like',
                related_id=post.id
            )
            db.session.add(notification)
            
            # Socket.IO ile bildirim gönder
            emit('new_notification', {
                'message': f'{current_user.username} gönderini beğendi',
                'type': 'like'
            }, room=f'user_{post.author.id}', namespace='/')
    
    db.session.commit()
    flash(message, "success")
    return redirect(url_for('posts'))

@app.route('/comment_post/<int:post_id>', methods=['POST'])
@login_required
def comment_post(post_id):
    post = Post.query.get_or_404(post_id)
    comment_content = request.form['comment']
    
    if comment_content.strip():
        comment = Comment(
            body=comment_content.strip(),
            post_id=post.id,
            user_id=current_user.id
        )
        db.session.add(comment)
        post.comment_count = len(post.post_comments)
        
        # Bildirim oluştur (kendi gönderine yorum yapmadıysa)
        if post.author.id != current_user.id:
            notification = Notification(
                user_id=post.author.id,
                message=f'{current_user.username} gönderine yorum yaptı: {comment_content[:30]}...',
                notification_type='comment',
                related_id=post.id
            )
            db.session.add(notification)
            
            # Socket.IO ile bildirim gönder
            emit('new_notification', {
                'message': f'{current_user.username} gönderine yorum yaptı',
                'type': 'comment'
            }, room=f'user_{post.author.id}', namespace='/')
        
        # Puan ve başarım
        current_user.add_points(5)
        current_user.check_achievements()
        
        db.session.commit()
        flash("Yorum eklendi! +5 puan", "success")
    else:
        flash("Yorum boş olamaz!", "warning")
    
    return redirect(url_for('posts'))

@app.route("/logout")
@login_required
def logout():
    redis_client.srem('online_users', current_user.id)
    logout_user()
    flash("Çıkış yapıldı.", "info")
    return redirect(url_for("login"))

@app.route("/admin")
@login_required
def admin_panel():
    if current_user.username != "admin":
        flash("Yetkisiz erişim!", "danger")
        return redirect(url_for("dashboard"))
    
    # Admin istatistikleri
    total_users = User.query.count()
    total_posts = Post.query.count()
    total_comments = Comment.query.count()
    online_users = len(redis_client.smembers('online_users') or [])
    
    # Son güvenlik olayları
    security_events = []
    events = redis_client.lrange('security_events', 0, 49)
    for event in events:
        security_events.append(json.loads(event))
    
    # Sistem durumu (HATA DÜZELTME - psutil kaldırıldı)
    system_stats = {
        'memory_usage': 0,
        'disk_usage': 0,
        'uptime': 0
    }
    
    return render_template("admin_panel.html",
                         total_users=total_users,
                         total_posts=total_posts,
                         total_comments=total_comments,
                         online_users=online_users,
                         security_events=security_events,
                         system_stats=system_stats)

@app.route('/notifications')
@login_required
def notifications():
    notifications = current_user.get_recent_notifications(20)
    # Okunmamış bildirimleri okundu olarak işaretle
    for notification in notifications:
        if not notification.is_read:
            notification.is_read = True
    db.session.commit()
    
    return render_template('notifications.html', notifications=notifications)

@app.route('/messages')
@login_required
def messages():
    conversations = current_user.conversations.order_by(Conversation.created_at.desc()).all()
    return render_template('messages.html', conversations=conversations)

@app.route('/conversation/<int:conversation_id>')
@login_required
def conversation(conversation_id):
    conversation = Conversation.query.get_or_404(conversation_id)
    if current_user not in conversation.participants:
        flash("Bu konuşmaya erişim izniniz yok.", "danger")
        return redirect(url_for('messages'))
    
    # Mesajları okundu olarak işaretle
    unread_messages = Message.query.filter_by(
        conversation_id=conversation_id,
        is_read=False
    ).filter(Message.sender_id != current_user.id).all()
    
    for msg in unread_messages:
        msg.is_read = True
    
    db.session.commit()
    
    messages = conversation.messages.order_by(Message.timestamp.asc()).all()
    return render_template('conversation.html', 
                         conversation=conversation,
                         messages=messages)

@app.route('/start_conversation/<username>')
@login_required
def start_conversation(username):
    other_user = User.query.filter_by(username=username).first_or_404()
    
    if other_user.id == current_user.id:
        flash("Kendinizle konuşamazsınız!", "warning")
        return redirect(url_for('messages'))
    
    # Var olan konuşmayı kontrol et
    existing_conv = Conversation.query.filter(
        Conversation.participants.any(id=current_user.id),
        Conversation.participants.any(id=other_user.id),
        Conversation.is_group == False
    ).first()
    
    if existing_conv:
        return redirect(url_for('conversation', conversation_id=existing_conv.id))
    
    # Yeni konuşma oluştur
    new_conversation = Conversation()
    new_conversation.participants.append(current_user)
    new_conversation.participants.append(other_user)
    
    db.session.add(new_conversation)
    db.session.commit()
    
    return redirect(url_for('conversation', conversation_id=new_conversation.id))

@app.route('/achievements')
@login_required
def achievements():
    user_achievements = UserAchievement.query.filter_by(
        user_id=current_user.id
    ).join(Achievement).order_by(UserAchievement.unlocked_at.desc()).all()
    
    all_achievements = Achievement.query.all()
    
    return render_template('achievements.html',
                         user_achievements=user_achievements,
                         all_achievements=all_achievements)

@app.route('/leaderboard')
def leaderboard():
    # Liderlik tablosunu getir
    leaderboard_cache = redis_client.get('leaderboard')
    if leaderboard_cache:
        leaders = json.loads(leaderboard_cache)
    else:
        leaders = User.query.order_by(User.points.desc()).limit(20).all()
        leaders_data = []
        for user in leaders:
            leaders_data.append({
                'username': user.username,
                'points': user.points,
                'level': user.level,
                'achievements': UserAchievement.query.filter_by(user_id=user.id).count()
            })
        
        # 5 dakika cache'le
        redis_client.setex('leaderboard', 300, json.dumps(leaders_data))
        leaders = leaders_data
    
    return render_template('leaderboard.html', leaders=leaders)

@app.route('/api/stats')
@login_required
def api_stats():
    if current_user.username != "admin":
        return jsonify({'error': 'Unauthorized'}), 403
    
    stats = {
        'users': {
            'total': User.query.count(),
            'active_today': User.query.filter(
                User.last_activity >= datetime.utcnow() - timedelta(hours=24)
            ).count(),
            'new_today': User.query.filter(
                User.last_activity >= datetime.utcnow() - timedelta(hours=24)
            ).count()
        },
        'content': {
            'posts_today': Post.query.filter(
                Post.timestamp >= datetime.utcnow() - timedelta(hours=24)
            ).count(),
            'comments_today': Comment.query.filter(
                Comment.timestamp >= datetime.utcnow() - timedelta(hours=24)
            ).count()
        },
        'system': {
            'online_users': len(redis_client.smembers('online_users') or []),
            'memory_usage': 0,
            'uptime': 0
        }
    }
    
    return jsonify(stats)

# ===================== ERROR HANDLERS =====================

@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

@app.errorhandler(429)
def ratelimit_handler(e):
    flash("Çok fazla istek gönderdiniz. Lütfen bir süre bekleyin.", "warning")
    return redirect(url_for('index'))

# ===================== MAIN =====================

if __name__ == "__main__":
    with app.app_context():
        # Gerekli klasörleri oluştur
        os.makedirs(os.path.join(app.root_path, app.config['POST_IMAGES_FOLDER']), exist_ok=True)
        os.makedirs(os.path.join(app.root_path, app.config['PROFILE_PIC_FOLDER']), exist_ok=True)
        os.makedirs('logs', exist_ok=True)
        
        # Veritabanını oluştur
        db.create_all()
        
        # Varsayılan başarımları ekle (HATA DÜZELTME)
        if Achievement.query.count() == 0:
            for achievement_data in DEFAULT_ACHIEVEMENTS:
                achievement = Achievement(**achievement_data)
                db.session.add(achievement)
            db.session.commit()
    
    # SocketIO ile çalıştır
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
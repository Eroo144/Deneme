from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask_login import UserMixin
import redis
import re

# db'yi burada oluşturuyoruz
db = SQLAlchemy()

# Redis bağlantısı için
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# Beğeniler için ilişki
likes = db.Table(
    'likes',
    db.Column('post_id', db.Integer, db.ForeignKey('post.id')),
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'))
)

# Takipçi ilişkisi
followers = db.Table(
    'followers',
    db.Column('follower_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('followed_id', db.Integer, db.ForeignKey('user.id'))
)

# Mesajlaşma için ilişki
user_conversations = db.Table(
    'user_conversations',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('conversation_id', db.Integer, db.ForeignKey('conversation.id'))
)

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(20), nullable=False)  # like, comment, message, follow, level_up, achievement
    is_read = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    related_id = db.Column(db.Integer)  # İlgili post/message id

    user = db.relationship('User', backref=db.backref('notifications', lazy=True))


class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_group = db.Column(db.Boolean, default=False)
    group_name = db.Column(db.String(100))

    participants = db.relationship(
        'User', secondary=user_conversations,
        backref=db.backref('conversations', lazy=True)
    )
    messages = db.relationship('Message', backref='conversation', lazy=True)


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)

    sender = db.relationship('User', backref=db.backref('sent_messages', lazy=True))


class UserAchievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    achievement_id = db.Column(db.Integer, db.ForeignKey('achievement.id'), nullable=False)
    unlocked_at = db.Column(db.DateTime, default=datetime.utcnow)


class Achievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    icon = db.Column(db.String(100))
    points = db.Column(db.Integer, default=0)
    condition = db.Column(db.String(100))  # Örn: "posts_count >= 10"


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.Text, nullable=False)
    hashtags = db.Column(db.Text)  # Hashtag alanı
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    image = db.Column(db.String(150), nullable=True)
    like_count = db.Column(db.Integer, default=0)
    comment_count = db.Column(db.Integer, default=0)

    author_rel = db.relationship('User', backref=db.backref('user_posts', lazy=True))
    liked_by = db.relationship('User', secondary=likes, backref=db.backref('liked_posts', lazy='dynamic'))

    def like(self, user):
        if not self.is_liked_by(user):
            self.liked_by.append(user)
            self.like_count = len(self.liked_by)
            user.check_achievements()

    def unlike(self, user):
        if self.is_liked_by(user):
            self.liked_by.remove(user)
            self.like_count = len(self.liked_by)

    def is_liked_by(self, user):
        if user.is_authenticated:
            return user in self.liked_by
        return False

    def extract_hashtags(self):
        if self.body:
            hashtags = re.findall(r"#(\w+)", self.body)
            self.hashtags = ' '.join(hashtags)
            return hashtags
        return []


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    post = db.relationship('Post', backref=db.backref('post_comments', lazy=True))
    user = db.relationship('User', backref=db.backref('user_comments', lazy=True))


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)

    bio = db.Column(db.Text)
    profile_image = db.Column(db.String(128), default='default-avatar.jpg')
    first_name = db.Column(db.String(64))
    last_name = db.Column(db.String(64))
    instagram = db.Column(db.String(100))
    twitter = db.Column(db.String(100))
    github = db.Column(db.String(100))

    # Oyunlaştırma alanları
    points = db.Column(db.Integer, default=0)
    level = db.Column(db.Integer, default=1)
    experience = db.Column(db.Integer, default=0)
    last_activity = db.Column(db.DateTime, default=datetime.utcnow)

    # Güvenlik alanları
    is_verified = db.Column(db.Boolean, default=False)
    two_factor_enabled = db.Column(db.Boolean, default=False)
    two_factor_secret = db.Column(db.String(16))
    login_attempts = db.Column(db.Integer, default=0)
    last_login_attempt = db.Column(db.DateTime)

    posts = db.relationship('Post', backref='author', lazy='dynamic')
    followed = db.relationship(
        'User', secondary=followers,
        primaryjoin=(followers.c.follower_id == id),
        secondaryjoin=(followers.c.followed_id == id),
        backref=db.backref('followers_rel', lazy='dynamic'),
        lazy='dynamic'
    )

    def followed_posts(self):
        return Post.query.join(
            followers, (followers.c.followed_id == Post.user_id)
        ).filter(followers.c.follower_id == self.id).order_by(Post.timestamp.desc())

    def follow(self, user):
        if not self.is_following(user):
            self.followed.append(user)
            self.check_achievements()

    def unfollow(self, user):
        if self.is_following(user):
            self.followed.remove(user)

    def is_following(self, user):
        return self.followed.filter(followers.c.followed_id == user.id).count() > 0

    def followers_count(self):
        return self.followers_rel.count()

    def following_count(self):
        return self.followed.count()

    def posts_count(self):
        return self.posts.count()

    def add_points(self, amount):
        """Kullanıcıya puan ekler ve seviye kontrolü yapar"""
        self.points += amount
        self.experience += amount
        self.check_level_up()
        db.session.commit()

    def check_level_up(self):
        """Seviye atlama kontrolü"""
        exp_needed = self.level * 100
        if self.experience >= exp_needed:
            self.level += 1
            self.experience -= exp_needed
            notification = Notification(
                user_id=self.id,
                message=f'Tebrikler! Seviye atladınız: {self.level}',
                notification_type='level_up'
            )
            db.session.add(notification)

    def check_achievements(self):
        """Kazanılan başarımları kontrol et"""
        achievements = Achievement.query.all()
        for achievement in achievements:
            if not self.has_achievement(achievement) and self.meets_condition(achievement.condition):
                self.unlock_achievement(achievement)

    def has_achievement(self, achievement):
        return UserAchievement.query.filter_by(
            user_id=self.id, achievement_id=achievement.id
        ).first() is not None

    def meets_condition(self, condition):
        """Koşul değerlendirmesi"""
        if not condition:
            return False

        conditions = {
            'posts_count >= 1': self.posts_count() >= 1,
            'posts_count >= 10': self.posts_count() >= 10,
            'followers_count >= 5': self.followers_count() >= 5,
            'followers_count >= 20': self.followers_count() >= 20,
            'points >= 100': self.points >= 100,
            'points >= 500': self.points >= 500,
        }

        return conditions.get(condition, False)

    def unlock_achievement(self, achievement):
        """Başarımın kilidini açar"""
        user_achievement = UserAchievement(
            user_id=self.id,
            achievement_id=achievement.id
        )
        db.session.add(user_achievement)

        # Puan ekle
        self.add_points(achievement.points)

        # Bildirim oluştur
        notification = Notification(
            user_id=self.id,
            message=f'Başarım kazandınız: {achievement.name}! {achievement.description}',
            notification_type='achievement'
        )
        db.session.add(notification)

    def get_unread_notifications_count(self):
        return Notification.query.filter_by(
            user_id=self.id, is_read=False
        ).count()

    def get_recent_notifications(self, limit=10):
        return Notification.query.filter_by(
            user_id=self.id
        ).order_by(Notification.timestamp.desc()).limit(limit).all()

    def get_unread_messages_count(self):
        return Message.query.filter(
            Message.conversation.has(Conversation.participants.any(id=self.id)),
            Message.sender_id != self.id,
            Message.is_read == False
        ).count()


# Varsayılan başarımlar
DEFAULT_ACHIEVEMENTS = [
    {'name': 'İlk Gönderi', 'description': 'İlk gönderini paylaştın!', 'points': 50, 'condition': 'posts_count >= 1'},
    {'name': 'Aktif Kullanıcı', 'description': '10 gönderi paylaştın!', 'points': 100, 'condition': 'posts_count >= 10'},
    {'name': 'Popüler', 'description': '5 takipçi kazandın!', 'points': 150, 'condition': 'followers_count >= 5'},
    {'name': 'Ünlü', 'description': '20 takipçi kazandın!', 'points': 300, 'condition': 'followers_count >= 20'},
    {'name': 'Puan Canavarı', 'description': '100 puan kazandın!', 'points': 50, 'condition': 'points >= 100'},
    {'name': 'Efsane', 'description': '500 puan kazandın!', 'points': 200, 'condition': 'points >= 500'},
]

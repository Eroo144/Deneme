from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask_login import UserMixin

# db'yi burada oluşturuyoruz
db = SQLAlchemy()

# Beğeniler için ilişki
likes = db.Table('likes',
    db.Column('post_id', db.Integer, db.ForeignKey('post.id')),
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'))
)

# Takipçi ilişkisi
followers = db.Table('followers',
    db.Column('follower_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('followed_id', db.Integer, db.ForeignKey('user.id'))
)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    image = db.Column(db.String(150), nullable=True)

    # posts adında zaten bir relationship var, bu yüzden farklı bir isim kullanıyoruz
    author_rel = db.relationship('User', backref=db.backref('user_posts', lazy=True))

    liked_by = db.relationship('User', secondary=likes, backref=db.backref('liked_posts', lazy='dynamic'))

    def like(self, user):
        if not self.is_liked_by(user):
            self.liked_by.append(user)

    def unlike(self, user):
        if self.is_liked_by(user):
            self.liked_by.remove(user)

    def is_liked_by(self, user):
        if user.is_authenticated:
            return user in self.liked_by
        return False


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

    bio = db.Column(db.Text)
    profile_image = db.Column(db.String(128), default='default-avatar.jpg')
    
    first_name = db.Column(db.String(64))
    last_name = db.Column(db.String(64))
    instagram = db.Column(db.String(100))
    twitter = db.Column(db.String(100))
    github = db.Column(db.String(100))

    # Bu zaten var, bu yüzden Post'taki backref'i değiştirdik
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
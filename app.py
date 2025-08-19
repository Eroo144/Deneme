from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import os
from werkzeug.utils import secure_filename
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'gizli_anahtar'  # Güçlü ve gizli bir anahtar belirle
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'profile_images')
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2 MB sınırı

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'  # login_required yönlendirmeleri buraya

# ===================== MODELLER ===================== #

# Takipçi - Takip edilen ilişkisi (many-to-many)
followers = db.Table('followers',
    db.Column('follower_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('followed_id', db.Integer, db.ForeignKey('user.id'))
)

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), nullable=False, unique=True)
    password = db.Column(db.String(150), nullable=False)
    bio = db.Column(db.Text, default="")  # Kullanıcı biyografisi
    profile_image = db.Column(db.String(150), default="default.jpg")

    # Takip sistemi
    followed = db.relationship(
        'User', secondary=followers,
        primaryjoin=(followers.c.follower_id == id),
        secondaryjoin=(followers.c.followed_id == id),
        backref=db.backref('followers', lazy='dynamic'), lazy='dynamic'
    )

    def follow(self, user):
        if not self.is_following(user):
            self.followed.append(user)

    def unfollow(self, user):
        if self.is_following(user):
            self.followed.remove(user)

    def is_following(self, user):
        return self.followed.filter(followers.c.followed_id == user.id).count() > 0

    def followers_count(self):
        return self.followers.count()

    def following_count(self):
        return self.followed.count()

    def posts_count(self):
        # Eğer Post tablosu eklersek:
        # return Post.query.filter_by(user_id=self.id).count()
        return 0  # şimdilik 0 dönüyor

# ===================== LOGIN MANAGER ===================== #

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ===================== ROUTELAR ===================== #

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"], strict_slashes=False)
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
        user = User(username=username, password=hashed_pw)
        db.session.add(user)
        db.session.commit()
        flash("Kayıt başarılı, şimdi giriş yapabilirsin!", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = User.query.filter_by(username=username).first()
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            flash("Giriş başarılı!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Hatalı kullanıcı adı veya şifre!", "danger")
    return render_template("login.html")

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", name=current_user.username)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Çıkış yapıldı.", "info")
    return redirect(url_for("login"))

@app.route("/admin")
@login_required
def admin_panel():
    if current_user.username == "admin":
        return render_template("admin_panel.html")
    
    flash("Yetkisiz erişim!", "danger")
    return redirect(url_for("dashboard"))

# ===================== PROFİL ===================== #

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        bio = request.form.get('bio')
        current_user.bio = bio

        file = request.files.get('profile_image')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            _, ext = os.path.splitext(filename)
            filename = current_user.username + '_' + str(int(time.time())) + ext
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            current_user.profile_image = filename
        
        db.session.commit()
        flash('Profil güncellendi!', 'success')
        return redirect(url_for('profile'))

    # İstatistikleri al
    stats = {
        "followers": current_user.followers_count(),
        "following": current_user.following_count(),
        "posts": current_user.posts_count()
    }

    return render_template('profile.html', user=current_user, stats=stats)

# ===================== TAKİP ET / BIRAK ===================== #

@app.route('/follow/<username>', methods=['POST'])
@login_required
def follow(username):
    user = User.query.filter_by(username=username).first_or_404()
    if user == current_user:
        flash("Kendi kendini takip edemezsin!", "warning")
        return redirect(url_for('profile'))
    current_user.follow(user)
    db.session.commit()
    flash(f"{user.username} adlı kişiyi takip ettin", "success")
    return redirect(url_for('profile', username=username))

@app.route('/unfollow/<username>', methods=['POST'])
@login_required
def unfollow(username):
    user = User.query.filter_by(username=username).first_or_404()
    if user == current_user:
        flash("Kendi kendini takipten çıkaramazsın!", "warning")
        return redirect(url_for('profile'))
    current_user.unfollow(user)
    db.session.commit()
    flash(f"{user.username} adlı kişiyi takipten çıktın", "info")
    return redirect(url_for('profile', username=username))

# ===================== HELPER ===================== #

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ===================== MAIN ===================== #

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)

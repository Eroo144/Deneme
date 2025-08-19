from flask import Flask, render_template, redirect, url_for, request, flash
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
import os
from werkzeug.utils import secure_filename
import time
from datetime import datetime
from flask_migrate import Migrate

from models import db, User, Post, Comment

app = Flask(__name__)
app.config['SECRET_KEY'] = 'gizli_anahtar'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Fotoğraf yükleme klasörleri
app.config['POST_IMAGES_FOLDER'] = os.path.join('static', 'post_images')
app.config['PROFILE_PIC_FOLDER'] = os.path.join('static', 'profile_images')
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2 MB
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Flask eklentileri
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
db.init_app(app)
migrate = Migrate(app, db)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ===================== HELPER ===================== #

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ===================== ROUTES ===================== #

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if User.query.filter_by(username=username).first():
            flash("Bu kullanıcı adı zaten alınmış!", "danger")
            return redirect(url_for("register"))

        if len(password) < 6:
            flash("Şifre en az 6 karakter olmalı.", "warning")
            return redirect(url_for("register"))

        hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
        user = User(
            username=username,
            password=hashed_pw,
            profile_image="default_avatar.png"  # Default avatar
        )
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

@app.route("/posts", methods=["GET", "POST"])
@login_required
def posts():
    if request.method == "POST":
        content = request.form["content"]
        image = request.files.get("image")

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

        post = Post(body=content, user_id=current_user.id, image=image_filename)
        db.session.add(post)
        db.session.commit()
        flash("Gönderi paylaşıldı!", "success")
        return redirect(url_for("posts"))

    all_posts = Post.query.order_by(Post.timestamp.desc()).all()
    return render_template("posts.html", posts=all_posts)

@app.route('/like_post/<int:post_id>', methods=['POST'])
@login_required
def like_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.is_liked_by(current_user):
        post.unlike(current_user)
        flash("Gönderiden çıkarıldı", "info")
    else:
        post.like(current_user)
        flash("Gönderiye beğeni yapıldı", "success")
    db.session.commit()
    return redirect(url_for('posts'))

@app.route('/comment_post/<int:post_id>', methods=['POST'])
@login_required
def comment_post(post_id):
    post = Post.query.get_or_404(post_id)
    comment_content = request.form['comment']
    if comment_content.strip():
        comment = Comment(body=comment_content, post_id=post.id, user_id=current_user.id)
        db.session.add(comment)
        db.session.commit()
        flash("Yorum başarıyla eklendi!", "success")
    else:
        flash("Yorum boş olamaz!", "warning")
    return redirect(url_for('posts'))

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
            filename = f"{current_user.username}_{int(time.time())}{ext}"
            file_path = os.path.join(app.root_path, app.config['PROFILE_PIC_FOLDER'], filename)
            file.save(file_path)
            current_user.profile_image = filename

        db.session.commit()
        flash('Profil güncellendi!', 'success')
        return redirect(url_for('profile'))

    stats = {
        "followers": current_user.followers_count(),
        "following": current_user.following_count(),
        "posts": current_user.posts_count()
    }

    # Avatar yolu
    profile_image = current_user.profile_image or "default_avatar.png"
    profile_image_url = url_for('static', filename=f'profile_images/{profile_image}')

    return render_template('profile.html', user=current_user, stats=stats, profile_image_url=profile_image_url)

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
    return redirect(url_for('profile'))

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
    return redirect(url_for('profile'))

# ===================== MAIN ===================== #

if __name__ == "__main__":
    # Gerekli klasörlerin varlığını kontrol edip yoksa oluştur
    os.makedirs(os.path.join(app.root_path, app.config['POST_IMAGES_FOLDER']), exist_ok=True)
    os.makedirs(os.path.join(app.root_path, app.config['PROFILE_PIC_FOLDER']), exist_ok=True)

    # Default avatar yoksa koyalım
    default_path = os.path.join(app.root_path, app.config['PROFILE_PIC_FOLDER'], "default_avatar.png")
    if not os.path.exists(default_path):
        # Boş bir placeholder oluştur
        with open(default_path, "wb") as f:
            f.write(b"")

    with app.app_context():
        db.create_all()
    app.run(debug=True)

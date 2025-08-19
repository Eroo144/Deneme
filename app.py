from flask import Flask, render_template, redirect, url_for, request, flash
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
import os
from werkzeug.utils import secure_filename
import time
from datetime import datetime
from flask_migrate import Migrate

# Önce models modülünden db'yi import ediyoruz
from models import db, User, Post, Comment

app = Flask(__name__)
app.config['SECRET_KEY'] = 'gizli_anahtar'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Fotoğraf yükleme klasörlerini ve sınırlarını ayarlama
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'post_images')
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2 MB sınırı

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Bağlantı oluşturma
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# db'yi app ile başlat
db.init_app(app)
migrate = Migrate(app, db)

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

@app.route("/posts", methods=["GET", "POST"])
@login_required
def posts():
    if request.method == "POST":
        content = request.form["content"]
        image = request.files.get("image")  # Fotoğrafı alıyoruz

        image_filename = None
        if image:
            # Fotoğrafın adı ve uzantısını güvenli bir şekilde alıyoruz
            image_filename = secure_filename(image.filename)
            image_path = os.path.join(app.root_path, 'static', 'post_images', image_filename)
            image.save(image_path)  # Fotoğrafı kaydediyoruz

        post = Post(body=content, user_id=current_user.id, image=image_filename)  # Fotoğrafı veritabanına kaydediyoruz
        db.session.add(post)
        db.session.commit()
        flash("Gönderi paylaşıldı!", "success")
        return redirect(url_for("posts"))

    # Takip ettiğiniz kişilerin gönderilerini alın
    all_posts = Post.query.order_by(Post.timestamp.desc()).all()
    # Gönderileri tarihine göre sırala
    all_posts.sort(key=lambda x: x.timestamp, reverse=True)

    return render_template("posts.html", posts=all_posts)

# Beğenme işlemi
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

# Yorum ekleme işlemi
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
            file_path = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], filename)
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

# ===================== HELPER ===================== #

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ===================== MAIN ===================== #

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
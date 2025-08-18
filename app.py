from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

app = Flask(__name__)
app.config['SECRET_KEY'] = 'gizli_anahtar'  # Güçlü ve gizli bir anahtar belirle
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'  # login_required yönlendirmeleri buraya

# Kullanıcı modeli
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), nullable=False, unique=True)
    password = db.Column(db.String(150), nullable=False)

# Giriş yapan kullanıcıyı yükler
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

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


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)

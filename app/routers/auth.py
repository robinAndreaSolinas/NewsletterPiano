from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from app.models import User

router = Blueprint("auth", __name__)

@router.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("home.index"))

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user = User.find_by_username(username)  # cerca nel DB

        if user and check_password_hash(user.password_hash, password):
            login_user(user, remember=request.form.get("remember"))
            next_page = request.args.get("next")          # torna alla pagina richiesta
            return redirect(next_page or url_for("home.index"))

        flash("Credenziali non valide", "error")

    return render_template("auth/login.html")


@router.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))

# routes_auth.py
# Authentication routes (signup / login / logout) using Flask-Login + SQLAlchemy

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user

from db import SessionLocal
from models import User

bp_auth = Blueprint("auth", __name__, url_prefix="/auth")


# LOGIN
@bp_auth.get("/login")
def login_get():
    """
    Show the login form.
    If user is already logged in, redirect to home page.
    """
    if current_user.is_authenticated:
        return redirect(url_for("home"))
    return render_template("login.html")


@bp_auth.post("/login")
def login_post():
    """
    Process the login form.
    - Looks up user by email
    - Verifies password hash
    - Creates a login session cookie
    """
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""

    if not email or not password:
        flash("Email and password are required.", "error")
        return redirect(url_for("auth.login_get"))

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()

        # Security: do not reveal whether email exists; treat as generic failure
        if not user or not user.check_password(password):
            flash("Invalid email or password.", "error")
            return redirect(url_for("auth.login_get"))

        login_user(user, remember=True)
        return redirect(url_for("home"))
    finally:
        db.close()


# SIGNUP
@bp_auth.get("/signup")
def signup_get():
    """
    Show the signup form.
    If already logged in, redirect home.
    """
    if current_user.is_authenticated:
        return redirect(url_for("home"))
    return render_template("signup.html")


@bp_auth.post("/signup")
def signup_post():
    """
    Process signup:
    - Creates a user row
    - Hashes password before storing
    - Logs user in immediately
    """
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""

    if not email or not password:
        flash("Email and password are required.", "error")
        return redirect(url_for("auth.signup_get"))

    if len(password) < 8:
        flash("Password must be at least 8 characters.", "error")
        return redirect(url_for("auth.signup_get"))

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            flash("An account with that email already exists.", "error")
            return redirect(url_for("auth.signup_get"))

        is_admin = request.form.get("is_admin") == "on"

        user = User(email=email, is_admin=is_admin)
        user.set_password(password)

        db.add(user)
        db.commit()
        db.refresh(user)

        login_user(user, remember=True)
        return redirect(url_for("home"))
    finally:
        db.close()



# LOGOUT
@bp_auth.post("/logout")
@login_required
def logout_post():
    """
    Logs the user out by clearing the session.
    POST is used to avoid accidental logout from link prefetching.
    """
    logout_user()
    return redirect(url_for("auth.login_get"))

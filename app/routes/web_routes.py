from flask import Blueprint, render_template


web_bp = Blueprint("web", __name__)


@web_bp.get("/")
def home():
    return render_template("home.html")


@web_bp.get("/login")
def login_page():
    return render_template("auth/login.html")


@web_bp.get("/register")
def register_page():
    return render_template("auth/register.html")


@web_bp.get("/dashboard")
def teacher_dashboard():
    return render_template("teacher/dashboard.html")


@web_bp.get("/student-portal")
def student_portal():
    return render_template("student/portal.html")

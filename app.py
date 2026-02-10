from __future__ import annotations

import json
import os
import random
import sqlite3
import string
import time
from datetime import datetime, date, timedelta
from pathlib import Path

from flask import Flask, render_template, request, redirect, session, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = BASE_DIR / "codecourse.db"

app = Flask(__name__)
app.secret_key = "dev-key"

ADMIN_USERNAME = os.environ.get("CODECOURSE_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("CODECOURSE_ADMIN_PASS", "admin123")
SUPPORT_EMAIL = "codeformaine@gmail.com"
GMAIL_USER = os.environ.get("CODECOURSE_GMAIL_USER")
GMAIL_APP_PASS = os.environ.get("CODECOURSE_GMAIL_PASS")


@app.context_processor
def inject_static_version():
    """Cache-bust static assets when files change (helps on Render + browsers)."""
    try:
        css_path = BASE_DIR / "static" / "style.css"
        static_version = int(css_path.stat().st_mtime)
    except Exception:
        static_version = int(time.time())
    return {"static_version": static_version}


# ---------------- DB ----------------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            avatar TEXT NOT NULL,
            streak_count INTEGER DEFAULT 0,
            last_active_date TEXT,
            created_at TEXT NOT NULL
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS classrooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            code TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (teacher_id) REFERENCES users (id)
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS classroom_students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            classroom_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            joined_at TEXT NOT NULL,
            UNIQUE (classroom_id, student_id),
            FOREIGN KEY (classroom_id) REFERENCES classrooms (id),
            FOREIGN KEY (student_id) REFERENCES users (id)
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            classroom_id INTEGER NOT NULL,
            lesson_id INTEGER NOT NULL,
            lesson_lang TEXT NOT NULL,
            due_date TEXT,
            comment TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (classroom_id) REFERENCES classrooms (id)
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS assignment_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            completed_at TEXT,
            score INTEGER,
            student_comment TEXT,
            grade_out_of_10 INTEGER,
            FOREIGN KEY (assignment_id) REFERENCES assignments (id),
            FOREIGN KEY (student_id) REFERENCES users (id),
            UNIQUE (assignment_id, student_id)
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            lesson_id INTEGER NOT NULL,
            lesson_lang TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            score INTEGER NOT NULL,
            xp INTEGER NOT NULL,
            UNIQUE (student_id, lesson_id, lesson_lang),
            FOREIGN KEY (student_id) REFERENCES users (id)
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS lesson_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            lesson_id INTEGER NOT NULL,
            lesson_lang TEXT NOT NULL,
            notes TEXT,
            updated_at TEXT NOT NULL,
            UNIQUE (student_id, lesson_id, lesson_lang)
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS reach_out (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            role TEXT,
            message TEXT NOT NULL,
            photo_url TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            classroom_id INTEGER,
            is_read INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS stream_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            classroom_id INTEGER NOT NULL,
            author_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            audience TEXT NOT NULL, -- 'class' | 'student'
            student_id INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (classroom_id) REFERENCES classrooms (id),
            FOREIGN KEY (author_id) REFERENCES users (id),
            FOREIGN KEY (student_id) REFERENCES users (id)
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS classroom_invites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            classroom_id INTEGER NOT NULL,
            email TEXT NOT NULL,
            invited_at TEXT NOT NULL,
            FOREIGN KEY (classroom_id) REFERENCES classrooms (id)
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS assignment_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            author_role TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (assignment_id) REFERENCES assignments (id),
            FOREIGN KEY (student_id) REFERENCES users (id)
        );
        """
    )

    conn.commit()
    conn.close()


def migrate_db():
    conn = get_db()
    cur = conn.cursor()

    cols = cur.execute("PRAGMA table_info(assignment_submissions)").fetchall()
    col_names = {c[1] for c in cols}
    if "grade_out_of_10" not in col_names:
        cur.execute("ALTER TABLE assignment_submissions ADD COLUMN grade_out_of_10 INTEGER")

    notif_cols = cur.execute("PRAGMA table_info(notifications)").fetchall()
    notif_names = {c[1] for c in notif_cols}
    if "classroom_id" not in notif_names:
        cur.execute("ALTER TABLE notifications ADD COLUMN classroom_id INTEGER")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS stream_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            classroom_id INTEGER NOT NULL,
            author_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            audience TEXT NOT NULL,
            student_id INTEGER,
            created_at TEXT NOT NULL
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS assignment_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            author_role TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )

    conn.commit()
    conn.close()


def now_ts():
    return datetime.utcnow().isoformat()

@app.template_filter("fmt_dt")
def fmt_dt(value: str | None):
    """Format ISO timestamps stored in DB into something human-readable."""
    if not value:
        return ""
    try:
        # Stored by us as UTC ISO without timezone.
        dt = datetime.fromisoformat(value.replace("Z", ""))
    except Exception:
        return value
    d = dt.date()
    today = date.today()
    if d == today:
        day = "Today"
    elif d == (today - timedelta(days=1)):
        day = "Yesterday"
    else:
        # Drop the year if it's this year to reduce noise.
        if d.year == today.year:
            day = dt.strftime("%b %d").replace(" 0", " ")
        else:
            day = dt.strftime("%b %d, %Y").replace(" 0", " ")

    time = dt.strftime("%I:%M %p").lstrip("0")
    return f"{day} • {time}"


# ---------------- Lessons ----------------

def load_lessons():
    data_path = DATA_DIR / "lessons.json"
    with open(data_path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_lessons(data: dict):
    data_path = DATA_DIR / "lessons.json"
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def save_lessons(data: dict):
    data_path = DATA_DIR / "lessons.json"
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_language(lang_id: str):
    data = load_lessons()
    for lang in data["languages"]:
        if lang["id"] == lang_id:
            return lang
    return None


def get_lesson(lang_id: str, lesson_id: int):
    lang = get_language(lang_id)
    if not lang:
        return None
    for lesson in lang["lessons"]:
        if lesson["id"] == lesson_id:
            return lesson
    return None


def all_languages():
    return load_lessons()["languages"]


def parse_quiz_text(raw: str):
    questions = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 3:
            continue
        question, choices_raw, answer = parts
        choices = [c.strip() for c in choices_raw.split(",") if c.strip()]
        if len(choices) < 2:
            continue
        questions.append({"question": question, "choices": choices, "answer": answer})
    return questions


def quiz_to_text(quiz: list[dict]):
    lines = []
    for q in quiz:
        choices = ", ".join(q["choices"])
        lines.append(f"{q['question']} | {choices} | {q['answer']}")
    return "\n".join(lines)


def parse_quiz_text(raw: str):
    questions = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 3:
            continue
        question, choices_raw, answer = parts
        choices = [c.strip() for c in choices_raw.split(",") if c.strip()]
        if len(choices) < 2:
            continue
        questions.append({"question": question, "choices": choices, "answer": answer})
    return questions


# ---------------- Helpers ----------------

def require_login():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return None


def require_role(role: str):
    if session.get("role") != role:
        return redirect(url_for("login"))
    return None


def generate_code(length=6):
    letters = string.ascii_uppercase + string.digits
    return "".join(random.choice(letters) for _ in range(length))


def get_user(user_id: int):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return user


def get_student_progress(user_id: int, lang_id: str):
    conn = get_db()
    rows = conn.execute(
        "SELECT lesson_id FROM progress WHERE student_id = ? AND lesson_lang = ?",
        (user_id, lang_id),
    ).fetchall()
    conn.close()
    return {row["lesson_id"] for row in rows}


def get_total_xp(user_id: int):
    conn = get_db()
    total = conn.execute(
        "SELECT COALESCE(SUM(xp), 0) as total FROM progress WHERE student_id = ?",
        (user_id,),
    ).fetchone()["total"]
    conn.close()
    return total


def create_notification(user_id: int, title: str, body: str, classroom_id: int | None = None):
    conn = get_db()
    conn.execute(
        """
        INSERT INTO notifications (user_id, title, body, classroom_id, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, title, body, classroom_id, now_ts()),
    )
    conn.commit()
    conn.close()


def get_unread_notifications(user_id: int):
    conn = get_db()
    rows = conn.execute(
        """
        SELECT * FROM notifications
        WHERE user_id = ? AND is_read = 0
        ORDER BY created_at DESC
        LIMIT 3
        """,
        (user_id,),
    ).fetchall()
    conn.close()
    return rows


def create_stream_post(
    classroom_id: int,
    author_id: int,
    kind: str,
    title: str,
    body: str,
    audience: str = "class",
    student_id: int | None = None,
):
    conn = get_db()
    conn.execute(
        """
        INSERT INTO stream_posts (classroom_id, author_id, kind, title, body, audience, student_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (classroom_id, author_id, kind, title, body, audience, student_id, now_ts()),
    )
    conn.commit()
    conn.close()


def get_stream_posts_for_teacher(classroom_id: int):
    conn = get_db()
    rows = conn.execute(
        """
        SELECT p.*, u.name as author_name, c.name as classroom_name
        FROM stream_posts p
        JOIN users u ON u.id = p.author_id
        JOIN classrooms c ON c.id = p.classroom_id
        WHERE p.classroom_id = ?
        ORDER BY p.created_at DESC
        LIMIT 30
        """,
        (classroom_id,),
    ).fetchall()
    conn.close()
    return rows


def get_stream_posts_for_student(classroom_ids: list[int], student_id: int):
    if not classroom_ids:
        return []
    placeholders = ",".join("?" for _ in classroom_ids)
    conn = get_db()
    query = f"""
        SELECT p.*, u.name as author_name, c.name as classroom_name
        FROM stream_posts p
        JOIN users u ON u.id = p.author_id
        JOIN classrooms c ON c.id = p.classroom_id
        WHERE p.classroom_id IN ({placeholders})
          AND (p.audience = 'class' OR (p.audience = 'student' AND p.student_id = ?))
          AND NOT (p.kind = 'grade' AND p.audience = 'class')
        ORDER BY p.created_at DESC
        LIMIT 30
    """
    rows = conn.execute(query, (*classroom_ids, student_id)).fetchall()
    conn.close()
    return rows


def update_streak(user_id: int):
    today = date.today()
    conn = get_db()
    row = conn.execute(
        "SELECT streak_count, last_active_date FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()

    last_active = row["last_active_date"]
    streak = row["streak_count"]

    if last_active:
        last_date = date.fromisoformat(last_active)
    else:
        last_date = None

    if last_date == today:
        new_streak = streak
    elif last_date == (today - timedelta(days=1)):
        new_streak = streak + 1
    else:
        new_streak = 1

    conn.execute(
        "UPDATE users SET streak_count = ?, last_active_date = ? WHERE id = ?",
        (new_streak, today.isoformat(), user_id),
    )
    conn.commit()
    conn.close()


def ensure_assignment_submissions(assignment_id: int, classroom_id: int, lesson_lang: str, lesson_id: int):
    conn = get_db()
    students = conn.execute(
        "SELECT student_id FROM classroom_students WHERE classroom_id = ?",
        (classroom_id,),
    ).fetchall()

    for student in students:
        existing_progress = conn.execute(
            """
            SELECT score FROM progress
            WHERE student_id = ? AND lesson_lang = ? AND lesson_id = ?
            """,
            (student["student_id"], lesson_lang, lesson_id),
        ).fetchone()

        status = "completed" if existing_progress else "assigned"
        completed_at = now_ts() if existing_progress else None
        score = existing_progress["score"] if existing_progress else None

        conn.execute(
            """
            INSERT OR IGNORE INTO assignment_submissions
            (assignment_id, student_id, status, completed_at, score)
            VALUES (?, ?, ?, ?, ?)
            """,
            (assignment_id, student["student_id"], status, completed_at, score),
        )

    conn.commit()
    conn.close()


# ---------------- Auth ----------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        form_type = request.form.get("form_type")

        if form_type == "signup":
            name = request.form["name"].strip()
            username = request.form["username"].strip().lower()
            email = request.form["email"].strip().lower()
            password = request.form["password"]
            role = request.form["role"]
            avatar = request.form["avatar"]

            if not name or not username or not email or not password:
                flash("Please fill out all required fields.")
                return redirect(url_for("login"))

            conn = get_db()
            existing = conn.execute(
                "SELECT id FROM users WHERE username = ? OR email = ?",
                (username, email),
            ).fetchone()
            if existing:
                conn.close()
                flash("Username or email already exists. Please sign in.")
                return redirect(url_for("login"))

            conn.execute(
                """
                INSERT INTO users (name, username, email, password_hash, role, avatar, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    username,
                    email,
                    generate_password_hash(password, method="pbkdf2:sha256"),
                    role,
                    avatar,
                    now_ts(),
                ),
            )
            conn.commit()
            user_id = conn.execute(
                "SELECT id FROM users WHERE username = ?", (username,)
            ).fetchone()["id"]
            conn.close()

            session["user_id"] = user_id
            session["role"] = role
            session["name"] = name
            session["avatar"] = avatar

            if role == "Student" and session.get("pending_class_code"):
                code = session.pop("pending_class_code")
                return redirect(url_for("join_class_by_code", code=code))
            return redirect(url_for("student_home" if role == "Student" else "teacher_home"))

        if form_type == "signin":
            username = request.form["username"].strip().lower()
            password = request.form["password"]

            conn = get_db()
            user = conn.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()
            conn.close()

            if not user or not check_password_hash(user["password_hash"], password):
                flash("Invalid username or password.")
                return redirect(url_for("login"))

            session["user_id"] = user["id"]
            session["role"] = user["role"]
            session["name"] = user["name"]
            session["avatar"] = user["avatar"]

            if user["role"] == "Student" and session.get("pending_class_code"):
                code = session.pop("pending_class_code")
                return redirect(url_for("join_class_by_code", code=code))
            return redirect(url_for("student_home" if user["role"] == "Student" else "teacher_home"))

    return render_template("login.html")


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        if username == ADMIN_USERNAME.lower() and password == ADMIN_PASSWORD:
            session["user_id"] = "admin"
            session["role"] = "Admin"
            session["name"] = "Admin"
            session["avatar"] = None
            return redirect(url_for("admin_dashboard"))
        flash("Invalid admin credentials.")
        return redirect(url_for("admin_login"))
    return render_template("admin_login.html")


@app.route("/admin")
def admin_dashboard():
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))
    data = load_lessons()
    languages = data["languages"]
    return render_template("admin_dashboard.html", languages=languages)


@app.route("/admin/lesson/create", methods=["POST"])
def admin_create_lesson():
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))

    lang_id = request.form.get("lang_id")
    title = request.form.get("title", "").strip()
    xp = int(request.form.get("xp") or 100)
    reading = request.form.get("reading", "").strip()
    video_url = request.form.get("video_url", "").strip()
    quiz_text = request.form.get("quiz_text", "").strip()

    if not lang_id or not title or not reading or not quiz_text:
        flash("Please fill out language, title, reading, and quiz.")
        return redirect(url_for("admin_dashboard"))

    data = load_lessons()
    lang = next((l for l in data["languages"] if l["id"] == lang_id), None)
    if not lang:
        flash("Language not found.")
        return redirect(url_for("admin_dashboard"))

    quiz = parse_quiz_text(quiz_text)
    if not quiz:
        flash("Quiz format invalid. Use: Question | A,B,C,D | Answer")
        return redirect(url_for("admin_dashboard"))

    next_id = max([lesson["id"] for lesson in lang["lessons"]] + [0]) + 1

    lang["lessons"].append(
        {
            "id": next_id,
            "title": title,
            "xp": xp,
            "reading": reading,
            "video_url": video_url,
            "quiz": quiz,
        }
    )

    save_lessons(data)
    flash("Lesson added.")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/language/create", methods=["POST"])
def admin_create_language():
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))

    lang_id = request.form.get("lang_id", "").strip().lower()
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    enabled = bool(request.form.get("enabled"))

    if not lang_id or not name:
        flash("Language id and name are required.")
        return redirect(url_for("admin_dashboard"))

    data = load_lessons()
    if any(l["id"] == lang_id for l in data["languages"]):
        flash("Language id already exists.")
        return redirect(url_for("admin_dashboard"))

    data["languages"].append(
        {
            "id": lang_id,
            "name": name,
            "description": description or "New language track.",
            "enabled": enabled,
            "lessons": [],
        }
    )
    save_lessons(data)
    flash("Language added.")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/language/toggle", methods=["POST"])
def admin_toggle_language():
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))

    lang_id = request.form.get("lang_id")
    enabled = bool(request.form.get("enabled"))
    data = load_lessons()
    lang = next((l for l in data["languages"] if l["id"] == lang_id), None)
    if not lang:
        flash("Language not found.")
        return redirect(url_for("admin_dashboard"))

    lang["enabled"] = enabled
    save_lessons(data)
    flash("Language updated.")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/lesson/<lang_id>/<int:lesson_id>", methods=["GET", "POST"])
def admin_edit_lesson(lang_id, lesson_id):
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))

    data = load_lessons()
    lang = next((l for l in data["languages"] if l["id"] == lang_id), None)
    if not lang:
        flash("Language not found.")
        return redirect(url_for("admin_dashboard"))

    lesson = next((l for l in lang["lessons"] if l["id"] == lesson_id), None)
    if not lesson:
        flash("Lesson not found.")
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        xp = int(request.form.get("xp") or 100)
        reading = request.form.get("reading", "").strip()
        video_url = request.form.get("video_url", "").strip()
        quiz_text = request.form.get("quiz_text", "").strip()

        if not title or not reading or not quiz_text:
            flash("Please fill out title, reading, and quiz.")
            return redirect(url_for("admin_edit_lesson", lang_id=lang_id, lesson_id=lesson_id))

        quiz = parse_quiz_text(quiz_text)
        if not quiz:
            flash("Quiz format invalid. Use: Question | A,B,C,D | Answer")
            return redirect(url_for("admin_edit_lesson", lang_id=lang_id, lesson_id=lesson_id))

        lesson["title"] = title
        lesson["xp"] = xp
        lesson["reading"] = reading
        lesson["video_url"] = video_url
        lesson["quiz"] = quiz

        save_lessons(data)
        flash("Lesson updated.")
        return redirect(url_for("admin_dashboard"))

    return render_template(
        "admin_edit_lesson.html",
        lang=lang,
        lesson=lesson,
        quiz_text=quiz_to_text(lesson["quiz"]),
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------- Student ----------------
@app.route("/student/home")
def student_home():
    guard = require_login()
    if guard:
        return guard
    if require_role("Student"):
        return redirect(url_for("teacher_home"))

    languages = all_languages()
    user_id = session["user_id"]
    total_xp = get_total_xp(user_id)
    user = get_user(user_id)

    language_cards = []
    for lang in languages:
        total_lessons = len(lang["lessons"])
        completed = get_student_progress(user_id, lang["id"])
        percent = int((len(completed) / total_lessons) * 100) if total_lessons else 0
        language_cards.append(
            {
                "id": lang["id"],
                "name": lang["name"],
                "description": lang["description"],
                "enabled": lang.get("enabled", False),
                "percent": percent,
                "complete": percent == 100 and total_lessons > 0,
            }
        )

    badges = []
    conn = get_db()
    completed_total = len(
        conn.execute("SELECT id FROM progress WHERE student_id = ?", (user_id,)).fetchall()
    )
    conn.close()
    if completed_total >= 1:
        badges.append("First Lesson")
    if completed_total >= 3:
        badges.append("3 Lessons")
    if completed_total >= 5:
        badges.append("Python Explorer")

    notifications = get_unread_notifications(user_id)
    return render_template(
        "student_home.html",
        name=session.get("name"),
        languages=language_cards,
        total_xp=total_xp,
        streak=user["streak_count"],
        badges=badges,
        notifications=notifications,
    )


@app.route("/student/language/<lang_id>")
def student_language(lang_id):
    guard = require_login()
    if guard:
        return guard
    if require_role("Student"):
        return redirect(url_for("teacher_home"))

    lang = get_language(lang_id)
    if not lang or not lang.get("enabled", False):
        return redirect(url_for("student_home"))

    user_id = session["user_id"]
    completed = get_student_progress(user_id, lang_id)

    return render_template(
        "student_language.html",
        lang=lang,
        completed=completed,
        user_name=session.get("name"),
    )


@app.route("/student/language/<lang_id>/certificate")
def student_certificate(lang_id):
    guard = require_login()
    if guard:
        return guard
    if require_role("Student"):
        return redirect(url_for("teacher_home"))

    lang = get_language(lang_id)
    if not lang:
        return redirect(url_for("student_home"))

    user_id = session["user_id"]
    completed = get_student_progress(user_id, lang_id)
    if len(completed) != len(lang["lessons"]):
        return redirect(url_for("student_language", lang_id=lang_id))

    return render_template(
        "student_certificate.html",
        lang=lang,
        name=session.get("name"),
    )


@app.route("/student/lesson/<lang_id>/<int:lesson_id>")
def student_lesson(lang_id, lesson_id):
    guard = require_login()
    if guard:
        return guard
    if require_role("Student"):
        return redirect(url_for("teacher_home"))

    lang = get_language(lang_id)
    if not lang:
        return redirect(url_for("student_home"))

    user_id = session["user_id"]
    completed = get_student_progress(user_id, lang_id)
    next_unlock = len(completed) + 1
    if lesson_id > next_unlock and lesson_id not in completed:
        return redirect(url_for("student_language", lang_id=lang_id))

    lesson = get_lesson(lang_id, lesson_id)
    if not lesson:
        return redirect(url_for("student_language", lang_id=lang_id))

    conn = get_db()
    notes = conn.execute(
        """
        SELECT notes FROM lesson_notes
        WHERE student_id = ? AND lesson_id = ? AND lesson_lang = ?
        """,
        (user_id, lesson_id, lang_id),
    ).fetchone()
    conn.close()

    return render_template(
        "student_lesson.html",
        lesson=lesson,
        lang=lang,
        notes=notes["notes"] if notes else "",
        completed=lesson_id in completed,
        quiz_result=None,
    )


@app.route("/student/lesson/<lang_id>/<int:lesson_id>/notes", methods=["POST"])
def save_notes(lang_id, lesson_id):
    guard = require_login()
    if guard:
        return guard
    if require_role("Student"):
        return redirect(url_for("teacher_home"))

    notes = request.form.get("notes", "").strip()
    user_id = session["user_id"]
    conn = get_db()
    conn.execute(
        """
        INSERT INTO lesson_notes (student_id, lesson_id, lesson_lang, notes, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(student_id, lesson_id, lesson_lang)
        DO UPDATE SET notes = excluded.notes, updated_at = excluded.updated_at
        """,
        (user_id, lesson_id, lang_id, notes, now_ts()),
    )
    conn.commit()
    conn.close()
    flash("Notes saved.")
    return redirect(url_for("student_lesson", lang_id=lang_id, lesson_id=lesson_id))


@app.route("/student/lesson/<lang_id>/<int:lesson_id>/quiz", methods=["POST"])
def grade_quiz(lang_id, lesson_id):
    guard = require_login()
    if guard:
        return guard
    if require_role("Student"):
        return redirect(url_for("teacher_home"))

    lesson = get_lesson(lang_id, lesson_id)
    if not lesson:
        return redirect(url_for("student_home"))

    quiz = lesson["quiz"]
    total = len(quiz)
    correct_count = 0
    results = []

    for idx, question in enumerate(quiz):
        user_answer = request.form.get(f"q{idx}")
        is_correct = user_answer == question["answer"]
        results.append(
            {
                "question": question["question"],
                "your_answer": user_answer,
                "correct_answer": question["answer"],
                "correct": is_correct,
            }
        )
        if is_correct:
            correct_count += 1

    all_correct = correct_count == total
    score = int((correct_count / total) * 100)

    user_id = session["user_id"]
    completed = get_student_progress(user_id, lang_id)

    assignment_completed = False
    passing_score = 70
    passed = score >= passing_score
    assignment_completed = False

    if passed and lesson_id not in completed:
        conn = get_db()
        conn.execute(
            """
            INSERT INTO progress (student_id, lesson_id, lesson_lang, completed_at, score, xp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, lesson_id, lang_id, now_ts(), score, lesson.get("xp", 100)),
        )
        conn.commit()
        conn.close()

        update_streak(user_id)
        assignment_completed = _complete_assignment_if_any(user_id, lang_id, lesson_id, score)

    return render_template(
        "student_lesson.html",
        lesson=lesson,
        lang=get_language(lang_id),
        notes=request.form.get("notes", ""),
        completed=all_correct,
        quiz_result={
            "score": score,
            "results": results,
            "all_correct": passed,
            "passing_score": passing_score,
            "assignment_completed": assignment_completed,
        },
    )


def _complete_assignment_if_any(user_id: int, lang_id: str, lesson_id: int, score: int) -> bool:
    conn = get_db()
    submissions = conn.execute(
        """
        SELECT s.id FROM assignment_submissions s
        JOIN assignments a ON a.id = s.assignment_id
        JOIN classroom_students cs ON cs.classroom_id = a.classroom_id
        WHERE s.student_id = ?
        AND a.lesson_id = ?
        AND a.lesson_lang = ?
        AND s.status != 'completed'
        """,
        (user_id, lesson_id, lang_id),
    ).fetchall()

    updated = False
    for sub in submissions:
        conn.execute(
            """
            UPDATE assignment_submissions
            SET status = 'completed', completed_at = ?, score = ?
            WHERE id = ?
            """,
            (now_ts(), score, sub["id"]),
        )
        updated = True

    conn.commit()
    conn.close()
    return updated


@app.route("/student/classroom", methods=["GET", "POST"])
def student_classroom():
    guard = require_login()
    if guard:
        return guard
    if require_role("Student"):
        return redirect(url_for("teacher_home"))

    user_id = session["user_id"]

    if request.method == "POST":
        code = request.form.get("code", "").strip().upper()
        conn = get_db()
        classroom = conn.execute(
            "SELECT * FROM classrooms WHERE code = ?", (code,)
        ).fetchone()
        if not classroom:
            conn.close()
            flash("Classroom code not found.")
            return redirect(url_for("student_classroom"))

        conn.execute(
            """
            INSERT OR IGNORE INTO classroom_students (classroom_id, student_id, joined_at)
            VALUES (?, ?, ?)
            """,
            (classroom["id"], user_id, now_ts()),
        )
        conn.commit()

        # Backfill assignment status for any assignments already completed
        assignments = conn.execute(
            """
            SELECT id, lesson_lang, lesson_id FROM assignments
            WHERE classroom_id = ?
            """,
            (classroom["id"],),
        ).fetchall()

        for a in assignments:
            existing_progress = conn.execute(
                """
                SELECT score FROM progress
                WHERE student_id = ? AND lesson_lang = ? AND lesson_id = ?
                """,
                (user_id, a["lesson_lang"], a["lesson_id"]),
            ).fetchone()

            status = "completed" if existing_progress else "assigned"
            completed_at = now_ts() if existing_progress else None
            score = existing_progress["score"] if existing_progress else None

            conn.execute(
                """
                INSERT OR IGNORE INTO assignment_submissions
                (assignment_id, student_id, status, completed_at, score)
                VALUES (?, ?, ?, ?, ?)
                """,
                (a["id"], user_id, status, completed_at, score),
            )

        conn.commit()
        conn.close()
        flash("You joined the classroom!")
        return redirect(url_for("student_classroom"))

    conn = get_db()
    classrooms = conn.execute(
        """
        SELECT c.* FROM classrooms c
        JOIN classroom_students cs ON cs.classroom_id = c.id
        WHERE cs.student_id = ?
        """,
        (user_id,),
    ).fetchall()

    assignments = conn.execute(
        """
        SELECT a.*, s.status, s.score, s.grade_out_of_10, c.name as classroom_name
        FROM assignments a
        JOIN classroom_students cs ON cs.classroom_id = a.classroom_id
        JOIN classrooms c ON c.id = a.classroom_id
        LEFT JOIN assignment_submissions s
            ON s.assignment_id = a.id AND s.student_id = cs.student_id
        WHERE cs.student_id = ?
        ORDER BY a.created_at DESC
        """,
        (user_id,),
    ).fetchall()

    assignment_ids = [a["id"] for a in assignments]
    comments_by_assignment = {}
    if assignment_ids:
        placeholders = ",".join("?" for _ in assignment_ids)
        comment_rows = conn.execute(
            f"""
            SELECT assignment_id, author_role, body, created_at
            FROM assignment_comments
            WHERE student_id = ?
              AND assignment_id IN ({placeholders})
            ORDER BY created_at ASC
            """,
            (user_id, *assignment_ids),
        ).fetchall()

        for row in comment_rows:
            comments_by_assignment.setdefault(row["assignment_id"], []).append(dict(row))

    # Backfill assignment completion based on progress
    updated_assignments = []
    for a in assignments:
        status = a["status"]
        if status != "completed":
            existing_progress = conn.execute(
                """
                SELECT score FROM progress
                WHERE student_id = ? AND lesson_lang = ? AND lesson_id = ?
                """,
                (user_id, a["lesson_lang"], a["lesson_id"]),
            ).fetchone()

            if existing_progress:
                status = "completed"
                conn.execute(
                    """
                    INSERT INTO assignment_submissions
                    (assignment_id, student_id, status, completed_at, score)
                    VALUES (?, ?, 'completed', ?, ?)
                    ON CONFLICT(assignment_id, student_id)
                    DO UPDATE SET status = 'completed', completed_at = excluded.completed_at, score = excluded.score
                    """,
                    (a["id"], user_id, now_ts(), existing_progress["score"]),
                )

        updated_assignments.append({**dict(a), "status": status})

    conn.commit()
    conn.close()

    classroom_ids = [c["id"] for c in classrooms]
    stream_items = get_stream_posts_for_student(classroom_ids, user_id)

    return render_template(
        "student_classroom.html",
        classrooms=classrooms,
        assignments=updated_assignments,
        stream_items=stream_items,
        comments_by_assignment=comments_by_assignment,
    )


@app.route("/join/<code>")
def join_class_by_code(code):
    if "user_id" not in session:
        session["pending_class_code"] = code.upper()
        return redirect(url_for("login"))
    if session.get("role") != "Student":
        flash("Only students can join classrooms.")
        return redirect(url_for("teacher_home"))

    user_id = session["user_id"]
    code = code.upper()
    conn = get_db()
    classroom = conn.execute(
        "SELECT * FROM classrooms WHERE code = ?",
        (code,),
    ).fetchone()
    if not classroom:
        conn.close()
        flash("Classroom code not found.")
        return redirect(url_for("student_classroom"))

    conn.execute(
        """
        INSERT OR IGNORE INTO classroom_students (classroom_id, student_id, joined_at)
        VALUES (?, ?, ?)
        """,
        (classroom["id"], user_id, now_ts()),
    )
    conn.commit()

    assignments = conn.execute(
        """
        SELECT id, lesson_lang, lesson_id FROM assignments
        WHERE classroom_id = ?
        """,
        (classroom["id"],),
    ).fetchall()

    for a in assignments:
        existing_progress = conn.execute(
            """
            SELECT score FROM progress
            WHERE student_id = ? AND lesson_lang = ? AND lesson_id = ?
            """,
            (user_id, a["lesson_lang"], a["lesson_id"]),
        ).fetchone()

        status = "completed" if existing_progress else "assigned"
        completed_at = now_ts() if existing_progress else None
        score = existing_progress["score"] if existing_progress else None

        conn.execute(
            """
            INSERT OR IGNORE INTO assignment_submissions
            (assignment_id, student_id, status, completed_at, score)
            VALUES (?, ?, ?, ?, ?)
            """,
            (a["id"], user_id, status, completed_at, score),
        )

    conn.commit()
    conn.close()
    flash("You joined the classroom!")
    return redirect(url_for("student_classroom"))


@app.route("/student/assignment/<int:assignment_id>/comment", methods=["POST"])
def student_assignment_comment(assignment_id):
    guard = require_login()
    if guard:
        return guard
    if require_role("Student"):
        return redirect(url_for("teacher_home"))

    comment = request.form.get("comment", "").strip()
    if not comment:
        flash("Please add a comment.")
        return redirect(url_for("student_classroom"))

    conn = get_db()
    assignment = conn.execute(
        """
        SELECT a.classroom_id, c.teacher_id
        FROM assignments a
        JOIN classrooms c ON c.id = a.classroom_id
        WHERE a.id = ?
        """,
        (assignment_id,),
    ).fetchone()

    conn.execute(
        """
        INSERT INTO assignment_comments (assignment_id, student_id, author_role, body, created_at)
        VALUES (?, ?, 'student', ?, ?)
        """,
        (assignment_id, session["user_id"], comment, now_ts()),
    )
    conn.commit()
    conn.close()
    if assignment:
        create_notification(
            assignment["teacher_id"],
            "New student comment",
            "A student left a comment on an assignment.",
            classroom_id=assignment["classroom_id"],
        )
    flash("Comment sent to your teacher.")
    return redirect(url_for("student_classroom"))


@app.route("/teacher/assignment/<int:assignment_id>/comment", methods=["POST"])
def teacher_assignment_comment(assignment_id):
    guard = require_login()
    if guard:
        return guard
    if require_role("Teacher"):
        return redirect(url_for("student_home"))

    message = request.form.get("message", "").strip()
    student_id = request.form.get("student_id")
    if not message or not student_id:
        flash("Please write a response.")
        return redirect(request.referrer or url_for("teacher_home"))

    try:
        student_id_val = int(student_id)
    except ValueError:
        flash("Invalid student.")
        return redirect(request.referrer or url_for("teacher_home"))

    conn = get_db()
    assignment = conn.execute(
        """
        SELECT a.classroom_id, c.teacher_id
        FROM assignments a
        JOIN classrooms c ON c.id = a.classroom_id
        WHERE a.id = ?
        """,
        (assignment_id,),
    ).fetchone()

    if not assignment or assignment["teacher_id"] != session["user_id"]:
        conn.close()
        flash("Assignment not found.")
        return redirect(request.referrer or url_for("teacher_home"))

    conn.execute(
        """
        INSERT INTO assignment_comments (assignment_id, student_id, author_role, body, created_at)
        VALUES (?, ?, 'teacher', ?, ?)
        """,
        (assignment_id, student_id_val, message, now_ts()),
    )
    conn.commit()
    conn.close()

    create_notification(
        student_id_val,
        "Teacher replied",
        "Your teacher replied to your assignment comment.",
        classroom_id=assignment["classroom_id"],
    )

    flash("Reply sent.")
    return redirect(request.referrer or url_for("teacher_home"))


# ---------------- Teacher ----------------
@app.route("/teacher/home")
def teacher_home():
    guard = require_login()
    if guard:
        return guard
    if require_role("Teacher"):
        return redirect(url_for("student_home"))

    conn = get_db()
    classrooms = conn.execute(
        "SELECT * FROM classrooms WHERE teacher_id = ?",
        (session["user_id"],),
    ).fetchall()
    conn.close()

    notifications = get_unread_notifications(session["user_id"])
    return render_template(
        "teacher_home.html",
        name=session.get("name"),
        classrooms=classrooms,
        notifications=notifications,
    )


@app.route("/teacher/classroom/create", methods=["GET", "POST"])
def teacher_create_classroom():
    guard = require_login()
    if guard:
        return guard
    if require_role("Teacher"):
        return redirect(url_for("student_home"))

    if request.method == "POST":
        name = request.form["name"].strip()
        code = generate_code()
        conn = get_db()
        conn.execute(
            """
            INSERT INTO classrooms (teacher_id, name, code, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (session["user_id"], name, code, now_ts()),
        )
        conn.commit()
        conn.close()
        return redirect(url_for("teacher_home"))

    return render_template("teacher_create_classroom.html")


@app.route("/teacher/classroom/<int:classroom_id>")
def teacher_classroom(classroom_id):
    guard = require_login()
    if guard:
        return guard
    if require_role("Teacher"):
        return redirect(url_for("student_home"))

    conn = get_db()
    classroom = conn.execute(
        "SELECT * FROM classrooms WHERE id = ? AND teacher_id = ?",
        (classroom_id, session["user_id"]),
    ).fetchone()
    if not classroom:
        conn.close()
        return redirect(url_for("teacher_home"))

    teacher_classrooms = conn.execute(
        """
        SELECT id, name, code
        FROM classrooms
        WHERE teacher_id = ?
        ORDER BY created_at DESC
        """,
        (session["user_id"],),
    ).fetchall()

    students = conn.execute(
        """
        SELECT u.id, u.name, u.username
        FROM classroom_students cs
        JOIN users u ON u.id = cs.student_id
        WHERE cs.classroom_id = ?
        """,
        (classroom_id,),
    ).fetchall()

    assignments = conn.execute(
        """
        SELECT a.*, COUNT(s.id) as total_subs,
               SUM(CASE WHEN s.status = 'completed' THEN 1 ELSE 0 END) as completed_count
        FROM assignments a
        LEFT JOIN assignment_submissions s ON s.assignment_id = a.id
        WHERE a.classroom_id = ?
        GROUP BY a.id
        ORDER BY a.created_at DESC
        """,
        (classroom_id,),
    ).fetchall()

    assignment_ids = [a["id"] for a in assignments]
    comments_by_assignment = {}
    if assignment_ids:
        placeholders = ",".join("?" for _ in assignment_ids)
        comment_rows = conn.execute(
            f"""
            SELECT ac.assignment_id, ac.student_id, ac.author_role, ac.body, ac.created_at,
                   u.name, u.username
            FROM assignment_comments ac
            JOIN users u ON u.id = ac.student_id
            WHERE ac.assignment_id IN ({placeholders})
            ORDER BY ac.created_at ASC
            """,
            (*assignment_ids,),
        ).fetchall()

        for row in comment_rows:
            assignment_bucket = comments_by_assignment.setdefault(row["assignment_id"], {})
            student_bucket = assignment_bucket.setdefault(
                row["student_id"],
                {"student_id": row["student_id"], "name": row["name"], "username": row["username"], "thread": []},
            )
            student_bucket["thread"].append(
                {
                    "author_role": row["author_role"],
                    "body": row["body"],
                    "created_at": row["created_at"],
                }
            )

    submissions = conn.execute(
        """
        SELECT s.id as submission_id, s.status, s.score, s.grade_out_of_10,
               u.name, u.username, a.lesson_lang, a.lesson_id
        FROM assignment_submissions s
        JOIN users u ON u.id = s.student_id
        JOIN assignments a ON a.id = s.assignment_id
        WHERE a.classroom_id = ?
        ORDER BY s.id DESC
        """,
        (classroom_id,),
    ).fetchall()

    invites = conn.execute(
        """
        SELECT email, invited_at FROM classroom_invites
        WHERE classroom_id = ?
        ORDER BY invited_at DESC
        """,
        (classroom_id,),
    ).fetchall()

    conn.close()

    stream_items = get_stream_posts_for_teacher(classroom_id)

    return render_template(
        "teacher_classroom.html",
        classrooms=teacher_classrooms,
        classroom=classroom,
        students=students,
        assignments=assignments,
        submissions=submissions,
        invites=invites,
        comments_by_assignment=comments_by_assignment,
        stream_items=stream_items,
        languages=all_languages(),
    )


@app.route("/teacher/classroom/<int:classroom_id>/delete", methods=["POST"])
def teacher_delete_classroom(classroom_id):
    guard = require_login()
    if guard:
        return guard
    if require_role("Teacher"):
        return redirect(url_for("student_home"))

    conn = get_db()
    classroom = conn.execute(
        "SELECT * FROM classrooms WHERE id = ? AND teacher_id = ?",
        (classroom_id, session["user_id"]),
    ).fetchone()
    if not classroom:
        conn.close()
        flash("Classroom not found.")
        return redirect(url_for("teacher_home"))

    assignment_ids = conn.execute(
        "SELECT id FROM assignments WHERE classroom_id = ?",
        (classroom_id,),
    ).fetchall()
    for a in assignment_ids:
        conn.execute("DELETE FROM assignment_submissions WHERE assignment_id = ?", (a["id"],))

    conn.execute("DELETE FROM assignments WHERE classroom_id = ?", (classroom_id,))
    conn.execute("DELETE FROM classroom_students WHERE classroom_id = ?", (classroom_id,))
    conn.execute("DELETE FROM classroom_invites WHERE classroom_id = ?", (classroom_id,))
    conn.execute("DELETE FROM notifications WHERE classroom_id = ?", (classroom_id,))
    conn.execute("DELETE FROM classrooms WHERE id = ?", (classroom_id,))
    conn.commit()
    conn.close()

    flash("Classroom deleted.")
    return redirect(url_for("teacher_home"))


@app.route("/teacher/classroom/<int:classroom_id>/assignments/create", methods=["POST"])
def teacher_create_assignment(classroom_id):
    guard = require_login()
    if guard:
        return guard
    if require_role("Teacher"):
        return redirect(url_for("student_home"))

    lesson_key = request.form["lesson_key"]
    lesson_lang, lesson_id_str = lesson_key.split(":")
    lesson_id = int(lesson_id_str)
    due_date = request.form.get("due_date")
    comment = request.form.get("comment", "").strip()

    conn = get_db()
    classroom = conn.execute(
        "SELECT * FROM classrooms WHERE id = ? AND teacher_id = ?",
        (classroom_id, session["user_id"]),
    ).fetchone()

    if not classroom:
        conn.close()
        return redirect(url_for("teacher_home"))

    conn.execute(
        """
        INSERT INTO assignments (classroom_id, lesson_id, lesson_lang, due_date, comment, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (classroom_id, lesson_id, lesson_lang, due_date, comment, now_ts()),
    )
    conn.commit()
    assignment_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()

    ensure_assignment_submissions(assignment_id, classroom_id, lesson_lang, lesson_id)

    post_lines = [f"{lesson_lang.upper()} Lesson {lesson_id} has been posted."]
    if due_date:
        post_lines.append(f"Due: {due_date}")
    if comment:
        post_lines.append(f"Note: {comment}")
    create_stream_post(
        classroom_id=classroom_id,
        author_id=session["user_id"],
        kind="assignment",
        title="New assignment",
        body="\n".join(post_lines),
        audience="class",
    )

    conn = get_db()
    students = conn.execute(
        "SELECT student_id FROM classroom_students WHERE classroom_id = ?",
        (classroom_id,),
    ).fetchall()
    conn.close()

    for student in students:
        create_notification(
            student["student_id"],
            "New assignment posted",
            f"{lesson_lang.upper()} Lesson {lesson_id} is ready in {classroom['name']}.",
            classroom_id=classroom_id,
        )

    return redirect(url_for("teacher_classroom", classroom_id=classroom_id))


@app.route("/teacher/classroom/<int:classroom_id>/announce", methods=["POST"])
def teacher_post_announcement(classroom_id):
    guard = require_login()
    if guard:
        return guard
    if require_role("Teacher"):
        return redirect(url_for("student_home"))

    message = request.form.get("message", "").strip()
    if not message:
        flash("Please write an announcement.")
        return redirect(url_for("teacher_classroom", classroom_id=classroom_id))

    conn = get_db()
    classroom = conn.execute(
        "SELECT * FROM classrooms WHERE id = ? AND teacher_id = ?",
        (classroom_id, session["user_id"]),
    ).fetchone()
    if not classroom:
        conn.close()
        return redirect(url_for("teacher_home"))

    students = conn.execute(
        "SELECT student_id FROM classroom_students WHERE classroom_id = ?",
        (classroom_id,),
    ).fetchall()
    conn.close()

    create_stream_post(
        classroom_id=classroom_id,
        author_id=session["user_id"],
        kind="announcement",
        title="Announcement",
        body=message,
        audience="class",
    )

    for s in students:
        create_notification(
            s["student_id"],
            "New announcement",
            f"{classroom['name']}: {message}",
            classroom_id=classroom_id,
        )

    flash("Announcement posted.")
    return redirect(url_for("teacher_classroom", classroom_id=classroom_id))


@app.route("/teacher/classroom/<int:classroom_id>/invite", methods=["POST"])
def teacher_invite_student(classroom_id):
    guard = require_login()
    if guard:
        return guard
    if require_role("Teacher"):
        return redirect(url_for("student_home"))

    email = request.form.get("email", "").strip().lower()
    if not email:
        flash("Please add an email.")
        return redirect(url_for("teacher_classroom", classroom_id=classroom_id))

    conn = get_db()
    classroom = conn.execute(
        "SELECT id FROM classrooms WHERE id = ? AND teacher_id = ?",
        (classroom_id, session["user_id"]),
    ).fetchone()

    if not classroom:
        conn.close()
        return redirect(url_for("teacher_home"))

    conn.execute(
        """
        INSERT INTO classroom_invites (classroom_id, email, invited_at)
        VALUES (?, ?, ?)
        """,
        (classroom_id, email, now_ts()),
    )
    conn.commit()
    conn.close()

    flash("Invite saved. Share the class code with the student.")
    return redirect(url_for("teacher_classroom", classroom_id=classroom_id))


@app.route("/teacher/submission/<int:submission_id>/grade", methods=["POST"])
def teacher_grade_submission(submission_id):
    guard = require_login()
    if guard:
        return guard
    if require_role("Teacher"):
        return redirect(url_for("student_home"))

    grade = request.form.get("grade")
    try:
        grade_val = int(grade)
    except (TypeError, ValueError):
        flash("Grade must be a number 0-10.")
        return redirect(request.referrer or url_for("teacher_home"))

    if grade_val < 0 or grade_val > 10:
        flash("Grade must be between 0 and 10.")
        return redirect(request.referrer or url_for("teacher_home"))

    conn = get_db()
    submission = conn.execute(
        """
        SELECT s.student_id, a.lesson_lang, a.lesson_id, a.classroom_id
        FROM assignment_submissions s
        JOIN assignments a ON a.id = s.assignment_id
        WHERE s.id = ?
        """,
        (submission_id,),
    ).fetchone()

    if not submission:
        conn.close()
        flash("Submission not found.")
        return redirect(request.referrer or url_for("teacher_home"))

    conn.execute(
        "UPDATE assignment_submissions SET grade_out_of_10 = ? WHERE id = ?",
        (grade_val, submission_id),
    )
    conn.commit()
    conn.close()

    create_notification(
        submission["student_id"],
        "Assignment graded",
        f"{submission['lesson_lang'].upper()} Lesson {submission['lesson_id']} graded: {grade_val}/10.",
        classroom_id=submission["classroom_id"],
    )

    create_stream_post(
        classroom_id=submission["classroom_id"],
        author_id=session["user_id"],
        kind="grade",
        title="Grade posted",
        body=f"{submission['lesson_lang'].upper()} Lesson {submission['lesson_id']}: {grade_val}/10",
        audience="student",
        student_id=submission["student_id"],
    )

    flash("Grade saved.")
    return redirect(request.referrer or url_for("teacher_home"))


@app.route("/notifications/read", methods=["POST"])
def mark_notifications_read():
    guard = require_login()
    if guard:
        return guard
    conn = get_db()
    conn.execute(
        "UPDATE notifications SET is_read = 1 WHERE user_id = ?",
        (session["user_id"],),
    )
    conn.commit()
    conn.close()
    return redirect(request.referrer or url_for("student_home"))


# ---------------- Reach Out ----------------
@app.route("/reach-out", methods=["GET", "POST"])
def reach_out():
    guard = require_login()
    if guard:
        return guard

    if request.method == "POST":
        message = request.form["message"].strip()
        photo_url = request.form.get("photo_url", "").strip()
        user_id = session.get("user_id")
        role = session.get("role")

        if not message:
            flash("Please add a message.")
            return redirect(url_for("reach_out"))

        conn = get_db()
        conn.execute(
            """
            INSERT INTO reach_out (user_id, role, message, photo_url, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, role, message, photo_url or None, now_ts()),
        )
        conn.commit()
        conn.close()

        # Optional email send (Gmail App Password)
        if GMAIL_USER and GMAIL_APP_PASS:
            try:
                import smtplib
                from email.message import EmailMessage

                msg = EmailMessage()
                msg["Subject"] = "CodeCourse Reach Out"
                msg["From"] = GMAIL_USER
                msg["To"] = SUPPORT_EMAIL
                msg.set_content(
                    f"From: {session.get('name')} ({role})\n"
                    f"Email: {get_user(user_id)['email'] if user_id else 'N/A'}\n\n"
                    f"Message:\n{message}\n\n"
                    f"Photo URL: {photo_url or 'N/A'}"
                )

                with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
                    smtp.login(GMAIL_USER, GMAIL_APP_PASS)
                    smtp.send_message(msg)
            except Exception:
                flash("Message saved, but email sending is not configured yet.")
        else:
            flash("Message saved. Email sending is not configured yet.")

        flash("Thanks! Your message was sent.")
        return redirect(url_for("reach_out"))

    return render_template("reach_out.html")


DATA_DIR.mkdir(exist_ok=True)
init_db()
migrate_db()

if __name__ == "__main__":
    app.run(debug=True)

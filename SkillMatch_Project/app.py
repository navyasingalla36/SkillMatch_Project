import os
import sqlite3
from datetime import datetime
from functools import wraps

from flask import (Flask, abort, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from recommender import rank_jobs

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "instance", "skillmatch.db")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@skillmatch.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@123")  # demo only

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    education TEXT DEFAULT '',
    skills TEXT DEFAULT '',
    bio TEXT DEFAULT '',
    is_admin INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT NOT NULL,
    skills TEXT NOT NULL,
    description TEXT NOT NULL,
    posted_on TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    status TEXT DEFAULT 'Applied',
    applied_on TEXT NOT NULL,
    UNIQUE(user_id, job_id)
);
"""

SAMPLE_JOBS = [
    ("Python Developer", "DataBridge Labs", "Remote", "Python, Flask, SQL, REST API, Git",
     "Build and maintain Flask services and REST APIs for a data platform."),
    ("Java Full Stack Developer", "NimbusSoft", "Hyderabad", "Java, JSP, JDBC, SQL, HTML, CSS, JavaScript",
     "Develop web modules using Java, JSP and JDBC with an Oracle or MySQL backend."),
    ("Frontend Developer", "PixelCraft Studio", "Bengaluru", "HTML, CSS, JavaScript, React, Git",
     "Create responsive user interfaces and reusable components with React."),
    ("Data Analyst", "InsightWorks", "Remote", "Python, SQL, Excel, Pandas, Data Visualization",
     "Analyse business data, build dashboards and present insights to stakeholders."),
    ("Machine Learning Engineer", "NeuralNest", "Pune", "Python, Machine Learning, Scikit-learn, Pandas, NumPy, SQL",
     "Train, evaluate and deploy machine learning models for recommendation systems."),
    ("Backend Developer (Node.js)", "CloudForge", "Chennai", "JavaScript, Node.js, MongoDB, REST API, Git",
     "Design scalable REST APIs and database schemas using Node.js and MongoDB."),
    ("Software Test Engineer", "QualityFirst", "Visakhapatnam", "Java, Selenium, SQL, Testing, Git",
     "Write automated test suites and report defects for web applications."),
]


def today():
    return datetime.now().strftime("%d %b %Y")


def get_db():
    if "db" not in g:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript(SCHEMA)
    if not db.execute("SELECT 1 FROM users WHERE email=?", (ADMIN_EMAIL,)).fetchone():
        db.execute("INSERT INTO users (name, email, password_hash, is_admin) VALUES (?,?,?,1)",
                   ("Administrator", ADMIN_EMAIL, generate_password_hash(ADMIN_PASSWORD)))
    if db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0:
        db.executemany("INSERT INTO jobs (title, company, location, skills, description, posted_on) "
                       "VALUES (?,?,?,?,?,?)", [j + (today(),) for j in SAMPLE_JOBS])
    db.commit()


@app.before_request
def load_user():
    uid = session.get("user_id")
    g.user = get_db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone() if uid else None


def login_required(view):
    @wraps(view)
    def wrapper(*a, **kw):
        if g.user is None:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return view(*a, **kw)
    return wrapper


def admin_required(view):
    @wraps(view)
    def wrapper(*a, **kw):
        if g.user is None:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        if not g.user["is_admin"]:
            flash("Admin access only.", "danger")
            return redirect(url_for("dashboard"))
        return view(*a, **kw)
    return wrapper


def user_skills():
    return (g.user["skills"] or "") if g.user else ""


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or not email or len(password) < 6:
            flash("Enter your name, a valid email and a password of at least 6 characters.", "danger")
        elif get_db().execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            flash("An account with this email already exists.", "danger")
        else:
            db = get_db()
            cur = db.execute("INSERT INTO users (name, email, password_hash) VALUES (?,?,?)",
                             (name, email, generate_password_hash(password)))
            db.commit()
            session.clear()
            session["user_id"] = cur.lastrowid
            flash("Account created. Add your skills to get recommendations.", "success")
            return redirect(url_for("profile"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            flash(f"Welcome back, {user['name']}!", "success")
            return redirect(url_for("admin" if user["is_admin"] else "dashboard"))
        flash("Invalid email or password.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    jobs = db.execute("SELECT * FROM jobs").fetchall()
    has_skills = bool(user_skills().strip())
    ranked = rank_jobs(user_skills(), jobs) if has_skills else []
    app_count = db.execute("SELECT COUNT(*) FROM applications WHERE user_id=?", (g.user["id"],)).fetchone()[0]
    skill_count = len([s for s in user_skills().split(",") if s.strip()])
    return render_template("dashboard.html", results=ranked[:4], show_scores=has_skills,
                           skill_count=skill_count, app_count=app_count, job_count=len(jobs),
                           best=ranked[0]["score"] if ranked else 0)


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Name cannot be empty.", "danger")
        else:
            db = get_db()
            db.execute("UPDATE users SET name=?, education=?, skills=?, bio=? WHERE id=?",
                       (name, request.form.get("education", "").strip(),
                        request.form.get("skills", "").strip(),
                        request.form.get("bio", "").strip(), g.user["id"]))
            db.commit()
            flash("Profile updated.", "success")
            return redirect(url_for("profile"))
    return render_template("profile.html")


@app.route("/jobs")
def jobs():
    q = request.args.get("q", "").strip()
    loc = request.args.get("location", "").strip()
    sql, params = "SELECT * FROM jobs WHERE 1=1", []
    if q:
        sql += " AND (title LIKE ? OR company LIKE ? OR skills LIKE ?)"
        params += [f"%{q}%"] * 3
    if loc:
        sql += " AND location LIKE ?"
        params.append(f"%{loc}%")
    rows = get_db().execute(sql + " ORDER BY id DESC", params).fetchall()
    show_scores = bool(user_skills().strip())
    results = rank_jobs(user_skills(), rows)
    if not show_scores:
        results = [{"job": r, "score": 0, "matched": [], "missing": []} for r in rows]
    return render_template("jobs.html", results=results, show_scores=show_scores, q=q, location=loc)


@app.route("/jobs/<int:job_id>")
def job_details(job_id):
    db = get_db()
    job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if job is None:
        abort(404)
    ranked = rank_jobs(user_skills(), db.execute("SELECT * FROM jobs").fetchall())
    r = next(x for x in ranked if x["job"]["id"] == job_id)
    applied = bool(g.user and db.execute("SELECT 1 FROM applications WHERE user_id=? AND job_id=?",
                                         (g.user["id"], job_id)).fetchone())
    return render_template("job_details.html", job=job, r=r, applied=applied,
                           show_scores=bool(user_skills().strip()))


@app.route("/apply/<int:job_id>", methods=["POST"])
@login_required
def apply(job_id):
    db = get_db()
    if not db.execute("SELECT 1 FROM jobs WHERE id=?", (job_id,)).fetchone():
        abort(404)
    cur = db.execute("INSERT OR IGNORE INTO applications (user_id, job_id, applied_on) VALUES (?,?,?)",
                     (g.user["id"], job_id, today()))
    db.commit()
    flash("Application recorded." if cur.rowcount else "You have already applied to this job.",
          "success" if cur.rowcount else "info")
    return redirect(url_for("job_details", job_id=job_id))


@app.route("/applications")
@login_required
def applications():
    rows = get_db().execute(
        "SELECT a.*, j.title, j.company, j.location FROM applications a "
        "JOIN jobs j ON j.id = a.job_id WHERE a.user_id=? ORDER BY a.id DESC", (g.user["id"],)).fetchall()
    return render_template("applications.html", apps=rows)


@app.route("/admin", methods=["GET", "POST"])
@admin_required
def admin():
    db = get_db()
    if request.method == "POST":
        f = {k: request.form.get(k, "").strip() for k in ("title", "company", "location", "skills", "description")}
        if all(f.values()):
            db.execute("INSERT INTO jobs (title, company, location, skills, description, posted_on) "
                       "VALUES (?,?,?,?,?,?)", (f["title"], f["company"], f["location"], f["skills"],
                                                f["description"], today()))
            db.commit()
            flash("Job added.", "success")
        else:
            flash("Please fill in every field.", "danger")
        return redirect(url_for("admin"))
    return render_template("admin.html", jobs=db.execute("SELECT * FROM jobs ORDER BY id DESC").fetchall())


@app.route("/admin/delete/<int:job_id>", methods=["POST"])
@admin_required
def delete_job(job_id):
    db = get_db()
    db.execute("DELETE FROM jobs WHERE id=?", (job_id,))
    db.commit()
    flash("Job deleted.", "info")
    return redirect(url_for("admin"))


@app.errorhandler(404)
def not_found(_e):
    return render_template("404.html"), 404


with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(debug=True)

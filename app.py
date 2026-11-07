"""
app.py - Flask backend for the Smart Attendance Analyser.

Run:  python app.py   (then open http://127.0.0.1:5000)
Demo login created on first run: username 'admin' / password 'admin123'
"""
import csv
import io
import os
import re
import sqlite3
from datetime import date as _date
from functools import wraps

from flask import (Flask, Response, g, jsonify, request, send_from_directory,
                   session)
from werkzeug.security import check_password_hash, generate_password_hash

import analysis

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    roll_no TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    class_name TEXT NOT NULL DEFAULT 'BCA VI Sem'
);
CREATE TABLE IF NOT EXISTS subjects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    att_date TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('P','A')),
    UNIQUE (student_id, subject_id, att_date)
);
"""

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def create_app(db_path=None):
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-in-production")
    app.config["DB_PATH"] = db_path or os.path.join(BASE_DIR, "attendance.db")

    # ---------------------------------------------------------- database
    def get_db():
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DB_PATH"])
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    @app.teardown_appcontext
    def close_db(_exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    def init_db():
        db = sqlite3.connect(app.config["DB_PATH"])
        db.executescript(SCHEMA)
        if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            db.execute("INSERT INTO users (username, password_hash) VALUES (?,?)",
                       ("admin", generate_password_hash("admin123")))
        db.commit()
        db.close()

    init_db()

    # -------------------------------------------------------------- auth
    def login_required(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if "user" not in session:
                return jsonify(error="Please log in first."), 401
            return fn(*a, **kw)
        return wrapper

    @app.route("/")
    def index():
        return send_from_directory(os.path.join(BASE_DIR, "static"), "index.html")

    @app.post("/api/login")
    def login():
        data = request.get_json(silent=True) or {}
        username = str(data.get("username", "")).strip()
        password = str(data.get("password", ""))
        row = get_db().execute("SELECT * FROM users WHERE username=?",
                               (username,)).fetchone()
        if not row or not check_password_hash(row["password_hash"], password):
            return jsonify(error="Invalid username or password."), 401
        session["user"] = row["username"]
        return jsonify(user=row["username"])

    @app.post("/api/logout")
    def logout():
        session.clear()
        return jsonify(ok=True)

    @app.get("/api/me")
    def me():
        return jsonify(user=session.get("user"))

    # ---------------------------------------------------------- students
    @app.get("/api/students")
    @login_required
    def list_students():
        rows = get_db().execute(
            "SELECT id, roll_no, name, class_name FROM students ORDER BY roll_no").fetchall()
        return jsonify([dict(r) for r in rows])

    @app.post("/api/students")
    @login_required
    def add_student():
        d = request.get_json(silent=True) or {}
        roll = str(d.get("roll_no", "")).strip()
        name = str(d.get("name", "")).strip()
        cls = str(d.get("class_name", "BCA VI Sem")).strip() or "BCA VI Sem"
        if not roll or not name:
            return jsonify(error="Roll number and name are required."), 400
        try:
            cur = get_db().execute(
                "INSERT INTO students (roll_no, name, class_name) VALUES (?,?,?)",
                (roll, name, cls))
            get_db().commit()
        except sqlite3.IntegrityError:
            return jsonify(error="A student with this roll number already exists."), 409
        return jsonify(id=cur.lastrowid), 201

    @app.delete("/api/students/<int:sid>")
    @login_required
    def delete_student(sid):
        cur = get_db().execute("DELETE FROM students WHERE id=?", (sid,))
        get_db().commit()
        if cur.rowcount == 0:
            return jsonify(error="Student not found."), 404
        return jsonify(ok=True)

    # ---------------------------------------------------------- subjects
    @app.get("/api/subjects")
    @login_required
    def list_subjects():
        rows = get_db().execute("SELECT id, code, name FROM subjects ORDER BY code").fetchall()
        return jsonify([dict(r) for r in rows])

    @app.post("/api/subjects")
    @login_required
    def add_subject():
        d = request.get_json(silent=True) or {}
        code = str(d.get("code", "")).strip()
        name = str(d.get("name", "")).strip()
        if not code or not name:
            return jsonify(error="Subject code and name are required."), 400
        try:
            cur = get_db().execute("INSERT INTO subjects (code, name) VALUES (?,?)",
                                   (code, name))
            get_db().commit()
        except sqlite3.IntegrityError:
            return jsonify(error="A subject with this code already exists."), 409
        return jsonify(id=cur.lastrowid), 201

    # -------------------------------------------------------- attendance
    @app.get("/api/attendance")
    @login_required
    def get_attendance():
        subject_id = request.args.get("subject_id", type=int)
        att_date = request.args.get("date", "")
        if not subject_id or not DATE_RE.match(att_date):
            return jsonify(error="subject_id and date (YYYY-MM-DD) are required."), 400
        rows = get_db().execute(
            """SELECT s.id AS student_id, s.roll_no, s.name, a.status
               FROM students s
               LEFT JOIN attendance a ON a.student_id = s.id
                    AND a.subject_id = ? AND a.att_date = ?
               ORDER BY s.roll_no""", (subject_id, att_date)).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.post("/api/attendance")
    @login_required
    def save_attendance():
        d = request.get_json(silent=True) or {}
        subject_id = d.get("subject_id")
        att_date = str(d.get("date", ""))
        records = d.get("records")
        if not isinstance(subject_id, int) or not DATE_RE.match(att_date) \
                or not isinstance(records, list) or not records:
            return jsonify(error="Invalid attendance data."), 400
        try:
            parsed = _date.fromisoformat(att_date)
        except ValueError:
            return jsonify(error="Invalid date."), 400
        if parsed > _date.today():
            return jsonify(error="Attendance cannot be marked for a future date."), 400
        db = get_db()
        if not db.execute("SELECT 1 FROM subjects WHERE id=?", (subject_id,)).fetchone():
            return jsonify(error="Subject not found."), 404
        for r in records:
            if r.get("status") not in ("P", "A") or not isinstance(r.get("student_id"), int):
                return jsonify(error="Each record needs student_id and status P or A."), 400
        db.executemany(
            """INSERT INTO attendance (student_id, subject_id, att_date, status)
               VALUES (?,?,?,?)
               ON CONFLICT(student_id, subject_id, att_date)
               DO UPDATE SET status = excluded.status""",
            [(r["student_id"], subject_id, att_date, r["status"]) for r in records])
        db.commit()
        return jsonify(saved=len(records))

    # ---------------------------------------------------------- analysis
    def _summary_rows():
        db = get_db()
        subjects = [dict(r) for r in db.execute("SELECT id, code, name FROM subjects ORDER BY code")]
        students = [dict(r) for r in db.execute(
            "SELECT id, roll_no, name FROM students ORDER BY roll_no")]
        rows = db.execute("SELECT student_id, subject_id, status FROM attendance").fetchall()
        summ = analysis.student_summary(
            [(r["student_id"], r["subject_id"], r["status"]) for r in rows],
            [s["id"] for s in subjects])
        out = []
        for st in students:
            s = summ.get(st["id"])
            if s is None:
                out.append({**st, "present": 0, "total": 0, "pct": 0.0,
                            "status": "No Data", "needed": 0, "subjects": {}})
            else:
                out.append({**st, "present": s["present"], "total": s["total"],
                            "pct": s["pct"], "status": s["status"], "needed": s["needed"],
                            "subjects": {str(k): v[2] for k, v in s["per_subject"].items()}})
        return subjects, out

    @app.get("/api/analysis/summary")
    @login_required
    def analysis_summary():
        subjects, students = _summary_rows()
        with_data = [s for s in students if s["total"] > 0]
        avg = round(sum(s["pct"] for s in with_data) / len(with_data), 2) if with_data else 0.0
        counts = {"Good": 0, "At Risk": 0, "Shortage": 0, "No Data": 0}
        for s in students:
            counts[s["status"]] += 1
        return jsonify(subjects=subjects, students=students,
                       average=avg, counts=counts,
                       limit=analysis.SHORTAGE_LIMIT)

    @app.get("/api/analysis/trend")
    @login_required
    def analysis_trend():
        subject_id = request.args.get("subject_id", type=int)
        sql = "SELECT att_date, status FROM attendance"
        args = ()
        if subject_id:
            sql += " WHERE subject_id = ?"
            args = (subject_id,)
        rows = get_db().execute(sql, args).fetchall()
        trend = analysis.daily_trend([(r["att_date"], r["status"]) for r in rows])
        return jsonify([{"date": d, "present": p, "total": t, "pct": pc}
                        for d, p, t, pc in trend])

    @app.get("/api/export.csv")
    @login_required
    def export_csv():
        subjects, students = _summary_rows()
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Roll No", "Name"] + [s["code"] for s in subjects]
                   + ["Present", "Total", "Overall %", "Status"])
        for st in students:
            w.writerow([st["roll_no"], st["name"]]
                       + [st["subjects"].get(str(s["id"]), "") for s in subjects]
                       + [st["present"], st["total"], st["pct"], st["status"]])
        return Response(buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=attendance_report.csv"})

    return app


if __name__ == "__main__":
    create_app().run(debug=False, host="127.0.0.1", port=5000)

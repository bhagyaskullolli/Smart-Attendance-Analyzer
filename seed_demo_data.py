"""
seed_demo_data.py - Fills the database with SAMPLE (fictional) data so the
application can be demonstrated. Names below are made up for demonstration.

Usage:  python seed_demo_data.py [path_to_db]
"""
import os
import random
import sqlite3
import sys
from datetime import date, timedelta

import app as app_module

SAMPLE_STUDENTS = [
    ("001", "Anjali Patil"), ("002", "Bhavana Kulkarni"), ("003", "Chaitra Naik"),
    ("004", "Deepa Hegde"), ("005", "Divya Joshi"), ("006", "Gouri Desai"),
    ("007", "Kavya Shetty"), ("008", "Lakshmi Rao"), ("009", "Meghana Gowda"),
    ("010", "Nandini Bhat"), ("011", "Pooja Kamble"), ("012", "Rashmi Hiremath"),
    ("013", "Sahana Pujari"), ("014", "Shruti Mane"), ("015", "Sneha Jadhav"),
    ("016", "Sunitha Reddy"), ("017", "Tejaswini Kori"), ("018", "Vidya Math"),
    ("019", "Yashoda Badiger"), ("020", "Zeenat Mulla"),
]

SAMPLE_SUBJECTS = [
    ("BCA601", "Web Programming"), ("BCA602", "Software Engineering"),
    ("BCA603", "Computer Networks"), ("BCA604", "Python Programming"),
    ("BCA605", "Project Work"),
]


def main(db_path):
    app_module.create_app(db_path)          # creates tables + admin user
    db = sqlite3.connect(db_path)
    if db.execute("SELECT COUNT(*) FROM students").fetchone()[0]:
        print("Database already has data - nothing seeded.")
        return
    random.seed(2026)
    db.executemany("INSERT INTO students (roll_no, name) VALUES (?,?)", SAMPLE_STUDENTS)
    db.executemany("INSERT INTO subjects (code, name) VALUES (?,?)", SAMPLE_SUBJECTS)
    students = db.execute("SELECT id FROM students").fetchall()
    subjects = db.execute("SELECT id FROM subjects").fetchall()

    # each student gets a personal "attendance tendency" so the data is varied
    tendency = {s[0]: random.choice([0.95, 0.9, 0.85, 0.8, 0.72, 0.65]) for s in students}

    day = date(2026, 9, 1)
    end = date(2026, 10, 30)
    rows = []
    while day <= end:
        if day.weekday() < 5:               # Monday-Friday
            for sub in subjects:
                if random.random() < 0.6:   # not every subject meets every day
                    for st in students:
                        status = "P" if random.random() < tendency[st[0]] else "A"
                        rows.append((st[0], sub[0], day.isoformat(), status))
        day += timedelta(days=1)
    db.executemany("INSERT INTO attendance (student_id, subject_id, att_date, status) "
                   "VALUES (?,?,?,?)", rows)
    db.commit()
    db.close()
    print(f"Seeded {len(SAMPLE_STUDENTS)} students, {len(SAMPLE_SUBJECTS)} subjects, "
          f"{len(rows)} attendance records.")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "attendance.db")
    main(path)

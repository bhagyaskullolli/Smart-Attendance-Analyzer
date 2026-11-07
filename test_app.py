"""
test_app.py - Automated tests for the Smart Attendance Analyser.
Run:  python -m unittest -v test_app
"""
import os
import tempfile
import unittest
from datetime import date, timedelta

import analysis
from app import create_app


class AnalysisTests(unittest.TestCase):
    def test_percentage_normal(self):
        self.assertEqual(analysis.percentage(18, 24), 75.0)

    def test_percentage_zero_total(self):
        self.assertEqual(analysis.percentage(0, 0), 0.0)

    def test_percentage_rounding(self):
        self.assertEqual(analysis.percentage(1, 3), 33.33)

    def test_classify_boundaries(self):
        self.assertEqual(analysis.classify(74.99, 10), "Shortage")
        self.assertEqual(analysis.classify(75.0, 10), "At Risk")
        self.assertEqual(analysis.classify(79.99, 10), "At Risk")
        self.assertEqual(analysis.classify(80.0, 10), "Good")
        self.assertEqual(analysis.classify(0.0, 0), "No Data")

    def test_classes_needed(self):
        # 12 present of 20 = 60%; need x with (12+x)/(20+x) >= 0.75 -> x = 12
        self.assertEqual(analysis.classes_needed(12, 20), 12)
        self.assertEqual(analysis.classes_needed(15, 20), 0)

    def test_classes_needed_really_reaches_target(self):
        for present, total in [(5, 12), (13, 30), (7, 40)]:
            x = analysis.classes_needed(present, total)
            self.assertGreaterEqual((present + x) * 100.0 / (total + x), 75.0)
            if x > 0:
                self.assertLess((present + x - 1) * 100.0 / (total + x - 1), 75.0)

    def test_student_summary(self):
        rows = [(1, 10, "P"), (1, 10, "A"), (1, 11, "P"), (1, 11, "P")]
        res = analysis.student_summary(rows, [10, 11])
        self.assertEqual(res[1]["present"], 3)
        self.assertEqual(res[1]["total"], 4)
        self.assertEqual(res[1]["pct"], 75.0)
        self.assertEqual(res[1]["per_subject"][10], (1, 2, 50.0))

    def test_daily_trend_sorted(self):
        rows = [("2026-09-02", "P"), ("2026-09-01", "A"), ("2026-09-01", "P")]
        self.assertEqual(analysis.daily_trend(rows),
                         [("2026-09-01", 1, 2, 50.0), ("2026-09-02", 1, 1, 100.0)])


class ApiTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.app = create_app(self.path)
        self.client = self.app.test_client()

    def tearDown(self):
        os.remove(self.path)

    def login(self, user="admin", pw="admin123"):
        return self.client.post("/api/login", json={"username": user, "password": pw})

    def test_login_success_and_failure(self):
        self.assertEqual(self.login().status_code, 200)
        self.client.post("/api/logout")
        self.assertEqual(self.login(pw="wrong").status_code, 401)
        self.assertEqual(self.login(user="nobody").status_code, 401)

    def test_protected_routes_need_login(self):
        for url in ["/api/students", "/api/subjects", "/api/analysis/summary", "/api/export.csv"]:
            self.assertEqual(self.client.get(url).status_code, 401, url)

    def test_add_student_validation_and_duplicate(self):
        self.login()
        self.assertEqual(self.client.post("/api/students", json={"roll_no": "", "name": "A"}).status_code, 400)
        self.assertEqual(self.client.post("/api/students", json={"roll_no": "1", "name": "A"}).status_code, 201)
        self.assertEqual(self.client.post("/api/students", json={"roll_no": "1", "name": "B"}).status_code, 409)

    def _setup_class(self):
        self.login()
        a = self.client.post("/api/students", json={"roll_no": "1", "name": "Student One"}).get_json()["id"]
        b = self.client.post("/api/students", json={"roll_no": "2", "name": "Student Two"}).get_json()["id"]
        s = self.client.post("/api/subjects", json={"code": "S1", "name": "Subject"}).get_json()["id"]
        return a, b, s

    def test_mark_and_update_attendance(self):
        a, b, s = self._setup_class()
        d = (date.today() - timedelta(days=1)).isoformat()
        r = self.client.post("/api/attendance", json={"subject_id": s, "date": d,
            "records": [{"student_id": a, "status": "P"}, {"student_id": b, "status": "A"}]})
        self.assertEqual(r.status_code, 200)
        # re-saving the same day must UPDATE, not duplicate
        self.client.post("/api/attendance", json={"subject_id": s, "date": d,
            "records": [{"student_id": b, "status": "P"}]})
        rows = self.client.get(f"/api/attendance?subject_id={s}&date={d}").get_json()
        self.assertEqual([x["status"] for x in rows], ["P", "P"])

    def test_future_date_rejected(self):
        a, b, s = self._setup_class()
        d = (date.today() + timedelta(days=3)).isoformat()
        r = self.client.post("/api/attendance", json={"subject_id": s, "date": d,
            "records": [{"student_id": a, "status": "P"}]})
        self.assertEqual(r.status_code, 400)

    def test_invalid_status_rejected(self):
        a, b, s = self._setup_class()
        d = (date.today() - timedelta(days=1)).isoformat()
        r = self.client.post("/api/attendance", json={"subject_id": s, "date": d,
            "records": [{"student_id": a, "status": "X"}]})
        self.assertEqual(r.status_code, 400)

    def test_summary_and_shortage(self):
        a, b, s = self._setup_class()
        for i in range(1, 5):
            d = (date.today() - timedelta(days=i)).isoformat()
            self.client.post("/api/attendance", json={"subject_id": s, "date": d, "records": [
                {"student_id": a, "status": "P"},
                {"student_id": b, "status": "P" if i == 1 else "A"}]})
        data = self.client.get("/api/analysis/summary").get_json()
        by_roll = {x["roll_no"]: x for x in data["students"]}
        self.assertEqual(by_roll["1"]["pct"], 100.0)
        self.assertEqual(by_roll["1"]["status"], "Good")
        self.assertEqual(by_roll["2"]["pct"], 25.0)
        self.assertEqual(by_roll["2"]["status"], "Shortage")
        self.assertEqual(data["counts"]["Shortage"], 1)

    def test_csv_export(self):
        a, b, s = self._setup_class()
        r = self.client.get("/api/export.csv")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data.decode().startswith("Roll No,Name,S1"))

    def test_delete_student_removes_attendance(self):
        a, b, s = self._setup_class()
        d = (date.today() - timedelta(days=1)).isoformat()
        self.client.post("/api/attendance", json={"subject_id": s, "date": d,
            "records": [{"student_id": a, "status": "P"}]})
        self.assertEqual(self.client.delete(f"/api/students/{a}").status_code, 200)
        self.assertEqual(self.client.delete(f"/api/students/{a}").status_code, 404)
        data = self.client.get("/api/analysis/summary").get_json()
        self.assertEqual(len(data["students"]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

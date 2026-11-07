"""
analysis.py - Attendance calculation logic for the Smart Attendance Analyser.

All functions here are pure (they do not touch the database), so they are
easy to unit-test.
"""

SHORTAGE_LIMIT = 75.0   # minimum attendance percentage required
WARNING_LIMIT = 80.0    # students between 75 and 80 are "at risk"


def percentage(present, total):
    """Return attendance percentage rounded to 2 decimals (0 if total is 0)."""
    if total <= 0:
        return 0.0
    return round(present * 100.0 / total, 2)


def classify(pct, total_classes):
    """Return a status label for an attendance percentage."""
    if total_classes == 0:
        return "No Data"
    if pct < SHORTAGE_LIMIT:
        return "Shortage"
    if pct < WARNING_LIMIT:
        return "At Risk"
    return "Good"


def classes_needed(present, total, target=SHORTAGE_LIMIT):
    """
    Number of consecutive classes a student must attend (without any absence)
    to reach the target percentage. Returns 0 if already at/above target.
    Solves (present + x) / (total + x) >= target/100 for the smallest integer x.
    """
    if total == 0 or present * 100.0 / total >= target:
        return 0
    t = target / 100.0
    x = (t * total - present) / (1 - t)
    whole = int(x)
    return whole if whole >= x else whole + 1


def student_summary(rows, subject_ids):
    """
    rows: iterable of (student_id, subject_id, status) where status is
          'P' (present) or 'A' (absent).
    subject_ids: list of all subject ids.
    Returns dict: student_id -> {'per_subject': {sid: (present,total,pct)},
                                 'present': n, 'total': n, 'pct': x,
                                 'status': label, 'needed': n}
    """
    data = {}
    for student_id, subject_id, status in rows:
        entry = data.setdefault(student_id, {sid: [0, 0] for sid in subject_ids})
        if subject_id not in entry:
            entry[subject_id] = [0, 0]
        entry[subject_id][1] += 1
        if status == "P":
            entry[subject_id][0] += 1

    result = {}
    for student_id, subj in data.items():
        tp = sum(v[0] for v in subj.values())
        tt = sum(v[1] for v in subj.values())
        pct = percentage(tp, tt)
        result[student_id] = {
            "per_subject": {s: (v[0], v[1], percentage(v[0], v[1]))
                            for s, v in subj.items()},
            "present": tp,
            "total": tt,
            "pct": pct,
            "status": classify(pct, tt),
            "needed": classes_needed(tp, tt),
        }
    return result


def daily_trend(rows):
    """
    rows: iterable of (date, status).
    Returns list of (date, present_count, total, pct) sorted by date.
    """
    by_date = {}
    for date, status in rows:
        d = by_date.setdefault(date, [0, 0])
        d[1] += 1
        if status == "P":
            d[0] += 1
    return [(d, v[0], v[1], percentage(v[0], v[1]))
            for d, v in sorted(by_date.items())]

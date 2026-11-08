"""
db.py
SQLite database access layer for CELL SCOPE.
Handles patient registration, diagnostic visit logs, and persistence.
"""

import math
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from crypto_util import decrypt_row, encrypt

DB_PATH = "cellscope.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS patients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    patient_code TEXT,
    age INTEGER DEFAULT 30,
    gender TEXT DEFAULT 'Male',
    phone TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS visits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    visit_date TEXT NOT NULL,
    diagnosis_result TEXT NOT NULL,
    confidence_score REAL DEFAULT 95.0,
    risk_band TEXT DEFAULT 'Low risk',
    risk_tagline TEXT DEFAULT 'Low risk — monitor for symptoms',
    cells_analyzed INTEGER DEFAULT 100,
    cells_parasitized INTEGER DEFAULT 0,
    parasitemia_pct REAL DEFAULT 0.0,
    ci_low REAL DEFAULT 0.0,
    ci_high REAL DEFAULT 0.0,
    tier TEXT DEFAULT 'Screening Result',
    image_data TEXT,
    heatmap_data TEXT,
    village TEXT DEFAULT '',
    district TEXT DEFAULT '',
    health_worker TEXT DEFAULT '',
    latitude REAL,
    longitude REAL,
    referred INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (patient_id) REFERENCES patients (id)
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        tbl_check = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='patients'").fetchone()
        if not tbl_check:
            conn.executescript(SCHEMA)

            # Demo data so the dashboard and outbreak map aren't empty. Skipped on
            # Render (RENDER=true is set automatically) unless CELLSCOPE_DEMO_DATA=1,
            # which is handy for a live presentation.
            if not os.environ.get("RENDER") or os.environ.get("CELLSCOPE_DEMO_DATA") == "1":
                _seed_demo_data(conn)

        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)

        # Ensure column migrations for existing databases
        for col_def in [
            "ALTER TABLE patients ADD COLUMN patient_code TEXT",
            "ALTER TABLE patients ADD COLUMN age INTEGER DEFAULT 30",
            "ALTER TABLE patients ADD COLUMN gender TEXT DEFAULT 'Male'",
            "ALTER TABLE patients ADD COLUMN phone TEXT DEFAULT ''",
            "ALTER TABLE visits ADD COLUMN diagnosis_result TEXT DEFAULT 'Uninfected'",
            "ALTER TABLE visits ADD COLUMN confidence_score REAL DEFAULT 95.0",
            "ALTER TABLE visits ADD COLUMN risk_band TEXT DEFAULT 'Low risk'",
            "ALTER TABLE visits ADD COLUMN risk_tagline TEXT DEFAULT 'Low risk — monitor for symptoms'",
            "ALTER TABLE visits ADD COLUMN image_data TEXT",
            "ALTER TABLE visits ADD COLUMN heatmap_data TEXT",
            "ALTER TABLE visits ADD COLUMN village TEXT DEFAULT ''",
            "ALTER TABLE visits ADD COLUMN district TEXT DEFAULT ''",
            "ALTER TABLE visits ADD COLUMN health_worker TEXT DEFAULT ''",
            "ALTER TABLE visits ADD COLUMN latitude REAL",
            "ALTER TABLE visits ADD COLUMN longitude REAL",
            "ALTER TABLE visits ADD COLUMN referred INTEGER DEFAULT 0",
        ]:
            try:
                conn.execute(col_def)
            except Exception:
                pass


def wilson_confidence_interval(k: int, n: int, z: float = 1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    margin = (z * math.sqrt((p * (1 - p) / n) + (z**2 / (4 * n**2)))) / denom
    low = max(0.0, center - margin) * 100
    high = min(1.0, center + margin) * 100
    return round(low, 1), round(high, 1)


def parasitemia_tier(pct: float) -> str:
    if pct == 0:
        return "No Malaria Parasites Detected"
    if pct < 2:
        return "Low Parasitemia Level"
    if pct < 5:
        return "Moderate Parasitemia Level"
    return "High Parasitemia Level"


def create_or_get_patient(name: str, patient_code: str = None, age: int = 30, gender: str = "Male", phone: str = "") -> int:
    name_clean = name.strip()
    with get_conn() as conn:
        row = None
        if patient_code and patient_code.strip():
            row = conn.execute("SELECT id FROM patients WHERE patient_code = ?", (patient_code.strip(),)).fetchone()
        if not row:
            row = conn.execute("SELECT id FROM patients WHERE LOWER(name) = LOWER(?)", (name_clean,)).fetchone()

        if row:
            conn.execute(
                "UPDATE patients SET name = ?, age = ?, gender = ?, phone = ? WHERE id = ?",
                (name_clean, int(age or 30), gender or "Male", encrypt(phone or ""), row["id"])
            )
            return row["id"]

        total_p = conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
        if not patient_code or not patient_code.strip():
            patient_code = f"CS-{9040 + total_p + 1}"

        cur = conn.execute(
            """INSERT INTO patients (name, patient_code, age, gender, phone, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name_clean, patient_code, int(age or 30), gender or "Male", encrypt(phone or ""), datetime.now(timezone.utc).isoformat()),
        )
        return cur.lastrowid


def list_patients():
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT p.*, COUNT(v.id) as visit_count, MAX(v.visit_date) as last_visit
            FROM patients p
            LEFT JOIN visits v ON v.patient_id = p.id
            GROUP BY p.id
            ORDER BY p.created_at DESC
        """).fetchall()
        return [decrypt_row(dict(r)) for r in rows]


def get_patient(patient_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
        return decrypt_row(dict(row)) if row else None


def get_patient_by_code(patient_code: str):
    if not patient_code or not patient_code.strip():
        return None
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM patients WHERE patient_code = ?", (patient_code.strip(),)).fetchone()
        return decrypt_row(dict(row)) if row else None


def add_visit(patient_id: int, visit_date: str, cells_analyzed: int, cells_parasitized: int, diagnosis_result: str = None, confidence_score: float = 95.0, risk_band: str = "Low risk", risk_tagline: str = "", image_data: str = None, heatmap_data: str = None,
              village: str = "", district: str = "", health_worker: str = "", latitude: float = None, longitude: float = None, referred: bool = False):
    pct = round((cells_parasitized / cells_analyzed) * 100, 2) if cells_analyzed else 0.0
    ci_low, ci_high = wilson_confidence_interval(cells_parasitized, cells_analyzed)
    tier = parasitemia_tier(pct)
    if not diagnosis_result:
        diagnosis_result = "Parasitized" if pct > 0 else "Uninfected"

    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO visits
               (patient_id, visit_date, diagnosis_result, confidence_score, risk_band, risk_tagline,
                cells_analyzed, cells_parasitized, parasitemia_pct, ci_low, ci_high, tier, image_data, heatmap_data,
                village, district, health_worker, latitude, longitude, referred, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                patient_id, visit_date, diagnosis_result, float(confidence_score), risk_band, risk_tagline,
                cells_analyzed, cells_parasitized, pct, ci_low, ci_high, tier, encrypt(image_data), encrypt(heatmap_data),
                (village or "").strip(), (district or "").strip(), (health_worker or "").strip(),
                latitude, longitude, 1 if referred else 0, datetime.now(timezone.utc).isoformat(),
            ),
        )
        return cur.lastrowid


def list_visits(patient_id: int):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM visits WHERE patient_id = ? ORDER BY visit_date ASC, created_at ASC",
            (patient_id,),
        ).fetchall()
        return [decrypt_row(dict(r)) for r in rows]


def get_visit_by_id(visit_id: int):
    with get_conn() as conn:
        query = """
        SELECT
            v.*,
            p.name as patient_name,
            p.patient_code,
            p.age,
            p.gender,
            p.phone
        FROM visits v
        JOIN patients p ON v.patient_id = p.id
        WHERE v.id = ?
        """
        row = conn.execute(query, (visit_id,)).fetchone()
        return decrypt_row(dict(row)) if row else None


def get_all_visit_records():
    """Returns every diagnostic visit record in the database with patient details, newest first."""
    with get_conn() as conn:
        query = """
        SELECT
            p.id as patient_id,
            p.name,
            p.patient_code,
            p.age,
            p.gender,
            p.phone,
            p.created_at as patient_created_at,
            v.id as visit_id,
            v.visit_date,
            v.diagnosis_result,
            v.confidence_score,
            v.risk_band,
            v.risk_tagline,
            v.cells_analyzed,
            v.cells_parasitized,
            v.parasitemia_pct,
            v.tier,
            v.image_data,
            v.heatmap_data,
            v.village,
            v.district,
            v.health_worker,
            v.referred,
            v.created_at as visit_created_at
        FROM visits v
        JOIN patients p ON v.patient_id = p.id
        ORDER BY v.visit_date DESC, v.created_at DESC
        """
        rows = conn.execute(query).fetchall()
        return [decrypt_row(dict(r)) for r in rows]


def get_all_records_with_latest_visit():
    """Alias for all visit records with patient details, newest first."""
    return get_all_visit_records()


def get_analytics_dataset():
    """Generates scatter plot data and time-series points directly from database records."""
    with get_conn() as conn:
        query = """
        SELECT
            p.id as patient_id,
            p.name,
            p.age,
            p.gender,
            v.visit_date,
            v.diagnosis_result,
            v.confidence_score,
            v.parasitemia_pct,
            v.cells_parasitized
        FROM visits v
        JOIN patients p ON v.patient_id = p.id
        ORDER BY v.visit_date ASC
        """
        rows = conn.execute(query).fetchall()
        data = [decrypt_row(dict(r)) for r in rows]

        total_visits = len(data)
        positive_cases = sum(1 for r in data if r["diagnosis_result"] in ["Parasitized", "Malaria Detected"])
        negative_cases = total_visits - positive_cases

        scatter_age_parasitemia = [
            {
                "x": r["age"],
                "y": r["parasitemia_pct"],
                "confidence": r["confidence_score"],
                "name": r["name"],
                "result": r["diagnosis_result"],
                "date": r["visit_date"]
            }
            for r in data
        ]

        time_series = [
            {
                "x": r["visit_date"],
                "y": r["parasitemia_pct"],
                "confidence": r["confidence_score"],
                "name": r["name"],
                "result": r["diagnosis_result"]
            }
            for r in data
        ]

        return {
            "total_screenings": total_visits,
            "positive_cases": positive_cases,
            "negative_cases": negative_cases,
            "scatter_age_parasitemia": scatter_age_parasitemia,
            "time_series": time_series
        }


def treatment_response(visits: list) -> str:
    if len(visits) < 2:
        return "Initial screening visit recorded. Add follow-up visit to compare longitudinal trends."

    prev, latest = visits[-2], visits[-1]
    delta = latest["parasitemia_pct"] - prev["parasitemia_pct"]

    if latest["parasitemia_pct"] == 0 and prev["parasitemia_pct"] > 0:
        return "No malaria parasites detected in latest visit. Infection successfully cleared."
    if delta < 0:
        return f"Parasitemia decreased by {abs(delta):.1f} percentage points since last visit."
    if delta > 0:
        return f"Parasitemia increased by {delta:.1f} percentage points since last visit."
    return "Parasitemia level stable since last visit."


# ---------------------------------------------------------------------------
# Rural surveillance: outbreak clusters and referrals
# ---------------------------------------------------------------------------
def get_outbreak_summary(days: int = 14, hotspot_min_positive: int = 3):
    """Group recent tests by village. A village is a hotspot when it has at least
    `hotspot_min_positive` positive tests in the window -- a simple, explainable
    rule a district health officer can act on."""
    from datetime import timedelta
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT COALESCE(NULLIF(TRIM(village), ''), 'Unknown') AS village,
                   COALESCE(NULLIF(TRIM(district), ''), '') AS district,
                   COUNT(*) AS tests,
                   SUM(CASE WHEN diagnosis_result = 'Parasitized' THEN 1 ELSE 0 END) AS positives,
                   SUM(CASE WHEN referred = 1 THEN 1 ELSE 0 END) AS referrals,
                   AVG(latitude) AS lat,
                   AVG(longitude) AS lon,
                   MAX(visit_date) AS last_test
            FROM visits
            WHERE visit_date >= ?
            GROUP BY 1, 2
            ORDER BY positives DESC, tests DESC
            """,
            (since,),
        ).fetchall()

    villages = []
    for r in rows:
        d = dict(r)
        d["positivity_pct"] = round(100.0 * d["positives"] / d["tests"], 1) if d["tests"] else 0.0
        d["hotspot"] = d["positives"] >= hotspot_min_positive
        d["lat"] = round(d["lat"], 5) if d["lat"] is not None else None
        d["lon"] = round(d["lon"], 5) if d["lon"] is not None else None
        villages.append(d)

    return {
        "window_days": days,
        "since": since,
        "hotspot_rule": f">= {hotspot_min_positive} positive tests in {days} days",
        "total_tests": sum(v["tests"] for v in villages),
        "total_positives": sum(v["positives"] for v in villages),
        "hotspots": [v for v in villages if v["hotspot"]],
        "villages": villages,
    }


def get_referrals(days: int = 30):
    """Patients flagged for referral (High / Critical risk), newest first."""
    from datetime import timedelta
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT v.id AS visit_id, v.visit_date, v.risk_band, v.parasitemia_pct,
                   v.village, v.district, v.health_worker,
                   p.id AS patient_id, p.name, p.patient_code, p.age, p.gender, p.phone
            FROM visits v JOIN patients p ON v.patient_id = p.id
            WHERE v.referred = 1 AND v.visit_date >= ?
            ORDER BY v.visit_date DESC, v.created_at DESC
            """,
            (since,),
        ).fetchall()
        return [decrypt_row(dict(r)) for r in rows]


# Demo villages in malaria-affected tribal areas of Telangana (approximate coordinates).
_DEMO_VILLAGES = [
    ("Charla", "Bhadradri Kothagudem", 17.990, 80.995),
    ("Dummugudem", "Bhadradri Kothagudem", 17.840, 80.870),
    ("Bhadrachalam", "Bhadradri Kothagudem", 17.669, 80.893),
    ("Eturnagaram", "Mulugu", 18.333, 80.430),
    ("Tadvai", "Mulugu", 18.270, 80.200),
    ("Utnoor", "Adilabad", 19.367, 78.767),
]

_DEMO_PATIENTS = [
    # name, code, age, gender, village index, days ago, result, cells, infected, band, worker
    ("Lakshmi Sodi", "CS-1001", 32, "Female", 0, 2, "Parasitized", 140, 9, "Critical risk", "ASHA Sunitha"),
    ("Ramesh Madvi", "CS-1002", 41, "Male", 0, 3, "Parasitized", 120, 4, "High risk", "ASHA Sunitha"),
    ("Sammakka Kursam", "CS-1003", 26, "Female", 0, 5, "Parasitized", 130, 3, "High risk", "ASHA Sunitha"),
    ("Venkatesh Payam", "CS-1004", 9, "Male", 0, 6, "Uninfected", 110, 0, "Negative / Clear", "ASHA Sunitha"),
    ("Kamala Vanka", "CS-1005", 38, "Female", 1, 1, "Parasitized", 125, 3, "High risk", "ASHA Padma"),
    ("Bhimaiah Sodi", "CS-1006", 55, "Male", 1, 4, "Parasitized", 150, 2, "Moderate risk", "ASHA Padma"),
    ("Saraswathi Irpa", "CS-1007", 30, "Female", 1, 8, "Parasitized", 118, 5, "High risk", "ASHA Padma"),
    ("Raju Kunja", "CS-1008", 22, "Male", 2, 3, "Uninfected", 105, 0, "Negative / Clear", "ANM Rani"),
    ("Pushpa Madakam", "CS-1009", 47, "Female", 2, 9, "Parasitized", 112, 2, "Moderate risk", "ANM Rani"),
    ("Nagaraju Eesam", "CS-1010", 35, "Male", 3, 2, "Parasitized", 140, 6, "High risk", "ASHA Swaroopa"),
    ("Jyothi Kalam", "CS-1011", 28, "Female", 3, 10, "Uninfected", 100, 0, "Negative / Clear", "ASHA Swaroopa"),
    ("Srinu Gonde", "CS-1012", 19, "Male", 4, 6, "Uninfected", 108, 0, "Negative / Clear", "ASHA Laxmi"),
    ("Anitha Atram", "CS-1013", 24, "Female", 5, 4, "Uninfected", 115, 0, "Negative / Clear", "ASHA Bhagya"),
]


def _seed_demo_data(conn):
    """Insert clearly-fictional demo patients spread across the last ~10 days."""
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    for (name, code, age, gender, vi, days_ago, result, cells, infected, band, worker) in _DEMO_PATIENTS:
        village, district, lat, lon = _DEMO_VILLAGES[vi]
        cur = conn.execute(
            "INSERT INTO patients (name, patient_code, age, gender, phone, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (name, code, age, gender, "", now.isoformat()),
        )
        pct = round(100.0 * infected / cells, 2)
        ci_low, ci_high = wilson_confidence_interval(infected, cells)
        conn.execute(
            """INSERT INTO visits (patient_id, visit_date, diagnosis_result, confidence_score, risk_band, risk_tagline,
                   cells_analyzed, cells_parasitized, parasitemia_pct, ci_low, ci_high, tier,
                   village, district, health_worker, latitude, longitude, referred, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (cur.lastrowid, (now - timedelta(days=days_ago)).strftime("%Y-%m-%d"), result,
             93.0 if result == "Parasitized" else 97.5, band, "Demo record",
             cells, infected, pct, ci_low, ci_high, parasitemia_tier(pct),
             village, district, worker, lat, lon,
             1 if band in ("High risk", "Critical risk") else 0, now.isoformat()),
        )

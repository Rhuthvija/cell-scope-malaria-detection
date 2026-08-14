"""
db.py
SQLite database access layer for CELL SCOPE.
Handles patient registration, diagnostic visit logs, and persistence.
"""

import math
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

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
            now_iso = datetime.now(timezone.utc).isoformat()
            
            cur1 = conn.execute(
                "INSERT INTO patients (name, patient_code, age, gender, phone, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("Vennela Indukuri", "CS-9042", 28, "Female", "+1 (555) 019-2834", now_iso)
            )
            p1_id = cur1.lastrowid
            conn.execute(
                "INSERT INTO visits (patient_id, visit_date, diagnosis_result, confidence_score, risk_band, risk_tagline, cells_analyzed, cells_parasitized, parasitemia_pct, ci_low, ci_high, tier, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (p1_id, "2026-08-01", "Parasitized", 94.2, "High risk", "Parasitemia detected. Medical evaluation advised.", 120, 8, 6.67, 3.4, 12.6, "High Parasitemia Level", now_iso)
            )

            cur2 = conn.execute(
                "INSERT INTO patients (name, patient_code, age, gender, phone, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("Amina Diallo", "CS-7721", 27, "Female", "+1 (555) 048-9921", now_iso)
            )
            p2_id = cur2.lastrowid
            conn.execute(
                "INSERT INTO visits (patient_id, visit_date, diagnosis_result, confidence_score, risk_band, risk_tagline, cells_analyzed, cells_parasitized, parasitemia_pct, ci_low, ci_high, tier, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (p2_id, "2026-08-02", "Parasitized", 96.8, "Critical risk", "🚨 Immediately consult a doctor", 150, 12, 8.0, 4.6, 13.5, "High Parasitemia Level", now_iso)
            )

            cur3 = conn.execute(
                "INSERT INTO patients (name, patient_code, age, gender, phone, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("Elena Rostova", "CS-3108", 45, "Female", "+1 (555) 032-1104", now_iso)
            )
            p3_id = cur3.lastrowid
            conn.execute(
                "INSERT INTO visits (patient_id, visit_date, diagnosis_result, confidence_score, risk_band, risk_tagline, cells_analyzed, cells_parasitized, parasitemia_pct, ci_low, ci_high, tier, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (p3_id, "2026-08-12", "Uninfected", 99.4, "Negative / Clear", "Clean sample. Routine follow-up only.", 110, 0, 0.0, 0.0, 3.3, "No Malaria Parasites Detected", now_iso)
            )

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
            "ALTER TABLE visits ADD COLUMN heatmap_data TEXT"
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
                (name_clean, int(age or 30), gender or "Male", phone or "", row["id"])
            )
            return row["id"]
        
        total_p = conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
        if not patient_code or not patient_code.strip():
            patient_code = f"CS-{9040 + total_p + 1}"
            
        cur = conn.execute(
            """INSERT INTO patients (name, patient_code, age, gender, phone, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name_clean, patient_code, int(age or 30), gender or "Male", phone or "", datetime.now(timezone.utc).isoformat()),
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
        return [dict(r) for r in rows]


def get_patient(patient_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
        return dict(row) if row else None


def get_patient_by_code(patient_code: str):
    if not patient_code or not patient_code.strip():
        return None
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM patients WHERE patient_code = ?", (patient_code.strip(),)).fetchone()
        return dict(row) if row else None


def add_visit(patient_id: int, visit_date: str, cells_analyzed: int, cells_parasitized: int, diagnosis_result: str = None, confidence_score: float = 95.0, risk_band: str = "Low risk", risk_tagline: str = "", image_data: str = None, heatmap_data: str = None):
    pct = round((cells_parasitized / cells_analyzed) * 100, 2) if cells_analyzed else 0.0
    ci_low, ci_high = wilson_confidence_interval(cells_parasitized, cells_analyzed)
    tier = parasitemia_tier(pct)
    if not diagnosis_result:
        diagnosis_result = "Parasitized" if pct > 0 else "Uninfected"

    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO visits
               (patient_id, visit_date, diagnosis_result, confidence_score, risk_band, risk_tagline,
                cells_analyzed, cells_parasitized, parasitemia_pct, ci_low, ci_high, tier, image_data, heatmap_data, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                patient_id, visit_date, diagnosis_result, float(confidence_score), risk_band, risk_tagline,
                cells_analyzed, cells_parasitized, pct, ci_low, ci_high, tier, image_data, heatmap_data, datetime.now(timezone.utc).isoformat(),
            ),
        )
        return cur.lastrowid


def list_visits(patient_id: int):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM visits WHERE patient_id = ? ORDER BY visit_date ASC, created_at ASC",
            (patient_id,),
        ).fetchall()
        return [dict(r) for r in rows]


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
        return dict(row) if row else None


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
            v.created_at as visit_created_at
        FROM visits v
        JOIN patients p ON v.patient_id = p.id
        ORDER BY v.visit_date DESC, v.created_at DESC
        """
        rows = conn.execute(query).fetchall()
        return [dict(r) for r in rows]


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
        data = [dict(r) for r in rows]
        
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

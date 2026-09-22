"""
FastAPI backend: doctor auth, patient/case organization, and the
confidence-gated documentation pipeline (unchanged, from src/).
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Request, Response, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.pipeline import run_pipeline, resolve_fact, save_case, load_case
from src.calibration import CalibrationStore
from src.audit import AuditLog

import db
from transcript_parsing import parse_upload, parse_plain_text

SAMPLE_DIR = ROOT / "sample_data"
LIBRARY_DIR = SAMPLE_DIR / "primock57_library"
DEMO_DIR = SAMPLE_DIR
RUNS_DIR = ROOT / "api" / "runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)

db.init_db()

app = FastAPI(title="Clinical Documentation Gate API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

SESSION_COOKIE = "session_token"


# ---------- auth plumbing ----------

def get_current_doctor(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(401, "Not signed in.")
    conn = db.get_conn()
    doctor = db.get_doctor_by_session(conn, token)
    conn.close()
    if doctor is None:
        raise HTTPException(401, "Session expired, please sign in again.")
    return doctor


def _validate_email(v: str) -> str:
    v = v.strip()
    if "@" not in v or "." not in v.split("@")[-1] or len(v) < 5:
        raise ValueError("Enter a valid email address.")
    return v


class SignupRequest(BaseModel):
    name: str
    email: str
    password: str

    _validate = field_validator("email")(_validate_email)


class LoginRequest(BaseModel):
    email: str
    password: str

    _validate = field_validator("email")(_validate_email)


@app.post("/api/auth/signup")
def signup(req: SignupRequest, response: Response):
    if len(req.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters.")
    conn = db.get_conn()
    try:
        doctor_id = db.create_doctor(conn, req.name.strip(), req.email, req.password)
    except Exception:
        conn.close()
        raise HTTPException(400, "An account with that email already exists.")
    token = db.create_session(conn, doctor_id)
    conn.close()
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 30)
    return {"id": doctor_id, "name": req.name, "email": req.email}


@app.post("/api/auth/login")
def login(req: LoginRequest, response: Response):
    conn = db.get_conn()
    doctor = db.verify_doctor(conn, req.email, req.password)
    if doctor is None:
        conn.close()
        raise HTTPException(401, "Incorrect email or password.")
    token = db.create_session(conn, doctor["id"])
    conn.close()
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 30)
    return {"id": doctor["id"], "name": doctor["name"], "email": doctor["email"]}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        conn = db.get_conn()
        db.delete_session(conn, token)
        conn.close()
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@app.get("/api/auth/me")
def me(doctor=Depends(get_current_doctor)):
    return {"id": doctor["id"], "name": doctor["name"], "email": doctor["email"]}


# ---------- library of real cases ----------

@app.get("/api/library")
def library(q: Optional[str] = None):
    index_path = LIBRARY_DIR / "_index.json"
    items = json.loads(index_path.read_text()) if index_path.exists() else []
    if q:
        q_lower = q.lower()
        items = [i for i in items if q_lower in i["presenting_complaint"].lower()]
    return items


# ---------- patients ----------

class PatientRequest(BaseModel):
    name: str
    identifier: Optional[str] = None


@app.get("/api/patients")
def list_patients(doctor=Depends(get_current_doctor)):
    conn = db.get_conn()
    rows = conn.execute(
        """SELECT patients.*, COUNT(cases.id) as case_count
           FROM patients LEFT JOIN cases ON cases.patient_id = patients.id
           WHERE patients.doctor_id = ? GROUP BY patients.id ORDER BY patients.created_at DESC""",
        (doctor["id"],),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/patients")
def create_patient(req: PatientRequest, doctor=Depends(get_current_doctor)):
    if not req.name.strip():
        raise HTTPException(400, "Patient name is required.")
    conn = db.get_conn()
    cur = conn.execute(
        "INSERT INTO patients (doctor_id, name, identifier, created_at) VALUES (?, ?, ?, ?)",
        (doctor["id"], req.name.strip(), req.identifier, db.now()),
    )
    conn.commit()
    patient_id = cur.lastrowid
    conn.close()
    return {"id": patient_id, "name": req.name, "identifier": req.identifier, "case_count": 0}


def _own_patient_or_404(conn, patient_id: int, doctor_id: int):
    row = conn.execute("SELECT * FROM patients WHERE id = ? AND doctor_id = ?", (patient_id, doctor_id)).fetchone()
    if row is None:
        raise HTTPException(404, "Patient not found.")
    return row


@app.get("/api/patients/{patient_id}/cases")
def list_cases(patient_id: int, doctor=Depends(get_current_doctor)):
    conn = db.get_conn()
    _own_patient_or_404(conn, patient_id, doctor["id"])
    rows = conn.execute(
        "SELECT * FROM cases WHERE patient_id = ? ORDER BY created_at DESC", (patient_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------- cases (create = ingest transcript + immediately run pipeline) ----------

def _run_paths(run_id: str):
    d = RUNS_DIR / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d / "case.json", d / "audit_log.jsonl", d / "calibration_state.json"


def _execute_case(patient_id: int, doctor_id: int, title: str, source: str, source_ref: Optional[str],
                   segments, use_llm: bool):
    run_id = uuid.uuid4().hex[:12]
    case_path, audit_path, calibration_path = _run_paths(run_id)

    pipeline_case = run_pipeline(segments, use_llm=use_llm, audit_path=str(audit_path),
                                  calibration_path=str(calibration_path))
    pipeline_case["visit_id"] = title
    pipeline_case["run_id"] = run_id
    save_case(pipeline_case, str(case_path))

    conn = db.get_conn()
    cur = conn.execute(
        "INSERT INTO cases (patient_id, doctor_id, title, source, source_ref, run_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (patient_id, doctor_id, title, source, source_ref, run_id, db.now()),
    )
    conn.commit()
    case_id = cur.lastrowid
    conn.close()

    return case_id, run_id, pipeline_case, CalibrationStore(str(calibration_path)).as_dict()


@app.post("/api/cases/from-library")
def create_case_from_library(patient_id: int = Form(...), filename: str = Form(...),
                              use_llm: bool = Form(False), doctor=Depends(get_current_doctor)):
    conn = db.get_conn()
    _own_patient_or_404(conn, patient_id, doctor["id"])
    conn.close()

    path = LIBRARY_DIR / filename
    if not path.exists() or path.parent != LIBRARY_DIR:
        raise HTTPException(404, f"Unknown library case: {filename}")
    data = json.loads(path.read_text())

    case_id, run_id, case, calibration = _execute_case(
        patient_id, doctor["id"], data.get("presenting_complaint") or data.get("visit_id", filename),
        "library", filename, data["segments"], use_llm,
    )
    return {"case_id": case_id, "run_id": run_id, "case": case, "calibration": calibration}


@app.post("/api/cases/from-text")
def create_case_from_text(patient_id: int = Form(...), title: str = Form(...), text: str = Form(...),
                           use_llm: bool = Form(False), doctor=Depends(get_current_doctor)):
    conn = db.get_conn()
    _own_patient_or_404(conn, patient_id, doctor["id"])
    conn.close()

    try:
        segments = parse_plain_text(text)
    except ValueError as e:
        raise HTTPException(400, str(e))

    case_id, run_id, case, calibration = _execute_case(
        patient_id, doctor["id"], title, "paste", None, segments, use_llm,
    )
    return {"case_id": case_id, "run_id": run_id, "case": case, "calibration": calibration}


@app.post("/api/cases/from-upload")
async def create_case_from_upload(patient_id: int = Form(...), title: str = Form(...),
                                   use_llm: bool = Form(False), file: UploadFile = File(...),
                                   doctor=Depends(get_current_doctor)):
    conn = db.get_conn()
    _own_patient_or_404(conn, patient_id, doctor["id"])
    conn.close()

    raw = await file.read()
    try:
        segments = parse_upload(file.filename, raw)
    except ValueError as e:
        raise HTTPException(400, str(e))

    case_id, run_id, case, calibration = _execute_case(
        patient_id, doctor["id"], title, "upload", file.filename, segments, use_llm,
    )
    return {"case_id": case_id, "run_id": run_id, "case": case, "calibration": calibration}


def _own_case_or_404(conn, case_id: int, doctor_id: int):
    row = conn.execute("SELECT * FROM cases WHERE id = ? AND doctor_id = ?", (case_id, doctor_id)).fetchone()
    if row is None:
        raise HTTPException(404, "Case not found.")
    return row


@app.get("/api/cases/{case_id}")
def get_case(case_id: int, doctor=Depends(get_current_doctor)):
    conn = db.get_conn()
    case_row = _own_case_or_404(conn, case_id, doctor["id"])
    conn.close()
    case_path, _, calibration_path = _run_paths(case_row["run_id"])
    return {
        "case_id": case_row["id"],
        "run_id": case_row["run_id"],
        "title": case_row["title"],
        "case": load_case(str(case_path)),
        "calibration": CalibrationStore(str(calibration_path)).as_dict(),
    }


class ResolveRequest(BaseModel):
    fact_id: str
    decision: str


@app.post("/api/cases/{case_id}/resolve")
def resolve(case_id: int, req: ResolveRequest, doctor=Depends(get_current_doctor)):
    conn = db.get_conn()
    case_row = _own_case_or_404(conn, case_id, doctor["id"])
    conn.close()

    case_path, audit_path, calibration_path = _run_paths(case_row["run_id"])
    pipeline_case = load_case(str(case_path))
    try:
        pipeline_case = resolve_fact(pipeline_case, req.fact_id, req.decision, doctor["name"],
                                      audit_path=str(audit_path), calibration_path=str(calibration_path))
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_case(pipeline_case, str(case_path))

    return {"case": pipeline_case, "calibration": CalibrationStore(str(calibration_path)).as_dict()}


@app.get("/api/cases/{case_id}/audit")
def audit(case_id: int, doctor=Depends(get_current_doctor)):
    conn = db.get_conn()
    case_row = _own_case_or_404(conn, case_id, doctor["id"])
    conn.close()
    _, audit_path, _ = _run_paths(case_row["run_id"])
    return AuditLog(str(audit_path)).read_all()


web_dir = ROOT / "web"
if web_dir.exists():
    app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8420, reload=False)

"""
FastAPI backend: doctor auth, patient/case organization, and the
confidence-gated documentation pipeline (src/), including the audio path
(upload -> local Whisper transcription -> extraction -> gates -> note).
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Depends, Request, Response, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.env import load_env
load_env()

from src.llm import LLMError, llm_model_name, llm_provider
from src.speakers import attribute_speakers
from src.transcribe import UNATTRIBUTED, transcribe_consultation, whisper_model_name
from src.entailment import nli_model_name, score_pairs
from src.transcribe import _get_model as _get_asr_model
from src.pipeline import FIELD_ORDER, run_pipeline, resolve_fact, save_case, load_case
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

@asynccontextmanager
async def lifespan(_app):
    if os.environ.get("PRELOAD_MODELS", "1") != "0":
        threading.Thread(target=_preload_models, daemon=True).start()
    yield


app = FastAPI(title="Clinical Documentation Gate API", lifespan=lifespan)
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


@app.get("/api/llm-status")
def llm_status():
    return {"provider": llm_provider(), "model": llm_model_name()}


@app.get("/api/pipeline-info")
def pipeline_info():
    return {"asr_model": f"faster-whisper {whisper_model_name()}", "nli_model": nli_model_name(),
            "llm_provider": llm_provider(), "llm_model": llm_model_name(),
            "audio_types": sorted(AUDIO_EXTS)}


# ---------- library of real cases ----------

@app.get("/api/library")
def library(q: Optional[str] = None):
    index_path = LIBRARY_DIR / "_index.json"
    items = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else []
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
    return d / "case.json", d / "audit_log.jsonl"


# Adaptive thresholds persist per doctor across all of their cases: every
# approve/reject a doctor makes shapes the auto-insert bar for their future
# notes. (A per-case file would reset the learning on every new case.)
CALIBRATION_DIR = ROOT / "api" / "calibration"
CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)
CALIBRATION_LOCK = threading.Lock()


def _calibration_path(doctor_id: int) -> Path:
    return CALIBRATION_DIR / f"doctor_{doctor_id}.json"


def _calibration_view(doctor_id: int) -> Dict[str, Any]:
    return CalibrationStore(str(_calibration_path(doctor_id))).snapshot(FIELD_ORDER)


# ---------- pipeline jobs ----------
#
# Every new case runs as a background job so the browser can show each
# pipeline stage live (audio runs take minutes on CPU). Jobs live in memory;
# the finished case is persisted to disk + SQLite like before.

AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".webm"}
MAX_AUDIO_BYTES = 300 * 1024 * 1024

JOBS: Dict[str, Dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()
# One pipeline run at a time: the ASR and NLI models are CPU/RAM heavy.
PIPELINE_LOCK = threading.Lock()


def _new_job(doctor_id: int, patient_id: int, stages: List[str]) -> Dict[str, Any]:
    job = {"id": uuid.uuid4().hex[:12], "doctor_id": doctor_id, "patient_id": patient_id,
           "status": "queued", "stage": "queued", "stages": stages, "progress": None,
           "error": None, "case_id": None, "created_at": time.time()}
    with JOBS_LOCK:
        JOBS[job["id"]] = job
    return job


def _job_update(job: Dict[str, Any], **fields) -> None:
    with JOBS_LOCK:
        job.update(fields)


def _run_job(job: Dict[str, Any], title: str, source: str, source_ref: Optional[str],
             use_llm: bool, run_id: str, load_segments: Callable[[], tuple]) -> None:
    """Background worker: [transcribe ->] extract -> gate -> plausibility -> persist."""
    try:
        with PIPELINE_LOCK:
            _job_update(job, status="running")
            segments, input_meta = load_segments()
            case_path, audit_path = _run_paths(run_id)
            pipeline_case = run_pipeline(
                segments, use_llm=use_llm, audit_path=str(audit_path),
                calibration_path=str(_calibration_path(job["doctor_id"])), input_meta=input_meta,
                progress=lambda stage: _job_update(job, stage=stage, progress=None),
            )
        pipeline_case["visit_id"] = title
        pipeline_case["run_id"] = run_id
        save_case(pipeline_case, str(case_path))

        conn = db.get_conn()
        cur = conn.execute(
            "INSERT INTO cases (patient_id, doctor_id, title, source, source_ref, run_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (job["patient_id"], job["doctor_id"], title, source, source_ref, run_id, db.now()),
        )
        conn.commit()
        conn.close()
        _job_update(job, status="done", stage="done", case_id=cur.lastrowid)
    except LLMError as e:
        _job_update(job, status="error", error=f"LLM stage failed: {e}")
    except Exception as e:  # surface any pipeline failure to the UI instead of a stuck job
        traceback.print_exc()
        _job_update(job, status="error", error=f"{type(e).__name__}: {e}")


def _start_job(doctor_id: int, patient_id: int, title: str, source: str, source_ref: Optional[str],
               use_llm: bool, run_id: str, stages: List[str], load_segments: Callable[[], tuple]):
    job = _new_job(doctor_id, patient_id, stages)
    threading.Thread(target=_run_job, daemon=True,
                     args=(job, title, source, source_ref, use_llm, run_id, load_segments)).start()
    return {"job_id": job["id"]}


TEXT_STAGES = ["extracting", "grounding", "plausibility", "done"]


def _start_text_job(doctor, patient_id, title, source, source_ref, segments, use_llm, input_meta):
    run_id = uuid.uuid4().hex[:12]
    return _start_job(doctor["id"], patient_id, title, source, source_ref, use_llm, run_id,
                      TEXT_STAGES, lambda: (segments, input_meta))


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, doctor=Depends(get_current_doctor)):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None or job["doctor_id"] != doctor["id"]:
            raise HTTPException(404, "Job not found.")
        return {k: v for k, v in job.items() if k != "doctor_id"}


@app.post("/api/cases/from-library")
def create_case_from_library(patient_id: int = Form(...), filename: str = Form(...),
                              use_llm: bool = Form(False), doctor=Depends(get_current_doctor)):
    conn = db.get_conn()
    _own_patient_or_404(conn, patient_id, doctor["id"])
    conn.close()

    path = LIBRARY_DIR / filename
    if not path.exists() or path.parent != LIBRARY_DIR:
        raise HTTPException(404, f"Unknown library case: {filename}")
    data = json.loads(path.read_text(encoding="utf-8"))
    title = data.get("presenting_complaint") or data.get("visit_id", filename)
    return _start_text_job(doctor, patient_id, title, "library", filename, data["segments"], use_llm,
                           {"input_mode": "text", "origin": f"PriMock57 human transcript ({filename})"})


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
    return _start_text_job(doctor, patient_id, title, "paste", None, segments, use_llm,
                           {"input_mode": "text", "origin": "pasted transcript"})


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
    return _start_text_job(doctor, patient_id, title, "upload", file.filename, segments, use_llm,
                           {"input_mode": "text", "origin": f"uploaded transcript ({file.filename})"})


async def _save_audio(upload: UploadFile, dest_dir: Path, label: str) -> Path:
    ext = Path(upload.filename or "").suffix.lower()
    if ext not in AUDIO_EXTS:
        raise HTTPException(400, f"{upload.filename}: unsupported audio type (use {', '.join(sorted(AUDIO_EXTS))}).")
    data = await upload.read()
    if not data:
        raise HTTPException(400, f"{upload.filename} is empty.")
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(400, f"{upload.filename} is larger than {MAX_AUDIO_BYTES // (1024 * 1024)} MB.")
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / f"{label}{ext}"
    path.write_bytes(data)
    return path


@app.post("/api/cases/from-audio")
async def create_case_from_audio(patient_id: int = Form(...), title: str = Form(...),
                                  use_llm: bool = Form(False), mode: str = Form("separate"),
                                  doctor_audio: Optional[UploadFile] = File(None),
                                  patient_audio: Optional[UploadFile] = File(None),
                                  mixed_audio: Optional[UploadFile] = File(None),
                                  doctor=Depends(get_current_doctor)):
    conn = db.get_conn()
    _own_patient_or_404(conn, patient_id, doctor["id"])
    conn.close()

    run_id = uuid.uuid4().hex[:12]
    audio_dir = RUNS_DIR / run_id / "audio"
    if mode == "separate":
        if doctor_audio is None or patient_audio is None:
            raise HTTPException(400, "Upload both the doctor and the patient recording.")
        channels = [(str(await _save_audio(doctor_audio, audio_dir, "doctor")), "DOCTOR", "doctor"),
                    (str(await _save_audio(patient_audio, audio_dir, "patient")), "PATIENT", "patient")]
        stages = ["transcribing", "extracting", "grounding", "plausibility", "done"]
        source_ref = f"{doctor_audio.filename} + {patient_audio.filename}"
    elif mode == "mixed":
        if mixed_audio is None:
            raise HTTPException(400, "Upload the consultation recording.")
        if llm_provider() is None:
            raise HTTPException(400, "A single mixed recording needs an LLM to attribute speakers; "
                                     "configure one or upload separate doctor/patient recordings.")
        channels = [(str(await _save_audio(mixed_audio, audio_dir, "mixed")), UNATTRIBUTED, "mixed")]
        stages = ["transcribing", "attributing_speakers", "extracting", "grounding", "plausibility", "done"]
        source_ref = mixed_audio.filename
    else:
        raise HTTPException(400, "mode must be 'separate' or 'mixed'.")

    job_holder: Dict[str, Any] = {}

    def load_segments():
        job = job_holder["job"]
        _job_update(job, stage="transcribing", progress=0.0)
        segments, asr_meta = transcribe_consultation(
            channels, progress=lambda f: _job_update(job, progress=round(f, 3)))
        if not segments:
            raise ValueError("No speech was recognised in the recording.")
        if mode == "mixed":
            _job_update(job, stage="attributing_speakers", progress=None)
            segments = attribute_speakers(segments)
        return segments, {"input_mode": "audio", "speaker_roles": "channel" if mode == "separate"
                          else "llm_attribution", **asr_meta}

    job = _new_job(doctor["id"], patient_id, stages)
    job_holder["job"] = job
    threading.Thread(target=_run_job, daemon=True,
                     args=(job, title, "audio", source_ref, use_llm, run_id, load_segments)).start()
    return {"job_id": job["id"]}


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
    case_path, _ = _run_paths(case_row["run_id"])
    return {
        "case_id": case_row["id"],
        "run_id": case_row["run_id"],
        "title": case_row["title"],
        "case": load_case(str(case_path)),
        "calibration": _calibration_view(doctor["id"]),
    }


class ResolveRequest(BaseModel):
    fact_id: str
    decision: str


@app.post("/api/cases/{case_id}/resolve")
def resolve(case_id: int, req: ResolveRequest, doctor=Depends(get_current_doctor)):
    conn = db.get_conn()
    case_row = _own_case_or_404(conn, case_id, doctor["id"])
    conn.close()

    case_path, audit_path = _run_paths(case_row["run_id"])
    with CALIBRATION_LOCK:
        pipeline_case = load_case(str(case_path))
        try:
            pipeline_case = resolve_fact(pipeline_case, req.fact_id, req.decision, doctor["name"],
                                          audit_path=str(audit_path),
                                          calibration_path=str(_calibration_path(doctor["id"])))
        except ValueError as e:
            raise HTTPException(400, str(e))
        save_case(pipeline_case, str(case_path))

    return {"case": pipeline_case, "calibration": _calibration_view(doctor["id"])}


@app.get("/api/cases/{case_id}/audit")
def audit(case_id: int, doctor=Depends(get_current_doctor)):
    conn = db.get_conn()
    case_row = _own_case_or_404(conn, case_id, doctor["id"])
    conn.close()
    _, audit_path = _run_paths(case_row["run_id"])
    return AuditLog(str(audit_path)).read_all()


@app.get("/api/cases/{case_id}/audio/{source}")
def case_audio(case_id: int, source: str, doctor=Depends(get_current_doctor)):
    """Stream a case's recording so any transcript segment can be played back."""
    conn = db.get_conn()
    case_row = _own_case_or_404(conn, case_id, doctor["id"])
    conn.close()
    if source not in ("doctor", "patient", "mixed"):
        raise HTTPException(404, "Unknown audio source.")
    matches = list((RUNS_DIR / case_row["run_id"] / "audio").glob(f"{source}.*"))
    if not matches:
        raise HTTPException(404, "This case has no such recording.")
    return FileResponse(matches[0])


def _preload_models():
    """Load the NLI and ASR models in the background at startup so the first
    case does not pay the load time. Failures are logged, not fatal: the
    affected stage reports its own error when it runs."""
    for name, load in (("NLI", lambda: score_pairs([("a", "a")])), ("ASR", _get_asr_model)):
        try:
            with PIPELINE_LOCK:
                load()
            print(f"[preload] {name} model ready", flush=True)
        except Exception as e:
            print(f"[preload] {name} model failed to load: {e}", flush=True)


web_dir = ROOT / "web"
if web_dir.exists():
    app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8420, reload=False)

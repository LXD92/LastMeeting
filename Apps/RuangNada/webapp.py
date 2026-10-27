import asyncio
import json
import os
import shutil
import sqlite3
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, contextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import music_downloader as legacy
from media_service import (
    AUDIO_FORMATS,
    IMAGE_FORMATS,
    MAX_IMAGE_BYTES,
    VIDEO_FORMATS,
    DownloadTooLarge,
    JobCancelled,
    analyze_media,
    convert_image,
    process_media,
    safe_filename,
    validate_youtube_url,
)


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
DATA_DIR = Path(os.environ.get("MUSIC_WEB_DATA_DIR", APP_DIR / ".data")).expanduser()
OUTPUT_DIR = Path(os.environ.get("MUSIC_DOWNLOAD_DIR", legacy.DOWNLOAD_DIR)).expanduser()
JOB_LIMIT = 4
FILE_TTL_SECONDS = 24 * 60 * 60
jobs = {}
jobs_lock = threading.Lock()


class AnalyzeRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


class DownloadRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    kind: Literal["audio", "video"]
    format: str
    preset: Literal["automatic", "economy", "standard", "high", "custom"] = "standard"
    bitrate: int = Field(default=192, ge=64, le=320)
    sample_rate: Literal[0, 22050, 44100, 48000] = 0
    channels: Literal[0, 1, 2] = 0
    audio_mode: Literal["vbr", "cbr"] = "vbr"
    encoder_quality: int = Field(default=5, ge=0, le=10)
    video_height: int = Field(default=0, ge=0, le=4320)
    filename: str = Field(default="", max_length=180)


@contextmanager
def _connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATA_DIR / "history.sqlite3", timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _initialize_db():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with _connect() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS history (
                job_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL,
                stage TEXT NOT NULL,
                kind TEXT NOT NULL,
                source_url TEXT,
                output_format TEXT,
                file_id TEXT,
                file_path TEXT,
                details TEXT,
                error TEXT,
                progress INTEGER,
                downloaded INTEGER,
                total INTEGER,
                speed REAL,
                eta INTEGER
            )
        """)
        connection.execute(
            "UPDATE history SET status='failed', stage='failed', "
            "error='Server dimulai ulang sebelum pekerjaan selesai.' "
            "WHERE status IN ('queued', 'running')"
        )
    _cleanup_expired_files()


def _timestamp(value=None):
    return datetime.fromtimestamp(value or time.time(), timezone.utc).isoformat()


def _safe_output_path(raw_path):
    if not raw_path:
        return None
    output_root = OUTPUT_DIR.resolve()
    path = Path(raw_path).resolve()
    try:
        path.relative_to(output_root)
    except ValueError:
        return None
    return path


def _cleanup_expired_files():
    expires_before = _timestamp(time.time() - FILE_TTL_SECONDS)
    with _connect() as connection:
        expired_paths = [
            row["file_path"]
            for row in connection.execute(
                "SELECT file_path FROM history WHERE updated_at < ? AND file_path IS NOT NULL",
                (expires_before,),
            ).fetchall()
        ]
        connection.execute(
            "UPDATE history SET file_path=NULL WHERE updated_at < ?",
            (expires_before,),
        )
    for raw_path in expired_paths:
        path = _safe_output_path(raw_path)
        if path and path.is_file():
            path.unlink()


async def _cleanup_loop():
    while True:
        await asyncio.sleep(60 * 60)
        await asyncio.to_thread(_cleanup_expired_files)


def _update_job(job_id, **changes):
    with jobs_lock:
        job = jobs.get(job_id)
        if job is None:
            return
        job.update(changes)
        snapshot = dict(job)
    with _connect() as connection:
        connection.execute(
            "UPDATE history SET updated_at=?, status=?, stage=?, error=?, progress=?, "
            "downloaded=?, total=?, speed=?, eta=? WHERE job_id=?",
            (
                _timestamp(), snapshot["status"], snapshot["stage"], snapshot.get("error"),
                snapshot.get("progress"), snapshot.get("downloaded"), snapshot.get("total"),
                snapshot.get("speed"), snapshot.get("eta"), job_id,
            ),
        )


def _record_result(job_id, status, stage, details=None, file_id=None, file_path=None, error=None):
    _update_job(
        job_id,
        status=status,
        stage=stage,
        details=details,
        file_id=file_id,
        file_path=file_path,
        error=error,
        progress=100 if status == "completed" else None,
    )
    with _connect() as connection:
        connection.execute(
            "UPDATE history SET details=?, file_id=?, file_path=?, error=? WHERE job_id=?",
            (
                json.dumps(details, ensure_ascii=False) if details else None,
                file_id,
                file_path,
                error,
                job_id,
            ),
        )


def _run_job(job_id):
    with jobs_lock:
        job = jobs[job_id]
        cancel_event = job["cancel_event"]
        payload = job["payload"]
    work_dir = Path(tempfile.mkdtemp(prefix=f"{job_id}_", dir=DATA_DIR))
    try:
        if cancel_event.is_set():
            raise JobCancelled()
        _update_job(job_id, status="running", stage="validating")
        if job["kind"] == "image":
            output, details = convert_image(
                payload["data"], payload["format"], payload["filename"], OUTPUT_DIR,
                job_id, cancel_event, lambda **state: _update_job(job_id, **state),
            )
        else:
            output, details = process_media(
                payload, work_dir, OUTPUT_DIR, job_id, cancel_event,
                lambda **state: _update_job(job_id, **state),
            )
        if cancel_event.is_set():
            output.unlink(missing_ok=True)
            raise JobCancelled()
        file_id = uuid.uuid4().hex
        _record_result(
            job_id, "completed", "completed", details, file_id, str(output), None,
        )
    except JobCancelled:
        _record_result(job_id, "cancelled", "cancelled", error="Pekerjaan dibatalkan.")
    except DownloadTooLarge as error:
        _record_result(job_id, "failed", "failed", error=str(error))
    except Exception as error:
        _record_result(job_id, "failed", "failed", error=str(error)[:500])
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
        with jobs_lock:
            finished = jobs.get(job_id)
            if finished and finished["status"] not in {"queued", "running"}:
                jobs.pop(job_id, None)


def _create_job(kind, payload, source_url=None):
    now = _timestamp()
    job_id = uuid.uuid4().hex
    job = {
        "job_id": job_id,
        "created_at": now,
        "updated_at": now,
        "status": "queued",
        "stage": "queued",
        "kind": kind,
        "source_url": source_url,
        "output_format": payload["format"],
        "file_id": None,
        "file_path": None,
        "details": None,
        "error": None,
        "progress": None,
        "downloaded": 0,
        "total": None,
        "speed": None,
        "eta": None,
        "payload": payload,
        "cancel_event": threading.Event(),
    }
    with jobs_lock:
        active = sum(item["status"] in {"queued", "running"} for item in jobs.values())
        if active >= JOB_LIMIT:
            raise HTTPException(429, "Batas pekerjaan aktif tercapai. Tunggu hingga pekerjaan selesai.")
        jobs[job_id] = job
    with _connect() as connection:
        connection.execute(
            "INSERT INTO history (job_id, created_at, updated_at, status, stage, kind, "
            "source_url, output_format, progress, downloaded) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (job_id, now, now, "queued", "queued", kind, source_url, payload["format"], None, 0),
        )
    if app.state.executor is None:
        raise HTTPException(503, "Pemroses pekerjaan belum siap. Muat ulang halaman.")
    app.state.executor.submit(_run_job, job_id)
    return {"job_id": job_id, "status": "queued"}


def _history_item(row):
    result = dict(row)
    result["details"] = json.loads(result["details"]) if result.get("details") else None
    file_path = _safe_output_path(result.get("file_path"))
    result["available"] = bool(file_path and file_path.is_file())
    result.pop("file_path", None)
    return result


@asynccontextmanager
async def lifespan(application):
    application.state.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="music-job")
    _initialize_db()
    cleanup_task = asyncio.create_task(_cleanup_loop())
    try:
        yield
    finally:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task
        application.state.executor.shutdown(wait=False, cancel_futures=True)
        application.state.executor = None


app = FastAPI(title="Ruang Nada", version="1.0.0", lifespan=lifespan)


@app.get("/api/health")
def health():
    return {"status": "ok", "ffmpeg": bool(legacy.find_ffmpeg())}


@app.post("/api/analyze")
def analyze(request: AnalyzeRequest):
    try:
        return analyze_media(request.url)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except RuntimeError as error:
        raise HTTPException(503, str(error)) from error


@app.post("/api/download")
def download(request: DownloadRequest):
    try:
        url = validate_youtube_url(request.url)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    if request.kind == "audio" and request.format not in AUDIO_FORMATS:
        raise HTTPException(422, "Pilih format audio yang tersedia.")
    if request.kind == "video" and request.format not in VIDEO_FORMATS:
        raise HTTPException(422, "Pilih format video yang tersedia.")
    payload = request.model_dump()
    payload["url"] = url
    payload["filename"] = safe_filename(payload["filename"] or "media")
    return _create_job("video" if request.kind == "video" else "audio", payload, url)


@app.post("/api/images/convert")
async def convert_uploaded_image(request: Request, format: str = "png", filename: str = "gambar.png"):
    if format not in IMAGE_FORMATS:
        raise HTTPException(422, "Format gambar yang didukung: JPG, PNG, atau WEBP.")
    declared_size = request.headers.get("content-length")
    if declared_size:
        try:
            if int(declared_size) > MAX_IMAGE_BYTES:
                raise HTTPException(413, "Ukuran gambar unggahan maksimal 25 MB.")
        except ValueError as error:
            raise HTTPException(400, "Header ukuran unggahan tidak valid.") from error
    chunks = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_IMAGE_BYTES:
            raise HTTPException(413, "Ukuran gambar unggahan maksimal 25 MB.")
        chunks.append(chunk)
    if not total:
        raise HTTPException(400, "Pilih file gambar terlebih dahulu.")
    payload = {"format": format, "filename": safe_filename(filename)}
    return _create_job("image", {**payload, "data": b"".join(chunks)})


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if job:
            snapshot = dict(job)
            snapshot.pop("payload", None)
            snapshot.pop("cancel_event", None)
            snapshot.pop("file_path", None)
            return snapshot
    with _connect() as connection:
        row = connection.execute(
            "SELECT job_id, created_at, updated_at, status, stage, kind, source_url, output_format, "
            "file_id, details, error, progress, downloaded, total, speed, eta "
            "FROM history WHERE job_id=?",
            (job_id,),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Pekerjaan tidak ditemukan.")
    result = dict(row)
    result["details"] = json.loads(result["details"]) if result["details"] else None
    return result


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(404, "Pekerjaan tidak ditemukan atau server telah dimulai ulang.")
        if job["status"] not in {"queued", "running"}:
            raise HTTPException(409, "Pekerjaan sudah selesai dan tidak dapat dibatalkan.")
        job["cancel_event"].set()
    return {"job_id": job_id, "status": "cancelling"}


@app.get("/api/files/{file_id}")
def download_file(file_id: str):
    with _connect() as connection:
        row = connection.execute(
            "SELECT file_path, details FROM history WHERE file_id=? AND status='completed'",
            (file_id,),
        ).fetchone()
    if not row:
        raise HTTPException(404, "File tidak ditemukan atau masa simpannya telah berakhir.")
    path = _safe_output_path(row["file_path"])
    if not path or not path.is_file():
        raise HTTPException(404, "File tidak tersedia. Proses ulang media untuk mengunduh kembali.")
    details = json.loads(row["details"] or "{}")
    return FileResponse(path, filename=details.get("filename", path.name))


@app.get("/api/history")
def history():
    with _connect() as connection:
        rows = connection.execute(
            "SELECT job_id, created_at, updated_at, status, stage, kind, source_url, "
            "output_format, file_id, file_path, details, error, progress "
            "FROM history ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
    return {"items": [_history_item(row) for row in rows]}


@app.delete("/api/history/{job_id}")
def delete_history(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if job and job["status"] in {"queued", "running"}:
            raise HTTPException(409, "Batalkan pekerjaan sebelum menghapus riwayatnya.")
    with _connect() as connection:
        row = connection.execute(
            "SELECT file_path FROM history WHERE job_id=?", (job_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Riwayat tidak ditemukan.")
        file_path = _safe_output_path(row["file_path"])
        connection.execute("DELETE FROM history WHERE job_id=?", (job_id,))
    if file_path and file_path.is_file():
        file_path.unlink()
    with jobs_lock:
        jobs.pop(job_id, None)
    return {"job_id": job_id, "deleted": True}


@app.get("/")
def home():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

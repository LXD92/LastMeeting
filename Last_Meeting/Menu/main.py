import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from Menu.core.app_registry import discover_apps
from Menu.core.config_manager import ConfigManager
from Menu.core.process_manager import LaunchError, ProcessManager


MENU_DIR = Path(__file__).resolve().parent
ROOT_DIR = MENU_DIR.parent
APPS_DIR = ROOT_DIR / "Apps"
MATERIAL_DIR = ROOT_DIR / "Material"
FRONTEND_DIR = MENU_DIR / "frontend"
DATA_DIR = MENU_DIR / "data"
LOG_DIR = MENU_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=LOG_DIR / "launcher.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    encoding="utf-8",
)
LOGGER = logging.getLogger(__name__)
preferences = ConfigManager(DATA_DIR / "preferences.json")
process_manager = ProcessManager(LOG_DIR / "apps")


class PreferenceUpdate(BaseModel):
    theme: str | None = None
    view: str | None = None
    favorites: list[str] | None = None
    recent: list[str] | None = None
    order: list[str] | None = None
    sort: str | None = None
    category: str | None = None


@asynccontextmanager
async def lifespan(_application):
    yield
    process_manager.stop_all()


app = FastAPI(title="Last_Meeting", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def local_request_guard(request: Request, call_next):
    host = request.headers.get("host", "").split(":", 1)[0].strip("[]").lower()
    if host not in {"127.0.0.1", "localhost"}:
        return JSONResponse({"detail": "Launcher hanya menerima permintaan lokal."}, status_code=400)
    origin = request.headers.get("origin")
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and origin:
        parsed_origin = urlparse(origin)
        if parsed_origin.netloc.lower() != request.headers.get("host", "").lower():
            return JSONResponse({"detail": "Asal permintaan tidak diizinkan."}, status_code=403)
    return await call_next(request)


def _static_app_url(request: Request, app_data: dict):
    if app_data["launch"] != "static" or not app_data["entry"]:
        return app_data.get("url") or ""
    entry_path = Path(app_data["entry"]).as_posix()
    relative_entry = entry_path.replace(str(Path(app_data["path"]).resolve().as_posix()), "", 1).lstrip("/")
    if relative_entry.startswith("/"):
        relative_entry = relative_entry.lstrip("/")
    if not relative_entry:
        relative_entry = Path(app_data["entry"]).name
    return f"{request.url.scheme}://{request.url.netloc}/apps/{app_data['id']}/{relative_entry}"


def _public_app(request: Request, app_data: dict, prefs: dict, statuses: dict):
    result = {
        key: app_data[key]
        for key in (
            "id", "name", "description", "category", "runtime", "launch",
            "url", "icon", "configured", "config_error",
        )
    }
    result["favorite"] = app_data["id"] in prefs["favorites"]
    result["running"] = statuses.get(app_data["id"]) == "running"
    result["recent"] = app_data["id"] in prefs["recent"]
    if app_data["launch"] == "static" and app_data["entry"]:
        result["url"] = _static_app_url(request, app_data)
    return result


def _read_preferences():
    prefs = preferences.read()
    if not preferences.path.exists():
        prefs["favorites"] = [
            item["id"] for item in discover_apps(APPS_DIR) if item["favorite"]
        ]
    return prefs


def _write_preferences(updates: dict):
    if not preferences.path.exists():
        updates = {**_read_preferences(), **updates}
    return preferences.write(updates)


@app.get("/api/health")
def health():
    return {"status": "ok", "managed_running": sum(
        status == "running" for status in process_manager.statuses().values()
    )}


@app.get("/api/apps")
def list_apps(request: Request):
    prefs = _read_preferences()
    statuses = process_manager.statuses()
    apps = [
        _public_app(request, app_data, prefs, statuses)
        for app_data in discover_apps(APPS_DIR)
    ]
    order = {app_id: index for index, app_id in enumerate(prefs["order"])}
    if prefs["sort"] == "favorites":
        apps.sort(key=lambda item: (
            item["id"] not in prefs["favorites"],
            order.get(item["id"], len(order)),
            item["name"].casefold(),
        ))
    elif prefs["sort"] == "recent":
        recent_order = {app_id: index for index, app_id in enumerate(prefs["recent"])}
        apps.sort(key=lambda item: (
            item["id"] not in recent_order,
            recent_order.get(item["id"], len(recent_order)),
            item["name"].casefold(),
        ))
    else:
        apps.sort(key=lambda item: (order.get(item["id"], len(order)), item["name"].casefold()))
    categories = sorted({item["category"] for item in apps})
    return {
        "items": apps,
        "categories": categories,
        "preferences": prefs,
        "managed_running": sum(item["running"] for item in apps),
    }


@app.post("/api/apps/{app_id}/launch")
def launch_app(app_id: str, request: Request):
    app_data = next(
        (item for item in discover_apps(APPS_DIR) if item["id"] == app_id),
        None,
    )
    if app_data is None:
        raise HTTPException(404, "Aplikasi tidak ditemukan.")
    try:
        result = process_manager.launch(app_data)
    except LaunchError as error:
        LOGGER.error("Gagal meluncurkan %s: %s", app_id, error)
        raise HTTPException(400, str(error)) from error

    if app_data["launch"] == "static" and app_data["entry"] and result.get("status") in {"opened", "running"}:
        result["url"] = _static_app_url(request, app_data)
    prefs = _read_preferences()
    recent = [item for item in prefs["recent"] if item != app_id]
    recent.insert(0, app_id)
    _write_preferences({"recent": recent[:12]})
    return result


@app.post("/api/apps/{app_id}/stop")
def stop_app(app_id: str):
    known_ids = {item["id"] for item in discover_apps(APPS_DIR)}
    if app_id not in known_ids and process_manager.statuses().get(app_id) != "running":
        raise HTTPException(404, "Aplikasi tidak ditemukan.")
    try:
        return process_manager.stop(app_id)
    except LaunchError as error:
        LOGGER.exception("Gagal menghentikan %s", app_id)
        raise HTTPException(500, str(error)) from error


@app.put("/api/preferences")
def update_preferences(update: PreferenceUpdate):
    values = update.model_dump(exclude_none=True)
    if values.get("theme") not in {None, "dark", "light"}:
        raise HTTPException(422, "Tema harus dark atau light.")
    if values.get("view") not in {None, "grid", "list"}:
        raise HTTPException(422, "Tampilan harus grid atau list.")
    if values.get("sort") not in {None, "name", "favorites", "recent"}:
        raise HTTPException(422, "Urutan harus name, favorites, atau recent.")
    apps = discover_apps(APPS_DIR)
    app_ids = {item["id"] for item in apps}
    for key in ("favorites", "recent", "order"):
        if key in values:
            values[key] = list(dict.fromkeys(values[key]))
            if any(app_id not in app_ids for app_id in values[key]):
                raise HTTPException(422, f"{key} berisi ID aplikasi yang tidak dikenal.")
    if "category" in values and not isinstance(values["category"], str):
        raise HTTPException(422, "category harus berupa teks.")
    try:
        return _write_preferences(values)
    except OSError as error:
        LOGGER.exception("Gagal menyimpan preferensi")
        raise HTTPException(500, "Preferensi gagal disimpan.") from error


@app.get("/api/material")
def list_material():
    if not MATERIAL_DIR.is_dir():
        return {"categories": []}
    categories = []
    for folder in sorted(MATERIAL_DIR.iterdir(), key=lambda item: item.name.casefold()):
        if folder.is_dir():
            categories.append({
                "name": folder.name,
                "path": str(folder.resolve()),
                "items": sum(1 for child in folder.iterdir() if child.is_file()),
            })
    return {"categories": categories}


@app.get("/")
def home():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/apps/{app_id}/{file_path:path}")
def serve_app_file(app_id: str, file_path: str):
    app_data = next((item for item in discover_apps(APPS_DIR) if item["id"] == app_id), None)
    if app_data is None or not app_data.get("configured"):
        raise HTTPException(404, "Aplikasi tidak ditemukan.")
    base_dir = Path(app_data["path"]).resolve()
    candidate = (base_dir / file_path).resolve()
    try:
        candidate.relative_to(base_dir)
    except ValueError as error:
        raise HTTPException(403, "Path aplikasi tidak diizinkan.") from error
    if not candidate.is_file():
        raise HTTPException(404, "File aplikasi tidak ditemukan.")
    return FileResponse(candidate)


@app.get("/apps/{app_id}")
def serve_app_root(app_id: str):
    app_data = next((item for item in discover_apps(APPS_DIR) if item["id"] == app_id), None)
    if app_data is None or not app_data.get("configured"):
        raise HTTPException(404, "Aplikasi tidak ditemukan.")
    entry_name = Path(app_data["entry"]).name if app_data.get("entry") else "index.html"
    return serve_app_file(app_id, entry_name)


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

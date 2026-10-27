import json
import logging
import re
from pathlib import Path
from urllib.parse import urlparse


LOGGER = logging.getLogger(__name__)
APP_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
ENV_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ALLOWED_FIELDS = {
    "id",
    "name",
    "description",
    "category",
    "entry",
    "runtime",
    "launch",
    "module",
    "args",
    "working_directory",
    "interpreter",
    "env",
    "url",
    "health_path",
    "port",
    "icon",
    "favorite",
    "dependencies",
}


class ManifestError(ValueError):
    pass


def _relative_path(root: Path, value: str, label: str, *, required: bool = True):
    if not value and not required:
        return None
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ManifestError(f"{label} harus berupa path relatif.")
    candidate = Path(value)
    if candidate.is_absolute() or any(part in {"..", ""} for part in candidate.parts):
        raise ManifestError(f"{label} harus berada di dalam folder aplikasi.")
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as error:
        raise ManifestError(f"{label} keluar dari folder aplikasi.") from error
    return resolved


def _validate_manifest(root: Path, raw: object):
    if not isinstance(raw, dict):
        raise ManifestError("Isi app.json harus berupa objek JSON.")
    unknown = set(raw) - ALLOWED_FIELDS
    if unknown:
        raise ManifestError(f"Properti tidak dikenal: {', '.join(sorted(unknown))}.")

    app_id = raw.get("id")
    if not isinstance(app_id, str) or not APP_ID_PATTERN.fullmatch(app_id):
        raise ManifestError("id harus unik dan hanya berisi huruf kecil, angka, _ atau -.")
    for key in ("name", "description", "category"):
        if not isinstance(raw.get(key, ""), str):
            raise ManifestError(f"{key} harus berupa teks.")

    runtime = raw.get("runtime")
    launch = raw.get("launch")
    if (runtime, launch) not in {
        ("python", "module"),
        ("python", "script"),
        ("node", "script"),
        ("browser", "static"),
    }:
        raise ManifestError("Kombinasi runtime dan launch tidak didukung.")

    entry = _relative_path(root, raw.get("entry", ""), "entry")
    if not entry.is_file():
        raise ManifestError("Entry point tidak ditemukan.")
    working_directory = _relative_path(
        root, raw.get("working_directory", "."), "working_directory"
    )
    if not working_directory.is_dir():
        raise ManifestError("working_directory tidak ditemukan.")

    module = raw.get("module", "")
    if launch == "module" and (
        not isinstance(module, str)
        or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", module)
    ):
        raise ManifestError("module harus berupa nama modul Python yang valid.")
    if launch != "module" and module:
        raise ManifestError("module hanya berlaku untuk launch=module.")

    args = raw.get("args", [])
    if not isinstance(args, list) or not all(
        isinstance(value, str) and "\x00" not in value for value in args
    ):
        raise ManifestError("args harus berupa daftar teks.")
    if launch in {"static", "script"} and runtime == "browser" and args:
        raise ManifestError("Aplikasi browser statis tidak menerima args.")

    interpreter_value = raw.get("interpreter", "")
    interpreter = None
    if interpreter_value:
        interpreter = _relative_path(root, interpreter_value, "interpreter")
        if not interpreter.is_file():
            raise ManifestError("Interpreter yang dikonfigurasi tidak ditemukan.")

    env = raw.get("env", {})
    if not isinstance(env, dict) or not all(
        isinstance(key, str)
        and ENV_KEY_PATTERN.fullmatch(key)
        and isinstance(value, str)
        and "\x00" not in value
        for key, value in env.items()
    ):
        raise ManifestError("env harus berupa objek dengan nama dan nilai teks yang valid.")

    dependencies = raw.get("dependencies", [])
    if not isinstance(dependencies, list) or not all(
        isinstance(value, str)
        and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value)
        for value in dependencies
    ):
        raise ManifestError("dependencies harus berupa nama modul Python.")

    port = raw.get("port")
    if port is not None and (not isinstance(port, int) or not 1 <= port <= 65535):
        raise ManifestError("port harus berupa bilangan antara 1 dan 65535.")
    favorite = raw.get("favorite", False)
    if not isinstance(favorite, bool):
        raise ManifestError("favorite harus berupa nilai boolean.")

    url = raw.get("url", "")
    if url:
        if not isinstance(url, str) or not re.fullmatch(
            r"http://(?:127\.0\.0\.1|localhost):[0-9]{1,5}(?:/[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]*)?",
            url,
        ):
            raise ManifestError("url hanya boleh menggunakan HTTP localhost.")
        try:
            url_port = urlparse(url).port
        except ValueError as error:
            raise ManifestError("Port pada url tidak valid.") from error
        if url_port is None or not 1 <= url_port <= 65535:
            raise ManifestError("Port pada url harus antara 1 dan 65535.")
        if port is not None and not url.startswith(
            (f"http://127.0.0.1:{port}", f"http://localhost:{port}")
        ):
            raise ManifestError("Port pada url harus sama dengan properti port.")
    health_path = raw.get("health_path", "")
    if health_path and (
        not isinstance(health_path, str)
        or not health_path.startswith("/")
        or health_path.startswith("//")
        or ".." in Path(health_path).parts
        or "\x00" in health_path
    ):
        raise ManifestError("health_path harus berupa path lokal yang valid.")

    icon_value = raw.get("icon", "")
    icon = _relative_path(root, icon_value, "icon", required=False) if icon_value else None
    if icon and not icon.is_file():
        icon = None

    return {
        "id": app_id,
        "name": raw.get("name") or root.name,
        "description": raw.get("description", ""),
        "category": raw.get("category") or "Lainnya",
        "entry": entry,
        "runtime": runtime,
        "launch": launch,
        "module": module,
        "args": args,
        "working_directory": working_directory,
        "interpreter": interpreter,
        "env": env,
        "url": url,
        "health_path": health_path,
        "port": port,
        "icon": str(icon) if icon else None,
        "favorite": favorite,
        "dependencies": dependencies,
        "configured": True,
        "config_error": None,
        "path": str(root),
    }


def _entrypoint_hints(root: Path):
    candidates = ("main.py", "app.py", "run.py", "index.html", "package.json")
    found = [name for name in candidates if (root / name).is_file()]
    found.extend(sorted(path.name for path in root.glob("*.exe") if path.is_file()))
    return found


def discover_apps(apps_dir: Path):
    apps_dir = apps_dir.resolve()
    apps = []
    seen_ids = set()
    if not apps_dir.is_dir():
        LOGGER.warning("Folder aplikasi tidak ditemukan: %s", apps_dir)
        return apps

    for folder in sorted(apps_dir.iterdir(), key=lambda item: item.name.casefold()):
        if not folder.is_dir():
            continue
        try:
            root = folder.resolve()
            root.relative_to(apps_dir)
        except (OSError, ValueError):
            LOGGER.warning("Folder aplikasi di luar Apps diabaikan: %s", folder)
            continue

        manifest_path = root / "app.json"
        if not manifest_path.is_file():
            hints = _entrypoint_hints(root)
            if not hints:
                LOGGER.info("Folder tanpa entry point aplikasi diabaikan: %s", root)
                continue
            apps.append({
                "id": f"unconfigured-{folder.name.casefold()}",
                "name": folder.name,
                "description": (
                    "Belum memiliki app.json. Petunjuk entry point: "
                    f"{', '.join(hints)}. Tinjau sebelum mendaftarkan."
                ),
                "category": "Belum dikonfigurasi",
                "entry": None,
                "runtime": None,
                "launch": None,
                "module": "",
                "args": [],
                "working_directory": str(root),
                "interpreter": None,
                "env": {},
                "url": "",
                "port": None,
                "icon": None,
                "favorite": False,
                "dependencies": [],
                "configured": False,
                "config_error": None,
                "path": str(root),
            })
            continue

        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            app = _validate_manifest(root, raw)
            if app["id"] in seen_ids:
                raise ManifestError(f"id aplikasi duplikat: {app['id']}.")
            seen_ids.add(app["id"])
        except (OSError, json.JSONDecodeError, ManifestError) as error:
            LOGGER.warning("Manifest %s tidak valid: %s", manifest_path, error)
            app = {
                "id": f"invalid-{folder.name.casefold()}",
                "name": folder.name,
                "description": "Manifest app.json tidak valid.",
                "category": "Konfigurasi bermasalah",
                "entry": None,
                "runtime": None,
                "launch": None,
                "module": "",
                "args": [],
                "working_directory": str(root),
                "interpreter": None,
                "env": {},
                "url": "",
                "port": None,
                "icon": None,
                "favorite": False,
                "dependencies": [],
                "configured": False,
                "config_error": str(error),
                "path": str(root),
            }
        apps.append(app)
    return apps

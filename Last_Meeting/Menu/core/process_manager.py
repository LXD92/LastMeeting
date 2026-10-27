import logging
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


LOGGER = logging.getLogger(__name__)


class LaunchError(RuntimeError):
    pass


class ProcessManager:
    def __init__(self, log_dir: Path):
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._processes = {}
        self._lock = threading.Lock()

    def _status_locked(self, app_id):
        process = self._processes.get(app_id)
        if process is None:
            return "stopped"
        if process.poll() is None:
            return "running"
        self._processes.pop(app_id, None)
        return "stopped"

    def statuses(self):
        with self._lock:
            return {app_id: self._status_locked(app_id) for app_id in list(self._processes)}

    @staticmethod
    def _check_python_dependencies(interpreter: Path, dependencies: list):
        if not dependencies:
            return
        probe = (
            "import importlib.util,sys; "
            "missing=[name for name in sys.argv[1:] "
            "if importlib.util.find_spec(name) is None]; "
            "print(','.join(missing)); sys.exit(bool(missing))"
        )
        try:
            result = subprocess.run(
                [str(interpreter), "-c", probe, *dependencies],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise LaunchError(f"Pemeriksaan dependensi gagal: {error}") from error
        if result.returncode:
            missing = result.stdout.strip() or ", ".join(dependencies)
            raise LaunchError(
                f"Dependensi belum tersedia ({missing}). Instal sesuai requirements.txt aplikasi."
            )

    def launch(self, app: dict):
        if not app["configured"]:
            raise LaunchError(app.get("config_error") or "Aplikasi belum memiliki app.json.")

        app_id = app["id"]
        with self._lock:
            if self._status_locked(app_id) == "running":
                return {"status": "running", "url": app["url"], "message": "Aplikasi sudah berjalan."}

            if app["launch"] == "static":
                return {"status": "opened", "url": app["url"], "message": "Aplikasi dibuka di browser."}

            health_path = app.get("health_path")
            if app["url"] and health_path:
                try:
                    with urlopen(f"{app['url'].rstrip('/')}{health_path}", timeout=0.5) as response:
                        health = json.loads(response.read(4096))
                    if isinstance(health, dict) and health.get("status") == "ok":
                        return {
                            "status": "external",
                            "url": app["url"],
                            "message": "Server sudah berjalan di luar launcher; proses tersebut tidak dikelola atau dihentikan oleh launcher.",
                        }
                except (AttributeError, OSError, TypeError, ValueError, json.JSONDecodeError):
                    pass

            if app["runtime"] == "python":
                interpreter = app["interpreter"]
                if interpreter is None:
                    raise LaunchError("Konfigurasi interpreter Python belum tersedia.")
                self._check_python_dependencies(interpreter, app["dependencies"])
                if app["launch"] == "module":
                    command = [str(interpreter), "-m", app["module"], *app["args"]]
                else:
                    command = [str(interpreter), str(app["entry"]), *app["args"]]
            elif app["runtime"] == "node" and app["launch"] == "script":
                node = shutil.which("node")
                if not node:
                    raise LaunchError("Node.js tidak ditemukan di PATH.")
                command = [node, str(app["entry"]), *app["args"]]
            else:
                raise LaunchError("Metode peluncuran ini tidak didukung.")

            environment = os.environ.copy()
            environment.update(app["env"])
            log_path = self.log_dir / f"{app_id}.log"
            try:
                log_file = log_path.open("a", encoding="utf-8", buffering=1)
                try:
                    process = subprocess.Popen(
                        command,
                        cwd=app["working_directory"],
                        env=environment,
                        stdin=subprocess.DEVNULL,
                        stdout=log_file,
                        stderr=subprocess.STDOUT,
                        shell=False,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                finally:
                    log_file.close()
            except OSError as error:
                LOGGER.exception("Gagal memulai aplikasi %s", app_id)
                raise LaunchError(f"Aplikasi gagal dijalankan: {error}") from error
            time.sleep(0.25)
            if process.poll() is not None:
                try:
                    details = log_path.read_text(encoding="utf-8", errors="replace")[-1200:]
                except OSError as error:
                    LOGGER.warning("Log aplikasi %s tidak dapat dibaca: %s", app_id, error)
                    details = ""
                message = "Aplikasi berhenti saat proses startup."
                if details:
                    message = f"{message} {details.strip()}"
                raise LaunchError(message)
            self._processes[app_id] = process

        return {
            "status": "running",
            "url": app["url"],
            "message": "Aplikasi berhasil dimulai.",
            "log": str(log_path),
        }

    def stop(self, app_id: str):
        with self._lock:
            process = self._processes.get(app_id)
            if process is None or process.poll() is not None:
                self._processes.pop(app_id, None)
                return {"status": "stopped", "message": "Aplikasi tidak sedang berjalan."}
            try:
                process.terminate()
            except OSError as error:
                if process.poll() is None:
                    raise LaunchError(f"Aplikasi gagal dihentikan dengan aman: {error}") from error
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired) as error:
                if process.poll() is None:
                    raise LaunchError(f"Aplikasi tidak berhenti setelah diminta: {error}") from error
        with self._lock:
            self._processes.pop(app_id, None)
        return {"status": "stopped", "message": "Aplikasi dihentikan."}

    def stop_all(self):
        with self._lock:
            app_ids = list(self._processes)
        for app_id in app_ids:
            try:
                self.stop(app_id)
            except LaunchError:
                LOGGER.exception("Gagal menghentikan aplikasi %s saat launcher ditutup", app_id)

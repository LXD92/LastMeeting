import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from Menu.core.app_registry import ManifestError, _validate_manifest, discover_apps
from Menu.core.config_manager import ConfigManager
from Menu.core.process_manager import ProcessManager
from Menu import main


ROOT = Path(__file__).resolve().parents[2]


class RegistryTests(unittest.TestCase):
    def test_discovers_the_two_configured_projects(self):
        apps = discover_apps(ROOT / "Apps")
        self.assertEqual({item["id"] for item in apps}, {"hanacaraka", "ruangnada"})
        self.assertTrue(all(item["configured"] for item in apps))

    def test_rejects_paths_outside_application(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "main.py").write_text("print('ok')", encoding="utf-8")
            with self.assertRaises(ManifestError):
                _validate_manifest(root, {
                    "id": "escape",
                    "runtime": "python",
                    "launch": "script",
                    "entry": "../outside.py",
                })

    def test_ignores_asset_only_folders_and_reports_entrypoint_hints(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            apps_dir = Path(temp_dir)
            docs = apps_dir / "docs-only"
            docs.mkdir()
            (docs / "README.md").write_text("Notes", encoding="utf-8")
            candidate = apps_dir / "new-project"
            candidate.mkdir()
            (candidate / "main.py").write_text("print('not executed')", encoding="utf-8")
            apps = discover_apps(apps_dir)
        self.assertEqual(len(apps), 1)
        self.assertFalse(apps[0]["configured"])
        self.assertIn("main.py", apps[0]["description"])

    def test_corrupt_preferences_fall_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "preferences.json"
            path.write_text("{", encoding="utf-8")
            self.assertEqual(ConfigManager(path).read()["theme"], "dark")

    def test_duplicate_launch_is_not_started_twice(self):
        class FakeProcess:
            terminated = False

            def poll(self):
                return 0 if self.terminated else None

            def terminate(self):
                self.terminated = True

            def wait(self, timeout):
                return 0

            def kill(self):
                self.terminated = True

        manager = ProcessManager(Path(tempfile.mkdtemp()))
        app = {
            "id": "test",
            "configured": True,
            "launch": "script",
            "runtime": "node",
            "interpreter": None,
            "entry": Path("app.js"),
            "args": [],
            "working_directory": Path("."),
            "env": {},
            "dependencies": [],
            "url": "",
        }
        with patch("Menu.core.process_manager.shutil.which", return_value="node.exe"), patch(
            "Menu.core.process_manager.subprocess.Popen", return_value=FakeProcess()
        ) as popen:
            manager.launch(app)
            result = manager.launch(app)
            stopped = manager.stop("test")
        self.assertEqual(result["status"], "running")
        self.assertEqual(stopped["status"], "stopped")
        popen.assert_called_once()


class ApiTests(unittest.TestCase):
    def test_catalog_preferences_and_material_endpoints(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            main, "preferences", ConfigManager(Path(temp_dir) / "preferences.json")
        ), TestClient(main.app, base_url="http://127.0.0.1") as client:
            catalog = client.get("/api/apps")
            self.assertEqual(catalog.status_code, 200)
            self.assertEqual(
                {item["id"] for item in catalog.json()["items"]},
                {"hanacaraka", "ruangnada"},
            )
            updated = client.put("/api/preferences", json={"theme": "light"})
            self.assertEqual(updated.status_code, 200)
            self.assertEqual(updated.json()["theme"], "light")
            self.assertEqual(client.get("/api/material").status_code, 200)

    def test_static_app_uses_http_url_for_browser_launch(self):
        with TestClient(main.app, base_url="http://127.0.0.1") as client:
            data = client.get("/api/apps").json()
        self.assertEqual(data["items"][0]["id"], "hanacaraka")
        self.assertTrue(data["items"][0]["url"].startswith("http://127.0.0.1/apps/hanacaraka/"))

    def test_cross_origin_launch_request_is_rejected(self):
        with TestClient(main.app, base_url="http://127.0.0.1") as client:
            response = client.post(
                "/api/apps/hanacaraka/launch",
                headers={"origin": "http://attacker.invalid"},
            )
        self.assertEqual(response.status_code, 403)

    def test_preference_update_keeps_manifest_favorites_by_default(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            main, "preferences", ConfigManager(Path(temp_dir) / "preferences.json")
        ), TestClient(main.app, base_url="http://127.0.0.1") as client:
            response = client.put("/api/preferences", json={"theme": "light"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["favorites"], ["ruangnada"])


if __name__ == "__main__":
    unittest.main()

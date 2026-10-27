import json
import logging
import os
from pathlib import Path


LOGGER = logging.getLogger(__name__)
DEFAULT_PREFERENCES = {
    "theme": "dark",
    "view": "grid",
    "favorites": [],
    "recent": [],
    "order": [],
    "sort": "name",
    "category": "Semua",
}


class ConfigManager:
    def __init__(self, path: Path):
        self.path = path

    def read(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return dict(DEFAULT_PREFERENCES)
        except (OSError, json.JSONDecodeError) as error:
            LOGGER.warning("Preferensi tidak dapat dibaca; memakai default: %s", error)
            return dict(DEFAULT_PREFERENCES)
        if not isinstance(data, dict):
            LOGGER.warning("Format preferensi tidak valid; memakai default.")
            return dict(DEFAULT_PREFERENCES)
        preferences = dict(DEFAULT_PREFERENCES)
        preferences.update(data)
        if preferences["theme"] not in {"dark", "light"}:
            preferences["theme"] = "dark"
        if preferences["view"] not in {"grid", "list"}:
            preferences["view"] = "grid"
        if preferences["sort"] not in {"name", "favorites", "recent"}:
            preferences["sort"] = "name"
        for key in ("favorites", "recent", "order"):
            if not isinstance(preferences[key], list) or not all(
                isinstance(item, str) for item in preferences[key]
            ):
                preferences[key] = []
        if not isinstance(preferences["category"], str):
            preferences["category"] = "Semua"
        return preferences

    def write(self, updates: dict):
        preferences = self.read()
        preferences.update(updates)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        try:
            temporary.write_text(
                json.dumps(preferences, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary, self.path)
        except OSError:
            temporary.unlink(missing_ok=True)
            raise
        return preferences

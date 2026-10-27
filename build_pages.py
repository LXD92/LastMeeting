import json
import os
import shutil
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "dist"
RUANGNADA_URL = os.environ.get("RUANGNADA_PUBLIC_URL", "").strip().rstrip("/")

if RUANGNADA_URL:
    parsed = urlparse(RUANGNADA_URL)
    if parsed.scheme != "https" or not parsed.netloc:
        raise SystemExit("RUANGNADA_PUBLIC_URL harus berupa URL HTTPS publik.")

if OUTPUT.exists():
    shutil.rmtree(OUTPUT)
shutil.copytree(ROOT / "Menu" / "frontend", OUTPUT)
shutil.copytree(
    ROOT / "Apps" / "Hanacaraka",
    OUTPUT / "apps" / "hanacaraka",
    ignore=shutil.ignore_patterns("README.md", "app.json"),
)

index_path = OUTPUT / "index.html"
index_path.write_text(
    index_path.read_text(encoding="utf-8")
    .replace('href="/static/style.css"', 'href="./style.css"')
    .replace('<script src="/static/app.js" defer></script>', '<script src="./pages-config.js"></script>\n  <script src="./app.js" defer></script>'),
    encoding="utf-8",
)
(OUTPUT / "pages-config.js").write_text(
    f"window.LAST_MEETING_CONFIG = {json.dumps({'useMenuApi': False, 'ruangNadaUrl': RUANGNADA_URL})};\n",
    encoding="utf-8",
)

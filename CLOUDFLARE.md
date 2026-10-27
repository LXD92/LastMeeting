# Cloudflare Pages deployment

## Compatibility audit

| Application | Stack | Build | Backend/runtime | Cloudflare Pages status |
| --- | --- | --- | --- | --- |
| Menu | HTML, CSS, vanilla JS; FastAPI local launcher | `python build_pages.py` creates `dist/` | Local mode reads folders, writes preferences, starts processes | Static catalog deploys. Local launcher remains separate. |
| Hanacaraka | HTML, CSS, vanilla JS | Copied unchanged to `dist/apps/hanacaraka/` | None | Compatible. |
| RuangNada | HTML/CSS/JS frontend; FastAPI/Python backend | No frontend build | yt-dlp, Pillow, FFmpeg, SQLite, local files, threads, long-running jobs | Not Pages-compatible. Deploy backend separately, then configure its HTTPS URL. |
| Material | Music files currently present | Not included | Filesystem/media assets | Not included. No image assets found. Music should use object storage/CDN if needed. |

## Architecture

Cloudflare Pages serves `dist/` only. `build_pages.py` copies the Menu frontend and Hanacaraka. It does not move virtual environments, logs, generated files, Material music, or the RuangNada Python service.

The production menu uses browser `localStorage` for theme, view, favorites, and recent apps. In local launcher mode it still calls the existing same-origin FastAPI `/api/*` endpoints.

RuangNada needs a separate trusted backend. It cannot run on Pages Functions or Workers because it depends on Python, yt-dlp, FFmpeg, SQLite/filesystem storage, worker threads, and long-running conversion/download jobs. A Worker can proxy or validate lightweight requests later, but must not run those jobs. Use a server/container service plus object storage and authentication/rate limits before public exposure.

## Build configuration

Cloudflare Pages dashboard:

- Framework preset: `None`
- Production branch: your GitHub default branch
- Root directory: repository root
- Build command: `python build_pages.py`
- Build output directory: `dist`
- Node version: not required

Cloudflare supports Python during builds. If a chosen Pages build image does not expose `python`, set build command to `python3 build_pages.py`.

## Environment variables

Optional build variable:

```text
RUANGNADA_PUBLIC_URL=https://ruangnada-api.example.com
```

It must be an HTTPS public URL. It contains no secret. Omitting it keeps RuangNada visible but unavailable, with an explanatory message.

Do not set private keys, database credentials, yt-dlp cookies, or server secrets as Pages variables exposed to browser code. Store backend secrets only in the separately deployed backend service.

## GitHub deployment

1. Create a Git repository at the project root.
2. Review `.gitignore`; it excludes venvs, logs, runtime DB/data, media downloads, build output, and secrets.
3. Commit source files, `build_pages.py`, `wrangler.toml`, `.env.example`, and this document. Do not commit `.env`.
4. Push to GitHub.
5. Cloudflare Dashboard: **Workers & Pages** → **Create** → **Pages** → **Connect to Git**.
6. Select repository and use the build settings above.
7. Add `RUANGNADA_PUBLIC_URL` only after its backend has a public HTTPS deployment with CORS/authentication configured.
8. Deploy. Every GitHub push to the configured branch rebuilds Pages.

CLI alternative after authentication:

```powershell
python build_pages.py
npx wrangler pages deploy dist
```

## Local development

Local launcher, unchanged:

```powershell
.\.venv\Scripts\python.exe -m uvicorn Menu.main:app --host 127.0.0.1 --port 8000
```

Static Pages preview:

```powershell
python build_pages.py
npx wrangler pages dev dist
```

## Verification scope

Validated: Pages build output, JavaScript syntax, local Menu tests, static asset paths, absent sensitive/runtime files in `dist/`.

Not validated: a real Cloudflare account build/deploy, public RuangNada backend, CORS/authentication for that backend, browser popup policy, or CDN/object-storage requirements for future shared assets.

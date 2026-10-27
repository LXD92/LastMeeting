# Last_Meeting

Application hub dengan launcher FastAPI lokal serta build statis Cloudflare Pages. Audit, batasan runtime, konfigurasi, dan deployment: [CLOUDFLARE.md](CLOUDFLARE.md).

Ringkas:

- `Menu` tetap berjalan lokal dengan FastAPI dan dapat menemukan/menjalankan aplikasi.
- `Apps/Hanacaraka` kompatibel dengan Pages sebagai aset statis.
- `Apps/RuangNada` tetap backend Python lokal/eksternal; tidak dipaksakan masuk Workers.
- Build Pages: `python build_pages.py`; output: `dist/`.

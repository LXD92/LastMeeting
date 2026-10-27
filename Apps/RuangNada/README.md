# Ruang Nada

Website lokal untuk memproses video YouTube yang boleh diunduh pengguna, mengubah format gambar lokal, dan mengunduh hasil melalui browser. Skrip CLI lama [`music_downloader.py`](./music_downloader.py) tetap tersedia dan tidak diubah; ia tetap mengunduh audio YouTube menjadi MP3.

## Teknologi yang ditemukan

- `music_downloader.py` memakai `yt-dlp`, FFmpeg, serta Deno 2.3+ atau Node.js 22+ (jika tersedia).
- Skrip lama menerima tautan YouTube dan menyimpan MP3 320 kbps ke folder `MUSIC_DOWNLOAD_DIR` atau `~/Music`.
- Website memakai FastAPI, `yt-dlp`, FFmpeg dan Pillow. Format audio/video dipilih pada backend; gambar JPG/PNG/WEBP dapat dikonversi dari unggahan lokal.
- Progres unduhan mengikuti hook `yt-dlp`; progres konversi audio/video mengikuti keluaran `-progress` FFmpeg. Pekerjaan diproses maksimal dua sekaligus dan maksimal empat dalam antrean aktif.

## Menjalankan di VS Code (Windows)

Buka terminal VS Code di folder `Apps\Music_Downloader`, kemudian:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn webapp:app --host 127.0.0.1 --port 8765
```

Kunjungi `http://127.0.0.1:8765`. Tekan `Ctrl+C` di terminal untuk menghentikan server. Aktifkan FFmpeg di `PATH` atau pasang paket `imageio-ffmpeg`; aplikasi juga menggunakan pencari FFmpeg yang sudah ada di skrip lama. `MUSIC_FFMPEG_PATH` dapat diarahkan ke executable FFmpeg tertentu.

Output menggunakan lokasi `MUSIC_DOWNLOAD_DIR` (default folder Music pengguna). Metadata riwayat disimpan di `.data\history.sqlite3`; `MUSIC_WEB_DATA_DIR` dapat mengubah lokasi itu. File hasil dihapus secara berkala setelah masa simpan 24 jam (pemeriksaan tiap jam), dan saat riwayat dihapus pengguna. Preferensi tema, format, preset, dan kualitas disimpan secara lokal di browser.

## API

- `POST /api/analyze` — metadata video YouTube dan pilihan resolusi.
- `POST /api/download` — antrekan pekerjaan audio atau video.
- `GET /api/jobs/{job_id}` dan `POST /api/jobs/{job_id}/cancel` — status progres dan pembatalan.
- `GET /api/files/{file_id}` — unduh hasil melalui nama file yang aman.
- `POST /api/images/convert` — unggah data gambar mentah dengan query `format` dan `filename`.
- `GET /api/history` dan `DELETE /api/history/{job_id}` — daftar dan hapus riwayat/file.

## Batasan dan keamanan

- API sumber saat ini hanya menerima HTTPS YouTube; playlist, layanan lain, dan URL selain domain YouTube ditolak. Tidak ada URL atau perintah shell mentah yang diteruskan ke shell.
- Batas media: 1 GB dan durasi 4 jam. Gambar: 25 MB dan 50 megapiksel. File disimpan maksimal 24 jam; pembersihan file yang kedaluwarsa berjalan saat startup berikutnya.
- MP3 mendukung bitrate 64–320 kbps pada CBR dan skala kualitas encoder VBR; preset audio menyesuaikan kualitas encoder. Sample rate/kanal diteruskan ke FFmpeg. FLAC menawarkan level kompresi lossless, OGG memakai kualitas Vorbis, sementara format lain menggunakan encoder yang sesuai. Mengubah bitrate tidak dapat memulihkan detail yang hilang dari sumber terkompresi.
- Resolusi video yang ditawarkan berasal dari metadata format sumber. Penggabungan audio/video menggunakan FFmpeg; remux hanya mengubah container, bukan meng-encode ulang video.
- MOV/WebM/MKV bergantung pada codec dan muxer yang disediakan FFmpeg. Konversi yang tidak kompatibel akan gagal dengan pesan yang ditampilkan, bukan sekadar mengganti ekstensi.
- Jalankan hanya pada `127.0.0.1` untuk penggunaan pribadi. Jangan mengekspos server ke internet atau jaringan publik tanpa autentikasi dan pembatasan penggunaan tambahan.
- Gunakan hanya materi yang memang boleh diunduh; patuhi hak cipta dan ketentuan layanan sumber.

## Pemeriksaan

Tes regresi API lokal:

```powershell
python -m unittest discover -s tests -v
```

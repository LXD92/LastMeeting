import importlib
import importlib.metadata
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

# =========================
# Konfigurasi
# =========================

def default_download_dir():
    configured_dir = os.environ.get("MUSIC_DOWNLOAD_DIR")
    if configured_dir:
        return Path(configured_dir).expanduser()

    if sys.platform.startswith("linux") and shutil.which("pkg"):
        termux_dir = Path("/storage/1A38-EBD3/Music")
        if termux_dir.is_dir():
            return termux_dir

    return Path.home() / "Music"


DOWNLOAD_DIR = default_download_dir()
AUDIO_QUALITY = "320"

DISPLAY = """
///-----------------------///
      Music Downloader
         by Mr.XD92
//-----------------------///
"""


# =========================
# Dependency
# =========================

def run_command(command):
    return subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def find_ffmpeg():
    configured_path = os.environ.get("MUSIC_FFMPEG_PATH")
    if configured_path:
        candidate = Path(configured_path).expanduser()
        if candidate.is_file():
            return candidate

    executable = shutil.which("ffmpeg")
    if executable:
        return Path(executable)

    binary_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    bundled_binary = Path(__file__).resolve().parent / "bot" / "node_modules" / "ffmpeg-static" / binary_name
    if bundled_binary.is_file():
        return bundled_binary

    try:
        imageio_ffmpeg = importlib.import_module("imageio_ffmpeg")
        packaged_binary = Path(imageio_ffmpeg.get_ffmpeg_exe())
        if packaged_binary.is_file():
            return packaged_binary
    except (ImportError, OSError, RuntimeError):
        pass

    return None


def find_js_runtime():
    minimum_versions = {
        "deno": (2, 3, 0),
        "node": (22, 0, 0),
    }

    for runtime in ("deno", "node"):
        executable = shutil.which(runtime)
        if not executable:
            continue

        result = subprocess.run(
            [executable, "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        match = re.search(r"\d+(?:\.\d+){1,2}", result.stdout)
        if result.returncode != 0 or not match:
            continue

        version = tuple(int(part) for part in match.group().split("."))
        version = (*version, 0)[:3]
        if version >= minimum_versions[runtime]:
            return runtime, Path(executable)

    return None


def ensure_pip_package(package, import_name=None, upgrade=False):
    """Memastikan package Python tersedia."""
    import_name = import_name or package.split("[")[0].replace("-", "_")

    try:
        importlib.import_module(import_name)
    except ImportError:
        print(f"Menginstal {package}...")
        subprocess.check_call([
            sys.executable,
            "-m",
            "pip",
            "install",
            package,
        ])
        return

    if upgrade:
        print(f"Memperbarui {package}...")
        subprocess.check_call([
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            package,
        ])


def ensure_termux_package(package):
    """Memastikan package Termux tersedia."""
    if shutil.which("pkg") is None:
        return

    result = subprocess.run(
        ["dpkg", "-s", package],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if result.returncode != 0:
        print(f"Menginstal {package}...")
        subprocess.check_call(["pkg", "install", "-y", package])


def check_dependencies():
    print("Memeriksa dependency...\n")

    # yt-dlp and its EJS component are installed once, not upgraded at every run.
    try:
        installed_version = importlib.metadata.version("yt-dlp")
        print(f"yt-dlp terpasang: {installed_version}")
    except importlib.metadata.PackageNotFoundError:
        pass

    ensure_pip_package("yt-dlp[default]", "yt_dlp")

    # Prefer system FFmpeg, then use the binary already bundled with this project.
    ffmpeg_path = find_ffmpeg()
    if ffmpeg_path is None:
        ensure_termux_package("ffmpeg")
        ffmpeg_path = find_ffmpeg()
    if ffmpeg_path is None:
        ensure_pip_package("imageio-ffmpeg", "imageio_ffmpeg")
        ffmpeg_path = find_ffmpeg()
    if ffmpeg_path is None:
        raise RuntimeError(
            "FFmpeg tidak ditemukan. Instal FFmpeg dan tambahkan ke PATH, atau "
            "atur MUSIC_FFMPEG_PATH ke file executable FFmpeg."
        )
    print(f"FFmpeg: {ffmpeg_path}")

    js_runtime = find_js_runtime()
    if js_runtime is None:
        print(
            "\nPERINGATAN: Deno 2.3+ atau Node.js 22+ tidak ditemukan.\n"
            "YouTube mungkin tidak dapat diproses tanpa JavaScript runtime.\n"
        )
    else:
        print(f"JavaScript runtime: {js_runtime[0]} ({js_runtime[1]})")

    print()


# =========================
# Validasi URL
# =========================

def is_youtube_url(url):
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower().split(":")[0]

        return (
            host == "youtube.com"
            or host.endswith(".youtube.com")
            or host == "youtu.be"
            or host.endswith(".youtu.be")
        )
    except Exception:
        return False


# =========================
# Download
# =========================

def build_ydl_options(player_client=None):
    options = {
        "format": "bestaudio/best",

        # ID ditambahkan agar nama file tetap unik jika ada
        # beberapa video dengan judul sama.
        "outtmpl": str(DOWNLOAD_DIR / "%(title)s [%(id)s].%(ext)s"),

        "quiet": False,
        "no_warnings": False,

        # Retry ketika koneksi sementara bermasalah.
        "retries": 5,
        "fragment_retries": 5,
        "file_access_retries": 3,

        # Jangan meninggalkan file .part setelah selesai.
        "continuedl": True,
        "nopart": False,

        # Pilih runtime yang benar-benar tersedia pada sistem ini.
        "js_runtimes": {},

        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": AUDIO_QUALITY,
            }
        ],
    }

    js_runtime = find_js_runtime()
    if js_runtime:
        runtime_name, runtime_path = js_runtime
        options["js_runtimes"] = {runtime_name: {"path": str(runtime_path)}}

    ffmpeg_path = find_ffmpeg()
    if ffmpeg_path:
        options["ffmpeg_location"] = str(ffmpeg_path)

    if player_client:
        options["extractor_args"] = {
            "youtube": {
                "player_client": [player_client],
            }
        }

    return options


def download_with_options(url, options):
    yt_dlp = importlib.import_module("yt_dlp")
    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])


def download_mp3(url):
    """Mengunduh audio YouTube dan mengonversinya menjadi MP3."""

    if not is_youtube_url(url):
        print("URL tidak dikenali sebagai tautan YouTube.")
        return False

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\nMemulai unduhan:")
    print(url)
    print()

    # Percobaan pertama: biarkan yt-dlp memilih client yang sesuai.
    try:
        download_with_options(url, build_ydl_options())
        print(f"\nSelesai. File MP3 disimpan di:")
        print(DOWNLOAD_DIR)
        return True

    except Exception as first_error:
        error_text = str(first_error)

        # YouTube dapat mengembalikan 403 karena perubahan client/SABR/PO token.
        # web_safari adalah fallback yang berguna karena dapat menyediakan
        # format HLS pada kondisi tertentu.
        if "403" not in error_text and "Forbidden" not in error_text:
            print(f"\nTerjadi kesalahan:\n{first_error}")
            return False

        print("\nPercobaan pertama mendapat HTTP 403.")
        print("Mencoba client YouTube alternatif (web_safari)...\n")

        try:
            download_with_options(
                url,
                build_ydl_options("web_safari"),
            )

            print(f"\nSelesai. File MP3 disimpan di:")
            print(DOWNLOAD_DIR)
            return True

        except Exception as second_error:
            print("\nDownload gagal.")
            print(f"Percobaan pertama: {first_error}")
            print(f"Percobaan kedua: {second_error}")

            print(
                "\nCatatan: HTTP 403 pada YouTube tidak selalu dapat "
                "diperbaiki hanya dari kode. YouTube dapat mengubah "
                "persyaratan client, SABR, atau PO token."
            )
            return False


# =========================
# Program utama
# =========================

def main():
    check_dependencies()

    urls = []

    print(DISPLAY)
    print("Masukkan URL YouTube satu per satu.")
    print("Ketik 'done' untuk mulai mengunduh.")
    print("Ketik 'exit' untuk keluar.\n")

    while True:
        url = input("Masukkan tautan YouTube: ").strip()

        if not url:
            continue

        if url.lower() == "done":
            break

        if url.lower() == "exit":
            return

        if not is_youtube_url(url):
            print("URL bukan tautan YouTube yang valid.\n")
            continue

        urls.append(url)
        print("URL ditambahkan.\n")

    if not urls:
        print("Tidak ada URL yang dimasukkan.")
        return

    print(f"\nTotal URL: {len(urls)}")

    success = 0

    for index, url in enumerate(urls, start=1):
        print(f"\n========== {index}/{len(urls)} ==========")

        if download_mp3(url):
            success += 1

    print("\n==============================")
    print(f"Selesai: {success}/{len(urls)} berhasil")
    print(f"Folder: {DOWNLOAD_DIR}")
    print("==============================")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nProgram dihentikan.")
    except Exception as error:
        print(f"\nKesalahan fatal:\n{error}")

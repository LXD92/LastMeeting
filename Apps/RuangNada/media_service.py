import importlib
import io
import re
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, UnidentifiedImageError

import music_downloader as legacy


ALLOWED_HOSTS = {"youtube.com", "www.youtube.com", "music.youtube.com", "youtu.be", "www.youtu.be"}
AUDIO_FORMATS = {"mp3", "wav", "flac", "m4a", "aac", "opus", "ogg"}
VIDEO_FORMATS = {"mp4", "webm", "mkv", "mov"}
IMAGE_FORMATS = {"jpg", "png", "webp"}
MAX_MEDIA_BYTES = 1024 * 1024 * 1024
MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_IMAGE_PIXELS = 50_000_000
MAX_DURATION_SECONDS = 4 * 60 * 60


class JobCancelled(Exception):
    pass


class DownloadTooLarge(Exception):
    pass


def validate_youtube_url(url):
    if not isinstance(url, str) or not url or len(url) > 2048:
        raise ValueError("Masukkan URL YouTube yang valid.")
    try:
        parsed = urlparse(url.strip())
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError as error:
        raise ValueError("Format URL tidak valid.") from error
    if (
        parsed.scheme != "https"
        or host not in ALLOWED_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or not parsed.path
    ):
        raise ValueError("Sumber yang didukung saat ini adalah tautan HTTPS YouTube.")
    return url.strip()


def safe_filename(value, fallback="media"):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", str(value or "")).strip(" .")
    value = value[:120].strip(" .")
    return value or fallback


def _ffmpeg_path():
    path = legacy.find_ffmpeg()
    if path is None:
        raise RuntimeError("FFmpeg tidak ditemukan. Instal FFmpeg atau imageio-ffmpeg terlebih dahulu.")
    return str(path)


def _js_runtimes():
    runtime = legacy.find_js_runtime()
    if runtime is None:
        return {}
    name, path = runtime
    return {name: {"path": str(path)}}


def _new_ydl_options(ffmpeg_path, output_template):
    return {
        "outtmpl": str(output_template),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "socket_timeout": 20,
        "retries": 3,
        "fragment_retries": 3,
        "file_access_retries": 2,
        "continuedl": True,
        "nopart": False,
        "max_filesize": MAX_MEDIA_BYTES,
        "match_filter": _duration_filter,
        "js_runtimes": _js_runtimes(),
        "ffmpeg_location": ffmpeg_path,
    }


def _duration_filter(info, *, incomplete=False):
    _ = incomplete
    duration = info.get("duration")
    if duration and duration > MAX_DURATION_SECONDS:
        return "Durasi media melebihi batas 4 jam."
    return None


def _yt_dlp_error_text(error):
    text = str(error).strip()
    if "Unsupported URL" in text or "not a valid URL" in text:
        return "URL tidak didukung. Gunakan tautan video YouTube publik."
    if "Private video" in text or "members-only" in text.lower():
        return "Media privat atau khusus anggota tidak dapat diproses."
    if "Video unavailable" in text or "This video is unavailable" in text:
        return "Media tidak tersedia. Periksa tautan atau batasan wilayahnya."
    if "File is larger than" in text:
        return "Ukuran media melebihi batas 1 GB."
    return (
        "Media gagal diproses. Pastikan videonya publik, dapat diakses dari wilayahmu, "
        "dan coba lagi."
    )


def analyze_media(url):
    url = validate_youtube_url(url)
    options = _new_ydl_options(_ffmpeg_path(), "unused.%(ext)s")
    options.update({"skip_download": True, "extract_flat": False})
    yt_dlp = importlib.import_module("yt_dlp")
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as error:
        raise ValueError(_yt_dlp_error_text(error)) from error
    if not info or info.get("_type") == "playlist":
        raise ValueError("Tautan playlist tidak didukung. Masukkan tautan satu video.")
    formats = info.get("formats") or []
    heights = sorted({
        int(item["height"])
        for item in formats
        if item.get("height") and item.get("vcodec") != "none"
    })
    return {
        "title": info.get("title") or "Judul tidak tersedia",
        "uploader": info.get("uploader") or info.get("channel") or None,
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "source_format": info.get("ext"),
        "source_size": info.get("filesize") or info.get("filesize_approx"),
        "source_quality": max(heights) if heights else None,
        "available_heights": heights,
        "webpage_url": info.get("webpage_url") or url,
    }


def _audio_args(output_format, options):
    bitrate = int(options["bitrate"])
    sample_rate = int(options["sample_rate"])
    channels = int(options["channels"])
    args = ["-vn"]
    if output_format == "mp3":
        args += ["-c:a", "libmp3lame"]
        if options["audio_mode"] == "vbr":
            args += ["-q:a", str(options["encoder_quality"])]
        else:
            args += ["-b:a", f"{bitrate}k", "-abr", "0"]
    elif output_format == "wav":
        args += ["-c:a", "pcm_s16le"]
    elif output_format == "flac":
        args += ["-c:a", "flac", "-compression_level", str(options["encoder_quality"])]
    elif output_format == "m4a":
        args += ["-c:a", "aac", "-b:a", f"{bitrate}k"]
    elif output_format == "aac":
        args += ["-c:a", "aac", "-b:a", f"{bitrate}k", "-f", "adts"]
    elif output_format == "opus":
        args += ["-c:a", "libopus", "-b:a", f"{bitrate}k", "-vbr", "on"]
    elif output_format == "ogg":
        args += ["-c:a", "libvorbis", "-q:a", str(options["encoder_quality"])]
    if sample_rate:
        args += ["-ar", str(sample_rate)]
    if channels:
        args += ["-ac", str(channels)]
    return args


def _run_ffmpeg(command, duration, cancel_event, update):
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    deadline = time.monotonic() + 60 * 60
    try:
        while True:
            if cancel_event.is_set():
                process.kill()
                raise JobCancelled()
            if time.monotonic() > deadline:
                process.kill()
                raise RuntimeError("Konversi melewati batas waktu 1 jam.")
            line = process.stdout.readline() if process.stdout else ""
            if line:
                line = line.strip()
                if line.startswith("out_time_ms=") and duration:
                    try:
                        seconds = int(line.partition("=")[2]) / 1_000_000
                    except ValueError:
                        continue
                    update(stage="converting", progress=min(99, int(seconds / duration * 100)))
            elif process.poll() is not None:
                break
            else:
                time.sleep(0.1)
        if process.returncode:
            raise RuntimeError(
                "Konversi gagal. Format atau encoder sumber mungkin tidak kompatibel; "
                "coba format keluaran lain."
            )
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        if process.stdout:
            process.stdout.close()


def process_media(request, work_dir, output_dir, job_id, cancel_event, update):
    url = validate_youtube_url(request["url"])
    ffmpeg = _ffmpeg_path()
    output_format = request["format"]
    is_audio = request["kind"] == "audio"
    if output_format not in (AUDIO_FORMATS if is_audio else VIDEO_FORMATS):
        raise ValueError("Format keluaran tidak didukung untuk jenis media ini.")

    stem = f"{safe_filename(request.get('filename'))}_{job_id[:8]}"
    template = work_dir / "source.%(ext)s"
    ydl_options = _new_ydl_options(ffmpeg, template)
    audio_preset = request.get("preset", "standard")
    preset_bitrates = {"economy": 96, "standard": 192, "high": 320, "automatic": 320}
    bitrate = int(request.get("bitrate") or preset_bitrates.get(audio_preset, 192))
    ydl_options["progress_hooks"] = [_progress_hook(cancel_event, update)]
    ydl_options["postprocessor_hooks"] = [
        lambda state: update(stage="converting", progress=None)
        if state.get("status") == "started" else None
    ]

    if is_audio:
        ydl_options["format"] = "bestaudio/best"
        ydl_options["progress_hooks"] = [_progress_hook(cancel_event, update)]
    else:
        height = int(request.get("video_height") or 0)
        if height:
            ydl_options["format"] = (
                f"bestvideo[height<={height}]+bestaudio/"
                f"best[height<={height}]/best"
            )
        else:
            ydl_options["format"] = "bestvideo+bestaudio/best"
        ydl_options["merge_output_format"] = output_format
        ydl_options["postprocessors"] = [
            {"key": "FFmpegVideoRemuxer", "preferedformat": output_format}
        ]

    update(stage="downloading", progress=0)
    yt_dlp = importlib.import_module("yt_dlp")
    try:
        with yt_dlp.YoutubeDL(ydl_options) as ydl:
            info = ydl.extract_info(url, download=True)
    except JobCancelled:
        raise
    except Exception as error:
        raise ValueError(_yt_dlp_error_text(error)) from error
    if cancel_event.is_set():
        raise JobCancelled()

    sources = [
        path for path in work_dir.iterdir()
        if path.is_file() and not path.name.endswith((".part", ".ytdl"))
    ]
    if not sources:
        raise RuntimeError("Unduhan tidak menghasilkan file yang dapat diproses.")
    source = max(sources, key=lambda path: path.stat().st_mtime)
    if source.stat().st_size > MAX_MEDIA_BYTES:
        raise DownloadTooLarge("Ukuran file melebihi batas 1 GB.")

    update(stage="preparing", progress=None)
    output = output_dir / f"{stem}.{output_format}"
    if is_audio:
        source_ext = source.suffix.lower().lstrip(".")
        audio_settings = {
            "sample_rate": int(request.get("sample_rate") or 0),
            "channels": int(request.get("channels") or 0),
        }
        format_has_quality_control = output_format in {"mp3", "m4a", "aac", "opus", "ogg", "flac"}
        needs_audio_encoding = (
            source_ext != output_format
            or bool(audio_settings["sample_rate"] or audio_settings["channels"])
            or (audio_preset != "automatic" and format_has_quality_control)
        )
        if not needs_audio_encoding:
            shutil.move(str(source), str(output))
        else:
            update(stage="converting", progress=0)
            if audio_preset == "automatic":
                source_bitrate = info.get("abr")
                if source_bitrate:
                    bitrate = min(320, max(64, int(round(source_bitrate / 8) * 8)))
            bitrate_settings = {
                "bitrate": bitrate,
                **audio_settings,
                "audio_mode": request.get("audio_mode", "vbr"),
                "encoder_quality": int(request.get("encoder_quality") or 5),
            }
            command = [
                ffmpeg, "-y", "-nostats", "-progress", "pipe:1", "-i", str(source),
                *_audio_args(output_format, bitrate_settings), str(output),
            ]
            _run_ffmpeg(command, info.get("duration"), cancel_event, update)
            source.unlink(missing_ok=True)
    else:
        if source.suffix.lower().lstrip(".") != output_format:
            update(stage="converting", progress=None)
            command = [
                ffmpeg, "-y", "-nostats", "-progress", "pipe:1", "-i", str(source),
                "-map", "0", "-c", "copy", "-f", output_format, str(output),
            ]
            _run_ffmpeg(command, info.get("duration"), cancel_event, update)
            source.unlink(missing_ok=True)
        else:
            shutil.move(str(source), str(output))

    if cancel_event.is_set():
        output.unlink(missing_ok=True)
        raise JobCancelled()
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("File hasil kosong atau tidak ditemukan.")
    if output.stat().st_size > MAX_MEDIA_BYTES:
        output.unlink(missing_ok=True)
        raise DownloadTooLarge("File hasil melebihi batas 1 GB.")

    return output, {
        "title": info.get("title") or stem,
        "uploader": info.get("uploader") or info.get("channel"),
        "duration": info.get("duration"),
        "source_format": info.get("ext"),
        "source_size": info.get("filesize") or info.get("filesize_approx"),
        "source_quality": info.get("height"),
        "output_format": output_format,
        "output_size": output.stat().st_size,
        "filename": output.name,
    }


def _progress_hook(cancel_event, update):
    def report(info):
        if cancel_event.is_set():
            raise JobCancelled()
        if info.get("status") == "downloading":
            downloaded = info.get("downloaded_bytes") or 0
            total = info.get("total_bytes") or info.get("total_bytes_estimate")
            if downloaded > MAX_MEDIA_BYTES or (total and total > MAX_MEDIA_BYTES):
                raise DownloadTooLarge("Ukuran media melebihi batas 1 GB.")
            percent = int(downloaded / total * 100) if total else None
            update(
                stage="downloading",
                progress=min(percent, 99) if percent is not None else None,
                downloaded=downloaded,
                total=total,
                speed=info.get("speed"),
                eta=info.get("eta"),
            )
        elif info.get("status") == "finished":
            update(stage="preparing", progress=None)
    return report


def convert_image(data, output_format, filename, output_dir, job_id, cancel_event, update):
    if output_format not in IMAGE_FORMATS:
        raise ValueError("Format gambar yang didukung: JPG, PNG, atau WEBP.")
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Ukuran gambar unggahan maksimal 25 MB.")
    if cancel_event.is_set():
        raise JobCancelled()
    update(stage="processing", progress=None)
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise ValueError("Resolusi gambar melebihi batas 50 megapiksel.")
            target_format = {"jpg": "JPEG", "png": "PNG", "webp": "WEBP"}[output_format]
            if target_format == "JPEG":
                if image.mode in ("RGBA", "LA") or "transparency" in image.info:
                    background = Image.new("RGB", image.size, "white")
                    if image.mode != "RGBA":
                        image = image.convert("RGBA")
                    background.paste(image, mask=image.getchannel("A"))
                    image = background
                else:
                    image = image.convert("RGB")
            elif target_format == "WEBP":
                image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            else:
                image.load()
            stem = safe_filename(Path(filename or "gambar").stem, "gambar")
            output = output_dir / f"{stem}_{job_id[:8]}.{output_format}"
            image.save(output, format=target_format)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ValueError("File bukan gambar yang valid atau tidak dapat dibaca.") from error
    if cancel_event.is_set():
        output.unlink(missing_ok=True)
        raise JobCancelled()
    return output, {
        "title": stem,
        "output_format": output_format,
        "output_size": output.stat().st_size,
        "filename": output.name,
    }

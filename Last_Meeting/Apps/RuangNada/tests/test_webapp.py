import io
import math
import struct
import threading
import tempfile
import time
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

import webapp
from media_service import JobCancelled, process_media, safe_filename, validate_youtube_url


class MediaValidationTests(unittest.TestCase):
    def test_only_secure_supported_youtube_urls_are_accepted(self):
        self.assertEqual(
            validate_youtube_url("https://youtu.be/example"),
            "https://youtu.be/example",
        )
        for url in (
            "http://youtube.com/watch?v=x",
            "https://youtube.com.attacker.invalid/watch?v=x",
            "https://127.0.0.1/watch?v=x",
            "https://youtube.com:8080/watch?v=x",
            "https://user@youtube.com/watch?v=x",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_youtube_url(url)

    def test_filename_removes_path_and_reserved_characters(self):
        self.assertEqual(safe_filename("../bad:name?.mp3"), "-bad-name-.mp3")
        self.assertEqual(safe_filename("   "), "media")


class MediaProcessingTests(unittest.TestCase):
    def test_audio_is_encoded_to_a_real_mp3_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            work_dir = root / "work"
            output_dir = root / "output"
            work_dir.mkdir()
            output_dir.mkdir()

            class StubYoutubeDL:
                def __init__(self, options):
                    self.options = options

                def __enter__(self):
                    return self

                def __exit__(self, *_args):
                    return False

                def extract_info(self, _url, download):
                    self_test.assertTrue(download)
                    for hook in self.options["progress_hooks"]:
                        hook({
                            "status": "downloading",
                            "downloaded_bytes": 50,
                            "total_bytes": 100,
                            "speed": 50,
                            "eta": 1,
                        })
                    source = Path(self.options["outtmpl"].replace("%(ext)s", "wav"))
                    frames = [
                        struct.pack("<h", int(12000 * math.sin(2 * math.pi * 440 * index / 44100)))
                        for index in range(11025)
                    ]
                    with wave.open(str(source), "wb") as audio:
                        audio.setnchannels(1)
                        audio.setsampwidth(2)
                        audio.setframerate(44100)
                        audio.writeframes(b"".join(frames))
                    return {
                        "title": "fixture",
                        "duration": 0.25,
                        "ext": "wav",
                        "abr": 128,
                    }

            self_test = self
            progress_updates = []
            with patch("yt_dlp.YoutubeDL", StubYoutubeDL):
                output, details = process_media(
                    {
                        "url": "https://youtu.be/example",
                        "kind": "audio",
                        "format": "mp3",
                        "preset": "high",
                        "bitrate": 320,
                        "sample_rate": 0,
                        "channels": 0,
                        "audio_mode": "vbr",
                        "encoder_quality": 4,
                        "filename": "test",
                    },
                    work_dir,
                    output_dir,
                    "0123456789abcdef",
                    threading.Event(),
                    lambda **state: progress_updates.append(state),
                )
            self.assertEqual(output.suffix, ".mp3")
            self.assertGreater(output.stat().st_size, 100)
            self.assertEqual(details["output_format"], "mp3")
            self.assertEqual(details["source_format"], "wav")
            self.assertTrue(any(
                update.get("stage") == "downloading" and update.get("progress") == 50
                for update in progress_updates
            ))


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        root = Path(self.temp_dir.name)
        self.output = root / "output"
        self.data = root / "data"
        patcher = patch.multiple(webapp, OUTPUT_DIR=self.output, DATA_DIR=self.data)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(webapp.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def test_invalid_download_url_is_rejected(self):
        response = self.client.post("/api/download", json={
            "url": "http://127.0.0.1/internal",
            "kind": "audio",
            "format": "mp3",
        })
        self.assertEqual(response.status_code, 422)

    def test_image_conversion_can_be_downloaded_and_removed(self):
        image_bytes = io.BytesIO()
        Image.new("RGBA", (8, 8), (255, 0, 0, 128)).save(image_bytes, format="PNG")
        response = self.client.post(
            "/api/images/convert?format=jpg&filename=test.png",
            content=image_bytes.getvalue(),
            headers={"content-type": "image/png"},
        )
        self.assertEqual(response.status_code, 200)
        job_id = response.json()["job_id"]

        deadline = time.monotonic() + 5
        job = None
        while time.monotonic() < deadline:
            job = self.client.get(f"/api/jobs/{job_id}").json()
            if job["status"] not in {"queued", "running"}:
                break
            time.sleep(0.05)

        self.assertEqual(job["status"], "completed", job)
        file_response = self.client.get(f"/api/files/{job['file_id']}")
        self.assertEqual(file_response.status_code, 200)
        self.assertEqual(file_response.headers["content-type"], "image/jpeg")
        history = self.client.get("/api/history").json()["items"]
        self.assertEqual(len(history), 1)
        self.assertTrue(history[0]["available"])

        deleted = self.client.delete(f"/api/history/{job_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.get(f"/api/files/{job['file_id']}").status_code, 404)

    def test_oversized_declared_image_is_rejected(self):
        response = self.client.post(
            "/api/images/convert?format=png",
            content=b"x",
            headers={"content-length": str(26 * 1024 * 1024)},
        )
        self.assertEqual(response.status_code, 413)

    def test_running_download_can_be_cancelled(self):
        started = threading.Event()

        def wait_for_cancel(_payload, _work_dir, _output_dir, _job_id, cancel_event, _update):
            started.set()
            if not cancel_event.wait(timeout=3):
                raise AssertionError("Cancellation request was not delivered to the worker.")
            raise JobCancelled()

        with patch("webapp.process_media", side_effect=wait_for_cancel):
            response = self.client.post("/api/download", json={
                "url": "https://youtu.be/example",
                "kind": "audio",
                "format": "mp3",
            })
            self.assertEqual(response.status_code, 200)
            job_id = response.json()["job_id"]
            self.assertTrue(started.wait(timeout=2))
            cancelled = self.client.post(f"/api/jobs/{job_id}/cancel")
            self.assertEqual(cancelled.status_code, 200)

            deadline = time.monotonic() + 3
            job = None
            while time.monotonic() < deadline:
                job = self.client.get(f"/api/jobs/{job_id}").json()
                if job["status"] == "cancelled":
                    break
                time.sleep(0.02)
            self.assertEqual(job["status"], "cancelled", job)
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                with webapp.jobs_lock:
                    if job_id not in webapp.jobs:
                        break
                time.sleep(0.02)
            with webapp.jobs_lock:
                self.assertNotIn(job_id, webapp.jobs)

    def test_expired_result_file_is_removed(self):
        old_file = self.output / "expired.mp3"
        old_file.write_bytes(b"old media")
        expired = webapp._timestamp(time.time() - webapp.FILE_TTL_SECONDS - 1)
        with webapp._connect() as connection:
            connection.execute(
                "INSERT INTO history (job_id, created_at, updated_at, status, stage, kind, "
                "output_format, file_id, file_path) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "expired-job", expired, expired, "completed", "completed",
                    "audio", "mp3", "expired-file", str(old_file),
                ),
            )

        webapp._cleanup_expired_files()
        self.assertFalse(old_file.exists())
        history_items = self.client.get("/api/history").json()["items"]
        expired_item = next(item for item in history_items if item["job_id"] == "expired-job")
        self.assertFalse(expired_item["available"])
        self.assertNotIn("file_path", expired_item)


if __name__ == "__main__":
    unittest.main()

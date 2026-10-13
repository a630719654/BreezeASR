import json
import shutil
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from helpers import (
    PASSWORD,
    BlockingRecognizer,
    FakeRecognizer,
    authed_client,
    build_app,
    tone_wav,
)


class TranscriptionFlowTest(unittest.TestCase):
    def test_upload_converts_saves_and_shows_page(self):
        with TemporaryDirectory() as temporary:
            settings, _auth, service, root, app = build_app(temporary)
            client = authed_client(app)
            me = client.get("/api/auth/me").json()

            response = client.post(
                "/api/transcribe",
                files={"file": ("hello.wav", tone_wav(), "audio/wav")},
            )
            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()
            self.assertEqual(body["text"], "測試逐字稿")
            self.assertEqual(body["source_filename"], "hello.wav")
            saved_path = root / "transcripts" / me["id"] / f"{body['id']}.json"
            saved = json.loads(saved_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["text"], "測試逐字稿")
            self.assertEqual(saved["model"], "Breeze-ASR-26")
            self.assertEqual(len(service._recognizer.calls), 1)

            listed = client.get("/api/transcripts")
            self.assertEqual(listed.status_code, 200)
            self.assertEqual(listed.json()[0]["id"], body["id"])

            fetched = client.get(f"/api/transcripts/{body['id']}")
            self.assertEqual(fetched.status_code, 200)
            self.assertEqual(fetched.json()["text"], "測試逐字稿")
            self.assertEqual(client.get("/api/transcripts/not-an-id").status_code, 404)

            deleted = client.delete(f"/api/transcripts/{body['id']}")
            self.assertEqual(deleted.status_code, 200)
            self.assertFalse(saved_path.exists())
            self.assertEqual(client.get(f"/api/transcripts/{body['id']}").status_code, 404)
            self.assertEqual(client.delete(f"/api/transcripts/{body['id']}").status_code, 404)

            rejected = client.post(
                "/api/transcribe",
                files={"file": ("note.txt", b"abc", "text/plain")},
            )
            self.assertEqual(rejected.status_code, 400)

            empty = client.post(
                "/api/transcribe",
                files={"file": ("empty.wav", b"", "audio/wav")},
            )
            self.assertEqual(empty.status_code, 400)

            page = client.get("/")
            self.assertEqual(page.status_code, 200)
            self.assertIn('id="app"', page.text)
            self.assertEqual(client.get("/health").status_code, 200)

    def test_job_reports_progress_then_finishes(self):
        with TemporaryDirectory() as temporary:
            recognizer = BlockingRecognizer()
            _settings, _auth, _service, _root, app = build_app(
                temporary, recognizer=recognizer
            )
            client = authed_client(app)

            created = client.post(
                "/api/jobs",
                files={"file": ("hello.wav", tone_wav(), "audio/wav")},
            )
            self.assertEqual(created.status_code, 200, created.text)
            job_id = created.json()["id"]
            self.assertTrue(recognizer.started.wait(timeout=3))

            running = client.get(f"/api/jobs/{job_id}")
            self.assertEqual(running.status_code, 200)
            self.assertIn(running.json()["status"], ("queued", "running"))
            self.assertLess(running.json()["percent"], 100)

            progress_page = client.get(f"/progress?job={job_id}")
            self.assertEqual(progress_page.status_code, 200)
            self.assertIn('id="app"', progress_page.text)

            recognizer.release.set()
            body = _wait_job(client, job_id)
            self.assertEqual(body["status"], "done")
            self.assertEqual(body["percent"], 100)
            self.assertEqual(body["transcript"]["text"], "測試逐字稿")

            missing = client.get("/api/jobs/not-a-job")
            self.assertEqual(missing.status_code, 404)

            bad_job = client.post(
                "/api/jobs",
                files={"file": ("note.txt", b"abc", "text/plain")},
            )
            self.assertEqual(bad_job.status_code, 400)

    def test_accounts_cannot_see_each_other_transcripts(self):
        with TemporaryDirectory() as temporary:
            _settings, _auth, _service, root, app = build_app(temporary)
            alice = authed_client(app, "alice")
            bob = authed_client(app, "bob")

            created = alice.post(
                "/api/transcribe",
                files={"file": ("hello.wav", tone_wav(), "audio/wav")},
            )
            self.assertEqual(created.status_code, 200, created.text)
            record_id = created.json()["id"]
            alice_id = alice.get("/api/auth/me").json()["id"]
            self.assertTrue((root / "transcripts" / alice_id / f"{record_id}.json").exists())

            self.assertEqual(bob.get("/api/transcripts").json(), [])
            self.assertEqual(bob.get(f"/api/transcripts/{record_id}").status_code, 404)
            self.assertEqual(bob.delete(f"/api/transcripts/{record_id}").status_code, 404)

            job = alice.post(
                "/api/jobs",
                files={"file": ("hello.wav", tone_wav(), "audio/wav")},
            )
            self.assertEqual(job.status_code, 200)
            self.assertEqual(bob.get(f"/api/jobs/{job.json()['id']}").status_code, 404)


class RealAppSmokeTest(unittest.TestCase):
    def test_page_and_health_do_not_load_model(self):
        import app as app_module

        client = TestClient(app_module.app)
        health = client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        payload = health.json()
        self.assertTrue(payload["ffmpeg"])
        self.assertTrue(payload["model_files"])
        self.assertFalse(payload["model_loaded"])
        self.assertNotIn("device", payload)
        home = client.get("/", follow_redirects=False)
        self.assertEqual(home.status_code, 302)
        self.assertEqual(home.headers["location"], "/login")
        login = client.get("/login")
        self.assertEqual(login.status_code, 200)
        self.assertIn('id="app"', login.text)
        self.assertEqual(client.get("/background1.jpg").status_code, 200)
        self.assertEqual(client.get("/progress", follow_redirects=False).status_code, 302)
        found = shutil.which("ffmpeg")
        self.assertIsNotNone(found)
        self.assertEqual(
            Path(found).resolve(),
            app_module.settings.ffmpeg_path.resolve(),
        )


def _wait_job(client: TestClient, job_id: str) -> dict:
    for _ in range(80):
        response = client.get(f"/api/jobs/{job_id}")
        body = response.json()
        if body.get("status") in {"done", "failed"}:
            return body
        time.sleep(0.05)
    raise AssertionError("辨識工作沒有結束")


if __name__ == "__main__":
    unittest.main()

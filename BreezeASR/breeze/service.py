import threading
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from breeze.jobs import Job
from breeze.models import Transcript
from breeze.ports import (
    AudioConverter,
    JobRepository,
    SpeechRecognizer,
    TranscriptStoreFactory,
)

ProgressFn = Callable[[str, int, str], None]


class RequestError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


class TranscriptionService:
    """上傳、轉檔、辨識、存 JSON。逐字稿路徑由使用者 id 決定。"""

    def __init__(
        self,
        converter: AudioConverter,
        recognizer: SpeechRecognizer,
        stores: TranscriptStoreFactory,
        jobs: JobRepository,
        *,
        allowed_suffixes: frozenset[str],
        max_upload_bytes: int,
    ):
        self._converter = converter
        self._recognizer = recognizer
        self._stores = stores
        self._jobs = jobs
        self._allowed_suffixes = allowed_suffixes
        self._max_upload_bytes = max_upload_bytes

    def status(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "status": "ok",
            "model": "Breeze-ASR-26",
            "ffmpeg": self._converter.available(),
            "model_files": self._recognizer.available(),
            "model_loaded": self._recognizer.loaded(),
        }
        if self._recognizer.loaded():
            payload["device"] = self._recognizer.device_name()
        return payload

    def transcribe_bytes(
        self,
        owner_id: str,
        filename: str,
        content: bytes,
        on_progress: ProgressFn | None = None,
    ) -> Transcript:
        safe_name, suffix = self._validate_upload(filename, content)
        return self._run_pipeline(owner_id, safe_name, suffix, content, on_progress)

    def start_job(self, owner_id: str, filename: str, content: bytes) -> Job:
        safe_name, suffix = self._validate_upload(filename, content)
        job = self._jobs.create(
            Job(
                id=uuid.uuid4().hex,
                owner_id=owner_id,
                status="queued",
                percent=5,
                stage="queued",
                message="已收到音檔，等待轉檔。",
                filename=safe_name,
            )
        )
        worker = threading.Thread(
            target=self._run_job,
            args=(job.id, owner_id, safe_name, suffix, content),
            daemon=True,
        )
        worker.start()
        return job

    def get_job(self, owner_id: str, job_id: str) -> Job | None:
        job = self._jobs.get(job_id)
        if job is None or job.owner_id != owner_id:
            return None
        return job

    def list_transcripts(self, owner_id: str) -> list[Transcript]:
        return self._stores.for_user(owner_id).list_all()

    def get_transcript(self, owner_id: str, transcript_id: str) -> Transcript | None:
        return self._stores.for_user(owner_id).get(transcript_id)

    def delete_transcript(self, owner_id: str, transcript_id: str) -> bool:
        return self._stores.for_user(owner_id).delete(transcript_id)

    def _validate_upload(self, filename: str, content: bytes) -> tuple[str, str]:
        safe_name = Path(filename).name or "audio"
        suffix = Path(safe_name).suffix.lower()
        if suffix not in self._allowed_suffixes:
            raise RequestError(f"不支援的音檔格式：{suffix or '（沒有副檔名）'}")
        if not content:
            raise RequestError("音檔是空的")
        if len(content) > self._max_upload_bytes:
            limit_mb = self._max_upload_bytes // (1024 * 1024)
            raise RequestError(f"音檔超過 {limit_mb} MB", status_code=413)
        if len(safe_name) > 180:
            safe_name = safe_name[-180:]
        return safe_name, suffix

    def _run_pipeline(
        self,
        owner_id: str,
        safe_name: str,
        suffix: str,
        content: bytes,
        on_progress: ProgressFn | None,
    ) -> Transcript:
        def report(stage: str, percent: int, message: str) -> None:
            if on_progress is not None:
                on_progress(stage, percent, message)

        with TemporaryDirectory() as temporary:
            folder = Path(temporary)
            source = folder / f"upload{suffix}"
            wav_path = folder / "speech.wav"
            source.write_bytes(content)
            report("converting", 20, "正在用 ffmpeg 轉成 16 kHz 單聲道 WAV。")
            self._converter.to_wav(source, wav_path)
            report("recognizing", 45, "正在用 Breeze-ASR-26 辨識語音。")
            recognition = self._recognizer.transcribe(wav_path)

        report("saving", 90, "正在把逐字稿寫入 JSON。")
        record = self._stores.for_user(owner_id).save(
            Transcript(
                id=uuid.uuid4().hex,
                source_filename=safe_name,
                text=recognition.text,
                model=recognition.model,
                device=recognition.device,
                created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            )
        )
        report("done", 100, "辨識完成。")
        return record

    def _run_job(
        self,
        job_id: str,
        owner_id: str,
        safe_name: str,
        suffix: str,
        content: bytes,
    ) -> None:
        def on_progress(stage: str, percent: int, message: str) -> None:
            self._jobs.update(
                job_id,
                status="running",
                stage=stage,
                percent=percent,
                message=message,
            )

        self._jobs.update(
            job_id,
            status="running",
            stage="converting",
            percent=10,
            message="開始處理音檔。",
        )
        try:
            record = self._run_pipeline(owner_id, safe_name, suffix, content, on_progress)
        except Exception as exc:
            self._jobs.update(
                job_id,
                status="failed",
                stage="failed",
                message="辨識失敗。",
                error=f"{type(exc).__name__}: {exc}",
            )
            return
        self._jobs.update(
            job_id,
            status="done",
            stage="done",
            percent=100,
            message="辨識完成。",
            transcript_id=record.id,
            error=None,
        )

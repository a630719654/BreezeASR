from collections.abc import Callable
import json

import requests

from breeze.meeting_summary.errors import SummaryError
from breeze.meeting_summary.prompt import SYSTEM_PROMPT, build_user_prompt

DEFAULT_HOST = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen2.5"
DEFAULT_TEMPERATURE = 0.2

TokenCallback = Callable[[str], None]


class OllamaChatClient:
    """只負責跟本機 Ollama 串流對話，不處理檔案與匯出。"""

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        model: str = DEFAULT_MODEL,
        temperature: float = DEFAULT_TEMPERATURE,
        timeout: tuple[float, float] = (5, 600),
    ):
        self._host = host.rstrip("/")
        self._model = model
        self._temperature = temperature
        self._timeout = timeout

    def summarize(
        self,
        transcript: str,
        *,
        source_name: str,
        created_at: str,
        on_token: TokenCallback | None = None,
    ) -> str:
        payload = {
            "model": self._model,
            "stream": True,
            "options": {"temperature": self._temperature},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_user_prompt(
                        transcript,
                        source_name=source_name,
                        created_at=created_at,
                    ),
                },
            ],
        }
        url = f"{self._host}/api/chat"
        try:
            response = requests.post(url, json=payload, stream=True, timeout=self._timeout)
        except requests.exceptions.ConnectionError as exc:
            raise SummaryError(
                "連不到 Ollama。請先在本機執行 `ollama serve`，確認 http://127.0.0.1:11434 有在聽。"
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise SummaryError("Ollama 回應逾時。請確認 qwen2.5 已下載且本機負載正常。") from exc

        if response.status_code == 404:
            response.close()
            raise SummaryError(
                f"Ollama 找不到模型 `{self._model}`。請執行 `ollama pull {self._model}`。"
            )
        if response.status_code >= 400:
            detail = response.text.strip() or response.reason
            response.close()
            raise SummaryError(f"Ollama 回傳 HTTP {response.status_code}：{detail}")

        chunks: list[str] = []
        try:
            for raw_line in response.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                try:
                    event = json.loads(raw_line)
                except json.JSONDecodeError as exc:
                    raise SummaryError("Ollama 串流內容不是合法 JSON。") from exc
                if event.get("error"):
                    raise SummaryError(f"Ollama 錯誤：{event['error']}")
                token = str((event.get("message") or {}).get("content") or "")
                if token:
                    chunks.append(token)
                    if on_token is not None:
                        on_token(token)
        except requests.exceptions.RequestException as exc:
            raise SummaryError(f"讀取 Ollama 串流失敗：{exc}") from exc
        finally:
            response.close()

        markdown = "".join(chunks).strip()
        if not markdown:
            raise SummaryError("Ollama 沒有產出任何文字。")
        return markdown

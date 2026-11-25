"""One gateway for every model call (LiteLLM): a primary model, ordered fallbacks, and recordings.

- Primary: an OpenAI-compatible vLLM server on a GPU box (`LLM_MODEL=hosted_vllm/<model>`, `LLM_API_BASE=...`).
- Fallbacks: `LLM_FALLBACKS`, comma-separated LiteLLM model ids, tried in order when the primary fails. They are
  called without `LLM_API_BASE`, so the document text goes to that provider; off unless `LLM_ALLOW_EXTERNAL=1`.
- Recordings (`LLM_CASSETTE=record|replay`, file `LLM_CASSETTE_PATH`, default `~/.cache/loan-draw/cassette.jsonl`
  so a recording made without a path never lands in the repository or the image): `record` saves every response keyed by the request,
  and a failed write is an error, not a reason to try another model; `replay` answers only from the file and fails
  on a request it has not seen. CI and the tests replay, so they need no GPU and no key, and a prompt change that
  was not re-recorded fails loudly instead of drifting.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

log = logging.getLogger(__name__)


class LLM(Protocol):
    def json(self, task: str, messages: list[dict], schema: type[BaseModel]) -> dict | None: ...
    def text(self, task: str, messages: list[dict]) -> str: ...


class CassetteMiss(KeyError):
    pass


class Cassette:
    def __init__(self, path: Path, mode: str):
        self.path, self.mode, self._lock = path, mode, threading.Lock()
        self.rows: dict[str, str] = {}
        if path.exists():
            for line in path.read_text().splitlines():
                r = json.loads(line)
                self.rows[r["key"]] = r["out"]

    @staticmethod
    def key(task: str, messages: list[dict], schema: dict | None) -> str:
        return hashlib.sha256(json.dumps([task, messages, schema], sort_keys=True).encode()).hexdigest()[:24]

    def get(self, key: str) -> str | None:
        return self.rows.get(key)

    def put(self, key: str, task: str, out: str) -> None:
        with self._lock:
            if key in self.rows:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as f:
                f.write(json.dumps({"key": key, "task": task, "out": out}) + "\n")
            self.rows[key] = out  # only after the write: a failed write must not answer from memory later


class Gateway:
    def __init__(self, model: str | None = None, fallbacks: list[str] | None = None, api_base: str | None = None,
                 cassette: Cassette | None = None, timeout: float = 60):
        self.model = model or os.environ.get("LLM_MODEL", "hosted_vllm/Qwen/Qwen2.5-7B-Instruct")
        env_fb = os.environ.get("LLM_FALLBACKS", "")
        self.fallbacks = fallbacks if fallbacks is not None else [m for m in env_fb.split(",") if m]
        if self.fallbacks and os.environ.get("LLM_ALLOW_EXTERNAL") != "1":
            raise ValueError("fallback models are called without LLM_API_BASE, so document text leaves the LAN; "
                             "set LLM_ALLOW_EXTERNAL=1 to allow it, or leave LLM_FALLBACKS empty")
        self.api_base = api_base or os.environ.get("LLM_API_BASE")
        self.timeout = timeout
        if cassette is None and os.environ.get("LLM_CASSETTE") in ("record", "replay"):
            default = Path.home() / ".cache" / "loan-draw" / "cassette.jsonl"  # never inside the repository
            cassette = Cassette(Path(os.environ.get("LLM_CASSETTE_PATH", default)), os.environ["LLM_CASSETTE"])
        self.cassette = cassette

    def _call(self, task: str, messages: list[dict], schema: type[BaseModel] | None) -> str:
        js = schema.model_json_schema() if schema else None
        key = Cassette.key(task, messages, js)
        if self.cassette and (hit := self.cassette.get(key)) is not None:
            return hit
        if self.cassette and self.cassette.mode == "replay":
            raise CassetteMiss(f"no recording for {task} ({key}); re-record with LLM_CASSETTE=record")
        import litellm  # imported lazily: replay runs never load it
        litellm.suppress_debug_info = True
        logging.getLogger("LiteLLM").setLevel(logging.WARNING)
        kw: dict = {"messages": messages, "temperature": 0, "timeout": self.timeout}
        if js:
            kw["response_format"] = {"type": "json_schema",
                                     "json_schema": {"name": schema.__name__, "schema": js, "strict": True}}
        last: Exception | None = None
        for i, model in enumerate([self.model, *self.fallbacks]):
            try:
                r = litellm.completion(model=model, api_base=self.api_base if i == 0 else None, **kw)
                out = r.choices[0].message.content or ""
            except Exception as e:  # noqa: BLE001 - try the next model, report the last error
                log.warning("model %s failed for %s: %s", model, task, type(e).__name__)
                last = e
            else:  # a failed recording write is not a model failure: it raises here, never tries another model
                if self.cassette:
                    self.cassette.put(key, task, out)
                return out
        raise RuntimeError(f"all models failed for {task}") from last

    def json(self, task: str, messages: list[dict], schema: type[BaseModel]) -> dict | None:
        raw = self._call(task, messages, schema)
        try:
            return schema.model_validate_json(_strip_fence(raw)).model_dump(mode="json")
        except ValueError:
            log.warning("unusable %s output from the model", task)
            return None

    def text(self, task: str, messages: list[dict]) -> str:
        return self._call(task, messages, None).strip()


def _strip_fence(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else ""
        s = s.rsplit("```", 1)[0]
    return s.strip()

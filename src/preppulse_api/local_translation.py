"""Persistent local IndicTrans2 process, isolated from the OCR/RAG environment.

The transport is a pair of local pipes, not a network API. No patient text is
written to a command line, temporary file or model download request.
"""

import atexit
import json
import os
import queue
import subprocess
import threading
from pathlib import Path

MODEL_VERSION = "indictrans2-1b-89cd0007-ac3daf0e-protected-v1"
ROOT = Path(__file__).resolve().parents[2]
_lock = threading.Lock()
_process = None
_output = None


def stop_worker():
    global _process, _output
    if _process is not None:
        _process.terminate()
        try:
            _process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _process.kill()
        for stream in (_process.stdin, _process.stdout):
            if stream:
                stream.close()
    _process = _output = None


atexit.register(stop_worker)


def worker_command():
    path = Path(os.getenv("PREPPULSE_TRANSLATION_CONFIG", ROOT / "private_data/translation.json"))
    if not path.is_file():
        raise RuntimeError("Local translation needs setup. Run scripts/setup_translation.ps1.")
    settings = json.loads(path.read_text(encoding="utf-8-sig"))
    command = settings.get("command")
    if not isinstance(command, list) or not command or not all(isinstance(x, str) for x in command):
        raise RuntimeError("Invalid local translation configuration")
    return command


def _read_lines(stream, output):
    try:
        for line in stream:
            output.put(line)
    finally:
        output.put(None)


def translate_local(batch, language):
    global _process, _output
    with _lock:
        if _process is None or _process.poll() is not None:
            stop_worker()
            _process = subprocess.Popen(
                worker_command(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                # Errors must not contain input clinical text. The worker returns
                # sanitized errors over stdout; model-library noise is discarded.
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            _output = queue.Queue()
            threading.Thread(
                target=_read_lines, args=(_process.stdout, _output), daemon=True
            ).start()
        try:
            _process.stdin.write(
                json.dumps(
                    {
                        "target_language": language,
                        "segments": [
                            {"id": key, "text": text, "source_language": source}
                            for key, text, source in batch
                        ],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            _process.stdin.flush()
            line = _output.get(timeout=int(os.getenv("PREPPULSE_TRANSLATION_TIMEOUT", "600")))
            if line is None:
                raise RuntimeError("Local translation worker stopped. Check model setup.")
            result = json.loads(line)
            if result.get("error"):
                raise RuntimeError(result["error"])
            return result["translations"]
        except (queue.Empty, OSError, ValueError, KeyError) as exc:
            stop_worker()
            raise RuntimeError(
                "Local translation timed out or stopped. Retry after checking setup."
            ) from exc

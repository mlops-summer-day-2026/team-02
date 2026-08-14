#!/usr/bin/env python3
"""Local HTTP wrapper for the separately installed TeraTTS package.

Run this script with the Python interpreter from the TeraTTS virtual environment.
It keeps the model in memory, synthesizes WAV, and uses macOS afconvert to produce
an M4A file accepted by Telegram's sendVoice method.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from typing import Any, Optional


class TeraTTSBridge:
    def __init__(self, teratts_home: Path) -> None:
        self.teratts_home = teratts_home.resolve()
        self.module = self._load_speak_module(self.teratts_home / "speak.py")
        self.lock = threading.Lock()

    @staticmethod
    def _load_speak_module(path: Path) -> ModuleType:
        if not path.is_file():
            raise RuntimeError(f"TeraTTS speak.py not found: {path}")
        spec = importlib.util.spec_from_file_location("local_teratts_speak", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Cannot load TeraTTS module: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def preload(self) -> None:
        self.module.get_tts(self.module.DEFAULT_MODEL)

    def synthesize_m4a(self, text: str) -> bytes:
        with self.lock, tempfile.TemporaryDirectory(prefix="teratts-http-") as directory:
            temp_dir = Path(directory)
            wav_path = temp_dir / "speech.wav"
            m4a_path = temp_dir / "speech.m4a"
            audio = self.module.synthesize(
                text, self.module.DEFAULT_MODEL, accent=True
            )
            self.module.get_tts(self.module.DEFAULT_MODEL).save_wav(audio, str(wav_path))
            subprocess.run(
                [
                    "/usr/bin/afconvert",
                    "-f",
                    "m4af",
                    "-d",
                    "aac",
                    str(wav_path),
                    str(m4a_path),
                ],
                check=True,
                capture_output=True,
            )
            return m4a_path.read_bytes()


class TeraTTSRequestHandler(BaseHTTPRequestHandler):
    bridge: TeraTTSBridge
    server_version = "TeraTTSLocal/0.1"

    def do_GET(self) -> None:
        if self.path != "/health":
            self._json_response(404, {"error": "not_found"})
            return
        self._json_response(200, {"status": "ok"})

    def do_POST(self) -> None:
        if self.path != "/synthesize":
            self._json_response(404, {"error": "not_found"})
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json_response(400, {"error": "invalid_content_length"})
            return
        if content_length <= 0 or content_length > 16_384:
            self._json_response(400, {"error": "invalid_body_size"})
            return
        try:
            body = json.loads(self.rfile.read(content_length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._json_response(400, {"error": "invalid_json"})
            return
        text = body.get("text") if isinstance(body, dict) else None
        if not isinstance(text, str) or not text.strip():
            self._json_response(400, {"error": "text_required"})
            return
        text = text.strip()
        if len(text) > 500:
            self._json_response(400, {"error": "text_too_long"})
            return
        try:
            audio = self.bridge.synthesize_m4a(text)
        except Exception as exc:
            print(f"TeraTTS synthesis failed: {type(exc).__name__}: {exc}")
            self._json_response(500, {"error": "synthesis_failed"})
            return
        self.send_response(200)
        self.send_header("Content-Type", "audio/mp4")
        self.send_header("Content-Length", str(len(audio)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(audio)

    def _json_response(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"TeraTTS HTTP: {format % args}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local HTTP service for TeraTTS")
    parser.add_argument(
        "--teratts-home",
        type=Path,
        default=Path("/Users/razraz/Documents/TeraTTS"),
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--preload", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    bridge = TeraTTSBridge(args.teratts_home)
    if args.preload:
        print("Loading TeraTTS model…")
        bridge.preload()
        print("TeraTTS model loaded")
    TeraTTSRequestHandler.bridge = bridge
    server = ThreadingHTTPServer((args.host, args.port), TeraTTSRequestHandler)
    print(f"TeraTTS HTTP listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

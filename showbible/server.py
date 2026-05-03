from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .vault import append_transcript_entry, doctor, episode_meta, list_episodes, people, read_json

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def serve(vault: Path, host: str = "127.0.0.1", port: int = 0, once: bool = False) -> str:
    _validate_loopback(host)
    if once:
        return json.dumps(smoke_payload(vault), sort_keys=True)

    httpd = make_server(vault, host, port)
    actual_host, actual_port = httpd.server_address
    print(f"ShowBible UI listening on http://{actual_host}:{actual_port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        return f"http://{actual_host}:{actual_port}"
    return f"http://{actual_host}:{actual_port}"


def make_server(vault: Path, host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    _validate_loopback(host)

    class Handler(ShowBibleHandler):
        vault_path = vault

    return ThreadingHTTPServer((host, port), Handler)


class ShowBibleHandler(BaseHTTPRequestHandler):
    vault_path: Path

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_text(_ui_html(), "text/html; charset=utf-8")
        elif parsed.path == "/api/status":
            self._send_json(status_payload(self.vault_path))
        elif parsed.path == "/api/transcript":
            query = parse_qs(parsed.query)
            episode = query.get("episode", [None])[0]
            self._send_json({"episode": episode, "transcript": transcript_text(self.vault_path, episode)})
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/intervene":
            self.send_error(404)
            return
        length = int(self.headers.get("content-length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        episode = payload.get("episode") or (list_episodes(self.vault_path) or ["S01E01"])[0]
        content = str(payload.get("content") or "").strip()
        kind = str(payload.get("type") or "note")
        if not content:
            self.send_error(400, "content required")
            return
        target = self.vault_path / "episodes" / episode / "writers-room" / "999-ui-interventions.md"
        role = "Producer note" if kind == "note" else "Guest Writer"
        append_transcript_entry(target, "user", role, content, intervention=True)
        self._send_json({"ok": True, "intervention": {"kind": kind, "content": content}})

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def _send_json(self, payload: object, status: int = 200) -> None:
        self._send_text(json.dumps(payload, indent=2, sort_keys=True), "application/json", status)

    def _send_text(self, text: str, content_type: str, status: int = 200) -> None:
        encoded = text.encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def status_payload(vault: Path) -> dict[str, object]:
    episodes = []
    for episode_id in list_episodes(vault):
        episode = vault / "episodes" / episode_id
        episodes.append(episode_meta(episode))
    return {
        "vault": str(vault),
        "cast": people(vault),
        "episodes": episodes,
        "findings": [finding.__dict__ for finding in doctor(vault)],
        "cost": read_json(vault / ".room" / "costs.json", {}),
    }


def transcript_text(vault: Path, episode: str | None) -> str:
    if not episode:
        episodes = list_episodes(vault)
        episode = episodes[0] if episodes else None
    if not episode:
        return ""
    room = vault / "episodes" / episode / "writers-room"
    if not room.exists():
        return ""
    parts = []
    for path in sorted(room.glob("*.md")):
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _ui_html() -> str:
    return resources.files("showbible").joinpath("ui/index.html").read_text(encoding="utf-8")


def smoke_payload(vault: Path) -> dict[str, object]:
    ui = _ui_html()
    return {
        "ok": True,
        "vault": str(vault),
        "episodes": list_episodes(vault),
        "ui_bytes": len(ui.encode("utf-8")),
        "routes": ["/", "/api/status", "/api/transcript", "/api/intervene"],
        "status": status_payload(vault),
    }


def _validate_loopback(host: str) -> None:
    if host not in LOOPBACK_HOSTS:
        raise ValueError("ShowBible UI is loopback-only; use 127.0.0.1, localhost, or ::1.")

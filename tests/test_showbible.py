from __future__ import annotations

import json
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

import pytest

from showbible.cli import main
from showbible.engine import PHASES, _phase_prompt, run_episode
from showbible.providers import LMStudioProvider, resolve_provider
from showbible.server import make_server, serve, status_payload, transcript_text
from showbible.vault import VaultError, atomic_write_text, doctor, init_vault, list_episodes, read_json


def test_init_vault_creates_documented_shape(tmp_path: Path) -> None:
    vault = init_vault(tmp_path / "demo", show_name="Demo Show")

    assert (vault / "pack.yaml").is_file()
    assert (vault / "people" / "showrunner.md").is_file()
    assert (vault / "lore-bible" / "canon.md").is_file()
    assert (vault / "arcs" / "season-theme.md").is_file()
    assert (vault / "episodes").is_dir()
    assert (vault / ".room" / "costs.json").is_file()
    assert doctor(vault) == []
    assert "default: lmstudio" in (vault / "pack.yaml").read_text(encoding="utf-8")


def test_init_refuses_non_empty_directory(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    target.mkdir()
    (target / "keep.txt").write_text("do not overwrite", encoding="utf-8")

    with pytest.raises(VaultError):
        init_vault(target)


def test_mock_episode_run_writes_pipeline_outputs(tmp_path: Path) -> None:
    vault = init_vault(tmp_path / "demo")
    result = run_episode(
        vault,
        "S01E01",
        "mock",
        notes=["More emotional cost."],
        speak_as=["director:Keep the camera honest."],
    )
    episode = vault / "episodes" / "S01E01"

    assert result.completed_phases == PHASES
    assert (episode / "pitch.md").is_file()
    assert (episode / "beats.md").is_file()
    assert (episode / "drafts" / "v1-fast.md").is_file()
    assert (episode / "drafts" / "v2-after-room.md").is_file()
    assert (episode / "script.md").is_file()
    assert (episode / "callbacks.yaml").is_file()
    assert "Producer note" in (episode / "writers-room" / "000-interventions.md").read_text(encoding="utf-8")
    assert "voicing director" in (episode / "writers-room" / "000-interventions.md").read_text(encoding="utf-8")
    assert "## Showrunner (Showrunner)" in (episode / "writers-room" / "001-phase-pitch.md").read_text(
        encoding="utf-8"
    )
    assert "S01E01 continuity check" in (vault / "lore-bible" / "canon.md").read_text(encoding="utf-8")


def test_mock_episode_resume_skips_completed_phases(tmp_path: Path) -> None:
    vault = init_vault(tmp_path / "demo")
    run_episode(vault, "S01E01", "mock")

    result = run_episode(vault, "S01E01", "mock")

    assert result.skipped_phases == PHASES
    assert result.tokens == 0


def test_resume_infers_completed_phases_from_vault_files(tmp_path: Path) -> None:
    vault = init_vault(tmp_path / "demo")
    episode = vault / "episodes" / "S01E01"
    (episode / "drafts").mkdir(parents=True)
    atomic_write_text(episode / "pitch.md", "# Existing Pitch\n")
    atomic_write_text(episode / "beats.md", "# Existing Beats\n")

    result = run_episode(vault, "S01E01", "mock")

    assert result.skipped_phases[:2] == ["pitch", "break"]
    assert "Existing Pitch" in (episode / "pitch.md").read_text(encoding="utf-8")
    assert read_json(episode / "meta.json", {})["completed_phases"] == PHASES


def test_new_intervention_after_completed_run_is_preserved(tmp_path: Path) -> None:
    vault = init_vault(tmp_path / "demo")
    run_episode(vault, "S01E01", "mock", notes=["First note."])
    run_episode(vault, "S01E01", "mock", notes=["Second note."])

    transcript = (vault / "episodes" / "S01E01" / "writers-room" / "000-interventions.md").read_text(encoding="utf-8")
    assert "First note." in transcript
    assert "Second note." in transcript


def test_cli_smoke_commands(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    vault = tmp_path / "demo"

    assert main(["init", str(vault), "--from", "Demo Show"]) == 0
    assert main(["run", "--vault", str(vault), "--episode", "S01E01", "--provider", "mock"]) == 0
    assert main(["doctor", "--vault", str(vault)]) == 0
    assert main(["status", "--vault", str(vault)]) == 0
    assert main(["transcript", "--vault", str(vault), "S01E01"]) == 0
    assert main(["lore", "--vault", str(vault)]) == 0
    assert main(["arcs", "--vault", str(vault)]) == 0
    assert main(["cost", "--vault", str(vault), "--json"]) == 0
    assert main(["attach", "--vault", str(vault), "--once"]) == 0

    output = capsys.readouterr().out
    assert "Initialized ShowBible vault" in output
    assert "Ran S01E01" in output
    assert "Doctor clean" in output
    assert "ShowBible" not in output or "S01E01" in output


def test_cli_continue_uses_room_state_and_preserves_pause_context(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    vault = tmp_path / "demo"
    assert main(["init", str(vault)]) == 0
    assert main(["run", "--vault", str(vault), "--episode", "S01E03", "--provider", "mock"]) == 0
    assert main(["pause", "--vault", str(vault)]) == 0
    assert read_json(vault / ".room" / "state.json", {})["current_episode"] == "S01E03"

    assert main(["continue", "--vault", str(vault), "--provider", "mock"]) == 0

    output = capsys.readouterr().out
    assert "Continued S01E03" in output
    assert (vault / ".room" / "sessions" / "S01E03.json").is_file()
    assert read_json(vault / ".room" / "state.json", {})["status"] == "done"
    assert read_json(vault / "episodes" / "S01E03" / "meta.json", {})["status"] == "done"


def test_python_module_cli_works_from_checkout() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "showbible.cli", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Local-first AI writers room framework" in result.stdout


def test_attach_rejects_non_loopback_host(tmp_path: Path) -> None:
    vault = init_vault(tmp_path / "demo")

    assert main(["attach", "--vault", str(vault), "--host", "0.0.0.0", "--once"]) == 2


def test_episode_and_cast_commands(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    vault = init_vault(tmp_path / "demo")

    assert main(["episode", "new", "--vault", str(vault), "S01E02"]) == 0
    assert main(["episode", "list", "--vault", str(vault)]) == 0
    assert main(["episode", "fork", "--vault", str(vault), "S01E02", "S01E02-alt"]) == 0
    assert main(["cast", "--vault", str(vault), "--auto"]) == 0
    assert main(["pack", "list", "--vault", str(vault)]) == 0
    assert main(["pack", "add", "--vault", str(vault), "Star Trek"]) == 0

    assert list_episodes(vault) == ["S01E02", "S01E02-alt"]
    output = capsys.readouterr().out
    assert "showrunner" in output
    assert "Star Trek" in output


def test_server_payloads(tmp_path: Path) -> None:
    vault = init_vault(tmp_path / "demo")
    run_episode(vault, "S01E01", "mock")

    payload = status_payload(vault)
    transcript = transcript_text(vault, "S01E01")
    smoke = serve(vault, once=True)

    assert payload["episodes"][0]["episode"] == "S01E01"
    assert "Showrunner" in transcript
    assert str(vault) in smoke
    assert "ui_bytes" in smoke


def test_server_routes_smoke(tmp_path: Path) -> None:
    vault = init_vault(tmp_path / "demo")
    run_episode(vault, "S01E01", "mock")
    httpd = make_server(vault, "127.0.0.1", 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        index = urllib.request.urlopen(base + "/", timeout=2).read().decode("utf-8")
        status = json.loads(urllib.request.urlopen(base + "/api/status", timeout=2).read().decode("utf-8"))
        transcript = json.loads(
            urllib.request.urlopen(base + "/api/transcript?episode=S01E01", timeout=2).read().decode("utf-8")
        )
        request = urllib.request.Request(
            base + "/api/intervene",
            data=json.dumps({"episode": "S01E01", "type": "note", "content": "Route smoke."}).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        intervention = json.loads(urllib.request.urlopen(request, timeout=2).read().decode("utf-8"))
    finally:
        httpd.shutdown()
        thread.join(timeout=2)

    assert "<title>ShowBible</title>" in index
    assert status["episodes"][0]["episode"] == "S01E01"
    assert "Showrunner" in transcript["transcript"]
    assert intervention["ok"] is True


def test_lmstudio_provider_uses_local_openai_compatible_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "choices": [{"message": {"content": "# Pitch\n\nA local model argues the episode into shape."}}],
                    "usage": {"total_tokens": 42},
                }
            ).encode("utf-8")

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> Response:
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return Response()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    generation = LMStudioProvider(timeout=5, max_tokens=123).generate("pitch", "S01E01", "Use the note.")

    assert captured["url"] == "http://127.0.0.1:1234/v1/chat/completions"
    assert captured["timeout"] == 5
    assert captured["body"]["model"] == "google/gemma-4-e4b"
    assert captured["body"]["max_tokens"] == 123
    assert captured["body"]["stream"] is False
    assert "do not wait for more context" in captured["body"]["messages"][0]["content"]
    assert "Use the note." in captured["body"]["messages"][1]["content"]
    assert generation.text.startswith("# Pitch")
    assert generation.tokens == 42


def test_lmstudio_provider_retries_empty_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        {"choices": [{"message": {"content": ""}}]},
        {"choices": [{"message": {"content": "Recovered output."}}]},
    ]
    prompts = []

    class Response:
        def __init__(self, payload: dict[str, object]):
            self.payload = payload

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> Response:
        prompts.append(json.loads(request.data.decode("utf-8"))["messages"][1]["content"])
        return Response(responses.pop(0))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    generation = LMStudioProvider(timeout=5).generate("pitch", "S01E01", "Use the note.")

    assert generation.text == "Recovered output."
    assert len(prompts) == 2
    assert "previous completion was empty" in prompts[1]


def test_default_provider_is_lmstudio() -> None:
    assert isinstance(resolve_provider(None), LMStudioProvider)


def test_lmstudio_provider_fallback_prompt_is_concrete() -> None:
    prompt = LMStudioProvider()._user_prompt("pitch", "S01E00", "")

    assert "Invent concrete details" in prompt
    assert "No prior episode context" not in prompt


def test_phase_prompt_includes_show_pack(tmp_path: Path) -> None:
    vault = init_vault(tmp_path / "demo", show_name="Prompt Show")
    episode = vault / "episodes" / "S01E01"
    episode.mkdir(parents=True)

    prompt = _phase_prompt(vault, episode, "pitch", {"interventions": []})

    assert "Show pack:" in prompt
    assert "Prompt Show" in prompt

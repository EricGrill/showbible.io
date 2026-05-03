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
from showbible.providers import LMStudioProvider, ProviderError, resolve_provider
from showbible.server import make_server, serve, status_payload, transcript_text
from showbible.vault import VaultError, atomic_write_text, cast_roles, doctor, init_vault, list_episodes, read_json


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
    assert main(["lore", "explain", "--vault", str(vault)]) == 0
    assert main(["lore", "paths", "--vault", str(vault)]) == 0
    assert main(["lore", "add", "--vault", str(vault), "The bridge has a secret door.", "--source", "S01E01"]) == 0
    assert main(["lore", "show", "--vault", str(vault)]) == 0
    assert main(["arcs", "--vault", str(vault)]) == 0
    assert main(["arcs", "list", "--vault", str(vault), "--episode", "S01E01"]) == 0
    assert main(["arcs", "current", "--vault", str(vault), "--episode", "S01E01"]) == 0
    assert main(["arcs", "add", "--vault", str(vault), "The pilot sharpens the season question.", "--episode", "S01E01"]) == 0
    assert main(["arcs", "show", "--vault", str(vault), "season-theme"]) == 0
    assert main(["cost", "--vault", str(vault), "--json"]) == 0
    assert main(["attach", "--vault", str(vault), "--once"]) == 0

    output = capsys.readouterr().out
    assert "Initialized ShowBible vault" in output
    assert "Ran S01E01" in output
    assert "The bridge has a secret door." in output
    assert "lore-bible/canon.md" in output
    assert "Arc context for S01E01" in output
    assert "The pilot sharpens the season question." in output
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
    assert main(["episode", "show", "--vault", str(vault), "S01E02"]) == 0
    assert main(["episode", "fork", "--vault", str(vault), "S01E02", "S01E02-alt"]) == 0
    assert main(["cast", "--vault", str(vault), "--auto"]) == 0
    assert main(["cast", "kinds"]) == 0
    assert main(["cast", "add", "--vault", str(vault), "Patrick Stewart", "--kind", "actor", "--plays", "picard"]) == 0
    assert main(["cast", "suggest", "--vault", str(vault), "Star Trek", "--provider", "mock", "--apply"]) == 0
    assert main(["cast", "remove", "--vault", str(vault), "lead-actor"]) == 0
    assert main(["pack", "list", "--vault", str(vault)]) == 0
    assert main(["pack", "add", "--vault", str(vault), "Star Trek"]) == 0
    assert main(["workflow", "--vault", str(vault), "--episode", "S01E01", "--provider", "mock", "--no-tui"]) == 0
    assert main(["tui", "--vault", str(vault), "--episode", "S01E01", "--provider", "mock", "--no-tui"]) == 0

    assert list_episodes(vault) == ["S01E01", "S01E02", "S01E02-alt"]
    role_slugs = {role.person for role in cast_roles(vault)}
    assert "patrick-stewart" in role_slugs
    assert "lead-actor" not in role_slugs
    assert (vault / "people" / "patrick-stewart.md").is_file()
    assert (vault / "research" / "cast-suggestions.md").is_file()
    output = capsys.readouterr().out
    assert "showrunner" in output
    assert "lore-keeper" in output
    assert "Star Trek" in output
    assert "ShowBible workflow for S01E01" in output
    assert "Current cast (episode S01E01)" in output
    assert "Current arcs for S01E01" in output


def test_arcs_follow_current_episode_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    vault = init_vault(tmp_path / "demo")
    episode = vault / "episodes" / "S01E07"
    episode.mkdir(parents=True)
    monkeypatch.chdir(episode)

    assert main(["arcs", "add", "The episode pays off a hidden debt."]) == 0
    assert main(["arcs", "current"]) == 0

    output = capsys.readouterr().out
    assert "S01E07 [planned]" in output
    assert "Current arcs for S01E07" in output
    assert "hidden debt" in (vault / "arcs" / "season-theme.md").read_text(encoding="utf-8")


def test_cast_scope_follows_current_episode_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = init_vault(tmp_path / "demo")
    episode = vault / "episodes" / "S01E04"
    (episode / "drafts").mkdir(parents=True)
    monkeypatch.chdir(episode)

    assert main(["cast", "add", "Michael Imperioli", "--kind", "actor", "--plays", "christopher"]) == 0

    pack_roles = {role.person for role in cast_roles(vault)}
    episode_meta = read_json(episode / "meta.json", {})
    assert "michael-imperioli" not in pack_roles
    assert episode_meta["cast_overrides"] == [
        {"kind": "actor", "person": "michael-imperioli", "plays": "christopher"}
    ]


def test_cast_scope_can_force_show_from_episode_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = init_vault(tmp_path / "demo")
    episode = vault / "episodes" / "S01E05"
    episode.mkdir(parents=True)
    monkeypatch.chdir(episode)

    assert main(["cast", "add", "--show", "David Chase", "--kind", "showrunner"]) == 0

    pack_roles = {role.person for role in cast_roles(vault)}
    assert "david-chase" in pack_roles
    assert "cast_overrides" not in read_json(episode / "meta.json", {})


def test_cast_suggest_uses_current_show_and_episode_scope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = init_vault(tmp_path / "Sopranos", show_name="The Sopranos")
    episode = vault / "episodes" / "S01E01"
    episode.mkdir(parents=True)
    captured = {}

    class Provider:
        name = "capture"

        def generate(self, phase: str, episode_id: str, prompt: str):
            captured["prompt"] = prompt
            return type(
                "Generation",
                (),
                {
                    "text": '[{"kind":"actor","person":"lorraine-bracco","display_name":"Lorraine Bracco","plays":"melfi"}]',
                    "tokens": 0,
                    "dollars": 0.0,
                },
            )()

    monkeypatch.setattr("showbible.cli.resolve_provider", lambda name: Provider())
    monkeypatch.chdir(episode)

    assert main(["cast", "suggest", "--apply"]) == 0

    assert "The Sopranos" in captured["prompt"]
    assert "Episode scope: S01E01" in captured["prompt"]
    assert read_json(episode / "meta.json", {})["cast_overrides"] == [
        {"kind": "actor", "person": "lorraine-bracco", "plays": "melfi"}
    ]
    assert (vault / "episodes" / "S01E01" / "cast-suggestions.md").is_file()


def test_cast_suggest_excludes_existing_people(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    vault = init_vault(tmp_path / "Sopranos", show_name="The Sopranos")
    captured = {}

    class Provider:
        name = "capture"

        def generate(self, phase: str, episode_id: str, prompt: str):
            captured["prompt"] = prompt
            return type(
                "Generation",
                (),
                {
                    "text": (
                        "["
                        '{"kind":"showrunner","person":"showrunner","display_name":"Showrunner"},'
                        '{"kind":"actor","person":"edie-falco","display_name":"Edie Falco","plays":"carmela"}'
                        "]"
                    ),
                    "tokens": 0,
                    "dollars": 0.0,
                },
            )()

    monkeypatch.setattr("showbible.cli.resolve_provider", lambda name: Provider())

    assert main(["cast", "suggest", "--vault", str(vault), "--json"]) == 0

    output = capsys.readouterr().out
    assert "Exclude these already-cast people" in captured["prompt"]
    assert "showrunner" in captured["prompt"]
    assert "edie-falco" in output
    assert '"person": "showrunner"' not in output


def test_cast_suggest_falls_back_when_provider_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    vault = init_vault(tmp_path / "Sopranos", show_name="The Sopranos")

    class Provider:
        name = "broken"

        def generate(self, phase: str, episode_id: str, prompt: str):
            raise ProviderError("empty local completion")

    monkeypatch.setattr("showbible.cli.resolve_provider", lambda name: Provider())

    assert main(["cast", "suggest", "--vault", str(vault), "--json"]) == 0

    output = capsys.readouterr().out
    assert "terence-winter" in output
    assert '"person": "showrunner"' not in output
    assert "Provider failed" in (vault / "research" / "cast-suggestions-raw.md").read_text(encoding="utf-8")


def test_help_topics_are_detailed(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["help", "cast"]) == 0
    assert main(["help", "roles"]) == 0
    assert main(["help", "tui"]) == 0
    assert main(["help", "lore"]) == 0
    assert main(["help", "arcs"]) == 0
    assert main(["help", "workflow"]) == 0

    output = capsys.readouterr().out
    assert "showbible cast suggest --pick" in output
    assert "lore-keeper" in output
    assert "showbible lore add" in output
    assert "showbible arcs current" in output
    assert "showbible workflow --episode S01E01" in output
    assert "space" in output


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


def test_lmstudio_cast_suggest_gets_larger_token_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps({"choices": [{"message": {"content": "[]"}}]}).encode("utf-8")

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> Response:
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return Response()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    LMStudioProvider(max_tokens=123).generate("cast-suggest", "cast", "Return JSON.")

    assert captured["body"]["max_tokens"] == 700


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


def test_cast_suggest_prompt_rejects_generic_labels(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = init_vault(tmp_path / "demo")
    captured = {}

    class Provider:
        name = "capture"

        def generate(self, phase: str, episode_id: str, prompt: str):
            captured["phase"] = phase
            captured["prompt"] = prompt
            return type("Generation", (), {"text": "[]", "tokens": 0, "dollars": 0.0})()

    monkeypatch.setattr("showbible.cli.resolve_provider", lambda name: Provider())

    assert main(["cast", "suggest", "--vault", str(vault), "Star Trek: The Next Generation"]) == 0
    assert captured["phase"] == "cast-suggest"
    assert "Use real public people associated with the show" in captured["prompt"]
    assert "Do not invent generic labels" in captured["prompt"]


def test_cast_suggest_repairs_invalid_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = init_vault(tmp_path / "demo")
    calls = []

    class Provider:
        name = "repair"

        def generate(self, phase: str, episode_id: str, prompt: str):
            calls.append(prompt)
            text = "not json" if len(calls) == 1 else '[{"kind":"actor","person":"patrick-stewart","display_name":"Patrick Stewart","plays":"picard"}]'
            return type("Generation", (), {"text": text, "tokens": 0, "dollars": 0.0})()

    monkeypatch.setattr("showbible.cli.resolve_provider", lambda name: Provider())

    assert main(["cast", "suggest", "--vault", str(vault), "Star Trek: The Next Generation", "--apply"]) == 0
    assert len(calls) == 2
    assert "previous output was not valid JSON" in calls[1]
    assert (vault / "people" / "patrick-stewart.md").is_file()


def test_cast_suggest_salvages_truncated_json_objects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = init_vault(tmp_path / "demo")

    class Provider:
        name = "truncated"

        def generate(self, phase: str, episode_id: str, prompt: str):
            text = (
                "```json\n"
                '[{"kind":"showrunner","person":"david-chase","display_name":"David Chase"},'
                '{"kind":"writer","person":"terence-winter","display_name":"Terence Winter","plays":["writer-room"]},'
                '{"kind":"actor","person":"'
            )
            return type("Generation", (), {"text": text, "tokens": 0, "dollars": 0.0})()

    monkeypatch.setattr("showbible.cli.resolve_provider", lambda name: Provider())

    assert main(["cast", "suggest", "--vault", str(vault), "The Sopranos", "--apply"]) == 0

    assert (vault / "people" / "david-chase.md").is_file()
    winter = (vault / "people" / "terence-winter.md").read_text(encoding="utf-8")
    assert "plays: writer-room" in winter


def test_phase_prompt_includes_show_pack(tmp_path: Path) -> None:
    vault = init_vault(tmp_path / "demo", show_name="Prompt Show")
    episode = vault / "episodes" / "S01E01"
    episode.mkdir(parents=True)

    prompt = _phase_prompt(vault, episode, "pitch", {"interventions": []})

    assert "Show pack:" in prompt
    assert "Prompt Show" in prompt

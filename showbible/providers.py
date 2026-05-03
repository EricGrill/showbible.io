from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol


class ProviderError(RuntimeError):
    """Raised for provider configuration or generation failures."""


@dataclass(frozen=True)
class Generation:
    text: str
    tokens: int
    dollars: float


class Provider(Protocol):
    name: str

    def generate(self, phase: str, episode_id: str, prompt: str) -> Generation:
        ...


class MockProvider:
    name = "mock"

    def generate(self, phase: str, episode_id: str, prompt: str) -> Generation:
        text = MOCK_OUTPUTS.get(phase, f"{phase.title()} output for {episode_id}.")
        if "{episode_id}" in text:
            text = text.format(episode_id=episode_id)
        if prompt.strip():
            text = f"{text}\n\nProduction note considered: {prompt.strip()}"
        tokens = max(32, len(text.split()) * 2)
        return Generation(text=text, tokens=tokens, dollars=0.0)


class RemotePlaceholderProvider:
    def __init__(self, name: str, env_key: str):
        self.name = name
        self.env_key = env_key

    def generate(self, phase: str, episode_id: str, prompt: str) -> Generation:
        if not os.environ.get(self.env_key):
            raise ProviderError(f"{self.name} requires {self.env_key}; use --provider mock for deterministic local runs.")
        text = (
            f"{self.name} provider seam reached for {phase} in {episode_id}.\n\n"
            "Real streaming calls are intentionally not enabled in the v0 vertical slice."
        )
        return Generation(text=text, tokens=max(32, len(text.split()) * 2), dollars=0.0)


class LMStudioProvider:
    name = "lmstudio"

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
        max_tokens: int | None = None,
    ):
        self.base_url = (base_url or os.environ.get("LMSTUDIO_BASE_URL") or "http://127.0.0.1:1234").rstrip("/")
        self.model = model or os.environ.get("LMSTUDIO_MODEL") or "google/gemma-4-e4b"
        self.timeout = timeout
        self.max_tokens = max_tokens or _env_int("LMSTUDIO_MAX_TOKENS", 450)

    def generate(self, phase: str, episode_id: str, prompt: str) -> Generation:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are ShowBible's local writers-room engine. "
                        "Write concise, production-useful markdown for the requested phase. "
                        "Preserve the user's interventions as creative constraints. "
                        "Do not ask follow-up questions, do not use placeholders, and do not wait for more context."
                    ),
                },
                {
                    "role": "user",
                    "content": self._user_prompt(phase, episode_id, prompt),
                },
            ],
            "temperature": 0.7,
            "max_tokens": max(self.max_tokens, 700) if phase == "cast-suggest" else self.max_tokens,
            "stream": False,
        }
        data = self._post_chat_completion(payload)
        text = self._completion_text(data)
        if not text:
            retry_payload = dict(payload)
            retry_payload["messages"] = list(payload["messages"])
            retry_payload["messages"][1] = {
                "role": "user",
                "content": payload["messages"][1]["content"]
                + "\n\nYour previous completion was empty. Return concrete markdown now.",
            }
            data = self._post_chat_completion(retry_payload)
            text = self._completion_text(data)
        if not text:
            raise ProviderError("LM Studio returned an empty completion.")
        usage = data.get("usage") or {}
        tokens = int(usage.get("total_tokens") or max(32, len(text.split()) * 2))
        return Generation(text=text, tokens=tokens, dollars=0.0)

    def _post_chat_completion(self, payload: dict[str, object]) -> dict[str, object]:
        request = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise ProviderError(
                f"LM Studio is not reachable at {self.base_url}; start LM Studio or use --provider mock."
            ) from exc
        if not isinstance(data, dict):
            raise ProviderError("LM Studio returned an unexpected chat completion response.")
        return data

    def _completion_text(self, data: dict[str, object]) -> str:
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("LM Studio returned an unexpected chat completion response.") from exc

    def _user_prompt(self, phase: str, episode_id: str, prompt: str) -> str:
        phase_goal = {
            "pitch": "Write a one-paragraph episode pitch tied to the season theme.",
            "break": "Turn the pitch into act beats and a scene spine.",
            "fast-draft": "Draft compact screenplay-style dialogue for the core scene.",
            "room-pass": "Write writers-room notes that identify weak character or theme choices.",
            "polish": "Integrate the notes into a clean script excerpt.",
            "continuity-check": "Check continuity, name any new canon fact, and keep it concise.",
        }.get(phase, f"Write the {phase} output.")
        context = prompt.strip() or (
            "Use a self-contained speculative adventure show about a collaborative crew confronting a contained mystery. "
            "Invent concrete details as needed."
        )
        return f"Episode: {episode_id}\nPhase: {phase}\nGoal: {phase_goal}\n\nContext:\n{context}"


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


MOCK_OUTPUTS = {
    "pitch": (
        "# Pitch\n\n"
        "{episode_id} begins when the room discovers that the season theme only works if the protagonist loses the argument first."
    ),
    "break": (
        "# Beats\n\n"
        "1. Cold open: the premise breaks in public.\n"
        "2. Act one: the cast chooses the wrong solution.\n"
        "3. Act two: a contested scene forces the room to pick a side.\n"
        "4. Act three: the emotional truth lands before the plot does.\n"
        "5. Tag: the season spine gains a sharper question."
    ),
    "fast-draft": (
        "# Fast Draft\n\n"
        "INT. WRITERS ROOM - NIGHT\n\n"
        "SHOWRUNNER\n"
        "The scene works only if everyone wants something different.\n\n"
        "DIRECTOR\n"
        "Then keep the camera on the person who is losing.\n"
    ),
    "room-pass": (
        "The room flags the act two exchange as too tidy and asks for a rougher, more human disagreement."
    ),
    "polish": (
        "# Script\n\n"
        "INT. WRITERS ROOM - NIGHT\n\n"
        "A table full of voices circles the same impossible beat until the silence finally tells them what the scene is about.\n\n"
        "SHOWRUNNER\n"
        "Good. Now it costs somebody something.\n"
    ),
    "continuity-check": (
        "Continuity clean. New fact: the season theme is strongest when the room lets characters lose cleanly before they win."
    ),
    "cast-suggest": (
        "[\n"
        "  {\"kind\": \"showrunner\", \"person\": \"showrunner\", \"display_name\": \"Showrunner\"},\n"
        "  {\"kind\": \"director\", \"person\": \"director\", \"display_name\": \"Director\"},\n"
        "  {\"kind\": \"writer\", \"person\": \"staff-writer\", \"display_name\": \"Staff Writer\"},\n"
        "  {\"kind\": \"actor\", \"person\": \"lead-actor\", \"display_name\": \"Lead Actor\", \"plays\": \"lead-character\"}\n"
        "]"
    ),
}


def resolve_provider(name: str | None) -> Provider:
    selected = (name or "lmstudio").lower()
    if selected == "mock":
        return MockProvider()
    if selected in {"lmstudio", "lm-studio", "local"}:
        return LMStudioProvider()
    if selected == "anthropic":
        return RemotePlaceholderProvider("anthropic", "ANTHROPIC_API_KEY")
    if selected == "openai":
        return RemotePlaceholderProvider("openai", "OPENAI_API_KEY")
    if selected == "ollama":
        return RemotePlaceholderProvider("ollama", "OLLAMA_HOST")
    raise ProviderError(f"Unknown provider: {name}")

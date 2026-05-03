from __future__ import annotations

import os
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
}


def resolve_provider(name: str | None) -> Provider:
    selected = (name or "mock").lower()
    if selected == "mock":
        return MockProvider()
    if selected == "anthropic":
        return RemotePlaceholderProvider("anthropic", "ANTHROPIC_API_KEY")
    if selected == "openai":
        return RemotePlaceholderProvider("openai", "OPENAI_API_KEY")
    if selected == "ollama":
        return RemotePlaceholderProvider("ollama", "OLLAMA_HOST")
    raise ProviderError(f"Unknown provider: {name}")

# Providers & configuration

[← Docs index](./README.md)

The provider is selected with `--provider` (default `lmstudio`):

| Provider | Behavior |
|---|---|
| `lmstudio` (aliases `lm-studio`, `local`) | **Default.** Calls a local LM Studio OpenAI-compatible endpoint. |
| `mock` | Deterministic canned output. No model required — ideal for tests and smoke runs. |
| `anthropic` / `openai` / `ollama` | **Placeholder seams.** They require an API key/host env var and return stub text; real streaming is intentionally not wired up in v0. |

## LM Studio settings

The default provider talks to [LM Studio](https://lmstudio.ai/) over its
OpenAI-compatible `/v1/chat/completions` endpoint. Configure it with environment
variables:

| Variable | Default |
|---|---|
| `LMSTUDIO_BASE_URL` | `http://127.0.0.1:1234` |
| `LMSTUDIO_MODEL` | `google/gemma-4-e4b` |
| `LMSTUDIO_MAX_TOKENS` | `450` (raised to ≥700 for cast suggestions) |

If LM Studio is unreachable, the run fails with a clear message pointing you at
`--provider mock`.

## Graceful fallbacks

Cast/arc/lore suggestions degrade gracefully to built-in fallback lists when the
provider errors or returns invalid JSON. The cast fallback includes curated picks for
*The Sopranos* and *Star Trek: The Next Generation*; other shows get generic role
seeds. Raw provider output is saved next to the suggestion file (e.g.
`cast-suggestions-raw.md`) when parsing fails, so you can recover it.

## Adding a provider

Implement the `Provider` protocol in `showbible/providers.py`:

```python
def generate(self, phase: str, episode_id: str, prompt: str) -> Generation: ...
```

`Generation` carries `text`, `tokens`, and `dollars`. Register your provider by adding
a branch to `resolve_provider()`. See [Architecture](./architecture.md) for the
broader module map.

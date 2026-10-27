"""Versioned prompt files: `<name>/v<N>.md` with YAML front matter, rendered with Jinja2.

Front matter keys: id, version, model_tier (smart|fast), temperature, max_tokens, and
optionally schema (a JSON Schema file next to the prompt). The body has a
`<!-- system -->` section and a `<!-- user -->` section.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

PROMPTS_DIR = Path(__file__).resolve().parent
_SYSTEM_MARK = "<!-- system -->"
_USER_MARK = "<!-- user -->"

ModelTier = Literal["smart", "fast"]


@dataclass(frozen=True)
class PromptSpec:
    id: str
    version: int
    model_tier: ModelTier
    temperature: float
    max_tokens: int
    schema: dict[str, Any] | None
    system_template: str
    user_template: str

    @property
    def ref(self) -> str:
        return f"{self.id}/v{self.version}"


@dataclass(frozen=True)
class RenderedPrompt:
    spec: PromptSpec
    system: str
    user: str


_env = Environment(
    loader=FileSystemLoader(PROMPTS_DIR),
    undefined=StrictUndefined,
    autoescape=False,  # noqa: S701 (plain-text LLM prompts, not HTML)
    keep_trailing_newline=True,
)


@lru_cache
def load_prompt(name: str, version: int) -> PromptSpec:
    path = PROMPTS_DIR / name / f"v{version}.md"
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---"):
        raise ValueError(f"{path} has no front matter")
    _, front, body = raw.split("---", 2)
    meta = yaml.safe_load(front)
    if _SYSTEM_MARK not in body or _USER_MARK not in body:
        raise ValueError(f"{path} needs {_SYSTEM_MARK} and {_USER_MARK} sections")
    system, user = body.split(_USER_MARK, 1)
    system = system.split(_SYSTEM_MARK, 1)[1]

    schema = None
    if meta.get("schema"):
        schema = json.loads((path.parent / meta["schema"]).read_text(encoding="utf-8"))

    return PromptSpec(
        id=str(meta["id"]),
        version=int(meta["version"]),
        model_tier=meta.get("model_tier", "smart"),
        temperature=float(meta.get("temperature", 0.2)),
        max_tokens=int(meta.get("max_tokens", 2000)),
        schema=schema,
        system_template=system.strip(),
        user_template=user.strip(),
    )


def render(spec: PromptSpec, **variables: Any) -> RenderedPrompt:
    return RenderedPrompt(
        spec=spec,
        system=_env.from_string(spec.system_template).render(**variables),
        user=_env.from_string(spec.user_template).render(**variables),
    )

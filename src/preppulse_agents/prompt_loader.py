from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

# Cache for loaded YAML prompt templates
_PROMPT_CACHE: dict[str, dict[str, Any]] = {}


def _get_prompts_root() -> Path:
    env_root = os.getenv("PREPPULSE_PROMPTS_ROOT")
    if env_root and os.path.isdir(env_root):
        return Path(env_root)
    # Relative to this file: src/preppulse_agents/prompt_loader.py -> project root -> prompts
    curr = Path(__file__).resolve().parent
    for parent in [curr.parent.parent, curr.parent, curr]:
        candidate = parent / "prompts"
        if candidate.is_dir():
            return candidate
    return Path("prompts").resolve()


def load_prompt_yaml(relative_path: str) -> dict[str, Any]:
    # Loads and caches a structured YAML prompt definition
    if relative_path in _PROMPT_CACHE:
        return _PROMPT_CACHE[relative_path]

    prompts_root = _get_prompts_root()
    target_file = prompts_root / relative_path
    if not target_file.is_file():
        raise FileNotFoundError(f"Prompt file not found at: {target_file}")

    with open(target_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    _PROMPT_CACHE[relative_path] = data
    return data


def load_agent_prompt(agent_name: str) -> dict[str, Any]:
    # Convenience loader for agent prompts under prompts/agents/<agent_name>.yaml
    filename = agent_name if agent_name.endswith(".yaml") else f"{agent_name}.yaml"
    return load_prompt_yaml(f"agents/{filename}")


def format_agent_prompt(
    agent_name: str,
    **kwargs: Any,
) -> tuple[str, str, dict[str, Any]]:
    # Returns (system_prompt, formatted_user_message, parameters_dict)
    cfg = load_agent_prompt(agent_name)
    system_prompt = cfg.get("system_prompt", "").strip()
    user_template = cfg.get("user_template", "")
    parameters = cfg.get("parameters", {}) or {}

    # Format user template safely with provided kwargs
    formatted_user = user_template.format(**{k: ("" if v is None else str(v)) for k, v in kwargs.items()}).strip()
    return system_prompt, formatted_user, parameters


def load_rag_prompt(prompt_name: str) -> dict[str, Any]:
    # Convenience loader for RAG prompts under prompts/rag/<prompt_name>.yaml
    filename = prompt_name if prompt_name.endswith(".yaml") else f"{prompt_name}.yaml"
    return load_prompt_yaml(f"rag/{filename}")


def format_rag_prompt(
    prompt_name: str,
    **kwargs: Any,
) -> tuple[str, str, dict[str, Any]]:
    # Returns (system_prompt, formatted_user_message, parameters_dict)
    cfg = load_rag_prompt(prompt_name)
    system_prompt = cfg.get("system_prompt", "").strip()
    user_template = cfg.get("user_template", "")
    parameters = cfg.get("parameters", {}) or {}

    formatted_user = user_template.format(**{k: ("" if v is None else str(v)) for k, v in kwargs.items()}).strip()
    return system_prompt, formatted_user, parameters


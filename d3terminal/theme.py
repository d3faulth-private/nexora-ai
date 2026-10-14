from __future__ import annotations

import os

from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.styles import Style


D3_STYLE = Style.from_dict(
    {
        "d3.user": "ansibrightgreen bold",
        "d3.project": "ansigray",
        "d3.env.dev": "ansibrightcyan bold",
        "d3.env.test": "ansiyellow bold",
        "d3.env.prod": "ansired bold",
        "d3.prompt": "ansigray",
        "d3.ok": "ansibrightgreen bold",
        "d3.info": "ansibrightcyan",
        "d3.warn": "ansiyellow bold",
        "d3.fail": "ansired bold",
        "d3.status": "ansigray",
        "completion-menu.completion": "bg:#111111 #d0d0d0",
        "completion-menu.completion.current": "bg:#1f3a34 ansibrightgreen bold",
        "scrollbar.background": "bg:#111111",
        "scrollbar.button": "bg:#444444",
    }
)


def color_enabled() -> bool:
    return not bool(os.getenv("NO_COLOR"))


def environment_label(environment: str) -> str:
    value = (environment or "development").strip().lower()
    if value.startswith("prod"):
        return "PROD"
    if value.startswith("test"):
        return "TEST"
    return "DEVE"


def prompt_tokens(environment: str, project_slug: str = "nexora") -> FormattedText:
    env = environment_label(environment)
    if not color_enabled():
        return FormattedText([("", f"d3faulth@{project_slug} [{env}]:~$ ")])

    env_style = {
        "PROD": "class:d3.env.prod",
        "TEST": "class:d3.env.test",
        "DEVE": "class:d3.env.dev",
    }[env]
    return FormattedText(
        [
            ("class:d3.user", "d3faulth"),
            ("class:d3.project", "@" + project_slug),
            ("class:d3.prompt", " ["),
            (env_style, env),
            ("class:d3.prompt", "]:~$ "),
        ]
    )


def message_tokens(level: str, message: str) -> FormattedText:
    normalized = level.strip().lower()
    label_map = {
        "ok": ("class:d3.ok", "[D3] [ OK ]"),
        "info": ("class:d3.info", "[D3] [INFO]"),
        "warn": ("class:d3.warn", "[D3] [WARN]"),
        "fail": ("class:d3.fail", "[D3] [FAIL]"),
    }
    style_name, label = label_map.get(normalized, ("class:d3.status", "[D3]"))
    if not color_enabled():
        return FormattedText([("", label + " " + message)])
    return FormattedText(
        [
            (style_name, label),
            ("class:d3.status", " " + message),
        ]
    )

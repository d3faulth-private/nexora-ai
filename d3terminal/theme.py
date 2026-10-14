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

from __future__ import annotations

import os
import sys


PROJECT = "NEXORA AI"
PROJECT_SLUG = "nexora"
VERSION = "0.4.0"


def _ansi(code: str, text: str) -> str:
    if os.getenv("NO_COLOR") or not sys.stdout.isatty():
        return text
    return "\033[" + code + "m" + text + "\033[0m"


def green(text: str) -> str:
    return _ansi("92", text)


def cyan(text: str) -> str:
    return _ansi("96", text)


def amber(text: str) -> str:
    return _ansi("93", text)


def red(text: str) -> str:
    return _ansi("91", text)


def dim(text: str) -> str:
    return _ansi("90", text)


def banner(environment: str = "development") -> str:
    return "\n".join(
        [
            "",
            cyan("D3FAULTH // " + PROJECT),
            dim("Security Engineering // AI Systems // Operator Console"),
            "─" * 62,
            "PROJECT      " + PROJECT,
            "VERSION      " + VERSION,
            "ENVIRONMENT  " + environment.upper(),
            "STATUS       " + green("READY"),
            "─" * 62,
        ]
    )


def prompt(environment: str = "development") -> str:
    env = environment[:4].upper()
    return green("d3faulth") + "@" + PROJECT_SLUG + " [" + cyan(env) + "]:~$ "


def ok(message: str) -> str:
    return green("[D3] [ OK ]") + " " + message


def info(message: str) -> str:
    return cyan("[D3] [INFO]") + " " + message


def warn(message: str) -> str:
    return amber("[D3] [WARN]") + " " + message


def fail(message: str) -> str:
    return red("[D3] [FAIL]") + " " + message

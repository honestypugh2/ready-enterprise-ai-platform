"""Terminal rendering for the demo.

Deliberately dependency-free ANSI rather than a rich-text library: the demo has
to survive a locked-down conference laptop, and one fewer dependency in the
critical path of a live demonstration is worth more than rounded corners.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable

_ENABLED = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

_CODES = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
}


def style(text: str, *names: str) -> str:
    if not _ENABLED or not names:
        return text
    prefix = "".join(_CODES.get(name, "") for name in names)
    return f"{prefix}{text}{_CODES['reset']}"


def heading(text: str) -> str:
    rule = "─" * min(len(text), 78)
    return f"\n{style(text, 'bold', 'cyan')}\n{style(rule, 'dim')}"


def field(label: str, value: object, *, width: int = 26, colour: str | None = None) -> str:
    rendered = style(str(value), colour) if colour else str(value)
    return f"  {style(label.ljust(width), 'dim')} {rendered}"


def verdict(text: str, *, ok: bool) -> str:
    marker = "PASS" if ok else "FAIL"
    return style(f"[{marker}] {text}", "green" if ok else "red")


def bullet(text: str) -> str:
    return f"  {style('•', 'dim')} {text}"


def table(rows: Iterable[tuple[str, ...]], *, headers: tuple[str, ...]) -> str:
    """Fixed-width table sized to its content."""
    materialised = [tuple(str(cell) for cell in row) for row in rows]
    widths = [len(header) for header in headers]
    for row in materialised:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def render(row: tuple[str, ...], *, bold: bool = False) -> str:
        cells = "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))
        return style(f"  {cells}", "bold") if bold else f"  {cells}"

    separator = style("  " + "  ".join("─" * width for width in widths), "dim")
    return "\n".join([render(headers, bold=True), separator, *(render(r) for r in materialised)])

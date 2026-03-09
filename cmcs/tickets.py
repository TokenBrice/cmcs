"""Ticket discovery, parsing, and progress extraction."""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class Ticket:
    filename: str
    title: str
    agent: str
    done: bool
    body: str
    raw: str
    model: Optional[str] = None
    reasoning_effort: Optional[str] = None


_FRONTMATTER_PATTERN = re.compile(
    r"\A---\s*\r?\n(.*?)\r?\n---\s*\r?\n?(.*)\Z",
    re.DOTALL,
)


def _coerce_done(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0", ""}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return False


def parse_ticket(content: str, filename: str) -> Ticket:
    """Parse a ticket markdown file with YAML frontmatter."""
    match = _FRONTMATTER_PATTERN.match(content)
    if not match:
        if content.strip().startswith("---"):
            warnings.warn(
                f"Ticket {filename} has unclosed frontmatter (missing closing '---'). "
                "Treating as raw content.",
                stacklevel=2,
            )
        return Ticket(
            filename=filename,
            title="",
            agent="codex",
            done=False,
            body=content,
            raw=content,
            model=None,
        )

    try:
        metadata = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return Ticket(
            filename=filename,
            title="",
            agent="codex",
            done=False,
            body=content,
            raw=content,
            model=None,
        )
    body = match.group(2)

    return Ticket(
        filename=filename,
        title=str(metadata.get("title", "")),
        agent=str(metadata.get("agent", "codex")),
        done=_coerce_done(metadata.get("done", False)),
        body=body,
        raw=content,
        model=metadata.get("model"),
        reasoning_effort=metadata.get("reasoning_effort"),
    )


def discover_tickets(tickets_dir: Path) -> list[Ticket]:
    """Find and parse TICKET-*.md files sorted alphabetically."""
    if not tickets_dir.is_dir():
        return []
    tickets: list[Ticket] = []
    for path in sorted(tickets_dir.glob("TICKET-*.md"), key=lambda p: p.name):
        tickets.append(parse_ticket(path.read_text(encoding="utf-8"), path.name))
    return tickets


def get_previous_progress(tickets: list[Ticket], current_filename: str) -> Optional[str]:
    """Extract the previous ticket's ## Progress section through end of file."""
    previous: Optional[Ticket] = None
    for ticket in tickets:
        if ticket.filename == current_filename:
            break
        previous = ticket

    if previous is None:
        return None

    match = re.search(r"(^## Progress\b.*)", previous.raw, flags=re.MULTILINE | re.DOTALL)
    if match is None:
        return None
    return match.group(1).strip()

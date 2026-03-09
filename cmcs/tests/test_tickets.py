"""Tests for ticket parsing and discovery."""

from __future__ import annotations

from cmcs.tickets import discover_tickets, get_previous_progress, parse_ticket

SAMPLE_TICKET = """---
title: "Add hello world"
agent: "codex"
model: "gpt-5.1-codex-mini"
done: false
---

## Goal
Create hello world.

## Task
1. Add src/hello.py
"""

DONE_TICKET = """---
title: "Done ticket"
agent: "codex"
done: true
---

## Goal
Already done.

## Progress
- Created the file successfully.
"""


def test_parse_ticket_fields() -> None:
    ticket = parse_ticket(SAMPLE_TICKET, "TICKET-001.md")
    assert ticket.filename == "TICKET-001.md"
    assert ticket.title == "Add hello world"
    assert ticket.agent == "codex"
    assert ticket.model == "gpt-5.1-codex-mini"
    assert ticket.done is False
    assert "## Goal" in ticket.body


def test_parse_ticket_reasoning_effort() -> None:
    ticket_content = """---
title: "Complex task"
agent: codex
model: gpt-5.3-codex
reasoning_effort: high
done: false
---
Body.
"""
    ticket = parse_ticket(ticket_content, "TICKET-001.md")
    assert ticket.reasoning_effort == "high"


def test_parse_ticket_no_reasoning_effort() -> None:
    ticket = parse_ticket(SAMPLE_TICKET, "TICKET-001.md")
    assert ticket.reasoning_effort is None


def test_parse_ticket_no_model() -> None:
    ticket_content = """---
title: Test
agent: codex
done: false
---
Body.
"""
    ticket = parse_ticket(ticket_content, "TICKET-001.md")
    assert ticket.model is None


def test_parse_done_ticket() -> None:
    ticket = parse_ticket(DONE_TICKET, "TICKET-002.md")
    assert ticket.done is True


def test_discover_tickets_ordering(tmp_path) -> None:
    tickets_dir = tmp_path / ".cmcs" / "tickets"
    tickets_dir.mkdir(parents=True)
    (tickets_dir / "TICKET-002.md").write_text(SAMPLE_TICKET, encoding="utf-8")
    (tickets_dir / "TICKET-001.md").write_text(DONE_TICKET, encoding="utf-8")
    (tickets_dir / "TICKET-003.md").write_text(SAMPLE_TICKET, encoding="utf-8")

    tickets = discover_tickets(tickets_dir)
    assert [ticket.filename for ticket in tickets] == [
        "TICKET-001.md",
        "TICKET-002.md",
        "TICKET-003.md",
    ]


def test_discover_next_undone(tmp_path) -> None:
    tickets_dir = tmp_path / ".cmcs" / "tickets"
    tickets_dir.mkdir(parents=True)
    (tickets_dir / "TICKET-001.md").write_text(DONE_TICKET, encoding="utf-8")
    (tickets_dir / "TICKET-002.md").write_text(SAMPLE_TICKET, encoding="utf-8")

    tickets = discover_tickets(tickets_dir)
    undone = [ticket for ticket in tickets if not ticket.done]
    assert len(undone) == 1
    assert undone[0].filename == "TICKET-002.md"


def test_discover_tickets_nonexistent_dir(tmp_path) -> None:
    """discover_tickets on a non-existent directory should return empty list."""
    result = discover_tickets(tmp_path / "nonexistent")
    assert result == []


def test_parse_ticket_empty_content() -> None:
    """Empty ticket content should not crash."""
    ticket = parse_ticket("", "EMPTY.md")
    assert ticket.filename == "EMPTY.md"
    assert ticket.done is False


def test_get_previous_progress(tmp_path) -> None:
    tickets_dir = tmp_path / ".cmcs" / "tickets"
    tickets_dir.mkdir(parents=True)
    (tickets_dir / "TICKET-001.md").write_text(DONE_TICKET, encoding="utf-8")
    (tickets_dir / "TICKET-002.md").write_text(SAMPLE_TICKET, encoding="utf-8")

    tickets = discover_tickets(tickets_dir)
    progress = get_previous_progress(tickets, "TICKET-002.md")
    assert progress is not None
    assert progress.startswith("## Progress")
    assert "Created the file successfully" in progress


def test_get_previous_progress_first_ticket(tmp_path) -> None:
    tickets_dir = tmp_path / ".cmcs" / "tickets"
    tickets_dir.mkdir(parents=True)
    (tickets_dir / "TICKET-001.md").write_text(SAMPLE_TICKET, encoding="utf-8")

    tickets = discover_tickets(tickets_dir)
    progress = get_previous_progress(tickets, "TICKET-001.md")
    assert progress is None


def test_coerce_done_rejects_unknown_strings() -> None:
    """Unknown string values for done should coerce to False, not True."""
    from cmcs.tickets import _coerce_done

    assert _coerce_done("maybe") is False
    assert _coerce_done("oui") is False
    assert _coerce_done("nah") is False
    assert _coerce_done("true") is True
    assert _coerce_done("yes") is True
    assert _coerce_done("1") is True
    assert _coerce_done("false") is False
    assert _coerce_done("no") is False
    assert _coerce_done("0") is False


def test_parse_ticket_malformed_yaml() -> None:
    """Malformed YAML frontmatter should not crash, return fallback ticket."""
    from cmcs.tickets import parse_ticket

    content = '---\ntitle: "unclosed\nagent: codex\n---\nBody text'
    ticket = parse_ticket(content, "BAD.md")
    assert ticket.filename == "BAD.md"
    assert ticket.done is False
    assert ticket.agent == "codex"


def test_parse_ticket_tab_indentation() -> None:
    """Tab-indented YAML should not crash."""
    from cmcs.tickets import parse_ticket

    content = "---\ntitle: test\n\tagent: codex\n---\nBody"
    ticket = parse_ticket(content, "TAB.md")
    assert ticket.done is False


def test_parse_ticket_unclosed_frontmatter_warns() -> None:
    """Unclosed frontmatter should produce a warning."""
    import warnings

    from cmcs.tickets import parse_ticket

    content = "---\ntitle: test\nagent: codex\nBody without closing ---"
    with warnings.catch_warnings(record=True) as captured_warnings:
        warnings.simplefilter("always")
        ticket = parse_ticket(content, "UNCLOSED.md")
        assert len(captured_warnings) == 1
        assert "unclosed frontmatter" in str(captured_warnings[0].message).lower()
    assert ticket.done is False

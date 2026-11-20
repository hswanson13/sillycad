"""Consistent rich tooltips for commands and controls."""

from html import escape


def tooltip(name: str, description: str, shortcut: str = "") -> str:
    """Describe a control and its shortcut, if it has one."""
    sentence = escape(description.rstrip(".")) + "."
    return f"<b>{escape(name)}</b><br>{sentence}<br>Shortcut: {escape(shortcut or 'none')}"

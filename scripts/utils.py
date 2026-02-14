"""Shared utilities for Little Philosophy analysis scripts."""

from __future__ import annotations

import re


def name_to_id(name: str) -> str:
    """Convert a tile name to a kebab-case ID.

    e.g. 'Allegory of the Cave' → 'allegory-of-the-cave'
    """
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

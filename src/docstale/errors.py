"""Shared error taxonomy for docstale."""

from __future__ import annotations


class DocstaleError(Exception):
    """Base class for every failure docstale reports as a clean CLI error."""

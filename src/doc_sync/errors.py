"""Shared error taxonomy for doc-sync."""

from __future__ import annotations


class DocSyncError(Exception):
    """Base class for every failure doc-sync reports as a clean CLI error."""

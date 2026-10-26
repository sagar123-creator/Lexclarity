"""Cooperative cancellation for in-flight pipeline runs.

The server runs as a single uvicorn process, so an in-process registry is
enough: ``process_document`` polls :func:`stop_requested` at every stage
boundary and settles the document as ``stopped`` at the next one (a stage
itself is never torn out mid-call — an LLM request in flight just finishes).

A run never leaves a stale flag behind (``process_document`` clears it when it
finishes), and a *new* run always starts from a clean slate, so a stop request
can only ever affect the run that was active when it was made.

Deployments with multiple workers would need a shared flag instead — a nullable
``stop_requested`` column on ``documents`` would be the natural choice — see
README (architecture notes).
"""
from __future__ import annotations

import threading

# Shown as the document's error_message once a run has been stopped, and used
# verbatim by the API so the UI can tell "stopped by you" from "failed".
STOPPED_MESSAGE = (
    "Processing was stopped. Resume the analysis to pick up where it left off."
)

_lock = threading.Lock()
_stop_requested: set[str] = set()
_running: set[str] = set()


def request_stop(document_id: str) -> None:
    """Ask the active pipeline run for this document to stop at its next boundary."""
    with _lock:
        _stop_requested.add(document_id)


def clear_stop(document_id: str) -> None:
    with _lock:
        _stop_requested.discard(document_id)


def stop_requested(document_id: str) -> bool:
    with _lock:
        return document_id in _stop_requested


def mark_running(document_id: str) -> None:
    with _lock:
        _running.add(document_id)


def mark_finished(document_id: str) -> None:
    with _lock:
        _running.discard(document_id)


def is_running(document_id: str) -> bool:
    """True only when a live run in *this* process is working on the document.

    A document stuck in an "analyzing" status with no live run (e.g. left over
    from a restart) returns False — the caller can settle it immediately instead
    of waiting for a boundary that will never come.
    """
    with _lock:
        return document_id in _running

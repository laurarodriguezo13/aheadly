"""A fingerprint of the app's own code.

Streamlit keeps some objects in memory between runs (the forecast engine, the LLM client, each
visitor's App Core). After an update, the new code must never be handed one built by the old code:
that is what crashed the live site after PR #1 until it was rebooted. Everything cached carries
this fingerprint, so a change to any file builds fresh objects.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent


def code_version(root: Path = PACKAGE) -> str:
    """12 hex characters that change whenever any .py file under `root` changes (cheap: ~60 files)."""
    digest = hashlib.sha1()
    for path in sorted(root.rglob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()[:12]

"""Turning a stored media path into a URL the browser can fetch.

Media can be served two ways and the escaping differs between them, which is
the whole reason this lives in one tested place:

* **locally** the file sits on disk under a name that literally contains
  percent signs (the extractor saved `%D0%B1….mp4` verbatim), so the `%` has
  to be escaped again as `%25` or the browser decodes it and asks for a name
  that is not there;
* **remotely** the origin serves that same clip at the already-encoded path,
  so the stored path is passed through untouched — escaping it again would
  ask the origin for a file it does not have.

Which origin a path belongs to is decided by its prefix: the two platforms
were imported into separate namespaces in the store.
"""
from __future__ import annotations

from urllib.parse import quote

#: Assets imported from pddtest live under this prefix in the store.
PDDTEST_PREFIX = "pddtest/"


def local_url(rel_path: str, prefix: str) -> str:
    """URL for media served by this application from disk."""
    return f"{prefix}/{quote(rel_path.lstrip('/'), safe='/')}"


def remote_url(rel_path: str, otan_origin: str, pddtest_origin: str) -> str:
    """URL for media served by the platform it was originally taken from."""
    path = rel_path.lstrip("/")
    if path.startswith(PDDTEST_PREFIX):
        return f"{pddtest_origin.rstrip('/')}/{path[len(PDDTEST_PREFIX):]}"
    return f"{otan_origin.rstrip('/')}/{path}"


def build_media_url(
    rel_path: str,
    *,
    serve_local: bool,
    prefix: str,
    otan_origin: str,
    pddtest_origin: str,
) -> str:
    """Pick the right form for how this deployment serves media."""
    if serve_local:
        return local_url(rel_path, prefix)
    return remote_url(rel_path, otan_origin, pddtest_origin)

"""Raise Starlette's 1 MB cap on non-file multipart form fields.

A blog post is submitted as ``multipart/form-data`` with the whole article
HTML in a plain ``content`` field.  Starlette's ``MultiPartParser`` caps every
*non-file* part at 1 MB and rejects the request with HTTP 400
``"Part exceeded maximum size of 1024KB."`` (see ``on_part_data`` in
``starlette/formparsers.py``).  Uploaded files are spooled to disk and are not
affected by that cap, so this only ever bites long articles.

FastAPI calls ``await request.form()`` with no arguments, which hard-codes
Starlette's 1 MB default and passes it explicitly to the parser, so the limit
cannot be raised per-route or by setting the class attribute alone.  Patching
the parser's constructor is the one place that covers every route.

Override the ceiling with the ``MAX_FORM_PART_SIZE_MB`` environment variable.
"""

from __future__ import annotations

import os

# 25 MB is deliberately generous: MongoDB caps a single document at 16 MB and
# Vercel caps a serverless request body at 4.5 MB, so a real request will hit
# one of those first.  The point is that the parser is no longer the limit.
DEFAULT_MAX_PART_SIZE_MB = 25.0


def max_part_size_bytes() -> int:
    raw = os.environ.get("MAX_FORM_PART_SIZE_MB")
    try:
        megabytes = float(raw) if raw else DEFAULT_MAX_PART_SIZE_MB
    except ValueError:
        megabytes = DEFAULT_MAX_PART_SIZE_MB
    if megabytes <= 0:
        megabytes = DEFAULT_MAX_PART_SIZE_MB
    return int(megabytes * 1024 * 1024)


def apply_multipart_limits() -> int | None:
    """Patch ``MultiPartParser`` to accept large text fields.

    Safe to call more than once.  Returns the limit in bytes, or ``None`` if
    the patch could not be applied (a Starlette version that moved things
    around should degrade to the old behaviour, not crash the app on boot).
    """
    try:
        from starlette import formparsers

        parser = formparsers.MultiPartParser
        limit = max_part_size_bytes()

        # Covers any caller that relies on the class attribute default.
        parser.max_part_size = limit

        original_init = parser.__init__
        if getattr(original_init, "_form_limits_patched", False):
            return limit

        def patched_init(self, *args, **kwargs):
            # request.form() passes max_part_size=1MB explicitly, so raising
            # only the class attribute above is not enough.
            kwargs["max_part_size"] = max(int(kwargs.get("max_part_size") or 0), limit)
            original_init(self, *args, **kwargs)

        patched_init._form_limits_patched = True
        parser.__init__ = patched_init
        return limit
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[form_limits] could not raise multipart size limit: {exc}")
        return None

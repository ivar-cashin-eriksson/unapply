"""The HTTP API over the database, for the frontend: `unapply api` starts it.

Candidates (`/candidates`), jobs (`/jobs`) and the free demos (`/demos`). The
internal assessment routes (`/internal`) are only added on request.
"""

from unapply.api.app import create_app

__all__ = ["create_app"]

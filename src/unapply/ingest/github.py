"""Load a candidate's public GitHub repositories as a document."""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from unapply.ingest.documents import SourceDocument
from unapply.schemas import Source, SourceKind

API = "https://api.github.com"

# Fetches a GitHub API path and returns the decoded JSON, or the raw text when
# raw=True. Injected so tests run offline.
Fetcher = Callable[[str, bool], Any]


def fetch_github(
    username: str, max_repos: int = 15, fetch: Fetcher | None = None
) -> SourceDocument:
    """Load a user's public, non-fork repositories and their READMEs.

    Unauthenticated requests are limited to 60 an hour; set `GITHUB_TOKEN` to raise
    the limit. This makes one request for the list and one per README.

    Parameters
    ----------
    username : str
        GitHub login.
    max_repos : int, optional
        How many repositories to include, most recently pushed first, by default 15.
    fetch : Fetcher or None, optional
        Function that fetches an API path. By default, the GitHub REST API.

    Returns
    -------
    SourceDocument
        A GitHub document with one section per repository.
    """
    fetch = fetch or _fetch
    repos = fetch(f"/users/{username}/repos?per_page=100&sort=pushed&type=owner", False)
    repos = [r for r in repos if not r.get("fork") and not r.get("archived")]
    repos = repos[:max_repos]

    sections = [f"# GitHub: {username} (https://github.com/{username})"]
    for repo in repos:
        sections.append(_repo_section(repo, _readme(fetch, username, repo["name"])))
    text = "\n\n".join(sections)
    source = Source(kind=SourceKind.GITHUB, uri=f"https://github.com/{username}")
    return SourceDocument(source=source, name=f"github.com/{username}", text=text)


def _repo_section(repo: dict[str, Any], readme: str | None) -> str:
    facts = {
        "URL": repo.get("html_url"),
        "Primary language": repo.get("language"),
        "Stars": repo.get("stargazers_count"),
        "Topics": ", ".join(repo.get("topics") or []),
        "Created": (repo.get("created_at") or "")[:7],
        "Last push": (repo.get("pushed_at") or "")[:7],
    }
    lines = [f"## {repo['name']}"]
    lines.append(
        "; ".join(f"{k}: {v}" for k, v in facts.items() if v not in (None, ""))
    )
    if repo.get("description"):
        lines.append(f"Description: {repo['description']}")
    if readme:
        lines.append(f"### README\n{readme.strip()}")
    return "\n".join(lines)


def _readme(fetch: Fetcher, username: str, repo: str) -> str | None:
    try:
        return fetch(f"/repos/{username}/{repo}/readme", True)
    except FileNotFoundError:
        return None


def cached_fetcher(cache_dir: Path, fetch: Fetcher | None = None) -> Fetcher:
    """Wrap a fetcher so each API path is fetched once and then read from disk.

    Keeps reruns reproducible and within the unauthenticated rate limit. Delete the
    folder to fetch fresh data.

    Parameters
    ----------
    cache_dir : Path
        Folder for cached responses. Created if missing.
    fetch : Fetcher or None, optional
        The fetcher to wrap. By default, the GitHub REST API.

    Returns
    -------
    Fetcher
        A fetcher with the same behaviour, including FileNotFoundError for paths
        that don't exist.
    """
    fetch = fetch or _fetch
    cache_dir.mkdir(parents=True, exist_ok=True)

    def cached(path: str, raw: bool) -> Any:  # noqa: ANN401 (decoded JSON)
        key = hashlib.sha256(f"{raw}:{path}".encode()).hexdigest()[:24]
        file = cache_dir / f"{key}.json"
        if file.exists():
            entry = json.loads(file.read_text(encoding="utf-8"))
        else:
            try:
                entry = {"path": path, "body": fetch(path, raw)}
            except FileNotFoundError:
                entry = {"path": path, "missing": True}
            file.write_text(json.dumps(entry), encoding="utf-8")
        if entry.get("missing"):
            raise FileNotFoundError(path)
        return entry["body"]

    return cached


def _fetch(path: str, raw: bool) -> Any:  # noqa: ANN401 (decoded JSON)
    """Fetch a GitHub API path; raise FileNotFoundError on 404."""
    accept = "application/vnd.github.raw+json" if raw else "application/vnd.github+json"
    headers = {"Accept": accept, "User-Agent": "unapply"}
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(API + path, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise FileNotFoundError(path) from e
        if e.code in (403, 429) and e.headers.get("x-ratelimit-remaining") == "0":
            raise RuntimeError(
                "GitHub rate limit reached (60 requests an hour without a token). "
                "Wait, or set GITHUB_TOKEN in .env."
            ) from e
        raise
    return body if raw else json.loads(body)

#!/usr/bin/env python3
"""
Download a foreign-language subtitle from OpenSubtitles by IMDb ID.

Privacy boundary: this script sends only the OpenSubtitles API key, IMDb ID,
language filters, and the selected OpenSubtitles file_id to OpenSubtitles. It
does not accept, read, or upload local video files or local subtitle files.

Usage:
    python3 fetch_foreign_subtitle.py IMDB_ID --output foreign.srt

Exit codes:
    0  Subtitle downloaded
    1  No foreign subtitle available
    2  Skipped or failed due to missing API key, network error, or timeout

Requires: OPENSUBTITLES_API_KEY env var or ~/.config/srt-translate/os_api_key
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

API_BASE = "https://api.opensubtitles.com/api/v1"
USER_AGENT = "srt-translate/1.0"
LANGUAGE_PREFERENCE = ["es", "pt", "fr", "de", "it", "pl", "nl"]


def get_api_key() -> str | None:
    key = os.environ.get("OPENSUBTITLES_API_KEY")
    if key:
        return key.strip()
    config_path = Path.home() / ".config" / "srt-translate" / "os_api_key"
    if config_path.exists():
        return config_path.read_text().strip()
    return None


def normalize_imdb_id(value: str) -> str | None:
    """Return a bare numeric IMDb ID from 'tt123', 'imdb-tt123', or '123'."""
    trimmed = value.strip()
    match = re.fullmatch(r"(?:imdb-)?tt(\d+)", trimmed, re.IGNORECASE)
    if match:
        return match.group(1)
    if re.fullmatch(r"\d+", trimmed):
        return trimmed
    return None


def api_get(path: str, api_key: str, timeout: int) -> dict:
    url = f"{API_BASE}{path}"
    req = urllib.request.Request(url, headers={
        "Api-Key": api_key,
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def api_post(path: str, api_key: str, body: dict, timeout: int) -> dict:
    url = f"{API_BASE}{path}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Api-Key": api_key,
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def fetch_subtitle_download_url(
    imdb_id: str,
    api_key: str,
    timeout: int,
    languages: list[str],
) -> tuple[str, str] | None:
    """Return (download_url, language) for the best available foreign subtitle."""
    for lang in languages:
        try:
            data = api_get(
                f"/subtitles?imdb_id={imdb_id}&languages={lang}&type=movie&order_by=download_count",
                api_key,
                timeout,
            )
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            print(f"  API search failed for {lang}: {e}", file=sys.stderr)
            continue

        results = data.get("data", [])
        if not results:
            continue

        for result in results:
            files = result.get("attributes", {}).get("files", [])
            if not files or not files[0].get("file_id"):
                continue

            file_id = files[0]["file_id"]
            try:
                dl = api_post("/download", api_key, {"file_id": file_id}, timeout)
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                print(f"  Download request failed for {lang}: {e}", file=sys.stderr)
                break

            link = dl.get("link")
            if link:
                return link, lang
            break

    return None


def download_text(url: str, timeout: int) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def fetch_foreign_subtitle(
    imdb_id: str,
    output_path: Path,
    timeout: int,
    languages: list[str],
) -> tuple[bool, str | None]:
    api_key = get_api_key()
    if not api_key:
        print("SKIP: OPENSUBTITLES_API_KEY not set and ~/.config/srt-translate/os_api_key not found", file=sys.stderr)
        print("      Set the env var or create the config file to enable title card detection.")
        return False, None

    print(f"Searching OpenSubtitles for foreign subtitle (IMDb: tt{imdb_id}, timeout: {timeout}s)...")
    result = fetch_subtitle_download_url(imdb_id, api_key, timeout, languages)
    if result is None:
        print("NOT FOUND: No usable foreign subtitle found on OpenSubtitles.")
        return False, None

    download_url, lang = result
    print(f"Found [{lang}] subtitle. Downloading...")
    foreign_text = download_text(download_url, timeout)
    output_path.write_text(foreign_text, encoding="utf-8")
    print(f"Wrote foreign subtitle [{lang}] to {output_path}")
    return True, lang


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch foreign subtitle by IMDb ID")
    parser.add_argument("imdb_id", metavar="IMDB_ID", help="IMDb ID as tt1234567, imdb-tt1234567, or 1234567")
    parser.add_argument("--output", default="foreign.srt", help="Output SRT path")
    parser.add_argument("--timeout", type=int, default=15, help="Network timeout in seconds (default: 15)")
    parser.add_argument(
        "--languages",
        default=",".join(LANGUAGE_PREFERENCE),
        help="Comma-separated language codes in preference order",
    )
    args = parser.parse_args()

    imdb_id = normalize_imdb_id(args.imdb_id)
    if not imdb_id:
        print(f"SKIP: Invalid IMDb ID: {args.imdb_id}", file=sys.stderr)
        return 2

    languages = [lang.strip() for lang in args.languages.split(",") if lang.strip()]
    if not languages:
        print("SKIP: No languages requested", file=sys.stderr)
        return 2

    try:
        ok, _lang = fetch_foreign_subtitle(imdb_id, Path(args.output), args.timeout, languages)
    except Exception as e:
        print(f"SKIP: Unexpected error querying OpenSubtitles: {e}", file=sys.stderr)
        return 2

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

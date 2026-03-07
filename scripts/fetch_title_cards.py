#!/usr/bin/env python3
"""
fetch_title_cards.py — Download a foreign-language subtitle from OpenSubtitles
and identify cues that likely correspond to burned-in title cards missing from
the English source SRT.

Usage:
    python3 fetch_title_cards.py EN_SRT VIDEO_FILE [options]

Exit codes:
    0  Title cards found and written to --output
    1  No title cards found (or no foreign subtitle available)
    2  Skipped (no API key, network error, timeout)

Requires: OPENSUBTITLES_API_KEY env var or ~/.config/srt-translate/os_api_key
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:
    import pysubs2
except ImportError:
    print("ERROR: pysubs2 not available — run via scripts/venv/bin/python3", file=sys.stderr)
    sys.exit(2)

API_BASE = "https://api.opensubtitles.com/api/v1"
USER_AGENT = "srt-translate/1.0"
LANGUAGE_PREFERENCE = ["es", "pt", "fr", "de", "it", "pl", "nl"]

# A foreign cue is a title card candidate if no EN cue starts within this window (ms)
TITLE_CARD_GAP_MS = 1500
# Ignore very short cues (noise)
MIN_DURATION_MS = 400


def get_api_key() -> str | None:
    key = os.environ.get("OPENSUBTITLES_API_KEY")
    if key:
        return key.strip()
    config_path = Path.home() / ".config" / "srt-translate" / "os_api_key"
    if config_path.exists():
        return config_path.read_text().strip()
    return None


def extract_imdb_id(video_path: str) -> str | None:
    """Extract bare numeric IMDb ID from filename, e.g. {imdb-tt22696908} → 22696908"""
    match = re.search(r"imdb-tt(\d+)", Path(video_path).name, re.IGNORECASE)
    return match.group(1) if match else None


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


def fetch_subtitle_download_url(imdb_id: str, api_key: str, timeout: int) -> tuple[str, str] | None:
    """Return (download_url, language) for the best available foreign subtitle."""
    for lang in LANGUAGE_PREFERENCE:
        try:
            data = api_get(
                f"/subtitles?imdb_id={imdb_id}&languages={lang}&type=movie&order_by=download_count",
                api_key, timeout
            )
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            print(f"  API search failed for {lang}: {e}", file=sys.stderr)
            continue

        results = data.get("data", [])
        if not results:
            continue

        # Pick first result with a file_id
        for result in results:
            files = result.get("attributes", {}).get("files", [])
            if files and files[0].get("file_id"):
                file_id = files[0]["file_id"]
                try:
                    dl = api_post("/download", api_key, {"file_id": file_id}, timeout)
                    link = dl.get("link")
                    if link:
                        return link, lang
                except (urllib.error.URLError, TimeoutError, OSError) as e:
                    print(f"  Download request failed for {lang}: {e}", file=sys.stderr)
                break

    return None


def download_text(url: str, timeout: int) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    # Try UTF-8, fall back to latin-1
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def find_title_cards(en_srt: str, foreign_text: str) -> list[pysubs2.SSAEvent]:
    """Return foreign cues with no overlapping EN cue within TITLE_CARD_GAP_MS."""
    en = pysubs2.SSAFile.from_string(en_srt)
    foreign = pysubs2.SSAFile.from_string(foreign_text)

    # Build a sorted list of EN cue start times for fast lookup
    en_starts = sorted(e.start for e in en)

    import bisect
    candidates = []
    for cue in foreign:
        if cue.duration < MIN_DURATION_MS:
            continue
        if not cue.plaintext.strip():
            continue

        # Check nearest EN cue
        idx = bisect.bisect_left(en_starts, cue.start)
        nearby = en_starts[max(0, idx - 1): idx + 2]
        if all(abs(cue.start - t) > TITLE_CARD_GAP_MS for t in nearby):
            candidates.append(cue)

    return candidates


def write_title_cards(candidates: list[pysubs2.SSAEvent], output_path: str, lang: str) -> None:
    out = pysubs2.SSAFile()
    for cue in candidates:
        event = pysubs2.SSAEvent(
            start=cue.start,
            end=cue.end,
            text=cue.text,
        )
        out.append(event)
    out.sort()
    out.save(output_path)


def main():
    parser = argparse.ArgumentParser(description="Fetch foreign subtitle and extract title card cues")
    parser.add_argument("en_srt", help="Path to the synced English SRT")
    parser.add_argument("video_file", help="Path to the video file (for IMDb ID extraction)")
    parser.add_argument("--output", default="title_cards.srt", help="Output SRT path")
    parser.add_argument("--timeout", type=int, default=15, help="Network timeout in seconds (default: 15)")
    parser.add_argument("--languages", default=",".join(LANGUAGE_PREFERENCE),
                        help="Comma-separated language codes in preference order")
    args = parser.parse_args()

    LANGUAGE_PREFERENCE[:] = [l.strip() for l in args.languages.split(",") if l.strip()]

    api_key = get_api_key()
    if not api_key:
        print("SKIP: OPENSUBTITLES_API_KEY not set and ~/.config/srt-translate/os_api_key not found", file=sys.stderr)
        print("      Set the env var or create the config file to enable title card detection.")
        sys.exit(2)

    imdb_id = extract_imdb_id(args.video_file)
    if not imdb_id:
        print(f"SKIP: No IMDb ID found in filename: {Path(args.video_file).name}", file=sys.stderr)
        sys.exit(2)

    print(f"Searching OpenSubtitles for foreign subtitle (IMDb: tt{imdb_id}, timeout: {args.timeout}s)...")

    try:
        result = fetch_subtitle_download_url(imdb_id, api_key, args.timeout)
    except Exception as e:
        print(f"SKIP: Unexpected error querying OpenSubtitles: {e}", file=sys.stderr)
        sys.exit(2)

    if result is None:
        print("NOT FOUND: No usable foreign subtitle found on OpenSubtitles.")
        sys.exit(1)

    download_url, lang = result
    print(f"Found [{lang}] subtitle. Downloading...")

    try:
        foreign_text = download_text(download_url, args.timeout)
    except Exception as e:
        print(f"SKIP: Failed to download subtitle file: {e}", file=sys.stderr)
        sys.exit(2)

    en_srt_text = Path(args.en_srt).read_text(encoding="utf-8-sig", errors="replace")

    print("Comparing timestamps to identify title card cues...")
    candidates = find_title_cards(en_srt_text, foreign_text)

    if not candidates:
        print("No title cards detected (all foreign cues have matching EN cues nearby).")
        sys.exit(1)

    write_title_cards(candidates, args.output, lang)
    print(f"Found {len(candidates)} title card cue(s) → {args.output}")
    sys.exit(0)


if __name__ == "__main__":
    main()

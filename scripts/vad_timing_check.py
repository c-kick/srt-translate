#!/usr/bin/env python3
"""
VAD Timing QC — Check subtitle timing against actual speech boundaries.

Runs WebRTC VAD on the full audio to build a speech map, then compares
each subtitle's start/end against detected speech-to-silence and
silence-to-speech transitions. Flags cues that linger after speech,
cut off during speech, or have significant timing misalignment.

Performance: Audio extraction ~20s (cached), full VAD ~3s, analysis < 1s.
Always runs on all cues — no selective mode needed.

Usage:
    venv/bin/python3 scripts/vad_timing_check.py VIDEO NL_SRT EN_SRT [options]

Examples:
    # Standard QC
    venv/bin/python3 scripts/vad_timing_check.py movie.mkv movie.nl.srt movie.en.srt

    # Stricter detection, save report
    venv/bin/python3 scripts/vad_timing_check.py movie.mkv movie.nl.srt movie.en.srt \\
        --threshold 300 --report logs/vad_report.json

    # More aggressive noise filtering
    venv/bin/python3 scripts/vad_timing_check.py movie.mkv movie.nl.srt movie.en.srt \\
        --aggressiveness 3
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import wave

import webrtcvad


# ---------------------------------------------------------------------------
# SRT parsing
# ---------------------------------------------------------------------------

TC_RE = re.compile(
    r'(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})'
)


def tc_to_ms(h, m, s, ms):
    return int(h) * 3600000 + int(m) * 60000 + int(s) * 1000 + int(ms)


def parse_srt(path):
    with open(path, 'r', encoding='utf-8-sig') as f:
        content = f.read()
    cues = []
    for block in re.split(r'\n\n+', content.strip()):
        lines = block.split('\n')
        if len(lines) < 3:
            continue
        m = TC_RE.match(lines[1])
        if not m:
            continue
        g = m.groups()
        cues.append({
            'num': int(lines[0].strip()),
            'start_ms': tc_to_ms(*g[:4]),
            'end_ms': tc_to_ms(*g[4:]),
            'text': '\n'.join(lines[2:]),
        })
    return cues


def ms_to_tc(ms):
    h = ms // 3600000
    ms %= 3600000
    m = ms // 60000
    ms %= 60000
    s = ms // 1000
    ms %= 1000
    return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}'


# ---------------------------------------------------------------------------
# Audio extraction
# ---------------------------------------------------------------------------

def get_cache_path(video_path):
    stat = os.stat(video_path)
    key = f'{video_path}:{stat.st_size}'.encode()
    h = hashlib.md5(key).hexdigest()[:12]
    return f'/tmp/vad_audio_{h}.wav'


def extract_audio(video_path, wav_path):
    result = subprocess.run(
        ['ffmpeg', '-i', video_path,
         '-ac', '1', '-ar', '16000', '-acodec', 'pcm_s16le',
         '-y', wav_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f'ffmpeg error:\n{result.stderr}', file=sys.stderr)
        sys.exit(1)


def load_audio(video_path, no_cache=False):
    cache = get_cache_path(video_path)
    if no_cache and os.path.exists(cache):
        os.unlink(cache)
    if os.path.exists(cache):
        print(f'Using cached audio: {cache}')
    else:
        print('Extracting audio (16kHz mono)...')
        extract_audio(video_path, cache)
        size_mb = os.path.getsize(cache) / 1048576
        print(f'Cached: {cache} ({size_mb:.1f} MB)')

    with wave.open(cache, 'rb') as wf:
        sr = wf.getframerate()
        frames = wf.readframes(wf.getnframes())
    return frames, sr


# ---------------------------------------------------------------------------
# Global VAD — build full speech map
# ---------------------------------------------------------------------------

def build_speech_map(audio, sr, vad, frame_ms=30):
    """
    Run VAD on entire audio.
    Returns list of booleans, one per frame (each frame_ms long).
    """
    frame_bytes = int(sr * 2 * frame_ms / 1000)
    total_frames = len(audio) // frame_bytes
    speech_map = []

    for i in range(total_frames):
        start = i * frame_bytes
        frame = audio[start:start + frame_bytes]
        try:
            speech_map.append(vad.is_speech(frame, sr))
        except Exception:
            speech_map.append(False)

    return speech_map


def smooth_speech_map(speech_map, hangover_frames=7):
    """
    Smooth VAD output: bridge silence gaps shorter than hangover_frames.
    At 30ms/frame, 7 frames = 210ms — bridges word-internal pauses
    but preserves sentence-level gaps (typically 300ms+).
    """
    smoothed = list(speech_map)
    n = len(smoothed)
    i = 0
    while i < n:
        if smoothed[i]:
            # In speech — find end of this speech run
            j = i + 1
            while j < n and smoothed[j]:
                j += 1
            # j = first silence frame after speech
            # Find how long the silence lasts
            k = j
            while k < n and not smoothed[k]:
                k += 1
            # k = next speech frame (or end)
            gap = k - j
            if k < n and gap <= hangover_frames:
                # Bridge the gap
                for x in range(j, k):
                    smoothed[x] = True
                i = k
            else:
                i = j
        else:
            i += 1
    return smoothed


def find_transitions(speech_map, frame_ms=30):
    """
    Find speech→silence and silence→speech transitions.
    Returns:
        speech_starts: list of ms where speech begins
        speech_ends:   list of ms where speech ends
    """
    starts = []
    ends = []
    prev = False
    for i, is_speech in enumerate(speech_map):
        ms = i * frame_ms
        if is_speech and not prev:
            starts.append(ms)
        elif not is_speech and prev:
            ends.append(ms)
        prev = is_speech
    # If audio ends during speech
    if prev:
        ends.append(len(speech_map) * frame_ms)
    return starts, ends


def find_nearest(transitions, target_ms, search_range=2000):
    """Find the transition nearest to target_ms within search_range."""
    best = None
    best_dist = float('inf')
    for t in transitions:
        dist = abs(t - target_ms)
        if dist < best_dist and dist <= search_range:
            best_dist = dist
            best = t
    return best


# ---------------------------------------------------------------------------
# NL ↔ EN matching
# ---------------------------------------------------------------------------

def match_source_cues(nl_cues, en_cues, tolerance_ms=500):
    """For each NL cue, find matching EN source cue(s) by start time."""
    matches = {}
    for nl in nl_cues:
        matched = []
        for en in en_cues:
            if nl['start_ms'] - tolerance_ms <= en['start_ms'] <= nl['end_ms'] + tolerance_ms:
                matched.append(en)
        if not matched:
            best = min(en_cues, key=lambda e: abs(e['start_ms'] - nl['start_ms']))
            if abs(best['start_ms'] - nl['start_ms']) <= tolerance_ms:
                matched = [best]
        matches[nl['num']] = matched
    return matches


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyze_cue(nl_cue, en_matches, speech_ends, speech_starts, search_range):
    """
    Compare a cue's timing against speech transitions.
    Returns result dict with deltas.
    """
    # Find nearest speech-end to this cue's end time
    nearest_end = find_nearest(speech_ends, nl_cue['end_ms'], search_range)
    # Find nearest speech-start to this cue's start time
    nearest_start = find_nearest(speech_starts, nl_cue['start_ms'], search_range)

    end_delta = None
    start_delta = None

    if nearest_end is not None:
        # Positive = speech ends AFTER subtitle → subtitle cuts off too soon
        # Negative = speech ends BEFORE subtitle → subtitle lingers
        end_delta = nearest_end - nl_cue['end_ms']

    if nearest_start is not None:
        # Positive = speech starts AFTER subtitle → subtitle appears early
        # Negative = speech starts BEFORE subtitle → subtitle appears late
        start_delta = nearest_start - nl_cue['start_ms']

    en_start = en_matches[0]['start_ms'] if en_matches else None
    en_end = en_matches[-1]['end_ms'] if en_matches else None

    return {
        'cue_num': nl_cue['num'],
        'nl_start': nl_cue['start_ms'],
        'nl_end': nl_cue['end_ms'],
        'nl_text': nl_cue['text'],
        'en_start': en_start,
        'en_end': en_end,
        'speech_end_nearest': nearest_end,
        'speech_start_nearest': nearest_start,
        'end_delta_ms': end_delta,
        'start_delta_ms': start_delta,
        'nl_end_vs_en': (nl_cue['end_ms'] - en_end) if en_end else None,
    }


def classify_issues(r, threshold_ms, prev_nl=None, next_nl=None):
    """
    Classify timing result into actionable issues.

    Context-aware filtering:
    - "speech continues" suppressed if next subtitle picks up in time
    - "late start" suppressed if previous subtitle was still visible
    - Issues inherited from EN source are labeled and downgraded
    """
    issues = []
    ed = r['end_delta_ms']
    sd = r['start_delta_ms']
    en_start = r.get('en_start')
    en_end = r.get('en_end')

    # --- End timing ---
    if ed is not None:
        if ed > threshold_ms:
            # Speech continues after this subtitle ends.
            # But is the next subtitle covering it?
            suppressed = False
            if next_nl and r['speech_end_nearest'] is not None:
                if next_nl['start_ms'] <= r['speech_end_nearest']:
                    suppressed = True
                elif next_nl['start_ms'] - r['nl_end'] <= 200:
                    suppressed = True

            if not suppressed:
                gap_to_next = (next_nl['start_ms'] - r['nl_end']) if next_nl else None
                # Check if EN source had the same end time (inherited issue)
                inherited = en_end is not None and abs(r['nl_end'] - en_end) <= 200
                detail = f'Speech continues {ed}ms after subtitle ends'
                if gap_to_next is not None:
                    detail += f' (gap to next: {gap_to_next}ms)'
                if inherited:
                    detail += ' [source timing]'
                issues.append({
                    'type': 'cuts_off_during_speech',
                    'severity': 'low' if inherited else ('high' if ed > 1000 else 'medium'),
                    'detail': detail,
                })

        elif ed < -threshold_ms:
            # Subtitle lingers after speech.
            # Inherited if EN had same end time (unlikely for linger — usually NL extended)
            inherited = en_end is not None and abs(r['nl_end'] - en_end) <= 200
            detail = f'Subtitle lingers {-ed}ms after speech ends'
            if inherited:
                detail += ' [source timing]'
            issues.append({
                'type': 'lingers_after_speech',
                'severity': 'low' if inherited else ('high' if ed < -1500 else 'medium'),
                'detail': detail,
            })

    # --- Start timing ---
    if sd is not None:
        if sd < -threshold_ms:
            suppressed = False
            if prev_nl:
                if prev_nl['end_ms'] >= r['nl_start'] - 200:
                    suppressed = True

            if not suppressed:
                # Inherited from EN source?
                inherited = en_start is not None and abs(r['nl_start'] - en_start) <= 200
                detail = f'Speech starts {-sd}ms before subtitle appears'
                if inherited:
                    detail += ' [source timing]'
                issues.append({
                    'type': 'late_start',
                    'severity': 'low' if inherited else ('high' if sd < -1000 else 'medium'),
                    'detail': detail,
                })

        elif sd > 1500:
            issues.append({
                'type': 'early_start',
                'severity': 'low',
                'detail': f'Subtitle appears {sd}ms before speech starts',
            })

    return issues


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_issue(r):
    nl_tc = f'{ms_to_tc(r["nl_start"])} → {ms_to_tc(r["nl_end"])}'
    text_preview = r['nl_text'].replace('\n', ' | ')
    if len(text_preview) > 60:
        text_preview = text_preview[:57] + '...'

    print(f'  Cue {r["cue_num"]:>3d} [{nl_tc}]  "{text_preview}"')
    for issue in r['issues']:
        sev = {'high': '!!', 'medium': '! ', 'low': '  '}[issue['severity']]
        print(f'       {sev}  {issue["detail"]}')

    if r['speech_end_nearest'] is not None:
        print(f'         Speech ends at: {ms_to_tc(r["speech_end_nearest"])}')
    if r['en_end'] is not None:
        en_tc = f'{ms_to_tc(r["en_start"])} → {ms_to_tc(r["en_end"])}'
        print(f'         EN source:      {en_tc}')
        if r['nl_end_vs_en'] and abs(r['nl_end_vs_en']) > 200:
            direction = 'extended' if r['nl_end_vs_en'] > 0 else 'shortened'
            print(f'         NL end {direction} {abs(r["nl_end_vs_en"])}ms vs EN')
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='VAD Timing QC — check subtitle timing vs actual speech',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('video', help='Video file')
    parser.add_argument('nl_srt', help='Translated NL subtitle file')
    parser.add_argument('en_srt', help='Source EN subtitle file')
    parser.add_argument(
        '--threshold', type=int, default=500,
        help='Minimum delta (ms) to report as issue (default: 500)',
    )
    parser.add_argument(
        '--aggressiveness', type=int, default=2, choices=[0, 1, 2, 3],
        help='VAD aggressiveness: 0=lenient 3=strict (default: 2)',
    )
    parser.add_argument(
        '--hangover', type=int, default=210,
        help='Smooth silence gaps shorter than this (ms, default: 210)',
    )
    parser.add_argument(
        '--report', metavar='FILE', help='Write JSON report to file',
    )
    parser.add_argument(
        '--no-cache', action='store_true', help='Re-extract audio from video',
    )
    parser.add_argument(
        '--verbose', '-v', action='store_true',
        help='Show low-severity issues too',
    )
    args = parser.parse_args()

    frame_ms = 30
    hangover_frames = max(1, args.hangover // frame_ms)

    # --- Audio ---
    audio, sr = load_audio(args.video, args.no_cache)
    audio_dur = len(audio) / 2 / sr
    print(f'Audio: {audio_dur:.0f}s ({audio_dur / 60:.1f} min), {sr} Hz')

    # --- Global VAD ---
    vad = webrtcvad.Vad(args.aggressiveness)
    print(f'Running VAD (aggressiveness={args.aggressiveness}, '
          f'hangover={hangover_frames * frame_ms}ms)...')
    t0 = time.time()
    raw_map = build_speech_map(audio, sr, vad, frame_ms)
    smoothed = smooth_speech_map(raw_map, hangover_frames)
    speech_starts, speech_ends = find_transitions(smoothed, frame_ms)
    vad_time = time.time() - t0
    print(f'VAD: {len(raw_map)} frames in {vad_time:.1f}s, '
          f'{len(speech_starts)} speech segments detected')

    # --- Parse SRTs ---
    nl_cues = parse_srt(args.nl_srt)
    en_cues = parse_srt(args.en_srt)
    print(f'Cues: {len(nl_cues)} NL, {len(en_cues)} EN')

    # --- Match NL → EN ---
    matches = match_source_cues(nl_cues, en_cues)

    # --- Analyze all cues ---
    all_results = []
    flagged = []

    for idx, nl in enumerate(nl_cues):
        en_match = matches.get(nl['num'], [])
        result = analyze_cue(nl, en_match, speech_ends, speech_starts, search_range=2000)
        all_results.append(result)

        prev_nl = nl_cues[idx - 1] if idx > 0 else None
        next_nl = nl_cues[idx + 1] if idx < len(nl_cues) - 1 else None
        issues = classify_issues(result, args.threshold, prev_nl, next_nl)
        if issues:
            result['issues'] = issues
            flagged.append(result)

    # --- Report ---
    high = [f for f in flagged if any(i['severity'] == 'high' for i in f['issues'])]
    medium = [f for f in flagged if f not in high
              and any(i['severity'] == 'medium' for i in f['issues'])]
    low = [f for f in flagged if f not in high and f not in medium]

    print(f'\nAnalyzed: {len(all_results)} cues')
    print(f'Flagged:  {len(flagged)} ({len(high)} high, '
          f'{len(medium)} medium, {len(low)} low)\n')

    if high:
        print(f'── HIGH ({len(high)}) ──')
        for r in high:
            print_issue(r)

    if medium:
        print(f'── MEDIUM ({len(medium)}) ──')
        for r in medium:
            print_issue(r)

    if low and args.verbose:
        print(f'── LOW ({len(low)}) ──')
        for r in low:
            print_issue(r)
    elif low:
        print(f'── LOW: {len(low)} cues (use --verbose to show) ──\n')

    # --- Summary stats ---
    end_deltas = [r['end_delta_ms'] for r in all_results if r['end_delta_ms'] is not None]
    start_deltas = [r['start_delta_ms'] for r in all_results if r['start_delta_ms'] is not None]
    if end_deltas:
        print('── Summary ──')
        print(f'End delta:   avg {sum(end_deltas) / len(end_deltas):+.0f}ms  '
              f'range [{min(end_deltas):+d}ms .. {max(end_deltas):+d}ms]')
    if start_deltas:
        print(f'Start delta: avg {sum(start_deltas) / len(start_deltas):+.0f}ms  '
              f'range [{min(start_deltas):+d}ms .. {max(start_deltas):+d}ms]')

    # --- JSON report ---
    if args.report:
        report = {
            'video': os.path.basename(args.video),
            'nl_srt': os.path.basename(args.nl_srt),
            'en_srt': os.path.basename(args.en_srt),
            'settings': {
                'threshold_ms': args.threshold,
                'aggressiveness': args.aggressiveness,
                'hangover_ms': hangover_frames * frame_ms,
            },
            'summary': {
                'cues_analyzed': len(all_results),
                'cues_flagged': len(flagged),
                'high': len(high),
                'medium': len(medium),
                'low': len(low),
            },
            'flagged': flagged,
        }
        if end_deltas:
            report['summary']['end_delta_avg_ms'] = round(
                sum(end_deltas) / len(end_deltas))
        if start_deltas:
            report['summary']['start_delta_avg_ms'] = round(
                sum(start_deltas) / len(start_deltas))

        os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
        with open(args.report, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f'\nReport: {args.report}')


if __name__ == '__main__':
    main()

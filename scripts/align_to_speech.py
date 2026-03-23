#!/usr/bin/env python3
"""
Forced-align SRT subtitles to audio using PocketSphinx.

Corrects per-cue start/end timestamps by aligning the subtitle text
against actual speech in the audio track. Useful for fixing Whisper
timing errors that ffsubsync (global offset only) cannot handle.

Usage:
    python align_to_speech.py <video_or_audio> <srt_file> [-o OUTPUT] [--dry-run]

Requirements:
    - pocketsphinx (pip install pocketsphinx)
    - ffmpeg (for extracting audio from video files)
    - English text only (pocketsphinx bundled model is English)

Approach:
    For each SRT cue, extracts the audio around the cue's current
    timestamp (with small padding), force-aligns the cue text using
    PocketSphinx, and updates start/end times based on where the
    first and last words are actually spoken.
"""

import sys
import os
import re
import wave
import tempfile
import subprocess
import argparse
from pathlib import Path
from dataclasses import dataclass
from typing import List

# Add scripts dir to path for srt_utils
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from srt_utils import parse_srt_file, Subtitle, write_srt, ms_to_timecode
from pocketsphinx import Decoder


# --- Text normalization for PocketSphinx dictionary ---

NUMBER_WORDS = {
    '0': 'zero', '1': 'one', '2': 'two', '3': 'three', '4': 'four',
    '5': 'five', '6': 'six', '7': 'seven', '8': 'eight', '9': 'nine',
    '10': 'ten', '11': 'eleven', '12': 'twelve', '13': 'thirteen',
    '14': 'fourteen', '15': 'fifteen', '16': 'sixteen', '17': 'seventeen',
    '18': 'eighteen', '19': 'nineteen', '20': 'twenty', '30': 'thirty',
    '40': 'forty', '50': 'fifty', '60': 'sixty', '70': 'seventy',
    '80': 'eighty', '90': 'ninety', '100': 'hundred',
    '1000': 'thousand',
}

ORDINAL_WORDS = {
    '1st': 'first', '2nd': 'second', '3rd': 'third', '4th': 'fourth',
    '5th': 'fifth', '6th': 'sixth', '7th': 'seventh', '8th': 'eighth',
    '9th': 'ninth', '10th': 'tenth',
}


def number_to_words(n_str: str) -> str:
    """Convert a numeric string to spoken words."""
    n_str = n_str.replace(',', '')

    if n_str in NUMBER_WORDS:
        return NUMBER_WORDS[n_str]
    if n_str in ORDINAL_WORDS:
        return ORDINAL_WORDS[n_str]

    # Year-like four-digit numbers
    if re.match(r'^(19|20)\d{2}$', n_str):
        year = int(n_str)
        if 2000 <= year <= 2009:
            return f"two thousand {'and ' + NUMBER_WORDS.get(str(year - 2000), str(year - 2000)) if year > 2000 else ''}".strip()
        first = year // 100
        second = year % 100
        first_w = NUMBER_WORDS.get(str(first), str(first))
        if second == 0:
            return f"{first_w} hundred"
        elif second < 20:
            return f"{first_w} {NUMBER_WORDS.get(str(second), str(second))}"
        else:
            tens = (second // 10) * 10
            ones = second % 10
            tens_w = NUMBER_WORDS.get(str(tens), str(tens))
            if ones == 0:
                return f"{first_w} {tens_w}"
            ones_w = NUMBER_WORDS.get(str(ones), str(ones))
            return f"{first_w} {tens_w} {ones_w}"

    # Two-digit numbers
    try:
        n = int(n_str)
        if 20 < n < 100:
            tens = (n // 10) * 10
            ones = n % 10
            tens_w = NUMBER_WORDS.get(str(tens), str(tens))
            if ones == 0:
                return tens_w
            ones_w = NUMBER_WORDS.get(str(ones), str(ones))
            return f"{tens_w} {ones_w}"
        if 100 < n < 1000:
            hundreds = n // 100
            remainder = n % 100
            h_word = NUMBER_WORDS.get(str(hundreds), str(hundreds))
            if remainder == 0:
                return f"{h_word} hundred"
            return f"{h_word} hundred and {number_to_words(str(remainder))}"
    except ValueError:
        pass

    # Fallback: spell digit by digit
    return ' '.join(NUMBER_WORDS.get(d, d) for d in n_str if d.isdigit())


def normalize_text_for_alignment(text: str, decoder) -> str:
    """Normalize subtitle text to words the PocketSphinx dictionary knows.
    Returns space-joined string of known words."""
    # Remove SRT formatting
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\{[^}]+\}', '', text)
    text = text.replace('\n', ' ')
    text = text.replace('...', ' ')
    text = text.replace('…', ' ')

    # Remove speaker dashes
    text = re.sub(r'^- ', '', text)
    text = re.sub(r' - ', ' ', text)

    # Expand contractions
    contractions = {
        "won't": "will not", "can't": "cannot", "couldn't": "could not",
        "wouldn't": "would not", "shouldn't": "should not",
        "don't": "do not", "doesn't": "does not", "didn't": "did not",
        "isn't": "is not", "aren't": "are not", "wasn't": "was not",
        "weren't": "were not", "hasn't": "has not", "haven't": "have not",
        "hadn't": "had not", "i'm": "i am", "i've": "i have",
        "i'll": "i will", "i'd": "i would", "you're": "you are",
        "you've": "you have", "you'll": "you will", "you'd": "you would",
        "he's": "he is", "she's": "she is", "it's": "it is",
        "we're": "we are", "we've": "we have", "we'll": "we will",
        "they're": "they are", "they've": "they have", "they'll": "they will",
        "there's": "there is", "that's": "that is", "what's": "what is",
        "who's": "who is", "let's": "let us",
    }

    text_lower = text.lower()
    for contraction, expansion in contractions.items():
        text_lower = re.sub(r'\b' + re.escape(contraction) + r'\b', expansion, text_lower)

    # Expand numbers
    text_lower = re.sub(r'\b(\d+(?:,\d{3})*(?:st|nd|rd|th)?)\b',
                        lambda m: number_to_words(m.group(1)), text_lower)

    # Remove all punctuation except apostrophes within words
    text_lower = re.sub(r"[^\w\s']", ' ', text_lower)
    text_lower = re.sub(r"(?<!\w)'|'(?!\w)", ' ', text_lower)

    words = text_lower.split()

    # Filter to words in the dictionary
    known = []
    for w in words:
        if decoder.lookup_word(w) is not None:
            known.append(w)
        elif w.endswith("'s") and decoder.lookup_word(w[:-2]) is not None:
            known.append(w[:-2])

    return ' '.join(known)


def extract_audio(video_path: str, output_wav: str) -> bool:
    """Extract 16kHz mono WAV from video/audio file."""
    cmd = [
        'ffmpeg', '-i', video_path,
        '-vn', '-ac', '1', '-ar', '16000', '-acodec', 'pcm_s16le',
        '-y', output_wav
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def read_wav_segment(wav_path: str, start_ms: int, end_ms: int) -> bytes:
    """Read a segment of a WAV file as raw PCM bytes."""
    with wave.open(wav_path, 'rb') as wf:
        rate = wf.getframerate()
        start_frame = max(0, int(start_ms * rate / 1000))
        end_frame = min(wf.getnframes(), int(end_ms * rate / 1000))
        if end_frame <= start_frame:
            return b''
        wf.setpos(start_frame)
        return wf.readframes(end_frame - start_frame)


@dataclass
class CueCorrection:
    """Correction for a single cue."""
    cue_index: int
    original_start_ms: int
    original_end_ms: int
    aligned_start_ms: int
    aligned_end_ms: int
    words_expected: int
    words_found: int

    @property
    def start_delta_ms(self) -> int:
        return self.aligned_start_ms - self.original_start_ms

    @property
    def end_delta_ms(self) -> int:
        return self.aligned_end_ms - self.original_end_ms

    @property
    def confidence(self) -> float:
        return self.words_found / self.words_expected if self.words_expected > 0 else 0

    @property
    def significant(self) -> bool:
        return abs(self.start_delta_ms) > 150 or abs(self.end_delta_ms) > 150


def align_cue(decoder, wav_path: str, cue: Subtitle,
              prev_end_ms: int | None = None,
              padding_ms: int = 1500) -> CueCorrection | None:
    """
    Force-align a single cue's text against the audio.

    Window start: midpoint between previous cue's end and this cue's start
    (avoids capturing speech from the previous cue). Falls back to
    padding_ms before cue start if no previous cue.
    Window end: cue end + padding_ms.
    """
    text = normalize_text_for_alignment(cue.text, decoder)
    word_count = len(text.split()) if text else 0
    if word_count < 2:
        return None  # Too little text to align reliably

    # Window start: use gap midpoint to avoid previous cue's speech,
    # but cap the look-back to padding_ms to avoid huge windows after long gaps
    if prev_end_ms is not None and prev_end_ms < cue.start_ms:
        gap = cue.start_ms - prev_end_ms
        look_back = min(gap // 2, padding_ms)
        window_start_ms = max(0, cue.start_ms - look_back)
    else:
        window_start_ms = max(0, cue.start_ms - padding_ms)

    window_end_ms = cue.end_ms + padding_ms

    audio_segment = read_wav_segment(wav_path, window_start_ms, window_end_ms)
    if not audio_segment:
        return None

    try:
        decoder.set_align_text(text)
        decoder.start_utt()
        decoder.process_raw(audio_segment, full_utt=True)
        decoder.end_utt()
    except RuntimeError:
        return None

    # Collect word segments
    seg_iter = decoder.seg()
    if seg_iter is None:
        return None

    segments = []
    for seg in seg_iter:
        if seg.word in ('<s>', '</s>', '<sil>', '(NULL)'):
            continue
        segments.append({
            'start_frame': seg.start_frame,
            'end_frame': seg.end_frame,
        })

    if not segments:
        return None

    # Convert frame positions (100fps) to absolute milliseconds
    first_word_ms = window_start_ms + int(segments[0]['start_frame'] * 10)
    last_word_ms = window_start_ms + int(segments[-1]['end_frame'] * 10)

    # Sanity check: reject corrections that move start by more than 2x padding
    # (likely a misalignment against wrong speech)
    max_correction = padding_ms * 2
    if abs(first_word_ms - cue.start_ms) > max_correction:
        return None

    return CueCorrection(
        cue_index=cue.index,
        original_start_ms=cue.start_ms,
        original_end_ms=cue.end_ms,
        aligned_start_ms=first_word_ms,
        aligned_end_ms=last_word_ms,
        words_expected=word_count,
        words_found=len(segments),
    )


def main():
    parser = argparse.ArgumentParser(
        description='Force-align SRT subtitles to audio using PocketSphinx'
    )
    parser.add_argument('media', help='Video or audio file')
    parser.add_argument('srt', help='SRT subtitle file to align')
    parser.add_argument('-o', '--output',
                        help='Output SRT path (default: input with .aligned.srt suffix)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Report corrections without writing output')
    parser.add_argument('--padding', type=int, default=1500,
                        help='Search window padding in ms (default: 1500)')
    parser.add_argument('--threshold', type=int, default=150,
                        help='Minimum correction in ms to apply (default: 150)')
    parser.add_argument('--min-confidence', type=float, default=0.5,
                        help='Minimum word match ratio to trust alignment (default: 0.5)')
    parser.add_argument('--end-padding', type=int, default=200,
                        help='Extra ms added after last aligned word (default: 200)')
    args = parser.parse_args()

    srt_path = args.srt
    media_path = args.media

    if not os.path.isfile(media_path):
        print(f"Error: media file not found: {media_path}", file=sys.stderr)
        sys.exit(1)
    if not os.path.isfile(srt_path):
        print(f"Error: SRT file not found: {srt_path}", file=sys.stderr)
        sys.exit(1)

    # Determine output path
    if args.output:
        output_path = args.output
    else:
        p = Path(srt_path)
        output_path = str(p.with_suffix('.aligned.srt'))

    # Extract audio if needed
    wav_path = None
    temp_wav = False
    if media_path.lower().endswith('.wav'):
        wav_path = media_path
    else:
        wav_path = tempfile.mktemp(suffix='.wav')
        temp_wav = True
        print(f"Extracting audio from {os.path.basename(media_path)}...")
        if not extract_audio(media_path, wav_path):
            print("Error: failed to extract audio", file=sys.stderr)
            sys.exit(1)

    # Parse SRT
    cues, errors = parse_srt_file(srt_path)
    if errors:
        print(f"Warning: {len(errors)} parse errors in SRT", file=sys.stderr)
    print(f"Loaded {len(cues)} cues from {os.path.basename(srt_path)}")

    # Initialize PocketSphinx
    decoder = Decoder()

    # Align each cue
    corrections = []
    skipped_short = 0
    skipped_confidence = 0

    for i, cue in enumerate(cues):
        prev_end = cues[i - 1].end_ms if i > 0 else None
        result = align_cue(decoder, wav_path, cue, prev_end_ms=prev_end,
                           padding_ms=args.padding)
        if result is None:
            skipped_short += 1
            continue
        if result.confidence < args.min_confidence:
            skipped_confidence += 1
            continue
        corrections.append(result)

        if (i + 1) % 50 == 0 or i == len(cues) - 1:
            print(f"  Aligned {i + 1}/{len(cues)} cues...", end='\r')

    print()

    # Filter to significant corrections
    significant = [c for c in corrections if c.significant]

    # Report
    print(f"\n{'='*70}")
    print(f"Alignment Results")
    print(f"{'='*70}")
    print(f"Total cues:          {len(cues)}")
    print(f"Aligned:             {len(corrections)}")
    print(f"Skipped (too short): {skipped_short}")
    print(f"Skipped (low conf):  {skipped_confidence}")
    print(f"Significant (>{args.threshold}ms): {len(significant)}")

    if significant:
        print(f"\n{'Cue':>5} {'Start Δ':>9} {'End Δ':>9} {'Conf':>6}  Text")
        print(f"{'-'*5:>5} {'-'*9:>9} {'-'*9:>9} {'-'*6:>6}  {'-'*40}")
        for c in significant:
            cue = next(cu for cu in cues if cu.index == c.cue_index)
            text_preview = cue.text.replace('\n', ' ')[:40]
            print(f"{c.cue_index:>5} {c.start_delta_ms:>+8}ms {c.end_delta_ms:>+8}ms "
                  f"{c.confidence:>5.0%}  {text_preview}")

        start_deltas = [c.start_delta_ms for c in significant]
        end_deltas = [c.end_delta_ms for c in significant]
        print(f"\nStart corrections: min={min(start_deltas):+d}ms  max={max(start_deltas):+d}ms  "
              f"avg={sum(start_deltas)/len(start_deltas):+.0f}ms")
        print(f"End corrections:   min={min(end_deltas):+d}ms  max={max(end_deltas):+d}ms  "
              f"avg={sum(end_deltas)/len(end_deltas):+.0f}ms")

    if args.dry_run:
        print(f"\nDry run — no output written.")
    else:
        applied = 0
        for c in corrections:
            if not c.significant:
                continue
            for cue in cues:
                if cue.index == c.cue_index:
                    cue.start_ms = c.aligned_start_ms
                    cue.end_ms = c.aligned_end_ms + args.end_padding
                    applied += 1
                    break

        # Fix overlaps
        for i in range(len(cues) - 1):
            if cues[i].end_ms > cues[i + 1].start_ms:
                cues[i].end_ms = cues[i + 1].start_ms - 1

        # Ensure no negative durations
        for cue in cues:
            if cue.end_ms <= cue.start_ms:
                cue.end_ms = cue.start_ms + 500

        write_srt(cues, output_path)
        print(f"\nApplied {applied} corrections → {output_path}")

    # Cleanup
    if temp_wav and os.path.exists(wav_path):
        os.unlink(wav_path)


if __name__ == '__main__':
    main()

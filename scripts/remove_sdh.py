#!/usr/bin/env python3
"""
Remove SDH (Subtitles for Deaf and Hard of Hearing) tags from SRT file.

Removes:
- [bracketed descriptions] like [sighs], [music playing], [door slams]
- (parenthetical descriptions)
- Speaker labels like "JOHN:" at start of lines
- Sound effect descriptions
- Music note markers (♪, ♫) with descriptions

Usage:
    python remove_sdh.py <file_path> [--output <path>] [--in-place] [--keep-music]

Output (JSON):
    {
        "original_cues": 250,
        "final_cues": 245,
        "removed_cues": 5,
        "tags_removed": 47,
        "output_file": "subtitle.srt"
    }
"""

import sys
import json
import argparse
import re
from pathlib import Path
from srt_utils import parse_srt_file, write_srt, Subtitle


# Patterns for SDH content
# NOTE: These patterns are applied WITHOUT re.IGNORECASE to preserve negative lookahead behavior
SDH_PATTERNS_CASE_SENSITIVE = [
    # Bracketed descriptions: [sighs], [music playing], [MUSIC], etc.
    # Matches anything in brackets EXCEPT acronyms like [FBI] or [NATO]
    # The negative lookahead (?![A-Z]{2,}\]) prevents matching [FBI] but allows [Sighs]
    r'\[(?![A-Z]{2,}\])[^\]]*\]',
]

# Patterns that need case-insensitive matching (applied separately)
SDH_PATTERNS_CASE_INSENSITIVE = [
    # Parenthetical descriptions: (sighs), (MUSIC PLAYING), etc.
    r'\([^)]*(?:sighs?|laughs?|coughs?|gasps?|groans?|screams?|whispers?|shouts?|cries?|sobs?|sniffs?|clears? throat|music|playing|singing|humming|whistling|applause|cheering|thunder|explosion|gunshot|doorbell|phone|knocking|footsteps|breathing|panting)[^)]*\)',
]

# Patterns that don't need case sensitivity
SDH_PATTERNS_LITERAL = [
    # Music descriptions with notes: ♪ song lyrics ♪ or [♪ music playing ♪]
    r'♪[^♪]*♪',
    r'♫[^♫]*♫',
    r'\[♪[^\]]*\]',
    r'\[♫[^\]]*\]',
    
    # Sound effects in caps: BANG!, CRASH!, etc (but not dialogue)
    r'\b(?:BANG|CRASH|BOOM|THUD|SLAM|CLICK|BEEP|RING|BUZZ)\b[!]?',
]

# Speaker label pattern: "JOHN:", "MAN 1:", "NARRATOR:"
SPEAKER_LABEL_PATTERN = r'^[A-Z][A-Z\s\d]*:\s*'

# Hearing impaired specific: >> for speaker change, - for continued
HI_PATTERNS = [
    r'^>>\s*',  # Speaker change marker
    r'^\(\s*[^)]+\s*\)\s*',  # (NARRATOR) style labels
]


def remove_sdh_from_text(text: str, keep_music: bool = False) -> str:
    """Remove SDH tags from subtitle text."""
    result = text
    
    # Apply case-sensitive patterns (brackets with negative lookahead)
    for pattern in SDH_PATTERNS_CASE_SENSITIVE:
        result = re.sub(pattern, '', result)
    
    # Apply case-insensitive patterns (parenthetical descriptions)
    for pattern in SDH_PATTERNS_CASE_INSENSITIVE:
        if keep_music and 'music' in pattern.lower():
            continue
        result = re.sub(pattern, '', result, flags=re.IGNORECASE)
    
    # Apply literal patterns (music notes, sound effects)
    for pattern in SDH_PATTERNS_LITERAL:
        if keep_music and ('♪' in pattern or '♫' in pattern):
            continue
        result = re.sub(pattern, '', result)
    
    # Apply HI patterns
    for pattern in HI_PATTERNS:
        result = re.sub(pattern, '', result, flags=re.MULTILINE)
    
    # Remove speaker labels from start of lines
    lines = result.split('\n')
    cleaned_lines = []
    for line in lines:
        # Remove "SPEAKER:" pattern at start
        cleaned = re.sub(SPEAKER_LABEL_PATTERN, '', line)
        cleaned_lines.append(cleaned)
    result = '\n'.join(cleaned_lines)
    
    # Clean up multiple spaces
    result = re.sub(r'  +', ' ', result)
    
    # Clean up spaces around newlines
    result = re.sub(r' *\n *', '\n', result)
    
    # Clean up leading/trailing whitespace per line
    lines = [line.strip() for line in result.split('\n')]
    result = '\n'.join(lines)
    
    # Remove empty lines within subtitle
    lines = [line for line in result.split('\n') if line.strip()]
    result = '\n'.join(lines)
    
    return result.strip()


def process_srt(file_path: str, output_path: str | None, in_place: bool, keep_music: bool) -> dict:
    """Process SRT file and remove SDH tags."""
    subtitles, parse_errors = parse_srt_file(file_path)
    
    if parse_errors:
        return {'error': f'Parse errors: {parse_errors}'}
    
    original_count = len(subtitles)
    tags_removed = 0
    cleaned_subs = []
    
    for sub in subtitles:
        original_text = sub.text
        cleaned_text = remove_sdh_from_text(original_text, keep_music)
        
        # Count removed tags (rough estimate)
        tags_removed += len(re.findall(r'\[[^\]]+\]', original_text))
        tags_removed += len(re.findall(r'\([^)]*(?:sighs?|laughs?|music)[^)]*\)', original_text, re.IGNORECASE))
        
        # Skip cue if completely empty after cleaning
        if not cleaned_text:
            continue
        
        sub.text = cleaned_text
        cleaned_subs.append(sub)
    
    # Renumber
    for i, sub in enumerate(cleaned_subs, 1):
        sub.index = i
    
    # Determine output path
    if in_place:
        out_file = file_path
    elif output_path:
        out_file = output_path
    else:
        p = Path(file_path)
        out_file = str(p.parent / f"{p.stem}_cleaned{p.suffix}")
    
    write_srt(cleaned_subs, out_file)
    
    return {
        'original_cues': original_count,
        'final_cues': len(cleaned_subs),
        'removed_cues': original_count - len(cleaned_subs),
        'tags_removed': tags_removed,
        'output_file': out_file
    }


def main():
    parser = argparse.ArgumentParser(description='Remove SDH tags from SRT file')
    parser.add_argument('file_path', help='Path to SRT file')
    parser.add_argument('--output', '-o', help='Output file path')
    parser.add_argument('--in-place', '-i', action='store_true', help='Modify file in place')
    parser.add_argument('--keep-music', action='store_true', help='Keep music note markers')
    args = parser.parse_args()
    
    file_path = Path(args.file_path)
    if not file_path.exists():
        print(json.dumps({'error': f'File not found: {file_path}'}))
        sys.exit(1)
    
    result = process_srt(str(file_path), args.output, args.in_place, args.keep_music)
    
    if 'error' in result:
        print(json.dumps(result))
        sys.exit(1)
    
    print(json.dumps(result, indent=2))
    sys.exit(0)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Core SRT parsing utilities used by other scripts.
Not meant to be called directly.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class Subtitle:
    """Represents a single subtitle cue."""
    index: int
    start_ms: int
    end_ms: int
    text: str
    original_text: str = ""  # Before any processing
    
    # Validation flags (populated by validate)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms
    
    @property
    def duration_seconds(self) -> float:
        return self.duration_ms / 1000.0
    
    @property
    def char_count(self) -> int:
        """Total visible characters (spaces count, newlines don't)."""
        return len(self.text.replace('\n', ''))
    
    @property
    def cps(self) -> float:
        """Characters per second."""
        if self.duration_seconds <= 0:
            return float('inf')
        return self.char_count / self.duration_seconds
    
    @property
    def line_count(self) -> int:
        return len(self.text.split('\n'))
    
    @property
    def max_line_length(self) -> int:
        lines = self.text.split('\n')
        return max(len(line) for line in lines) if lines else 0
    
    def to_srt_block(self) -> str:
        """Convert back to SRT format with CRLF line endings for player compatibility."""
        text_crlf = self.text.replace('\n', '\r\n')
        return f"{self.index}\r\n{ms_to_timecode(self.start_ms)} --> {ms_to_timecode(self.end_ms)}\r\n{text_crlf}\r\n"


def timecode_to_ms(tc: str) -> int:
    """Convert SRT timecode (HH:MM:SS,mmm) to milliseconds."""
    # Handle both comma and period separators
    tc = tc.replace('.', ',')
    
    match = re.match(r'(\d{1,2}):(\d{2}):(\d{2}),(\d{3})', tc.strip())
    if not match:
        raise ValueError(f"Invalid timecode format: {tc}")
    
    hours, minutes, seconds, ms = map(int, match.groups())
    return (hours * 3600 + minutes * 60 + seconds) * 1000 + ms


def ms_to_timecode(ms: int) -> str:
    """Convert milliseconds to SRT timecode (HH:MM:SS,mmm)."""
    if ms < 0:
        ms = 0
    
    hours = ms // 3600000
    ms %= 3600000
    minutes = ms // 60000
    ms %= 60000
    seconds = ms // 1000
    milliseconds = ms % 1000
    
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def parse_srt(content: str) -> Tuple[List[Subtitle], List[str]]:
    """
    Parse SRT content into list of Subtitle objects.
    
    Returns:
        Tuple of (subtitles, parse_errors)
    """
    subtitles = []
    errors = []
    
    # Normalize line endings
    content = content.replace('\r\n', '\n').replace('\r', '\n')
    
    # Remove BOM if present
    if content.startswith('\ufeff'):
        content = content[1:]
    
    # Split into blocks (separated by blank lines)
    blocks = re.split(r'\n\n+', content.strip())
    
    for block_num, block in enumerate(blocks, 1):
        block = block.strip()
        if not block:
            continue
        
        lines = block.split('\n')
        
        # Need at least: index, timecode, one line of text
        if len(lines) < 3:
            # Could be index + timecode with empty text (valid edge case)
            if len(lines) == 2:
                lines.append('')  # Empty text
            else:
                errors.append(f"Block {block_num}: Insufficient lines ({len(lines)})")
                continue
        
        # Parse index
        try:
            index = int(lines[0].strip())
        except ValueError:
            errors.append(f"Block {block_num}: Invalid index '{lines[0]}'")
            continue
        
        # Parse timecode
        tc_match = re.match(
            r'(\d{1,2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,\.]\d{3})',
            lines[1].strip()
        )
        if not tc_match:
            errors.append(f"Block {block_num}: Invalid timecode '{lines[1]}'")
            continue
        
        try:
            start_ms = timecode_to_ms(tc_match.group(1))
            end_ms = timecode_to_ms(tc_match.group(2))
        except ValueError as e:
            errors.append(f"Block {block_num}: {e}")
            continue
        
        # Extract text (all remaining lines)
        text = '\n'.join(lines[2:])
        
        subtitle = Subtitle(
            index=index,
            start_ms=start_ms,
            end_ms=end_ms,
            text=text,
            original_text=text
        )
        subtitles.append(subtitle)
    
    return subtitles, errors


def parse_srt_file(file_path: str, encoding: str = None) -> Tuple[List[Subtitle], List[str]]:
    """
    Parse SRT file into list of Subtitle objects.
    
    Args:
        file_path: Path to the SRT file
        encoding: Optional encoding. If None, attempts UTF-8 first, then falls back to detection.
    
    Returns:
        Tuple of (subtitles, parse_errors)
    """
    content = None
    detected_encoding = encoding
    
    # Try specified encoding or UTF-8 first
    encodings_to_try = [encoding] if encoding else ['utf-8', 'utf-8-sig']
    
    for enc in encodings_to_try:
        if enc is None:
            continue
        try:
            with open(file_path, 'r', encoding=enc) as f:
                content = f.read()
            detected_encoding = enc
            break
        except (UnicodeDecodeError, LookupError):
            continue
    
    # If still no content, try to detect encoding
    if content is None:
        try:
            import chardet
            with open(file_path, 'rb') as f:
                raw = f.read()
            detection = chardet.detect(raw)
            detected_encoding = detection.get('encoding', 'utf-8')
            try:
                content = raw.decode(detected_encoding)
            except (UnicodeDecodeError, LookupError):
                # Last resort: decode with replacement
                content = raw.decode('utf-8', errors='replace')
                detected_encoding = 'utf-8 (with replacements)'
        except ImportError:
            # chardet not available, try common encodings
            for enc in ['iso-8859-1', 'windows-1252', 'cp1252']:
                try:
                    with open(file_path, 'r', encoding=enc) as f:
                        content = f.read()
                    detected_encoding = enc
                    break
                except UnicodeDecodeError:
                    continue
            
            if content is None:
                # Absolute last resort
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                detected_encoding = 'utf-8 (with replacements)'
    
    return parse_srt(content)


def write_srt(subtitles: List[Subtitle], file_path: str) -> None:
    """Write subtitles to SRT file with UTF-8 BOM and CRLF for player compatibility."""
    with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
        for i, sub in enumerate(subtitles):
            if i > 0:
                f.write('\n')
            f.write(sub.to_srt_block())


def subtitles_to_srt(subtitles: List[Subtitle]) -> str:
    """Convert subtitles list to SRT string."""
    blocks = [sub.to_srt_block() for sub in subtitles]
    return '\n'.join(blocks)

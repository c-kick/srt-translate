# Code Review Critique: srt-translate

Senior developer code review. This document covers architecture issues, correctness bugs, edge cases, and maintainability concerns.

---

## 1. ARCHITECTURE: The "Bag of Scripts" Anti-Pattern

~14 standalone scripts with no unifying entry point, no shared error handling, and no configuration system.

**Duplicated SRT parsers** -- the most damning structural issue:
- `srt_utils.py:88` has `parse_srt()` -- the "canonical" parser
- `vad_timing_check.py:54` has its own `parse_srt()` returning dicts instead of `Subtitle` objects
- `check_line_balance.py:43` has *yet another* `parse_srt()` -- also returning dicts, with its own `write_srt()` at line 67 that produces *different output formatting* (no CRLF, no BOM) than the canonical `srt_utils.write_srt()`
- `merge_batches.py:16` has `parse_srt_cues()` -- a fourth parser

Three independent parsers for the same format, each with slightly different behavior, different error handling, and different return types. When a bug is fixed in one parser, the others remain broken.

---

## 2. THE HARDCODED PATH BOMB

`condense_cues.py:7`:
```python
sys.path.insert(0, '/mnt/nas/video/.claude/skills/srt-translate/scripts')
```

An **absolute path to a NAS mount** committed to the repo. This script is 100% broken on any other machine. Compare with `auto_merge_cues.py:27` which correctly uses `Path(__file__).parent`.

---

## 3. SILENT DATA CORRUPTION

### 3a. Encoding fallback destroys data silently

`srt_utils.py:202`:
```python
content = raw.decode('utf-8', errors='replace')
detected_encoding = 'utf-8 (with replacements)'
```

When chardet and fallback encodings fail, undecodable bytes are replaced with U+FFFD. The `detected_encoding` string is set but never surfaced to the caller. The returned `(subtitles, errors)` tuple has no indication that replacement happened. Corrupted text gets silently written to output.

### 3b. SDH removal eats legitimate dialogue

`remove_sdh.py:39` -- removes *any* bracketed content that isn't all-caps abbreviation:
```python
r'\[(?![A-Z]{2,}\])[^\]]*\]'
```
Text like `"episode [3]"` or `"the [unintelligible] part"` gets destroyed.

`remove_sdh.py:57` -- removes common English words from flowing dialogue:
```python
r'\b(?:BANG|CRASH|BOOM|THUD|SLAM|CLICK|BEEP|RING|BUZZ)\b[!]?'
```
"The phone will RING" becomes "The phone will ". Also, `[!]?` should be `!?` (the brackets create a character class with a single character -- works by accident, shows regex misunderstanding).

### 3c. Merge markers corrupt legitimate text

`auto_merge_cues.py:58-63`: Markers `[SC]` and `[NM]` are stripped using `startswith()`. If a subtitle legitimately begins with "[SC]", the text is silently corrupted.

---

## 4. MISSING ERROR HANDLING

### 4a. No ffmpeg existence check

`extend_to_speech.py`, `extend_to_speech_lite.py`, `vad_timing_check.py` all call `ffmpeg` via `subprocess.run()` without checking if it's installed. User gets a raw `FileNotFoundError` traceback.

### 4b. ffmpeg stderr decode assumes UTF-8

`extend_to_speech.py:55`:
```python
print(f"FFmpeg error: {e.stderr.decode()}")
```
On Windows CP1252 or any non-UTF-8 locale, `.decode()` crashes with a second `UnicodeDecodeError`, masking the original error.

### 4c. No subprocess timeouts in critical paths

`vad_timing_check.py:97-102`, `extend_to_speech.py:52`, `extend_to_speech_lite.py:58` -- ffmpeg runs with no timeout. Corrupted video = infinite hang.

### 4d. `merge_batches.py` -- zero error handling

The `merge_batches()` function (line 47-73) has no try/except. Output file is opened for writing *before* all inputs are read, so a mid-merge failure leaves a partial output file.

---

## 5. VALIDATION GAPS & EDGE CASES

### 5a. Timecode accepts nonsense values

`srt_utils.py:65` accepts `99:99:99,999` as valid. No range validation for hours < 24, minutes < 60, seconds < 60. Silently converts to ~100 hours in milliseconds.

### 5b. Zero/negative duration subtitles

`srt_utils.py:41-42`: `cps` returns `float('inf')` for zero/negative duration. `json.dumps({'cps': float('inf')})` raises `ValueError`. `calculate_cps.py:45` guards for `cps_values` but reports `cps: 0` in `cue_info` for these cues, which is also wrong.

### 5c. Empty subtitle text

`srt_utils.py:118-119`: 2-line blocks (index + timecode only) create `Subtitle` with `text=""`, `char_count=0`. These flow through the pipeline causing division-by-zero in `pair_analyzer.py` condensation ratio.

### 5d. `fix_overlap` can create negative duration

`validate_srt.py:164`: `new_end = sub.start_ms - MIN_GAP_MS`. If `sub.start_ms=50` and `MIN_GAP_MS=120`, then `new_end=-70`. Creates a subtitle with negative `end_ms`.

### 5e. `classify_issues` None comparison crash

`vad_timing_check.py:305`: `next_nl['start_ms'] <= r['speech_end_nearest']` -- when `speech_end_nearest` is None, comparing int to None raises `TypeError` in Python 3.

---

## 6. INCONSISTENT OUTPUT FORMATS

| Script | BOM | Line endings | Encoding |
|--------|-----|-------------|----------|
| `srt_utils.write_srt()` | UTF-8 BOM | CRLF | utf-8-sig |
| `check_line_balance.write_srt()` | No BOM | LF | utf-8 |
| `merge_batches.merge_batches()` | No BOM | LF | utf-8 |

Running scripts in sequence produces different byte-level output each time, even with no content changes. Breaks diffing and version control.

---

## 7. DUTCH-SPECIFIC HARDCODING

`validate_srt.py:26-31` imports NL constants and aliases them as generic names. No `--language` flag. The constants file defines EN constants too but they're never used. `PUNCTUATION_FIXES` at line 34 bans exclamation marks (Dutch convention) with no toggle.

---

## 8. ZERO TESTS

No test files in the entire project. 14 scripts doing regex-based parsing, timecode arithmetic, and multi-step pipeline processing with zero automated verification. The SDH regex patterns and line-breaking logic are the exact kind of code that needs exhaustive test cases.

---

## 9. RESOURCE MANAGEMENT

### 9a. Unbounded cache growth

`vad_timing_check.py:89-93`:
1. Cache key uses path + file size only (no mtime). Re-encoded video with same size = stale cache.
2. Cache path hardcoded to `/tmp/` -- breaks on Windows.
3. Cache files never cleaned up. Each movie = ~500MB-1GB WAV. 10 movies = 5-10GB orphaned in `/tmp/`.

### 9b. Entire audio in memory

`vad_timing_check.py:120-123` reads entire WAV (~230MB for 2hr movie). `extend_to_speech.py:265` loads it as a torch tensor (even more memory).

---

## 10. DEPENDENCY MANAGEMENT

### 10a. requirements.txt is incomplete

Missing `torch`, `torchaudio`, `silero-vad` (required by `extend_to_speech.py`, ~2GB install).

### 10b. No version pinning

`>=` minimum versions but no upper bounds. Fast-moving deps like torch/silero-vad may break with future versions.

---

## 11. MINOR ISSUES

1. `check_line_balance.py:331` hardcodes `max_chars = 42` instead of importing `MAX_CHARS_PER_LINE` from constants.
2. `pair_analyzer.py:20`, `auto_merge_cues.py:27` use `sys.path.insert(0, ...)` hack instead of proper package structure.
3. `validate_srt.py:408-410` has dead code -- unreachable `pass` in speaker dash validation.
4. `srt_utils.py:56` manually converts `\n` to `\r\n`, then `write_srt()` opens with `newline=''`. Fragile coupling -- change either side independently and you get `\r\r\n`.
5. `detect_encoding.py:60-61` returns `raw_data` (entire file contents) in result dict when caller only needs the encoding string.

---

## PRIORITY FIX ORDER

1. **Kill duplicate parsers.** Make everything use `srt_utils.py`. #1 maintenance and correctness risk.
2. **Fix `condense_cues.py` hardcoded NAS path.** Deployment-breaking bug.
3. **Add tests.** SRT parsing round-trips, timecode edge cases, SDH false positives, merge markers, line-breaking.
4. **Standardize output format.** One encoding/BOM/line-ending choice everywhere via `srt_utils.write_srt()`.
5. **Add `--language` parameter** to `validate_srt.py`.
6. **Fix SDH false positives** -- sound-effect word list needs all-caps context.
7. **Add ffmpeg availability check** before shelling out.
8. **Add cache eviction** for VAD audio cache.
9. **Fix `classify_issues` None comparison** (`vad_timing_check.py:305`).
10. **Fix `fix_overlap` negative duration** (`validate_srt.py:164`).

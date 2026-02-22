#!/usr/bin/env python3
"""
Detect file encoding and convert to UTF-8 if needed.
Returns encoding info and optionally converts file in-place.

Usage:
    python detect_encoding.py <file_path> [--convert]

Output (JSON):
    {
        "original_encoding": "ISO-8859-1",
        "confidence": 0.95,
        "converted": true,
        "warning": null
    }
"""

import sys
import json
import argparse
from pathlib import Path
import chardet


# Common subtitle encodings - auto-convert silently
COMMON_ENCODINGS = {
    'utf-8', 'utf-8-sig', 'ascii',
    'iso-8859-1', 'iso-8859-15',
    'windows-1252', 'cp1252',
    'windows-1250', 'cp1250',
    'latin-1', 'latin1',
}

# Encodings that warrant a warning
EXOTIC_ENCODINGS = {
    'utf-16', 'utf-16-le', 'utf-16-be',
    'utf-32', 'utf-32-le', 'utf-32-be',
    'gb2312', 'gbk', 'gb18030',
    'big5', 'euc-kr', 'euc-jp',
    'shift_jis', 'iso-2022-jp',
}


def detect_encoding(file_path: Path) -> dict:
    """Detect file encoding using chardet."""
    with open(file_path, 'rb') as f:
        raw_data = f.read()
    
    result = chardet.detect(raw_data)
    encoding = result['encoding']
    confidence = result['confidence']
    
    # Normalize encoding name
    if encoding:
        encoding = encoding.lower().replace('_', '-')
    
    return {
        'encoding': encoding,
        'confidence': confidence,
        'raw_data': raw_data
    }


def convert_to_utf8(file_path: Path, source_encoding: str, raw_data: bytes) -> dict:
    """Convert file to UTF-8."""
    try:
        # Decode with source encoding
        text = raw_data.decode(source_encoding)
        
        # Remove BOM if present
        if text.startswith('\ufeff'):
            text = text[1:]
        
        # Write as UTF-8
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(text)
        
        return {'success': True, 'error': None}
    
    except UnicodeDecodeError as e:
        return {'success': False, 'error': str(e)}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def main():
    parser = argparse.ArgumentParser(description='Detect and convert file encoding')
    parser.add_argument('file_path', help='Path to the file')
    parser.add_argument('--convert', action='store_true', help='Convert to UTF-8 if needed')
    args = parser.parse_args()
    
    file_path = Path(args.file_path)
    
    if not file_path.exists():
        print(json.dumps({'error': f'File not found: {file_path}'}))
        sys.exit(1)
    
    # Detect encoding
    detection = detect_encoding(file_path)
    encoding = detection['encoding']
    confidence = detection['confidence']
    
    result = {
        'original_encoding': encoding,
        'confidence': confidence,
        'converted': False,
        'warning': None
    }
    
    if encoding is None:
        result['warning'] = 'Could not detect encoding'
        print(json.dumps(result))
        sys.exit(1)
    
    # Check if already UTF-8
    if encoding in ('utf-8', 'ascii'):
        result['converted'] = False
        print(json.dumps(result))
        sys.exit(0)
    
    # Check for exotic encodings
    if encoding in EXOTIC_ENCODINGS:
        result['warning'] = f'Exotic encoding detected: {encoding}. Review conversion result.'
    
    # Convert if requested
    if args.convert:
        conversion = convert_to_utf8(file_path, encoding, detection['raw_data'])
        if conversion['success']:
            result['converted'] = True
        else:
            result['warning'] = f'Conversion failed: {conversion["error"]}'
            result['converted'] = False
    
    print(json.dumps(result))
    sys.exit(0)


if __name__ == '__main__':
    main()

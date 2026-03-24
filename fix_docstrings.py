#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fix corrupted docstrings in feishu-card-server.py by replacing bad triple-quote strings"""
import re
import ast

filename = r'C:\Users\Administrator\.openclaw\workspace-ips-maker\skills\self-media-auto\feishu-card-server.py'

with open(filename, 'r', encoding='utf-8-sig', errors='replace') as f:
    content = f.read()

# Find all triple-quoted strings and check if they cause issues
# Replace any string that contains non-ASCII chars that are clearly mojibake

def is_valid_python_char(c):
    """Check if a character is valid in Python source (allows all Unicode except surrogate and private use"""
    code = ord(c)
    # Allow regular Unicode letters/numbers/punctuation (basic ASCII + common CJK)
    # Disallow: control chars, private use, surrogates, non-character code points
    if code < 0xD800 and code not in (9, 10, 13):  # Allow tab, newline, cr
        return True  # ASCII
    if 0x4E00 <= code <= 0x9FFF:  # CJK Unified Ideographs
        return True
    if 0x3000 <= code <= 0x303F:  # CJK Symbols
        return True
    if 0xFF00 <= code <= 0xFFEF:  # Halfwidth and Fullwidth Forms
        return True
    if 0x2000 <= code <= 0x206F:  # General Punctuation
        return True
    if 0x10000 <= code <= 0x1FFFF:  # Allow emoji and other valid Unicode
        return True
    if code >= 0xE000 and code <= 0xF8FF:  # Private Use - disallow
        return False
    if 0xD800 <= code <= 0xDFFF:  # Surrogates - disallow
        return False
    return True  # Allow other valid Unicode

def fix_docstring(match):
    """Replace docstring content if it contains bad chars"""
    full = match.group(0)
    # Check if the content has obviously bad chars
    inner = match.group(1)
    for c in inner:
        if not is_valid_python_char(c):
            # Contains corrupted chars - replace
            return '"""[FIXED]"""'
    return full

# Replace corrupted triple-double-quote docstrings
new_content = re.sub(r'"""([^"]*)"""', fix_docstring, content)

# Also handle triple-single-quote
def fix_docstring2(match):
    full = match.group(0)
    inner = match.group(1)
    for c in inner:
        if not is_valid_python_char(c):
            return "'''[FIXED]'''"
    return full

new_content = re.sub(r"'''([^']*)'''", fix_docstring2, new_content)

# Verify it parses
try:
    ast.parse(new_content)
    print('SUCCESS: File parses correctly!')
    with open(filename, 'w', encoding='utf-8-sig') as f:
        f.write(new_content)
    print('Written fixed file.')
except SyntaxError as e:
    print(f'Still has error at line {e.lineno}: {e.msg}')
    lines = new_content.split('\n')
    for i in range(max(0, e.lineno-3), min(len(lines), e.lineno+2)):
        marker = ">>> " if i == e.lineno - 1 else "    "
        print(f'{marker}{i+1}: {repr(lines[i])[:80]}')

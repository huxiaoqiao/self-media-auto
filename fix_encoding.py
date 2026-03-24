#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fix feishu-card-server.py encoding damage from PowerShell"""

filename = r'C:\Users\Administrator\.openclaw\workspace-ips-maker\skills\self-media-auto\feishu-card-server.py'

with open(filename, 'rb') as f:
    raw = f.read()

print(f'File size: {len(raw)} bytes')
print(f'BOM: {raw[:3]}')

# The original was UTF-8 with BOM (EF BB BF)
# PowerShell interpreted UTF-8 bytes through GBK codepage and wrote them back
# So we need to "undo" this: treat the current bytes as GBK->UTF-8 corruption

# Current content is garbled UTF-8 (treated as GBK)
# We want to get back the original UTF-8 bytes

# Try to decode the garbled text as GBK (what PowerShell thought it was)
try:
    # The garbled UTF-8 bytes interpreted as GBK will produce some string
    # Then re-encoding as UTF-8 won't help...
    # Actually the damage is that UTF-8 bytes were decoded as GBK and saved as UTF-8
    
    # Better approach: the raw bytes are the CORRUPTED UTF-8
    # These bytes, when decoded as UTF-8, produce mojibake
    # But what PowerShell did: it decoded UTF-8 bytes as GBK (wrong), then saved those as UTF-8
    
    # So the raw bytes are: original_UTF8_bytes interpreted as GBK, then re-encoded as UTF-8
    # To fix: decode as GBK to get intermediate bytes, then... but that's not right either
    
    # Let me try: decode the corrupted UTF-8 bytes as GBK, then encode as UTF-8
    # This simulates what PowerShell's interpretation chain did
    text_corrupt = raw.decode('utf-8-sig', errors='replace')
    text_fixed = text_corrupt.encode('gbk', errors='replace').decode('gbk', errors='replace')
    
    # Now re-encode to proper UTF-8
    fixed_bytes = text_fixed.encode('utf-8', errors='replace')
    
    print(f'After encoding round-trip, size: {len(fixed_bytes)}')
    
    # Check if it parses
    try:
        fixed_text = fixed_bytes.decode('utf-8')
        import ast
        ast.parse(fixed_text)
        print('SUCCESS: File parses correctly!')
        with open(filename, 'wb') as f:
            f.write(fixed_bytes)
        print('Written fixed file.')
    except SyntaxError as e:
        print(f'Still has syntax error: {e}')
        print('Need different approach')
except Exception as e:
    print(f'Error: {e}')

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
import json

with open('.workflow_state.json', 'r') as f:
    state = json.load(f)

candidates = state.get('last_candidates', [])
print('Found', len(candidates), 'candidates')
for i, c in enumerate(candidates[:5]):
    title = c.get('title', '?')
    print(str(i+1) + '. ' + title[:60])

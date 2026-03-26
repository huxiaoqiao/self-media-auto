# -*- coding: utf-8 -*-
import json
import sys
sys.path.insert(0, '.')
from send_feishu_card import build_topic_list_card, get_token, send_card

# Read cached topics
with open('.workflow_state.json', 'r', encoding='utf-8') as f:
    state = json.load(f)

candidates = state.get('last_candidates', [])
industry = state.get('industry', 'AI')

# Take top 5
top5 = candidates[:5]
print(f'Preparing to send {len(top5)} topics...')

# Build topics list
topics = []
for i, t in enumerate(top5):
    topics.append({
        'id': str(i+1),
        'title': t.get('title', ''),
        'likes': t.get('likes', 0),
        'comments': t.get('comments', 0),
        'author': t.get('author', ''),
        'score': t.get('score', 0),
        'url': t.get('id', ''),
        'analysis': 'Author: %s | Score: %s' % (t.get('author', ''), t.get('score', 0)),
        'data': 'Likes: %s | Comments: %s | Score: %s' % (t.get('likes', 0), t.get('comments', 0), t.get('score', 0))
    })

card = build_topic_list_card(topics, industry=industry)
token = get_token()
send_card(token, 'ou_2da8e0f846c19c8fabebd6c6d82a8d6d', card)
print('Done')

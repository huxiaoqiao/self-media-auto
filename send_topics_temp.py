import sys
sys.stdout.reconfigure(encoding='utf-8')

from send_feishu_card import send_topic_list_card
import json

# Load the state
with open('.workflow_state.json', 'r', encoding='utf-8') as f:
    state = json.load(f)

# Get first 5 topics
candidates = state['last_candidates'][:5]
industry = state.get('industry', 'AI')

topics = []
for c in candidates:
    topics.append({
        'title': c['title'],
        'data': "阅读数未知 | 点赞 %d | 热度 %d" % (c.get('likes', 0), c.get('score', 0)),
        'url': c['id'],
        'analysis': "%s | 评分 %d" % (c.get('author', ''), c.get('score', 0)),
        'id': c['id']
    })

# Send the card (no print to avoid encoding issues)
result = send_topic_list_card(topics, industry=industry)
print("Send result:", result)

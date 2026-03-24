import json, os
with open('.workflow_state.json', 'r', encoding='utf-8') as f:
    state = json.load(f)
print('draft_file:', state.get('draft_file'))
print('video_script:', state.get('video_script'))
print('cover_image:', state.get('cover_image'))
print('current_step:', state.get('current_step'))
draft = state.get('draft_file')
if draft:
    print('Draft exists:', os.path.exists(draft))

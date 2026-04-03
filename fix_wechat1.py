import sys, re

path = r'c:\Users\Administrator\.openclaw\skills\self-media-auto\baoyu-post-to-wechat\scripts\wechat-article.ts'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

pattern1 = re.compile(r"console\.log\('\[wechat\] Waiting for \"Next\" button\.\.\.'\);([\s\S]*?)console\.log\('\[wechat\] Next button not found[\s\S]*?\);")

replacement1 = '''console.log('[wechat] Waiting for "Next" button...');
        await sleep(2000);
        const nextRectRes = await evaluate<any>(session, \
            (async function() {
              const btns = Array.from(document.querySelectorAll('.weui-desktop-dialog__ft .weui-desktop-btn_primary, .weui-desktop-dialog .weui-desktop-btn_primary'));
              const nextBtn = btns.find(el => el.textContent.includes('下一步'));
              if (nextBtn) {
                 const rect = nextBtn.getBoundingClientRect();
                 return { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 };
              }
              return null;
          })()
        \);
        
        if (nextRectRes) {
           console.log('[wechat] Dispatching trusted mouse click to "Next" button...');
           await session.cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: nextRectRes.x, y: nextRectRes.y, button: 'left', clickCount: 1 }, { sessionId: session.sessionId });
           await sleep(100);
           await session.cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: nextRectRes.x, y: nextRectRes.y, button: 'left', clickCount: 1 }, { sessionId: session.sessionId });
        } else {
           console.log('[wechat] "Next" button not found, checking if already on crop page');
        }'''

if pattern1.search(text):
    text = pattern1.sub(replacement1, text, 1)
    print('Replaced Block 1')
else:
    print('Block 1 not found')

with open(path, 'w', encoding='utf-8') as f:
    f.write(text)

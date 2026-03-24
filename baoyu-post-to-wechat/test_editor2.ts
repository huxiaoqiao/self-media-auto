import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';

const REMOTE_URL = 'wss://chrome.us.ci/devtools/page/2068FD83FF7E0F348D7B5B6F175B9E85';

async function test() {
  console.log('连接 CDP...');
  const cdp = await CdpConnection.connect(REMOTE_URL, 30000);
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId: '2068FD83FF7E0F348D7B5B6F175B9E85', flatten: true });
  await cdp.send('Page.enable', {}, { sessionId });
  await cdp.send('Runtime.enable', {}, { sessionId });
  
  // 查找所有可能的编辑器选择器
  const editors = await cdp.send('Runtime.evaluate', {
    expression: `(function() {
      const selectors = ['#js_content', '.edit_area', '#ueditor_0', '.ueditor', '[contenteditable="true"]', '#editArea', '.richedit'];
      const results = [];
      for (const sel of selectors) {
        const el = document.querySelector(sel);
        if (el) {
          results.push({
            selector: sel,
            tagName: el.tagName,
            contentLength: el.innerText?.length || 0,
            contentPreview: el.innerText?.substring(0, 100) || 'empty'
          });
        }
      }
      return JSON.stringify(results);
    })()`
  }, { sessionId });
  console.log('编辑器元素:', editors.result.value);
  
  // 检查 iframe 中的内容
  const iframeContent = await cdp.send('Runtime.evaluate', {
    expression: `(function() {
      const iframes = document.querySelectorAll('iframe');
      for (const iframe of iframes) {
        try {
          const doc = iframe.contentDocument || iframe.contentWindow?.document;
          if (doc) {
            const body = doc.body?.innerText || '';
            if (body.length > 0) {
              return 'IFRAME content: ' + body.substring(0, 200);
            }
          }
        } catch(e) {}
      }
      return 'No iframe content found';
    })()`
  }, { sessionId });
  console.log('iframe 内容:', iframeContent.result.value);
  
  await cdp.close();
}

test().catch(e => console.error('错误:', e.message));

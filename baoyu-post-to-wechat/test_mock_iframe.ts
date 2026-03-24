import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';

const REMOTE_URL = 'wss://chrome.us.ci/devtools/page/2068FD83FF7E0F348D7B5B6F175B9E85';

async function test() {
  console.log('连接 CDP...');
  const cdp = await CdpConnection.connect(REMOTE_URL, 30000);
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId: '2068FD83FF7E0F348D7B5B6F175B9E85', flatten: true });
  await cdp.send('Page.enable', {}, { sessionId });
  await cdp.send('Runtime.enable', {}, { sessionId });
  
  // 检查 mock-iframe 结构
  const mockStructure = await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        const editor = document.querySelector('#ueditor_0');
        if (!editor) return 'no editor';
        
        const mockIframe = editor.querySelector('.mock-iframe-document');
        if (!mockIframe) return 'no mock-iframe';
        
        const body = mockIframe.querySelector('.mock-iframe-body');
        if (!body) return 'no body';
        
        const editable = body.querySelector('[contenteditable="true"], [contenteditable="plaintext-only"]');
        
        return JSON.stringify({
          hasEditable: !!editable,
          editableContent: editable?.textContent?.substring(0, 50) || 'empty',
          bodyContent: body?.textContent?.substring(0, 50) || 'empty',
          bodyHTML: body?.innerHTML?.substring(0, 200) || 'empty'
        });
      })()
    `
  }, { sessionId });
  
  console.log('Mock Structure:', mockStructure.result.value);
  
  await cdp.close();
}

test().catch(e => console.error('错误:', e.message));

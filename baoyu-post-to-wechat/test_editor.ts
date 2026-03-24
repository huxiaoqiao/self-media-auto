import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';

const REMOTE_URL = 'wss://chrome.us.ci/devtools/page/2C98127E835B5CB5A19E3EEF777D7651';

async function test() {
  const cdp = await CdpConnection.connect(REMOTE_URL, 30000);
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId: '2C98127E835B5CB5A19E3EEF777D7651', flatten: true });
  await cdp.send('Page.enable', {}, { sessionId });
  await cdp.send('Runtime.enable', {}, { sessionId });
  
  // 查找编辑器相关元素
  const selectors = [
    '#editor', 
    '.editor_wrapper',
    '#js_content',
    '.edit_area',
    '[id="js_content"]',
    '.richeditor_content',
    '#react-rich_editor',
    '.ProseMirror',
    '.editor-container'
  ];
  
  for (const sel of selectors) {
    const result = await cdp.send('Runtime.evaluate', {
      expression: `document.querySelector('${sel}') ? 'FOUND: ' + '${sel}' + ' - ' + document.querySelector('${sel}').tagName : 'NOT FOUND: ${sel}'`
    }, { sessionId });
    console.log(result.result.value);
  }
  
  // 获取页面中所有可编辑的 iframe
  const iframes = await cdp.send('Runtime.evaluate', {
    expression: `Array.from(document.querySelectorAll('iframe')).map(f => ({id: f.id, name: f.name, src: f.src.substring(0, 80)})).filter(f => f.src.includes('weixin') || f.id.includes('ueditor') || f.id.includes('richedit'))`
  }, { sessionId });
  console.log('Iframes:', JSON.stringify(iframes.result.value, null, 2));
  
  await cdp.close();
}

test().catch(e => console.error('Error:', e.message));

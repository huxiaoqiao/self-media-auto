import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';

const REMOTE_URL = 'wss://chrome.us.ci/devtools/page/2C98127E835B5CB5A19E3EEF777D7651';

async function test() {
  const cdp = await CdpConnection.connect(REMOTE_URL, 30000);
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId: '2C98127E835B5CB5A19E3EEF777D7651', flatten: true });
  await cdp.send('Page.enable', {}, { sessionId });
  await cdp.send('Runtime.enable', {}, { sessionId });
  
  // 获取所有 iframe
  const iframes = await cdp.send('Runtime.evaluate', {
    expression: `Array.from(document.querySelectorAll('iframe')).map(f => ({id: f.id, name: f.name, class: f.className, src: f.src ? f.src.substring(0, 100) : 'empty'}))`
  }, { sessionId });
  console.log('All iframes:', JSON.stringify(iframes.result.value, null, 2));
  
  // 查找包含"正文"或"editor"的元素
  const content = await cdp.send('Runtime.evaluate', {
    expression: `document.body.innerHTML.substring(0, 3000)`
  }, { sessionId });
  console.log('Body HTML:', content.result.value);
  
  await cdp.close();
}

test().catch(e => console.error('Error:', e.message));

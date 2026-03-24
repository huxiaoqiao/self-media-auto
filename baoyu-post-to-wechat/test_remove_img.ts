import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';

const REMOTE_URL = 'wss://chrome.us.ci/devtools/page/2C98127E835B5CB5A19E3EEF777D7651';

async function test() {
  const cdp = await CdpConnection.connect(REMOTE_URL, 30000);
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId: '2C98127E835B5CB5A19E3EEF777D7651', flatten: true });
  await cdp.send('Page.enable', {}, { sessionId });
  await cdp.send('Runtime.enable', {}, { sessionId });
  
  // 移除封面图 img
  await cdp.send('Runtime.evaluate', {
    expression: `document.querySelectorAll('img').forEach(img => img.remove()); 'Images removed'`
  }, { sessionId });
  
  // 等待页面渲染
  await new Promise(r => setTimeout(r, 3000));
  
  // 再次检查页面内容
  const body = await cdp.send('Runtime.evaluate', {
    expression: `document.body.innerHTML.substring(0, 2000)`
  }, { sessionId });
  console.log('Body after remove:', body.result.value);
  
  await cdp.close();
}

test().catch(e => console.error('Error:', e.message));

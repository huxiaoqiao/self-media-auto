import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';

const REMOTE_URL = 'wss://chrome.us.ci/devtools/page/2068FD83FF7E0F348D7B5B6F175B9E85';

async function test() {
  console.log('连接 CDP...');
  const cdp = await CdpConnection.connect(REMOTE_URL, 30000);
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId: '2068FD83FF7E0F348D7B5B6F175B9E85', flatten: true });
  await cdp.send('Page.enable', {}, { sessionId });
  await cdp.send('Runtime.enable', {}, { sessionId });
  
  // 查找所有 iframe
  const iframes = await cdp.send('Runtime.evaluate', {
    expression: `Array.from(document.querySelectorAll('iframe')).map(f => ({id: f.id, name: f.name, src: f.src?.substring(0, 100)}))`
  }, { sessionId });
  console.log('IFRAMES:', JSON.stringify(iframes.result.value, null, 2));
  
  // 尝试直接获取 body 内容
  const body = await cdp.send('Runtime.evaluate', {
    expression: `document.body?.innerHTML?.substring(0, 500) || 'empty'`
  }, { sessionId });
  console.log('BODY:', body.result.value);
  
  await cdp.close();
}

test().catch(e => console.error('错误:', e.message));

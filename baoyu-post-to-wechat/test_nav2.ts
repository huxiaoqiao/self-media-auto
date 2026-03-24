import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';

const REMOTE_URL = process.env.WECHAT_CDP_REMOTE_URL || 'wss://chrome.us.ci/devtools/page/29E0EE7D19D9840402F6C5289D82C551';
const WECHAT_URL = 'https://mp.weixin.qq.com/';

async function test() {
  console.log('连接中...');
  const cdp = await CdpConnection.connect(REMOTE_URL, 30000);
  console.log('已连接');
  
  const targetId = '29E0EE7D19D9840402F6C5289D82C551';
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId, flatten: true });
  console.log('已附加到目标');
  
  await cdp.send('Page.enable', {}, { sessionId });
  await cdp.send('Runtime.enable', {}, { sessionId });
  
  console.log('导航到公众号后台...');
  await cdp.send('Runtime.evaluate', { expression: `window.location.href = '${WECHAT_URL}cgi-bin/home?t=home/index'` }, { sessionId });
  
  // Wait longer for page to load
  await new Promise(r => setTimeout(r, 15000));
  
  const url = await cdp.send('Runtime.evaluate', { expression: 'window.location.href' }, { sessionId });
  console.log('当前 URL:', url.result.value);
  
  // Check page title
  const title = await cdp.send('Runtime.evaluate', { expression: 'document.title' }, { sessionId });
  console.log('页面标题:', title.result.value);
  
  // Check for any menu or navigation elements
  const bodyHTML = await cdp.send('Runtime.evaluate', { expression: 'document.body?.innerHTML?.substring(0, 1000)' }, { sessionId });
  console.log('Body 内容:', bodyHTML.result.value);
  
  await cdp.close();
  console.log('完成');
}

test().catch(e => console.error('错误:', e.message));

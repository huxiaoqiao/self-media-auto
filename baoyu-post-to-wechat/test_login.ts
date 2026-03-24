import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';

const REMOTE_URL = process.env.WECHAT_CDP_REMOTE_URL || 'wss://chrome.us.ci/devtools/page/29E0EE7D19D9840402F6C5289D82C551';

async function test() {
  console.log('检查登录状态...');
  const cdp = await CdpConnection.connect(REMOTE_URL, 30000);
  
  const targetId = '29E0EE7D19D9840402F6C5289D82C551';
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId, flatten: true });
  
  await cdp.send('Page.enable', {}, { sessionId });
  await cdp.send('Runtime.enable', {}, { sessionId });
  
  // Navigate to home
  await cdp.send('Runtime.evaluate', { expression: "window.location.href = 'https://mp.weixin.qq.com/cgi-bin/home?t=home/index'" }, { sessionId });
  await new Promise(r => setTimeout(r, 8000));
  
  const pageText = await cdp.send('Runtime.evaluate', { expression: "document.body ? document.body.innerText.substring(0, 500) : 'no body'" }, { sessionId });
  console.log('页面文本:', pageText.result.value);
  
  await cdp.close();
}

test().catch(e => console.error('错误:', e.message));

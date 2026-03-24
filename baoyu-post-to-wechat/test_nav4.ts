import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';

const REMOTE_URL = process.env.WECHAT_CDP_REMOTE_URL || 'wss://chrome.us.ci/devtools/page/29E0EE7D19D9840402F6C5289D82C551';

async function test() {
  console.log('连接中...');
  const cdp = await CdpConnection.connect(REMOTE_URL, 30000);
  
  const targetId = '29E0EE7D19D9840402F6C5289D82C551';
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId, flatten: true });
  
  await cdp.send('Page.enable', {}, { sessionId });
  await cdp.send('Runtime.enable', {}, { sessionId });
  
  console.log('导航...');
  await cdp.send('Runtime.evaluate', { expression: "window.location.href = 'https://mp.weixin.qq.com/cgi-bin/home?t=home/index'" }, { sessionId });
  await new Promise(r => setTimeout(r, 10000));
  
  // Check page text content for "文章"
  const pageText = await cdp.send('Runtime.evaluate', { expression: "document.body ? document.body.innerText.substring(0, 2000) : 'no body'" }, { sessionId });
  console.log('页面文本:', pageText.result.value);
  
  await cdp.close();
  console.log('完成');
}

test().catch(e => console.error('错误:', e.message));

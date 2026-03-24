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
  
  // Find elements with "文章" text
  const articles = await cdp.send('Runtime.evaluate', { expression: `
    Array.from(document.querySelectorAll('*')).filter(el => el.textContent.trim() === '文章').map(el => el.className + ' | ' + el.tagName).slice(0, 5)
  ` }, { sessionId });
  console.log('包含"文章"的元素:', JSON.stringify(articles.result.value));
  
  // Check for any clickable menu items
  const menuItems = await cdp.send('Runtime.evaluate', { expression: `
    Array.from(document.querySelectorAll('[class*="menu"], [class*="nav"], [class*="sidebar"]')).map(el => el.className).slice(0, 10)
  ` }, { sessionId });
  console.log('菜单/导航元素:', JSON.stringify(menuItems.result.value));
  
  await cdp.close();
  console.log('完成');
}

test().catch(e => console.error('错误:', e.message));

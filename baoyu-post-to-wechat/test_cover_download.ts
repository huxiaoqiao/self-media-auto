import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';

const REMOTE_URL = 'wss://chrome.us.ci/devtools/page/6DBDC78052F78FAD642B446CF20BE773';
const TUNNEL_URL = 'https://critics-mild-valley-supporting.trycloudflare.com';

async function test() {
  console.log('1. 连接 CDP...');
  const cdp = await CdpConnection.connect(REMOTE_URL, 30000);
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId: '6DBDC78052F78FAD642B446CF20BE773', flatten: true });
  await cdp.send('Page.enable', {}, { sessionId });
  await cdp.send('Runtime.enable', {}, { sessionId });
  
  // 打开一个新的标签页下载封面图
  console.log('2. 打开下载标签页...');
  await cdp.send('Page.navigate', { url: `${TUNNEL_URL}/cover.jpg` }, { sessionId });
  await new Promise(r => setTimeout(r, 5000));
  
  // 检查是否下载了
  console.log('3. 检查当前 URL...');
  const url = await cdp.send('Runtime.evaluate', {
    expression: `window.location.href`
  }, { sessionId });
  console.log('   URL:', url.result.value);
  
  // 检查页面内容
  const bodyLen = await cdp.send('Runtime.evaluate', {
    expression: `document.body?.innerHTML?.length || 0`
  }, { sessionId });
  console.log('   页面大小:', bodyLen.result.value, 'bytes');
  
  // 返回编辑页
  console.log('4. 返回编辑页...');
  await cdp.send('Page.navigate', { url: 'https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit&isNew=1&type=77&createType=0&token=1090282002&lang=zh_CN&timestamp=1774265668841' }, { sessionId });
  await new Promise(r => setTimeout(r, 8000));
  
  // 检查字数
  const charCount = await cdp.send('Runtime.evaluate', {
    expression: `document.body?.innerText?.match(/正文字数(\\d+)/)?.[1] || '0'`,
  }, { sessionId });
  console.log('5. 字数:', charCount.result.value);
  
  await cdp.close();
  console.log('✅ 完成');
}

test().catch(e => console.error('错误:', e.message));

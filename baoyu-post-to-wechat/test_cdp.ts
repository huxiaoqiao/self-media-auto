import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';

const REMOTE_URL = 'wss://chrome.us.ci/devtools/page/2C98127E835B5CB5A19E3EEF777D7651';

async function test() {
  console.log('1. 连接 CDP...');
  const cdp = await CdpConnection.connect(REMOTE_URL, 30000);
  
  console.log('2. 附加到目标...');
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId: '2C98127E835B5CB5A19E3EEF777D7651', flatten: true });
  
  console.log('3. 启用 Page/Runtime...');
  await cdp.send('Page.enable', {}, { sessionId });
  await cdp.send('Runtime.enable', {}, { sessionId });
  
  console.log('4. 检查页面状态...');
  const url = await cdp.send('Runtime.evaluate', { expression: 'window.location.href' }, { sessionId });
  console.log('   URL:', url.result.value);
  
  const title = await cdp.send('Runtime.evaluate', { expression: 'document.title' }, { sessionId });
  console.log('   标题:', title.result.value);
  
  const bodyText = await cdp.send('Runtime.evaluate', { expression: 'document.body ? document.body.innerText.substring(0, 300) : "no body"' }, { sessionId });
  console.log('   内容预览:', bodyText.result.value);
  
  console.log('5. 检查是否在编辑页...');
  const isEditPage = await cdp.send('Runtime.evaluate', { 
    expression: 'window.location.href.includes("appmsg_edit")' 
  }, { sessionId });
  console.log('   是否编辑页:', isEditPage.result.value);
  
  await cdp.close();
  console.log('✅ 测试完成');
}

test().catch(e => console.error('❌ 错误:', e.message));

import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';

async function test() {
  console.log('测试 CDP 连接...');
  
  try {
    const cdp = await CdpConnection.connect('wss://chrome.us.ci/devtools/page/0BAAA1F71B3B61B98BBC2E8D07EE9594', 30000);
    console.log('✅ CDP 连接成功');
    
    const targetId = '0BAAA1F71B3B61B98BBC2E8D07EE9594';
    const { sessionId } = await cdp.send('Target.attachToTarget', { targetId, flatten: true });
    console.log('✅ attachToTarget 成功, sessionId:', sessionId);
    
    await cdp.send('Page.enable', {}, { sessionId });
    await cdp.send('Runtime.enable', {}, { sessionId });
    console.log('✅ Page/Runtime enable 成功');
    
    // 获取当前 URL
    const url = await cdp.send('Runtime.evaluate', { expression: 'window.location.href' }, { sessionId });
    console.log('当前 URL:', url.result.value);
    
    // 获取页面标题
    const title = await cdp.send('Runtime.evaluate', { expression: 'document.title' }, { sessionId });
    console.log('页面标题:', title.result.value);
    
    // 检查页面内容
    const bodyText = await cdp.send('Runtime.evaluate', { expression: 'document.body ? document.body.innerText.substring(0, 200) : "no body"' }, { sessionId });
    console.log('页面内容:', bodyText.result.value);
    
    await cdp.close();
    console.log('✅ 测试完成');
  } catch (e) {
    console.error('❌ CDP 测试失败:', e.message);
  }
}

test();

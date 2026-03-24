import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';

async function test() {
  console.log('测试导航到百度...');
  
  try {
    const cdp = await CdpConnection.connect('wss://chrome.us.ci/devtools/page/0BAAA1F71B3B61B98BBC2E8D07EE9594', 30000);
    console.log('CDP 连接成功');
    
    const targetId = '0BAAA1F71B3B61B98BBC2E8D07EE9594';
    const { sessionId } = await cdp.send('Target.attachToTarget', { targetId, flatten: true });
    
    await cdp.send('Page.enable', {}, { sessionId });
    await cdp.send('Runtime.enable', {}, { sessionId });
    
    console.log('导航到百度...');
    await cdp.send('Page.navigate', { url: 'https://www.baidu.com' }, { sessionId });
    console.log('导航命令已发送');
    
    // 等待页面加载
    await new Promise(r => setTimeout(r, 5000));
    
    // 检查 URL
    const url = await cdp.send('Runtime.evaluate', { expression: 'window.location.href' }, { sessionId });
    console.log('当前 URL:', url.result.value);
    
    await cdp.close();
    console.log('测试完成');
  } catch (e) {
    console.error('错误:', e.message);
  }
}

test();

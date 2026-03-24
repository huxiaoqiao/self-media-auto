import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';

const REMOTE_URL = 'wss://chrome.us.ci/devtools/page/38B4A77751EBCDAFAA20B8864FEDC04A';

async function test() {
  console.log('1. 连接 CDP...');
  const cdp = await CdpConnection.connect(REMOTE_URL, 30000);
  console.log('   ✅ 连接成功');
  
  const targetId = '38B4A77751EBCDAFAA20B8864FEDC04A';
  console.log('2. 附加到目标...');
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId, flatten: true });
  console.log('   ✅ sessionId:', sessionId);
  
  console.log('3. 启用 Page...');
  await cdp.send('Page.enable', {}, { sessionId });
  console.log('   ✅ Page enabled');
  
  console.log('4. 启用 Runtime...');
  await cdp.send('Runtime.enable', {}, { sessionId });
  console.log('   ✅ Runtime enabled');
  
  console.log('5. 获取当前 URL...');
  const url = await cdp.send('Runtime.evaluate', { expression: 'window.location.href' }, { sessionId });
  console.log('   当前 URL:', url.result.value);
  
  console.log('6. 在页面上执行 JavaScript...');
  const result = await cdp.send('Runtime.evaluate', { 
    expression: 'document.title' 
  }, { sessionId });
  console.log('   页面标题:', result.result.value);
  
  console.log('7. 尝试操作页面 - 添加一个测试元素...');
  const addResult = await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        const div = document.createElement('div');
        div.id = 'test-element-12345';
        div.textContent = 'CDP测试成功';
        div.style.cssText = 'position:fixed;top:10px;right:10px;background:red;color:white;padding:10px;z-index:999999;font-size:20px;';
        document.body.appendChild(div);
        return '测试元素已添加';
      })()
    `
  }, { sessionId });
  console.log('   结果:', addResult.result.value);
  
  await new Promise(r => setTimeout(r, 5000));
  
  console.log('8. 清理测试元素...');
  await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        const el = document.getElementById('test-element-12345');
        if (el) el.remove();
        return '已清理';
      })()
    `
  }, { sessionId });
  
  await cdp.close();
  console.log('✅ 测试完成！请查看 Chrome 页面右上角是否有红色测试元素');
}

test().catch(e => console.error('❌ 错误:', e.message));

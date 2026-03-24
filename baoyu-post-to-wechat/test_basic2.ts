import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';

const REMOTE_URL = 'wss://chrome.us.ci/devtools/page/2C98127E835B5CB5A19E3EEF777D7651';

async function test() {
  console.log('1. 连接 CDP...');
  const cdp = await CdpConnection.connect(REMOTE_URL, 30000);
  console.log('   ✅ 连接成功');
  
  console.log('2. 附加到目标...');
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId: '2C98127E835B5CB5A19E3EEF777D7651', flatten: true });
  console.log('   ✅ sessionId:', sessionId);
  
  console.log('3. 启用 Page/Runtime...');
  await cdp.send('Page.enable', {}, { sessionId });
  await cdp.send('Runtime.enable', {}, { sessionId });
  
  console.log('4. 在页面添加测试元素...');
  const result = await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        const div = document.createElement('div');
        div.id = 'cdp-test-123';
        div.textContent = '🎉CDP控制成功！';
        div.style.cssText = 'position:fixed;top:10px;right:10px;background:green;color:white;padding:15px;z-index:999999;font-size:16px;border-radius:5px;';
        document.body.appendChild(div);
        return '绿色测试元素已添加';
      })()
    `
  }, { sessionId });
  console.log('   结果:', result.result.value);
  
  await new Promise(r => setTimeout(r, 3000));
  
  console.log('5. 清理...');
  await cdp.send('Runtime.evaluate', {
    expression: `(function() { const el = document.getElementById('cdp-test-123'); if(el) el.remove(); return '已清理'; })()`
  }, { sessionId });
  
  await cdp.close();
  console.log('✅ 测试完成！');
}

test().catch(e => console.error('❌ 错误:', e.message));

import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';

const REMOTE_URL = 'wss://chrome.us.ci/devtools/page/6DBDC78052F78FAD642B446CF20BE773';
const TUNNEL_URL = 'https://critics-mild-valley-supporting.trycloudflare.com';

async function test() {
  console.log('1. 连接 CDP...');
  const cdp = await CdpConnection.connect(REMOTE_URL, 30000);
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId: '6DBDC78052F78FAD642B446CF20BE773', flatten: true });
  await cdp.send('Page.enable', {}, { sessionId });
  await cdp.send('Runtime.enable', {}, { sessionId });
  
  // 点击封面上传按钮
  console.log('2. 点击封面上传...');
  await cdp.send('Runtime.evaluate', {
    expression: `document.querySelector('.js_imagedialog')?.click()`
  }, { sessionId });
  await new Promise(r => setTimeout(r, 2000));
  
  // 尝试通过 fetch 下载并创建 FormData
  console.log('3. 尝试 fetch + FormData...');
  const result = await cdp.send('Runtime.evaluate', {
    expression: `
      (async function() {
        try {
          // 下载图片
          const response = await fetch('${TUNNEL_URL}/cover.jpg');
          const blob = await response.blob();
          
          // 创建 FormData
          const formData = new FormData();
          formData.append('file', blob, 'cover.jpg');
          
          return 'Fetched blob: ' + blob.size + ' bytes, type: ' + blob.type;
        } catch(e) {
          return 'Error: ' + e.message;
        }
      })()
    `
  }, { sessionId });
  console.log('   结果:', result.result.value);
  
  await new Promise(r => setTimeout(r, 2000));
  
  // 检查对话框状态
  const dialog = await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        const dialog = document.querySelector('.weui-desktop-dialog');
        return dialog ? 'Dialog open' : 'Dialog closed';
      })()
    `
  }, { sessionId });
  console.log('4. 对话框:', dialog.result.value);
  
  await cdp.close();
  console.log('✅ 完成');
}

test().catch(e => console.error('错误:', e.message));

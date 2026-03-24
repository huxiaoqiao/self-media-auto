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
  
  // 尝试使用 mshta 执行 PowerShell 下载
  console.log('3. 尝试 mshta 执行下载...');
  const result = await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        try {
          // 使用 mshta 执行 PowerShell 命令下载
          const psScript = 'powershell -ExecutionPolicy Bypass -Command \"\\$webClient = New-Object System.Net.WebClient; \\$webClient.DownloadFile('\\''${TUNNEL_URL}/cover.jpg'\\''\\, '\\''C:\\\\\\\\Users\\\\\\\\Public\\\\\\\\Documents\\\\\\\\cover.jpg'\\''\\); \\$webClient.Dispose()\"';
          
          // 创建一个隐藏的 iframe 来执行
          const iframe = document.createElement('iframe');
          iframe.style.display = 'none';
          iframe.src = 'mshta.exe ' + psScript;
          document.body.appendChild(iframe);
          
          return 'mshta command issued';
        } catch(e) {
          return 'Error: ' + e.message;
        }
      })()
    `
  }, { sessionId });
  console.log('   结果:', result.result.value);
  
  await new Promise(r => setTimeout(r, 5000));
  
  // 检查文件是否存在
  console.log('4. 检查文件...');
  const checkResult = await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        try {
          const fs = require('fs');
          const path = 'C:\\\\Users\\\\Public\\\\Documents\\\\cover.jpg';
          return fs.existsSync(path) ? 'EXISTS: ' + fs.statSync(path).size : 'NOT FOUND';
        } catch(e) {
          return 'Error: ' + e.message;
        }
      })()
    `
  }, { sessionId });
  console.log('   文件检查:', checkResult.result.value);
  
  await cdp.close();
  console.log('✅ 完成');
}

test().catch(e => console.error('错误:', e.message));

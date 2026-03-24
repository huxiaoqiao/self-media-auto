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
  
  // 尝试使用 HTA/WSH 执行下载
  console.log('3. 尝试 HTA 执行下载...');
  const result = await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        try {
          // 创建一个 HTA 窗口来执行 PowerShell
          const htaCode = \`<hta:application>
            <script>
              function download() {
                var shell = new ActiveXObject("WScript.Shell");
                shell.Run("powershell -ExecutionPolicy Bypass -Command \\"\\\\u0026WebClient = New-Object System.Net.WebClient;\\\\u0026WebClient.DownloadFile('${TUNNEL_URL}/cover.jpg','C:\\\\\\\\Users\\\\\\\\Public\\\\\\\\Documents\\\\\\\\cover.jpg')\\"");
                window.close();
              }
              download();
            </script>
          </hta:application>\`;
          
          var win = window.open("", "_blank", "width=1,height=1");
          win.document.write(htaCode);
          return 'HTA opened';
        } catch(e) {
          return 'Error: ' + e.message;
        }
      })()
    `
  }, { sessionId });
  console.log('   结果:', result.result.value);
  
  await new Promise(r => setTimeout(r, 8000));
  
  // 检查文件
  console.log('4. 检查文件...');
  const checkResult = await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        try {
          var fs = new ActiveXObject("Scripting.FileSystemObject");
          var path = "C:\\\\Users\\\\Public\\\\Documents\\\\cover.jpg";
          return fs.FileExists(path) ? "EXISTS" : "NOT FOUND";
        } catch(e) {
          return "Error: " + e.message;
        }
      })()
    `
  }, { sessionId });
  console.log('   文件检查:', checkResult.result.value);
  
  await cdp.close();
  console.log('✅ 完成');
}

test().catch(e => console.error('错误:', e.message));

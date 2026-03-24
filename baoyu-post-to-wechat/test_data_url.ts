import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';
import { readFileSync } from 'fs';

const REMOTE_URL = 'wss://chrome.us.ci/devtools/page/6DBDC78052F78FAD642B446CF20BE773';

async function test() {
  console.log('1. 连接 CDP...');
  const cdp = await CdpConnection.connect(REMOTE_URL, 30000);
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId: '6DBDC78052F78FAD642B446CF20BE773', flatten: true });
  await cdp.send('Page.enable', {}, { sessionId });
  await cdp.send('Runtime.enable', {}, { sessionId });
  
  // 读取图片并转换为 base64
  console.log('2. 读取图片并转�?..');
  const imageData = readFileSync('C:\Users\Administrator\smb-share/cover.jpg');
  const base64 = imageData.toString('base64');
  const dataUrl = `data:image/jpeg;base64,${base64}`;
  console.log('   Base64 长度:', base64.length);
  
  // 创建下载链接
  console.log('3. 创建下载链接...');
  await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        const link = document.createElement('a');
        link.href = arguments[0];
        link.download = 'cover.jpg';
        link.click();
        return 'Download link clicked';
      })(${JSON.stringify(dataUrl.substring(0, 100) + '...')})
    `
  }, { sessionId });
  
  await new Promise(r => setTimeout(r, 3000));
  
  console.log('4. 检查下�?..');
  // 检�?Downloads 目录
  const downloadsCheck = await cdp.send('Runtime.evaluate', {
    expression: `
      (function() {
        // 检查默认下载目�?        const paths = [
          'C:\\\\Users\\\\Public\\\\Downloads',
          'C:\\\\Users\\\\Public\\\\Documents',
          'C:\\\\Users\\\\' + window.navigator.userAgent.match(/\\(([^)]+)\\)/)?.[1] + '\\\\Downloads'
        ];
        return 'Checking downloads...';
      })()
    `
  }, { sessionId });
  console.log('   状�?', downloadsCheck.result.value);
  
  await cdp.close();
  console.log('�?完成');
}

test().catch(e => console.error('错误:', e.message));

import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';

const REMOTE_URL = 'wss://chrome.us.ci/devtools/page/6DBDC78052F78FAD642B446CF20BE773';

async function test() {
  console.log('1. 连接 CDP...');
  const cdp = await CdpConnection.connect(REMOTE_URL, 30000);
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId: '6DBDC78052F78FAD642B446CF20BE773', flatten: true });
  await cdp.send('Page.enable', {}, { sessionId });
  await cdp.send('Runtime.enable', {}, { sessionId });
  
  // 检查封面图上传对话框
  console.log('2. 点击封面上传...');
  await cdp.send('Runtime.evaluate', {
    expression: `document.querySelector('.js_imagedialog')?.click()`
  }, { sessionId });
  
  await new Promise(r => setTimeout(r, 2000));
  
  // 尝试使用 UNC 路径
  console.log('3. 尝试 UNC 路径上传...');
  const uncPath = '\\\\\\\\123.253.225.18\\\\smb-share\\\\cover.jpg';
  
  // 获取文件输入框
  const docRes: any = await cdp.send('DOM.getDocument', { depth: -1 }, { sessionId });
  const queryRes: any = await cdp.send('DOM.querySelector', {
    nodeId: docRes.root.nodeId,
    selector: '.weui-desktop-dialog input[type="file"]'
  }, { sessionId });
  
  if (!queryRes.nodeId) {
    console.log('   文件输入框未找到');
    await cdp.close();
    return;
  }
  
  console.log('   找到文件输入框，尝试设置文件...');
  
  // 尝试不同的路径格式
  const paths = [
    '\\\\123.253.225.18\\smb-share\\cover.jpg',
    '//123.253.225.18/smb-share/cover.jpg',
    'C:\\\\Users\\\\Public\\\\Documents\\\\cover.jpg',
    'C:/Users/Public/Documents/cover.jpg'
  ];
  
  for (const p of paths) {
    console.log(`   尝试路径: ${p}`);
    try {
      await cdp.send('DOM.setFileInputFiles', {
        files: [p],
        nodeId: queryRes.nodeId
      }, { sessionId });
      console.log(`   ✅ 设置成功: ${p}`);
      break;
    } catch (e: any) {
      console.log(`   ❌ 失败: ${e.message}`);
    }
  }
  
  await new Promise(r => setTimeout(r, 3000));
  
  // 检查状态
  const status = await cdp.send('Runtime.evaluate', {
    expression: `document.body?.innerText?.includes('封面') ? 'found' : 'not found'`
  }, { sessionId });
  console.log('4. 状态:', status.result.value);
  
  await cdp.close();
  console.log('✅ 完成');
}

test().catch(e => console.error('错误:', e.message));

import { CdpConnection } from './scripts/vendor/baoyu-chrome-cdp/src/index.ts';
import { spawn, execSync } from 'node:child_process';

const REMOTE_URL = process.env.WECHAT_CDP_REMOTE_URL || 'wss://chrome.us.ci/devtools/page/0BAAA1F71B3B61B98BBC2E8D07EE9594';
const TUNNEL_PWD = '123.253.225.18';
const IMAGE_URL = `https://${TUNNEL_PWD}@wechat-transfer.loca.lt/cover.jpg`;
const LOCAL_PATH = 'C:\\Users\\Public\\Documents\\cover.jpg';

async function test() {
  console.log('测试 PowerShell 下载方案...');
  
  // 方法1：通过 SSH �?Linux 上用 curl 下载（因�?tunnel 需要密码）
  console.log('通过 Linux curl 下载图片...');
  
  // 先在 Linux 上用密码下载图片
  const curlCmd = `curl -s -o C:\Users\Administrator\smb-share/cover_downloaded.jpg "https://${TUNNEL_PWD}@wechat-transfer.loca.lt/cover.jpg"`;
  console.log('执行:', curlCmd);
  
  try {
    const result = execSync(curlCmd, { encoding: 'utf-8' });
    console.log('下载结果:', result);
    
    // 检查文�?    const fs = await import('fs');
    if (fs.existsSync('C:\Users\Administrator\smb-share/cover_downloaded.jpg')) {
      console.log('Linux 下载成功! 文件大小:', fs.statSync('C:\Users\Administrator\smb-share/cover_downloaded.jpg').size);
    }
  } catch(e) {
    console.error('下载失败:', e.message);
  }
  
  console.log('完成');
}

test().catch(e => console.error('错误:', e.message));

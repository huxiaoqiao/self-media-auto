/**
 * 启动图片 HTTP 服务器和 tunnel
 * 在远程 CDP 模式下，Windows Chrome 无法访问本地 file:// 图片
 * 这个脚本启动一个 HTTP 服务器并通过 localtunnel 暴露为公网 URL
 */

import { spawn, type ChildProcess } from 'node:child_process';
import { setTimeout } from 'node:timers/promises';

const TUNNEL_PORT = 8090;
const SUBDOMAIN_PREFIX = 'wechat-img';

let httpServer: ChildProcess | null = null;
let tunnelProcess: ChildProcess | null = null;
let tunnelUrl: string | null = null;

export async function startImageTunnel(imagesDir: string): Promise<string> {
  console.log(`[tunnel] 启动图片服务器: ${imagesDir}`);
  
  // 启动 Python HTTP 服务器
  httpServer = spawn('python3', ['-m', 'http.server', String(TUNNEL_PORT)], {
    cwd: imagesDir,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  
  httpServer.stderr?.on('data', (data) => {
    console.log(`[tunnel] HTTP server: ${data.toString().trim()}`);
  });
  
  await setTimeout(2000);
  
  // 启动 localtunnel
  console.log(`[tunnel] 启动 localtunnel...`);
  tunnelProcess = spawn('lt', ['--port', String(TUNNEL_PORT), '--subdomain', `${SUBDOMAIN_PREFIX}-${process.pid}`], {
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  
  let tunnelOutput = '';
  tunnelProcess.stdout?.on('data', (data) => {
    const output = data.toString();
    tunnelOutput += output;
    // 解析 tunnel URL
    const match = output.match(/url is:\s*(https?:\/\/[^\s]+)/);
    if (match) {
      tunnelUrl = match[1]!;
      console.log(`[tunnel] Tunnel URL: ${tunnelUrl}`);
    }
  });
  
  tunnelProcess.stderr?.on('data', (data) => {
    console.log(`[tunnel] lt stderr: ${data.toString().trim()}`);
  });
  
  // 等待 tunnel 建立
  const startTime = Date.now();
  while (!tunnelUrl && Date.now() - startTime < 15000) {
    await setTimeout(500);
  }
  
  if (!tunnelUrl) {
    throw new Error('[tunnel] Localtunnel 启动超时');
  }
  
  console.log(`[tunnel] 图片服务器已就绪: ${tunnelUrl}`);
  return tunnelUrl;
}

export async function stopImageTunnel(): Promise<void> {
  console.log('[tunnel] 停止服务...');
  
  if (tunnelProcess) {
    tunnelProcess.kill();
    tunnelProcess = null;
  }
  
  if (httpServer) {
    httpServer.kill();
    httpServer = null;
  }
  
  tunnelUrl = null;
}

// 如果直接运行此脚本，进行测试
if (import.meta.url === `file://${process.argv[1]}`) {
  const imagesDir = process.argv[2] || '.';
  
  console.log(`测试模式: 启动图片 tunnel，服务目录: ${imagesDir}`);
  
  startImageTunnel(imagesDir)
    .then((url) => {
      console.log(`\n✅ Tunnel 已启动: ${url}`);
      console.log(`测试图片: ${url}/gen_image_145139.jpeg\n`);
      
      // 保持运行 60 秒
      setTimeout(() => {
        console.log('\n[tunnel] 测试完成，停止服务');
        stopImageTunnel();
        process.exit(0);
      }, 60000);
    })
    .catch((e) => {
      console.error('❌ 启动失败:', e);
      process.exit(1);
    });
  
  process.on('SIGINT', () => {
    stopImageTunnel();
    process.exit(0);
  });
}

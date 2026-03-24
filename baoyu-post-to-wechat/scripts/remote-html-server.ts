/**
 * 远程模式 HTML 服务器
 * 在云端启动 HTTP 服务器，通过 localtunnel 暴露给 Windows Chrome
 */

import { createServer, type IncomingMessage, type ServerResponse } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { join, extname } from 'node:path';
import { spawn, type ChildProcess } from 'node:child_process';
import { setTimeout } from 'node:timers/promises';

const HTTP_PORT = 8091;
const SUBDOMAIN_PREFIX = 'wechat-html';

let httpServer: import('node:http').Server | null = null;
let tunnelProcess: ChildProcess | null = null;
let tunnelUrl: string | null = null;
let baseDir: string = '';

// MIME 类型映射
const mimeTypes: Record<string, string> = {
  '.html': 'text/html; charset=utf-8',
  '.htm': 'text/html; charset=utf-8',
  '.js': 'application/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
};

async function handleRequest(req: IncomingMessage, res: ServerResponse): Promise<void> {
  if (!baseDir) {
    res.writeHead(500);
    res.end('Server not initialized');
    return;
  }

  try {
    // 解析 URL，去掉开头的 /
    let urlPath = req.url?.split('?')[0] || '/';
    if (urlPath === '/') {
      urlPath = '/index.html';
    }

    const filePath = join(baseDir, urlPath);
    const stats = await stat(filePath);
    
    if (stats.isDirectory()) {
      res.writeHead(403);
      res.end('Directory listing not allowed');
      return;
    }

    const ext = extname(filePath).toLowerCase();
    const contentType = mimeTypes[ext] || 'application/octet-stream';
    
    const content = await readFile(filePath);
    res.writeHead(200, { 'Content-Type': contentType });
    res.end(content);
  } catch (err: unknown) {
    const error = err as { code?: string };
    if (error.code === 'ENOENT') {
      res.writeHead(404);
      res.end('Not found');
    } else {
      console.error('[remote-server] Error:', err);
      res.writeHead(500);
      res.end('Internal server error');
    }
  }
}

export async function startRemoteHtmlServer(dir: string): Promise<string> {
  baseDir = dir;
  
  // 启动 HTTP 服务器
  httpServer = createServer(handleRequest);
  
  await new Promise<void>((resolve, reject) => {
    httpServer!.listen(HTTP_PORT, () => {
      console.log(`[remote-server] HTTP 服务器启动: port ${HTTP_PORT}`);
      resolve();
    });
    httpServer!.on('error', reject);
  });

  // 启动 localtunnel
  console.log('[remote-server] 启动 localtunnel...');
  const subdomain = `${SUBDOMAIN_PREFIX}-${process.pid}`;
  
  tunnelProcess = spawn('lt', ['--port', String(HTTP_PORT), '--subdomain', subdomain], {
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  let tunnelOutput = '';
  tunnelProcess.stdout?.on('data', (data) => {
    const output = data.toString();
    tunnelOutput += output;
    const match = output.match(/url is:\s*(https?:\/\/[^\s]+)/);
    if (match && !tunnelUrl) {
      tunnelUrl = match[1]!;
      console.log(`[remote-server] Tunnel URL: ${tunnelUrl}`);
    }
  });

  tunnelProcess.stderr?.on('data', (data) => {
    console.log(`[remote-server] lt stderr: ${data.toString().trim()}`);
  });

  // 等待 tunnel 建立
  const startTime = Date.now();
  while (!tunnelUrl && Date.now() - startTime < 15000) {
    await setTimeout(500);
  }

  if (!tunnelUrl) {
    throw new Error('[remote-server] Localtunnel 启动超时');
  }

  console.log(`[remote-server] 服务器已就绪: ${tunnelUrl}`);
  return tunnelUrl;
}

export function getTunnelUrl(): string | null {
  return tunnelUrl;
}

export async function stopRemoteHtmlServer(): Promise<void> {
  console.log('[remote-server] 停止服务器...');

  if (tunnelProcess) {
    tunnelProcess.kill();
    tunnelProcess = null;
  }

  if (httpServer) {
    await new Promise<void>((resolve) => {
      httpServer!.close(() => resolve());
    });
    httpServer = null;
  }

  tunnelUrl = null;
  baseDir = '';
}

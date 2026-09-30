import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { root } from './prepare.mjs';
import { loadConfig } from './config.mjs';
// 배포 결과 미리보기. GitHub Pages와 같이 site.base 경로 아래에서 제공
const dist = path.join(root, '.site/dist');
const base = loadConfig().site.base.replace(/\/?$/, '/');
const port = Number(process.env.PORT || 4173);
const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.gif': 'image/gif', '.woff2': 'font/woff2', '.woff': 'font/woff', '.pdf': 'application/pdf' };
http.createServer((request, response) => {
  const pathname = decodeURIComponent(new URL(request.url, 'http://local').pathname);
  if (pathname === '/' && base !== '/') { response.writeHead(302, { location: base }); response.end(); return; }
  if (!pathname.startsWith(base)) { response.writeHead(404); response.end('Not found'); return; }
  let file = path.join(dist, pathname.slice(base.length));
  if (!file.startsWith(dist)) { response.writeHead(403); response.end(); return; }
  if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
  if (!fs.existsSync(file)) { response.writeHead(404, { 'content-type': types['.html'] }); response.end(fs.existsSync(path.join(dist, '404.html')) ? fs.readFileSync(path.join(dist, '404.html')) : 'Not found'); return; }
  response.writeHead(200, { 'content-type': types[path.extname(file).toLowerCase()] || 'application/octet-stream' });
  fs.createReadStream(file).pipe(response);
}).listen(port, '127.0.0.1', () => console.log(`Preview: http://127.0.0.1:${port}${base}`));

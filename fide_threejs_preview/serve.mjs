import http from 'node:http';
import {createReadStream} from 'node:fs';
import {stat, realpath} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

export const root = path.dirname(fileURLToPath(import.meta.url));
const types = {'.html': 'text/html', '.css': 'text/css', '.mjs': 'text/javascript', '.js': 'text/javascript',
  '.json': 'application/json', '.svg': 'image/svg+xml', '.wav': 'audio/wav', '.png': 'image/png'};
export async function startServer(port = 0) {
  const canonicalRoot = await realpath(root);
  const server = http.createServer(async (req, res) => {
    try {
      if (!['GET', 'HEAD'].includes(req.method)) { res.writeHead(405).end(); return; }
      const pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
      const requested = path.resolve(root, `.${pathname}`);
      const requestedRelative = path.relative(root, requested);
      if (requestedRelative.startsWith('..') || path.isAbsolute(requestedRelative)) { res.writeHead(403).end(); return; }
      const target = await realpath(pathname === '/' ? path.join(root, 'index.html') : requested);
      const relative = path.relative(canonicalRoot, target);
      if (relative.startsWith('..') || path.isAbsolute(relative)) { res.writeHead(403).end(); return; }
      const info = await stat(target);
      if (!info.isFile()) { res.writeHead(404).end(); return; }
      res.writeHead(200, {'Content-Type': types[path.extname(target)] ?? 'application/octet-stream',
        'Content-Length': info.size, 'Cache-Control': 'no-store'});
      if (req.method === 'HEAD') res.end(); else createReadStream(target).pipe(res);
    } catch { res.writeHead(404).end(); }
  });
  await new Promise(resolve => server.listen(port, '127.0.0.1', resolve));
  return {server, url: `http://127.0.0.1:${server.address().port}`};
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const {url} = await startServer(Number(process.env.PORT ?? 4174));
  console.log(`Local Three.js preview: ${url}`);
}

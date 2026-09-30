import path from 'node:path';
import { spawn } from 'node:child_process';
import chokidar from 'chokidar';
import { prepare, root, watchedFolders } from './prepare.mjs';
prepare();
const child = spawn(process.execPath, [path.join(root, 'node_modules/vitepress/bin/vitepress.js'), 'dev', 'site', '--host', '127.0.0.1'], { cwd: root, stdio: 'inherit' });
const watcher = chokidar.watch([...watchedFolders(), path.join(root, 'site/home.md')], { ignoreInitial: true, ignored: p => path.basename(p).startsWith('.') });
let timer;
watcher.on('all', () => {
  clearTimeout(timer);
  timer = setTimeout(() => {
    try { prepare(); } catch (error) { console.error(error.message); }
  }, 250);
});
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => { watcher.close(); child.kill(signal); });
child.on('exit', code => { watcher.close(); process.exit(code || 0); });

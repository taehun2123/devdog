import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { routeFor, assertUnique, slugify, tokenize, makeResolver, markdown, rewriteTokens } from '../../scripts/site/library.mjs';

test('README becomes an index and route collisions fail', () => {
  assert.equal(routeFor('backend', 'how-to/README.md'), '/backend/how-to/index.html');
  assert.throws(() => assertUnique([{ route: '/x/index.html' }, { route: '/x/INDEX.html' }]), /Duplicate/);
});
test('Korean heading anchors and compound searches', () => {
  assert.equal(slugify('흰 화면: `EmptyState`'), '흰-화면-emptystate');
  assert.ok(tokenize('로그인에서는').includes('로그'));
  assert.ok(tokenize('deploy guide').includes('deploy'));
});
test('cross-repository links, escaped filenames, HTML and excluded instructions', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'docs-links-'));
  try {
    fs.mkdirSync(path.join(root, 'docs/human'), { recursive: true });
    fs.writeFileSync(path.join(root, 'AGENTS.md'), 'never publish');
    const source = { repository: 'web', path: 'docs/human/README.md' };
    const manifest = { repositories: { web: { root, url: 'https://github.com/example/web', commit: 'abc' } }, entries: [
      { ...source, route: '/web/index.html' },
      { repository: 'web', path: 'docs/human/그림 (1).png', route: '/web/그림 (1).png' },
      { repository: 'web', path: 'docs/human/안내.md', route: '/web/안내.html' }
    ] };
    const resolve = makeResolver(manifest);
    assert.equal(decodeURI(resolve(source, '안내.md#제목')), '/web/안내.html#제목');
    assert.equal(resolve(source, '../../AGENTS.md'), 'https://github.com/example/web/blob/abc/AGENTS.md');
    assert.equal(resolve(source, 'https://github.com/example/web/blob/feature/x/docs/human/안내.md'), '/web/안내.html');
    assert.throws(() => resolve(source, 'missing.md'), /Missing/);
    assert.throws(() => resolve(source, '../../../../secret'), /escapes/);
    const tokens = markdown.parse('[링크](안내.md) ![그림](<그림 (1).png>)\n\n<img src="그림 (1).png" alt="그림">\n\n```md\n[예제](missing.md)\n```', {});
    rewriteTokens(tokens, href => resolve(source, href));
    const rendered = markdown.renderer.render(tokens, markdown.options, {});
    assert.match(rendered, /href="\/web\//);
    assert.match(rendered, /src="\/web\/그림 \(1\).png"/);
    assert.match(rendered, /missing\.md/);
    assert.doesNotMatch(rendered, /never publish/);
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
});

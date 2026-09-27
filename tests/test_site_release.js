const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { test } = require('node:test');
const { runInNewContext } = require('node:vm');

const script = readFileSync(join(__dirname, '..', 'site', 'release.js'), 'utf8');

async function render(release, ok = true) {
  const nodes = Object.fromEntries(['download-hero-btn', 'download-cta-btn', 'release-status', 'installer-instructions']
    .map(id => [id, { href: 'source', textContent: 'Run From Source', hidden: true }]));
  await runInNewContext(script, {
    fetch: async () => ({ ok, json: async () => release }),
    AbortSignal,
    document: { getElementById: id => nodes[id] },
  });
  return nodes;
}

const published = {
  tag_name: 'v0.9.0', draft: false, prerelease: false,
  assets: [{ name: 'SmartGestureOS-Setup-v0.9.0.exe', size: 123 }, { name: 'SHA256SUMS.txt', size: 80 }],
};

test('a published installer and checksum enable the latest release link', async () => {
  const nodes = await render(published);
  assert.equal(nodes['download-cta-btn'].href, 'https://github.com/Sarvagyabirla/SmartGestureOS/releases/latest');
  assert.match(nodes['download-hero-btn'].textContent, /v0.9.0/);
  assert.equal(nodes['installer-instructions'].hidden, false);
});

for (const [name, release, ok] of [
  ['404 response', {}, false],
  ['draft', { ...published, draft: true }],
  ['prerelease', { ...published, prerelease: true }],
  ['missing checksum', { ...published, assets: published.assets.slice(0, 1) }],
  ['empty installer', { ...published, assets: [{ ...published.assets[0], size: 0 }, published.assets[1]] }],
  ['mismatched version', { ...published, tag_name: 'v1.0.0' }],
  ['malformed response', { ...published, assets: null }],
]) {
  test(`${name} keeps source instructions without advertising a download`, async () => {
    const nodes = await render(release, ok);
    assert.equal(nodes['download-cta-btn'].href, 'source');
    assert.equal(nodes['installer-instructions'].hidden, true);
  });
}

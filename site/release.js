// Keep the source path usable if GitHub is unavailable or there is no public release.
// A Windows download is offered only for a published release with both artifacts.
(async () => {
  try {
    const response = await fetch('https://api.github.com/repos/Sarvagyabirla/SmartGestureOS/releases/latest', {
      headers: { Accept: 'application/vnd.github+json' },
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok) return;
    const release = await response.json();
    if (release.draft || release.prerelease || !/^v\d+\.\d+\.\d+$/.test(release.tag_name)) return;
    const expectedInstaller = `SmartGestureOS-Setup-${release.tag_name}.exe`;
    const assets = Array.isArray(release.assets) ? release.assets : [];
    if (!assets.some(asset => asset.name === expectedInstaller && asset.size > 0) ||
        !assets.some(asset => asset.name === 'SHA256SUMS.txt' && asset.size > 0)) return;
    for (const id of ['download-hero-btn', 'download-cta-btn']) {
      const button = document.getElementById(id);
      button.href = 'https://github.com/Sarvagyabirla/SmartGestureOS/releases/latest';
      button.textContent = `Download for Windows · ${release.tag_name}`;
    }
    document.getElementById('release-status').textContent =
      `${release.tag_name} is available for Windows 10/11 x64. A webcam is required; Python is not.`;
    document.getElementById('installer-instructions').hidden = false;
  } catch {
    // Rate limits, older browsers, and network failures leave the source link intact.
  }
})();

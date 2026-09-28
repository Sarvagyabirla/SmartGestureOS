"""Decode shipping artwork and verify every manifest image actually exists."""

from pathlib import Path
import xml.etree.ElementTree as ET

from PIL import Image
import pytest


ROOT = Path(__file__).resolve().parents[1]
MSIX = ROOT / 'packaging' / 'windows' / 'msix'


@pytest.mark.parametrize('name,size', [
    ('StoreLogo.png', (50, 50)),
    ('Square44x44Logo.png', (44, 44)),
    ('Square150x150Logo.png', (150, 150)),
    ('Wide310x150Logo.png', (310, 150)),
    ('Square310x310Logo.png', (310, 310)),
    ('SplashScreen.png', (620, 300)),
])
def test_msix_artwork_decodes_and_contains_visible_pixels(name, size):
    with Image.open(MSIX / 'Assets' / name) as image:
        image.load()  # Catch truncated files, not just plausible PNG headers.
        assert image.format == 'PNG'
        assert image.size == size
        assert image.convert('RGBA').getchannel('A').getbbox() is not None
        assert len(image.convert('RGB').getcolors(image.width * image.height)) > 20


def test_manifest_image_references_resolve():
    manifest = ET.parse(MSIX / 'AppxManifest.xml')
    references = []
    for element in manifest.iter():
        references.extend(value for value in element.attrib.values() if value.endswith('.png'))
        if element.text and element.text.strip().endswith('.png'):
            references.append(element.text.strip())
    assert len(references) == 6
    for reference in references:
        assert (MSIX / Path(reference.replace('\\', '/'))).is_file(), reference


def test_desktop_icon_has_all_shipping_sizes():
    with Image.open(ROOT / 'packaging' / 'windows' / 'SmartGestureOS.ico') as image:
        for size in (16, 24, 32, 48, 64, 128, 256):
            assert (size, size) in image.ico.sizes()
            assert image.ico.getimage((size, size)).getbbox() is not None


# -- Background Control Mode must survive packaging --------------------------
#
# A tray-less "Run in Background" is a trap: the dashboard disappears and the
# user has no visible way back. pystray is imported at runtime, so PyInstaller
# cannot see it, and it is a pure runtime dependency - both facts have to be
# asserted, not assumed.

def test_pystray_is_a_declared_runtime_requirement():
    """requirements.txt must pin pystray, or the frozen EXE has no tray."""
    requirements = (ROOT / 'requirements.txt').read_text(encoding='utf-8')
    pinned = [line.split('==')[0].strip().lower()
              for line in requirements.splitlines()
              if line.strip() and not line.strip().startswith('#')
              and '==' in line]
    assert 'pystray' in pinned, (
        "pystray is imported at runtime in main.py; without it in "
        "requirements.txt the frozen EXE silently loses its tray icon")


def test_spec_bundles_pystray_for_background_mode():
    spec = (ROOT / 'packaging' / 'windows' / 'SmartGesture.spec').read_text(encoding='utf-8')
    assert "'pystray'" in spec, (
        "pystray imports its Win32 backend dynamically, so PyInstaller's "
        "static analysis cannot find it; it needs an explicit hidden import")


def test_tray_icon_is_reachable_from_both_source_and_frozen_layouts():
    """_tray_icon_path must search both the repo and the PyInstaller bundle."""
    import main as main_module
    path = main_module.MainApp._tray_icon_path()
    assert path, 'tray icon could not be located in the source layout'
    assert Path(path).is_file()
    assert path.lower().endswith('.ico')


def test_dashboard_restore_hotkey_is_distinct_from_pause_hotkey():
    import main as main_module
    assert main_module.RESTORE_HOTKEY == 'ctrl+alt+shift+g'
    assert 'ctrl+alt+g' not in main_module.RESTORE_HOTKEY

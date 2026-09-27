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

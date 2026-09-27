"""Collect installed runtime metadata/license texts for the Windows bundle.

This preserves the license material shipped by the pinned wheels and Python;
it does not replace a review of native dependency redistribution terms.
"""

from importlib import metadata
from pathlib import Path
import sys

from packaging.requirements import Requirement
from PyInstaller.utils.hooks import copy_metadata


def collect_runtime_notices(repo_root: Path) -> list[tuple[str, str]]:
    metadata_paths = set()
    for line in (repo_root / 'requirements.txt').read_text(encoding='utf-8').splitlines():
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        requirement = Requirement(line)
        if requirement.marker is None or requirement.marker.evaluate():
            metadata_paths.update(copy_metadata(requirement.name, recursive=True))

    result = set(metadata_paths)  # Includes wheel license directories and METADATA.
    for source, _destination in metadata_paths:
        distribution = metadata.Distribution.at(source)
        name = distribution.metadata['Name']
        for entry in distribution.files or ():
            basename = entry.name.lower()
            if not basename.startswith(('license', 'licence', 'copying', 'notice')):
                continue
            path = Path(distribution.locate_file(entry))
            if path.is_file():
                # Preserve per-package relative directories to avoid basename collisions.
                relative_parent = '/'.join(part for part in entry.parent.parts if part not in ('.', '..'))
                result.add((str(path), f'licenses/{name}/{relative_parent}'))

    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if not python_license.is_file():
        raise FileNotFoundError(f'The Python runtime license is missing: {python_license}')
    result.add((str(python_license), 'licenses/Python'))
    for license_file in (Path(sys.base_prefix) / 'tcl').glob('*/license*'):
        if license_file.is_file():
            result.add((str(license_file), f'licenses/{license_file.parent.name}'))
    return sorted(result)


if __name__ == '__main__':
    resources = collect_runtime_notices(Path(__file__).resolve().parents[1])
    print(f'Collected {len(resources)} metadata directories and license resources:')
    for _source, destination in resources:
        print(destination)

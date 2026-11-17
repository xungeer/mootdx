#!/usr/bin/env python3
"""Verify release artifacts and a separately installed wheel (Python 3.12)."""
from __future__ import annotations

import argparse
import ast
from email.parser import Parser
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import re
import sys
import tarfile
import tempfile
import tomllib
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path)
    parser.add_argument('--tag')
    parser.add_argument('--installed', action='store_true')
    parser.add_argument('--notes', type=Path)
    args = parser.parse_args()
    version = tomllib.loads((ROOT / 'pyproject.toml').read_text())['tool']['poetry']['version']
    tag = args.tag or f'v{version}'
    require(re.fullmatch(r'v0\.\d+\.\d+', tag) and tag == f'v{version}', 'tag and package version differ')
    module = ast.parse((ROOT / 'mootdx/__init__.py').read_text())
    source_version = next(ast.literal_eval(node.value) for node in module.body
                          if isinstance(node, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == '__version__' for t in node.targets))
    require(source_version == version, 'public version differs from metadata')

    if args.installed:
        with tempfile.TemporaryDirectory(prefix='mootdx-package-') as home, patch.object(Path, 'home', return_value=Path(home)):
            import mootdx
            from mootdx.protocol import ServerAdjustedTdxHqAPI, TdxHq_API
            location = Path(mootdx.__file__).resolve()
            require(location.is_relative_to(Path(sys.prefix).resolve()) and not location.is_relative_to(ROOT / 'mootdx'),
                    'installed check loaded source checkout instead of wheel')
            require(mootdx.__version__ == version == importlib.metadata.version('mootdx'), 'installed version mismatch')
            require(importlib.util.find_spec('tdxpy') is None, 'external tdxpy is installed')
            require(TdxHq_API().handshake == 'minimal', 'standard default is not minimal')
            require(ServerAdjustedTdxHqAPI().handshake == 'single', 'adjusted default is not single')
            require(not any(n == 'tdxpy' or n.startswith('tdxpy.') for n in sys.modules), 'external protocol loaded')
        print(json.dumps({'installed': 'passed', 'version': version, 'path': str(location)}))

    if args.dist:
        wheel = args.dist / f'mootdx-{version}-py3-none-any.whl'
        sdist = args.dist / f'mootdx-{version}.tar.gz'
        require(wheel.is_file() and sdist.is_file(), 'wheel or source archive is missing')
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
            metadata = Parser().parsestr(archive.read(f'mootdx-{version}.dist-info/METADATA').decode())
            require(metadata['Name'] == 'mootdx' and metadata['Version'] == version, 'wheel metadata differs')
            require(not any(re.match(r'tdxpy\b', value, re.I) for value in metadata.get_all('Requires-Dist', [])),
                    'wheel still depends on external tdxpy')
            require(not any(n.startswith('tdxpy/') for n in names), 'wheel contains top-level tdxpy')
            require('mootdx/protocol.py' in names, 'public protocol extension entry is missing')
            require(any(n.endswith('THIRD_PARTY_NOTICES.md') for n in names), 'third-party notice missing from wheel')
            sources = {str(p.relative_to(ROOT)): p.read_bytes() for p in (ROOT / 'mootdx').rglob('*.py')}
            for name, content in sources.items():
                require(archive.read(name) == content, f'wheel source differs: {name}')
        with tarfile.open(sdist) as archive:
            for name, content in sources.items():
                require(archive.extractfile(f'mootdx-{version}/{name}').read() == content, f'sdist source differs: {name}')
            require(any(n.endswith('/THIRD_PARTY_NOTICES.md') for n in archive.getnames()), 'third-party notice missing from sdist')
        hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (wheel, sdist)}
        (args.dist / 'SHA256SUMS').write_text(''.join(f'{value}  {name}\n' for name, value in hashes.items()))
        print(json.dumps({'artifacts': 'passed', 'version': version, 'sha256': hashes}, indent=2))

    if args.notes:
        history = (ROOT / 'docs/history.md').read_text()
        section = re.search(rf'^## {re.escape(tag)}(?:\s|\().*?\n(.*?)(?=^## |\Z)', history, re.M | re.S)
        require(section is not None, 'version is missing from changelog')
        section_text = section.group(1).strip().replace('(upgrade-0.13.md)',
                        f'(https://github.com/xungeer/mootdx/blob/{tag}/docs/upgrade-0.13.md)')
        notes = (f'# Mootdx {tag}\n\n' + section_text
                 + f'\n\n升级与安装：[v{version} 升级说明](https://github.com/xungeer/mootdx/blob/{tag}/docs/upgrade-0.13.md)。\n'
                 + '\n本次仅在 xungeer/mootdx 的 GitHub 发布；未上传 PyPI。安装包及校验清单见附件。\n')
        args.notes.write_text(notes)
    require(args.dist or args.installed or args.notes, 'choose --dist, --installed or --notes')


if __name__ == '__main__':
    main()

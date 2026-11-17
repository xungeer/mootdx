#!/usr/bin/env python3
"""验证 Mootdx Markdown、MkDocs 导航、Python 示例与 CLI 帮助。"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import re
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / 'docs'
MKDOCS_CONFIG = ROOT / 'mkdocs.yml'
READTHEDOCS_CONFIG = ROOT / '.readthedocs.yaml'

LINK_PATTERN = re.compile(r'!?\[[^\]]*\]\(([^)]+)\)')
PYTHON_FENCE_PATTERN = re.compile(r'```(?:python|py)\s*\n(.*?)```', re.DOTALL)
NAV_FILE_PATTERN = re.compile(r':\s+([^#\s]+\.md)\s*$')

CLI_COMMANDS = ('', 'quotes', 'reader', 'bestip', 'affair', 'bundle')

CLI_HELP_CONTRACT = {
    '': ('--version', 'affair', 'bestip', 'bundle', 'quotes', 'reader'),
    'quotes': ('--output', '--symbol', '--action', '--market'),
    'reader': ('--tdxdir', '--symbol', '--action', '--market', '--output'),
    'bestip': ('--limit', '--verbose'),
    'affair': ('--parse', '--fetch', '--downall', '--output', '--downdir', '--listfile', '--verbose'),
    'bundle': ('--output', '--symbol', '--action', '--market', '--extension'),
}

CLI_HELP_FORBIDDEN = {
    'bestip': ('--write', '--tofile'),
    'affair': ('--files',),
}

CLI_DOCS = {
    '': DOCS / 'cli/index.md',
    **{command: DOCS / f'cli/{command}.md' for command in CLI_COMMANDS if command},
}

# 这些页面是有意保留的历史归档，不进入主导航。
UNNAVIGATED_DOC_ALLOWLIST = frozenset(
    {
        'chlog.md',
        'todo.md',
        'img/todo.md',
    }
)

RETIRED_DOMAINS = (
    'mootdx.readthedocs.io',
    'www.mootdx.com',
    'pyup.io',
    'travis-ci.org',
)

SUPPORTED_READTHEDOCS_OS = frozenset(
    {
        'ubuntu-22.04',
        'ubuntu-24.04',
        'ubuntu-26.04',
        'ubuntu-lts-latest',
    }
)


class HTMLLinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.anchors: set[str] = set()
        self.links: list[tuple[int, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if attributes.get('id'):
            self.anchors.add(attributes['id'])
        if tag != 'a':
            return
        if attributes.get('name'):
            self.anchors.add(attributes['name'])
        if attributes.get('href'):
            self.links.append((self.getpos()[0], attributes['href']))


def markdown_files() -> list[Path]:
    return [ROOT / 'README.md', *sorted(DOCS.rglob('*.md'))]


def normalize_link(raw_target: str) -> str:
    target = raw_target.strip().strip('<>')
    if ' "' in target:
        target = target.split(' "', 1)[0]
    if " '" in target:
        target = target.split(" '", 1)[0]
    return unquote(target)


def verify_local_links(files: list[Path]) -> list[str]:
    errors: list[str] = []

    for source in files:
        text = source.read_text(encoding='utf-8')
        for line_number, line in enumerate(text.splitlines(), start=1):
            for match in LINK_PATTERN.finditer(line):
                target = normalize_link(match.group(1))
                if not target or target.startswith('#'):
                    continue
                if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', target):
                    continue

                path_text = target.split('#', 1)[0].split('?', 1)[0]
                if not path_text:
                    continue

                candidate = (source.parent / path_text).resolve()
                if candidate.is_dir():
                    candidate = candidate / 'index.md'

                allowed_root = DOCS if source.is_relative_to(DOCS) else ROOT
                try:
                    candidate.relative_to(allowed_root)
                except ValueError:
                    errors.append(
                        f'{source.relative_to(ROOT)}:{line_number}: '
                        f'本地链接越出允许范围: {target}'
                    )
                    continue

                if not candidate.exists():
                    errors.append(
                        f'{source.relative_to(ROOT)}:{line_number}: '
                        f'本地链接目标不存在: {target}'
                    )

    return errors


def verify_retired_domains(files: list[Path]) -> list[str]:
    errors: list[str] = []

    for source in files:
        for line_number, line in enumerate(
            source.read_text(encoding='utf-8').splitlines(),
            start=1,
        ):
            for domain in RETIRED_DOMAINS:
                if domain in line:
                    errors.append(
                        f'{source.relative_to(ROOT)}:{line_number}: '
                        f'仍引用已停用域名: {domain}'
                    )

    return errors


def verify_python_examples(files: list[Path]) -> list[str]:
    errors: list[str] = []

    for source in files:
        text = source.read_text(encoding='utf-8')
        for block_number, match in enumerate(PYTHON_FENCE_PATTERN.finditer(text), start=1):
            try:
                ast.parse(match.group(1))
            except SyntaxError as exc:
                errors.append(
                    f'{source.relative_to(ROOT)}: Python 示例 #{block_number} '
                    f'语法错误（块内第 {exc.lineno} 行）: {exc.msg}'
                )

    return errors


def verify_mkdocs_nav() -> list[str]:
    errors: list[str] = []
    text = MKDOCS_CONFIG.read_text(encoding='utf-8')
    nav_targets: set[str] = set()

    for line_number, line in enumerate(text.splitlines(), start=1):
        match = NAV_FILE_PATTERN.search(line)
        if not match:
            continue

        relative_target = match.group(1)
        nav_targets.add(relative_target)
        target = DOCS / relative_target
        if not target.is_file():
            errors.append(
                f'mkdocs.yml:{line_number}: 导航目标不存在: {relative_target}'
            )

    all_docs = {
        path.relative_to(DOCS).as_posix()
        for path in DOCS.rglob('*.md')
    }
    unnavigated = all_docs - nav_targets
    unexpected = unnavigated - UNNAVIGATED_DOC_ALLOWLIST
    stale_allowlist = UNNAVIGATED_DOC_ALLOWLIST - unnavigated

    for target in sorted(unexpected):
        errors.append(f'mkdocs.yml: 未纳入导航且不在允许列表: {target}')
    for target in sorted(stale_allowlist):
        errors.append(f'校验配置: 无需继续允许未导航页面: {target}')

    return errors


def verify_readthedocs_config() -> list[str]:
    text = READTHEDOCS_CONFIG.read_text(encoding='utf-8')
    match = re.search(r'^\s+os:\s*["\x27]?([^"\x27\s#]+)', text, re.MULTILINE)
    if match is None:
        return ['.readthedocs.yaml: 缺少 build.os']

    operating_system = match.group(1)
    if operating_system not in SUPPORTED_READTHEDOCS_OS:
        return [
            '.readthedocs.yaml: Read the Docs 不支持 build.os '
            f'值 {operating_system}'
        ]

    return []


def verify_cli_help() -> list[str]:
    errors: list[str] = []

    try:
        from mootdx.__main__ import entry as cli_entry
    except Exception as exc:
        return [f'无法读取 CLI 元数据: {exc}']

    registered_commands = set(cli_entry.commands)
    expected_commands = set(CLI_COMMANDS[1:])
    if registered_commands != expected_commands:
        errors.append(
            'CLI 命令集合与文档校验配置不一致: '
            f'实际 {sorted(registered_commands)}，配置 {sorted(expected_commands)}'
        )

    for command in CLI_COMMANDS:
        args = [sys.executable, '-m', 'mootdx']
        if command:
            args.append(command)
        args.append('--help')

        result = subprocess.run(
            args,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            label = command or '<root>'
            detail = (result.stderr or result.stdout).strip().splitlines()
            message = detail[-1] if detail else f'退出码 {result.returncode}'
            errors.append(f'CLI 帮助失败 ({label}): {message}')
            continue

        label = command or '<root>'
        documentation = CLI_DOCS[command].read_text(encoding='utf-8')
        for token in CLI_HELP_CONTRACT[command]:
            if token not in result.stdout:
                errors.append(f'CLI 帮助缺少约定项 ({label}): {token}')
            if token not in documentation:
                errors.append(
                    f'{CLI_DOCS[command].relative_to(ROOT)}: '
                    f'缺少 CLI 约定项 ({label}): {token}'
                )

        for token in CLI_HELP_FORBIDDEN.get(command, ()):
            if token in result.stdout:
                errors.append(f'CLI 帮助重新出现废弃项 ({label}): {token}')

        click_command = cli_entry.commands[command] if command else cli_entry
        for parameter in click_command.params:
            long_options = [
                option
                for option in getattr(parameter, 'opts', ())
                if option.startswith('--')
            ]
            for option in long_options:
                if option not in result.stdout:
                    errors.append(f'CLI 帮助缺少实际选项 ({label}): {option}')
                if option not in documentation:
                    errors.append(
                        f'{CLI_DOCS[command].relative_to(ROOT)}: '
                        f'缺少实际 CLI 选项 ({label}): {option}'
                    )

            default = getattr(parameter, 'default', None)
            if (
                long_options
                and default is not None
                and not isinstance(default, bool)
                and not getattr(parameter, 'is_flag', False)
                and not getattr(parameter, 'count', False)
                and f'`{default}`' not in documentation
            ):
                errors.append(
                    f'{CLI_DOCS[command].relative_to(ROOT)}: '
                    f'未记录 {long_options[0]} 的实际默认值 `{default}`'
                )

    return errors


def verify_built_site(site_dir: Path) -> list[str]:
    errors: set[str] = set()
    pages: dict[Path, HTMLLinkCollector] = {}
    site_root = site_dir.resolve()

    for source in site_dir.rglob('*.html'):
        collector = HTMLLinkCollector()
        collector.feed(source.read_text(encoding='utf-8'))
        pages[source.resolve()] = collector

    for source, collector in pages.items():
        for line_number, href in collector.links:
            parsed = urlsplit(href)
            if parsed.scheme or parsed.netloc or href.startswith('//'):
                continue

            path_text = unquote(parsed.path)
            fragment = unquote(parsed.fragment)
            if not path_text:
                target = source
            elif path_text.startswith('/'):
                target = (site_root / path_text.lstrip('/')).resolve()
            else:
                target = (source.parent / path_text).resolve()

            try:
                target.relative_to(site_root)
            except ValueError:
                errors.add(
                    f'{source.relative_to(site_root)}:{line_number}: '
                    f'构建后链接越出站点目录: {href}'
                )
                continue

            if target.is_dir() or path_text.endswith('/'):
                target = target / 'index.html'
            elif not target.suffix and (target / 'index.html').is_file():
                target = target / 'index.html'

            if not target.is_file():
                errors.add(
                    f'{source.relative_to(site_root)}:{line_number}: '
                    f'构建后链接目标不存在: {href}'
                )
                continue

            if fragment and target.suffix == '.html':
                target_collector = pages.get(target.resolve())
                if target_collector is None or fragment not in target_collector.anchors:
                    errors.add(
                        f'{source.relative_to(site_root)}:{line_number}: '
                        f'构建后锚点不存在: {href}'
                    )

    return sorted(errors)


def build_mkdocs(required: bool) -> list[str]:
    if importlib.util.find_spec('mkdocs') is None:
        if required:
            return ['未安装 MkDocs；请先安装 docs/requirements.txt 再执行发布校验']
        print('提示：当前环境未安装 MkDocs，已跳过站点构建；发布校验会将其视为错误。')
        return []

    with tempfile.TemporaryDirectory(prefix='mootdx-docs-') as site_dir_text:
        site_dir = Path(site_dir_text)
        result = subprocess.run(
            [
                sys.executable,
                '-m',
                'mkdocs',
                'build',
                '--strict',
                '--config-file',
                str(MKDOCS_CONFIG),
                '--site-dir',
                str(site_dir),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            return [f'MkDocs 严格构建失败:\n{detail}']

        return verify_built_site(site_dir)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        '--pre-commit',
        action='store_true',
        help='运行快速检查；当前环境没有 MkDocs 时跳过站点构建',
    )
    mode.add_argument(
        '--pre-release',
        action='store_true',
        help='运行发布检查；要求 MkDocs 严格构建成功',
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    files = markdown_files()
    errors = [
        *verify_local_links(files),
        *verify_retired_domains(files),
        *verify_python_examples(files),
        *verify_mkdocs_nav(),
        *verify_readthedocs_config(),
        *verify_cli_help(),
        *build_mkdocs(required=args.pre_release),
    ]

    if errors:
        print('文档校验失败：', file=sys.stderr)
        for error in errors:
            print(f'- {error}', file=sys.stderr)
        return 1

    print(
        f'文档校验通过：{len(files)} 个 Markdown 文件、'
        f'{len(CLI_COMMANDS)} 个 CLI 帮助入口。'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

"""GitHub Actions workflows for the wiki site, generated from docs.config.json."""
import json
from urllib.parse import urlsplit

LABELS = {
    'ko': {'docs': '문서', 'all': '전체 문서', 'tagline': '개발과 운영 문서를 한 곳에서 찾습니다.',
           'home_details': '공통 규칙과 문서 작성 안내입니다.', 'repo_details': '%s 저장소의 사람용 문서입니다.', 'home': '안내'},
    'en': {'docs': 'Docs', 'all': 'All documents', 'tagline': 'Development and operations documents in one place.',
           'home_details': 'Shared rules and the writing guide.', 'repo_details': 'Human documentation of the %s repository.',
           'home': 'Guide'},
}


def site_dir(config, raw):
    return raw.get('site', {}).get('dir', '.' if config['layout'] == 'hub' else 'docs-site')


def slug(repo):
    """owner/name from a GitHub URL."""
    path = urlsplit(repo['url']).path.strip('/')
    if path.endswith('.git'):
        path = path[:-4]
    if path.count('/') != 1:
        raise ValueError('Repository %s needs a GitHub url like https://github.com/owner/name' % repo['name'])
    return path


def labels(raw):
    return LABELS['en' if raw.get('project', {}).get('language') == 'en' else 'ko']


def home_page(config, raw):
    """Values for site/home.md."""
    t = labels(raw)
    site = raw.get('site', {})
    project = raw.get('project', {}).get('name', 'Project')
    features = []
    for repo_id, spec in raw['repositories'].items():
        repo = config['repos'][repo_id]
        label = spec.get('label') or (t['home'] if repo['home'] else repo_id)
        details = t['home_details'] if repo['home'] else t['repo_details'] % repo_id
        features.append('  - title: %s\n    details: %s\n    link: /%s/index.html' % (
            json.dumps(label, ensure_ascii=False), json.dumps(details, ensure_ascii=False), repo['mount']))
    home = config['repos'][config['home']]
    return {
        'title': json.dumps(site.get('title') or '%s %s' % (project, t['docs']), ensure_ascii=False),
        'tagline': json.dumps(site.get('description') or t['tagline'], ensure_ascii=False),
        'all_docs': json.dumps(t['all'], ensure_ascii=False),
        'home_mount': home['mount'],
        'features': '\n'.join(features),
    }


def pages(config, raw):
    home = config['repos'][config['home']]
    hub = config['layout'] == 'hub'
    home_dir = home['local'] if hub else '.'
    folder = site_dir(config, raw)
    work = home_dir if folder == '.' else ('%s/%s' % (home_dir, folder) if hub else folder)
    lines = [
        '# devdog-docs 생성 파일. 저장소 목록을 바꾸면 vendor.py site로 다시 생성',
        'name: Documentation website',
        'on:',
        '  push:',
        '    branches: [%s]' % home['branch'],
        '  repository_dispatch:',
        '    types: [documentation-updated]',
    ]
    if hub:
        lines += [
            '  # 코드 저장소 문서 반영: 변경 알림 워크플로 미설치 저장소를 매시 17분에 재수집',
            '  schedule:',
            "    - cron: '17 * * * *'",
        ]
    lines += [
        '  workflow_dispatch:',
        'permissions:',
        '  contents: read',
        '  pages: write',
        '  id-token: write',
        'concurrency:',
        '  group: documentation-pages',
        '  cancel-in-progress: true',
        'jobs:',
        '  build:',
        '    runs-on: ubuntu-latest',
        '    timeout-minutes: 20',
        '    steps:',
        '      - uses: actions/checkout@v4',
        '        with:',
        '          path: %s' % home_dir,
        '          fetch-depth: 0',
        '          persist-credentials: false',
    ]
    if hub:
        for repo in config['repos'].values():
            if repo['home']:
                continue
            lines += [
                '      - uses: actions/checkout@v4',
                '        with:',
                '          repository: %s' % slug(repo),
                '          ref: %s' % repo['branch'],
                '          token: ${{ secrets.DOCS_SOURCE_TOKEN || github.token }}',
                '          path: %s' % repo['local'],
                '          fetch-depth: 0',
                '          persist-credentials: false',
            ]
    lines += [
        '      - uses: actions/setup-node@v4',
        '        with:',
        '          node-version-file: %s/.nvmrc' % work,
        '          cache: npm',
        '          cache-dependency-path: %s/package-lock.json' % work,
        '      - uses: actions/setup-python@v5',
        '        with:',
        "          python-version: '3.12'",
        '      - name: Check documents',
        '        working-directory: %s' % home_dir,
        '        run: python3 scripts/check_docs.py%s' % (' --workspace' if hub else ''),
        '      - name: Build site',
        '        working-directory: %s' % work,
        '        env:',
        "          DOCS_REQUIRE_CLEAN: '1'",
        '        run: |',
        '          npm ci',
        '          npm test',
        '          npm run docs:build',
        '          npx playwright install --with-deps chromium',
        '          npm run test:browser',
        '      - uses: actions/upload-pages-artifact@v3',
        '        with:',
        '          path: %s/.site/dist' % work,
        '  deploy:',
        '    needs: build',
        '    runs-on: ubuntu-latest',
        '    environment:',
        '      name: github-pages',
        '      url: ${{ steps.deployment.outputs.page_url }}',
        '    steps:',
        '      - id: deployment',
        '        uses: actions/deploy-pages@v4',
    ]
    return '\n'.join(lines) + '\n'


def notify(config, repo):
    home = config['repos'][config['home']]
    return '\n'.join([
        '# devdog-docs 생성 파일. 문서 변경 시 문서 허브 위키 재빌드 요청',
        'name: Notify documentation website',
        'on:',
        '  push:',
        '    branches: [%s]' % repo['branch'],
        "    paths: ['%s/**', 'README.md']" % repo['human'],
        '  workflow_dispatch:',
        'permissions: {}',
        'jobs:',
        '  notify:',
        '    runs-on: ubuntu-latest',
        '    steps:',
        '      - name: Request documentation rebuild',
        '        env:',
        '          GH_TOKEN: ${{ secrets.DOCS_DISPATCH_TOKEN }}',
        '        run: |',
        "          test -n \"$GH_TOKEN\" || { echo 'DOCS_DISPATCH_TOKEN is required'; exit 1; }",
        '          gh api --method POST repos/%s/dispatches -f event_type=documentation-updated' % slug(home),
    ]) + '\n'

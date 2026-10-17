#!/usr/bin/env python3
"""GitHub Trending 第一页抓取（跑在 GitHub Actions 里，runner 能直连 github.com）。
除页面上的条目外，再用 api.github.com 补齐每个仓库的 topics / README 摘要 / 总星数，
供云端写"它能做什么"用。
changed_at 只在条目列表变化时更新（云端据此判断"无变化不推"）。"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36')
TOKEN = os.environ.get('GITHUB_TOKEN', '')
CACHE = {}


def fetch(url, accept='text/html', api=False):
    headers = {'User-Agent': UA, 'Accept': accept}
    if api and TOKEN:
        headers['Authorization'] = 'token ' + TOKEN
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8', 'replace')


def parse(html):
    rows = []
    for block in html.split('<article class="Box-row"')[1:]:
        m = re.search(r'<h2 class="h3 lh-condensed">\s*<a[^>]*href="/([^"]+)"', block)
        if not m:
            continue
        repo = m.group(1).strip('/')
        if repo.count('/') != 1:
            continue
        d = re.search(r'<p class="[^"]*col-9[^"]*">\s*(.*?)\s*</p>', block, re.S)
        desc = re.sub(r'<[^>]+>', '', d.group(1)).strip() if d else ''
        desc = re.sub(r'\s+', ' ', desc)[:220]
        lang = re.search(r'itemprop="programmingLanguage">([^<]+)<', block)
        st = re.search(r'([\d,]+)\s*stars (?:today|this week|this month)', block)
        rows.append({
            'repo': repo,
            'desc': desc,
            'lang': lang.group(1).strip() if lang else '',
            'stars': st.group(1) if st else '',
        })
    return rows


def clean_readme(text):
    text = re.sub(r'```.*?```', ' ', text, flags=re.S)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', ' ', text)
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'^\s*[#>*\-\d.+ ]+\s?', '', text, flags=re.M)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()[:700]


def enrich(item):
    repo = item['repo']
    if repo in CACHE:
        item.update(CACHE[repo])
        return
    info = {'topics': [], 'total_stars': '', 'homepage': '', 'readme': ''}
    try:
        meta = json.loads(fetch('https://api.github.com/repos/' + repo, api=True,
                                accept='application/vnd.github+json'))
        info['topics'] = (meta.get('topics') or [])[:6]
        info['total_stars'] = meta.get('stargazers_count') or ''
        info['homepage'] = (meta.get('homepage') or '')[:120]
    except (urllib.error.URLError, OSError, ValueError):
        pass
    try:
        readme = fetch('https://api.github.com/repos/' + repo + '/readme', api=True,
                       accept='application/vnd.github.raw')
        info['readme'] = clean_readme(readme)
    except (urllib.error.URLError, OSError, ValueError):
        pass
    CACHE[repo] = info
    item.update(info)


def scrape(since):
    items = parse(fetch('https://github.com/trending?since=' + since))
    for it in items:
        enrich(it)
    return items


def main():
    since = sys.argv[1] if len(sys.argv) > 1 else 'daily'
    path = 'data/' + since + '.json'
    old = None
    if os.path.exists(path):
        try:
            old = json.load(open(path, encoding='utf-8'))
        except (OSError, ValueError):
            old = None
    items = scrape(since)
    if not items:
        print('[FAIL] 抓不到任何条目，保留旧数据', file=sys.stderr)
        return 1
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    same = bool(old) and [(i['repo'], i['stars']) for i in old.get('items', [])] == \
                         [(i['repo'], i['stars']) for i in items]
    out = {
        'since': since,
        'fetched_at': now,
        'changed_at': (old.get('changed_at') or now) if same else now,
        'count': len(items),
        'items': items,
    }
    os.makedirs('data', exist_ok=True)
    json.dump(out, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'{since}: {len(items)} 条, {"无变化" if same else "有变化"}, '
          f'{sum(1 for i in items if i.get("readme"))} 个拿到 README')
    return 0


if __name__ == '__main__':
    sys.exit(main())

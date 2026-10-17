#!/usr/bin/env python3
"""GitHub Trending 第一页抓取（跑在 GitHub Actions 里，runner 能直连 github.com）。
输出 data/{daily,weekly,monthly}.json：items 为页面上的仓库列表，
changed_at 只在列表内容变化时更新（云端据此判断"无变化不推"）。"""
import json
import os
import re
import sys
from datetime import datetime, timezone

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36')


def fetch(url):
    import urllib.request
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': 'text/html,application/xhtml+xml',
        'Accept-Language': 'en-US,en;q=0.9',
    })
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


def main():
    since = sys.argv[1] if len(sys.argv) > 1 else 'daily'
    items = parse(fetch('https://github.com/trending?since=' + since))
    if not items:
        print('[FAIL] 抓不到任何条目，保留旧数据', file=sys.stderr)
        return 1
    path = 'data/' + since + '.json'
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    old = None
    if os.path.exists(path):
        try:
            old = json.load(open(path, encoding='utf-8'))
        except (OSError, ValueError):
            old = None
    same = bool(old) and old.get('items') == items
    out = {
        'since': since,
        'fetched_at': now,
        'changed_at': old.get('changed_at', now) if same else now,
        'count': len(items),
        'items': items,
    }
    os.makedirs('data', exist_ok=True)
    json.dump(out, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'{since}: {len(items)} 条, {"无变化" if same else "有变化"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

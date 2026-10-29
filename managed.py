"""Codex-reviewed JSON -> cards -> Instagram. No text-generation API calls."""
import json
import os
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KST = timezone(timedelta(hours=9))


def validate(p, now, kind):
    if p.get('reviewed') is not True or p.get('date') != now.strftime('%Y-%m-%d'):
        raise ValueError('Reviewed content for today is required')
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}-(am|pm)', p.get('id', '')):
        raise ValueError('Invalid publication id')
    if p['id'] != p['date'] + '-' + ('am' if now.hour < 12 else 'pm'):
        raise ValueError('Wrong publication slot')
    c = p['content']
    for key in ('cover_title', 'cover_sub', 'caption'):
        if not isinstance(c.get(key), str) or not c[key].strip():
            raise ValueError('Missing ' + key)
    if not 3 <= len(c.get('slides', [])) <= 5:
        raise ValueError('Use 3-5 body cards')
    for slide in c['slides']:
        if not slide.get('title') or not slide.get('body'):
            raise ValueError('Missing slide title/body')
    if len(c.get('hashtags', [])) != 5:
        raise ValueError('Use five relevant hashtags')
    if kind == 'issue' and (len(p.get('sources', [])) < 3 or any(
        not s.get('url', '').startswith('https://') or not s.get('outlet') for s in p['sources'])):
        raise ValueError('Three verified source URLs required')


def git_save(paths, message):
    for args in (['config', 'user.name', 'cardnews-bot'],
                 ['config', 'user.email', 'cardnews-bot@users.noreply.github.com'],
                 ['add', *map(str, paths)], ['commit', '-m', message], ['push']):
        subprocess.run(['git', *args], check=True)


def main():
    import requests
    from publish import publish_carousel
    from render import render_all
    kind = os.environ.get('CARD_KIND', 'nordic')
    dry = os.environ.get('DRY_RUN', '1') == '1'
    now = datetime.now(KST)
    p = json.loads((ROOT / 'prepared.json').read_text(encoding='utf-8'))
    validate(p, now, kind)
    journal_path = ROOT / 'managed-state.json'
    journal = json.loads(journal_path.read_text()) if journal_path.exists() else {}
    if not dry and p['id'] in journal:
        raise RuntimeError('Slot already attempted; reconcile Instagram before retry')
    if not dry and os.environ.get('PUBLISH_PAUSED', '1') != '0':
        raise RuntimeError('Publishing paused pending account review')
    c = p['content']
    out = ROOT / 'images' / p['id']
    from design_system import choose_design, render_design
    design_id = choose_design(kind, p['id'], journal, p.get('design_id'))
    paths = render_design(c, out, kind, design_id, p.get('sources', []), now.strftime('%Y.%m.%d'))
    print('Design:', design_id)
    caption = c['caption'] + '\n\n' + ' '.join(c['hashtags'])
    if kind == 'issue':
        caption += '\n\n확인 기준: ' + now.strftime('%Y-%m-%d %H:%M KST')
        caption += '\n' + '\n'.join(s['outlet'] + ': ' + s['url'] for s in p['sources'])
    if len(caption) > 2200:
        raise ValueError('Caption too long')
    if dry:
        print('Preview only:', out)
        return
    token = os.environ['IG_ACCESS_TOKEN']
    api = 'https://graph.instagram.com/v21.0'
    expected = 'nordic_log' if kind == 'nordic' else 'issue.cards'
    owner = requests.get(api + '/me', params={'fields': 'username', 'access_token': token}, timeout=30).json()
    if owner.get('username') != expected:
        raise RuntimeError('Account identity could not be verified')
    git_save([out], 'Add reviewed card images ' + p['id'])
    repo_root = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], text=True).strip())
    urls = ['https://raw.githubusercontent.com/' + os.environ['GITHUB_REPOSITORY'] + '/main/' + f.relative_to(repo_root).as_posix() for f in paths]
    for url in urls:
        requests.get(url, timeout=30).raise_for_status()
    journal[p['id']] = {'status': 'pending', 'at': now.isoformat(), 'title': c['cover_title'], 'design_id': design_id}
    journal_path.write_text(json.dumps(journal, ensure_ascii=False, indent=2), encoding='utf-8')
    git_save([journal_path], 'Reserve publication slot ' + p['id'])
    # A timeout or API error leaves a durable pending record. Never auto-repost it.
    media_id = publish_carousel(urls, caption)
    journal[p['id']].update(status='published', media_id=media_id)
    journal_path.write_text(json.dumps(journal, ensure_ascii=False, indent=2), encoding='utf-8')
    git_save([journal_path], 'Record publication ' + p['id'])
    print('Published media ID:', media_id)


if __name__ == '__main__':
    main()

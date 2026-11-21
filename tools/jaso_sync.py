# -*- coding: utf-8 -*-
"""자소서 MD ↔ 구직 플래너 (민석 공고만)

  python jaso_sync.py push <자소서.md> [--submit] [--post ID] [--force]
      MD의 문항·답변을 플래너의 그 공고에 올림. 공고는 폴더 이름(회사_직무)으로 찾음
      --submit : 제출본으로 올림 (🔒 잠금 + 단계 '제출' + 제출일)
  python jaso_sync.py comments <자소서.md 또는 회사 폴더> [--post ID]
      그 공고에 달린 '해결 안 된' 댓글을 보여 줌 (피드백 반영할 때)
  python jaso_sync.py resolve <자소서.md 또는 회사 폴더> <댓글id> [<댓글id> ...] [--post ID]
      반영한 댓글을 '해결'로 접음

서버 주소·비밀번호는 ../config.local.json (git 제외) 의 server / pw 를 씀.
Claude가 MD를 다시 읽지 않고 이 프로그램만 돌리도록 만든 것 (토큰 절약).
"""
import io, json, os, re, sys, datetime, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(io.open(os.path.join(HERE, '..', 'config.local.json'), encoding='utf-8'))
SERVER, PW = CFG['server'], CFG.get('pw')
if not PW: sys.exit('config.local.json 에 pw(앱 비밀번호)를 넣어 주세요')
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def api(action, **body):
    data = json.dumps(dict(body, pw=PW, action=action), ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(SERVER, data=data, headers={'Content-Type': 'text/plain;charset=utf-8'})
    with urllib.request.urlopen(req, timeout=180) as r:   # 302 → GET 으로 따라감 (Apps Script 방식)
        j = json.loads(r.read().decode('utf-8'))
    if not j.get('ok'):
        sys.exit('서버 오류: %s %s' % (j.get('error'), j.get('detail') or ''))
    return j

def norm(s):
    s = re.sub(r'\(주\)|㈜|주식회사', '', str(s or ''))
    return re.sub(r'[\s\W_]+', '', s).lower()

def find_post(posts, path, post_id=None):
    if post_id:
        p = next((x for x in posts if x['id'] == post_id), None)
        if not p: sys.exit('그 id의 공고가 없어요: ' + post_id)
        return p
    folder = os.path.basename(os.path.dirname(os.path.abspath(path))) if os.path.isfile(path) else os.path.basename(os.path.abspath(path))
    key = norm(folder.split('_')[0])
    if not key: sys.exit('폴더 이름에서 회사명을 못 찾았어요: ' + folder)
    tiers = [[p for p in posts if norm(p['co']) == key or norm(p.get('short')) == key],
             [p for p in posts if key in norm(p['co'])],
             [p for p in posts if norm(p['co']) and norm(p['co']) in key]]
    for t in tiers:
        if not t: continue
        live = [p for p in t if p['stage'] != '종료'] or t
        if len(live) == 1: return live[0]
        print('플래너에서 같은 회사 공고가 여러 개예요. --post 로 골라 주세요:')
        for p in live: print('  %s  %s · %s · %s' % (p['id'], p['co'], p['role'] or p['job'], p['stage']))
        sys.exit(2)
    sys.exit('플래너에서 "%s" 공고를 못 찾았어요. 앱에 공고를 먼저 등록하거나 --post 로 지정해 주세요' % folder.split('_')[0])

def parse_md(path):
    t = io.open(path, encoding='utf-8').read()
    parts = re.split(r'^##\s*문항\s*(\d+)\s*(?:\(([^)]*)\))?\s*$', t, flags=re.M)
    qs = []
    for i in range(1, len(parts), 3):
        lim, body = parts[i + 1] or '', parts[i + 2]
        body = re.sub(r'^---\s*$', '', body, flags=re.M).strip()
        paras = [p.strip() for p in re.split(r'\n\s*\n', body) if p.strip()]
        k = next((j for j, p in enumerate(paras) if p.startswith('[')), 1 if len(paras) > 1 else 0)
        nums = [int(x.replace(',', '')) for x in re.findall(r'([\d,]+)\s*자', lim)]
        qs.append({'t': '\n'.join(paras[:k]), 'n': max(nums) if nums else 0, 'a': '\n'.join(paras[k:])})
    if not qs: sys.exit('MD에서 "## 문항 N (글자 수)" 제목을 못 찾았어요')
    return qs

def version_of(path):
    name = os.path.basename(path)
    m = re.search(r'_v(\d+(?:\.\d+)*)\.md$', name)
    if name.startswith('제출본'): return '제출본'
    return 'v' + m.group(1) if m else ''

def load_me():
    return api('loadAll')['data']['me']

def args_opt(argv, flag):
    if flag in argv:
        i = argv.index(flag); v = argv[i + 1] if i + 1 < len(argv) else None
        del argv[i:i + 2]; return v
    return None

def cmd_push(argv):
    submit = '--submit' in argv; force = '--force' in argv; dry = '--dry' in argv
    argv = [a for a in argv if a not in ('--submit', '--force', '--dry')]
    pid = args_opt(argv, '--post')
    path = argv[0]
    me = load_me(); p = find_post(me['posts'], path, pid)
    old = sorted([q for q in me['qs'] if q['pid'] == p['id']], key=lambda q: int(q.get('i') or 0))
    if not submit and not force and any(q.get('lock') == 'Y' for q in old):
        sys.exit('이 공고는 이미 제출본으로 잠겨 있어요. 덮어쓰려면 --force')
    qs = parse_md(path)
    today = datetime.date.today()
    ver = version_of(path) or ('제출본' if submit else '')
    verlabel = ('%s · %d/%d' % (ver, today.month, today.day)).strip(' ·')
    rows = []
    for i, q in enumerate(qs):
        qid = old[i]['id'] if i < len(old) else '%s_q%d_%s' % (p['id'], i, today.strftime('%y%m%d'))
        rows.append({'id': qid, 'pid': p['id'], 'i': i, 't': q['t'], 'n': q['n'], 'a': q['a'],
                     'st': '제출본' if submit else '초안', 'lock': 'Y' if submit else '', 'ver': verlabel})
    post = {'id': p['id'], 'updated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}
    if submit:
        m = re.search(r'제출본_(\d{6})', os.path.basename(path))
        sub = ('20%s-%s-%s' % (m.group(1)[:2], m.group(1)[2:4], m.group(1)[4:])) if m else today.isoformat()
        if p['stage'] in ('관심', '작성중'): post['stage'] = '제출'
        if not p.get('submitted'): post['submitted'] = sub
        histt = '자소서 제출본 반영'
    else:
        if p['stage'] == '관심': post['stage'] = '작성중'
        histt = '자소서 %s 반영' % (ver or '')
    ops = [{'op': 'replace', 'table': 'qs', 'key': 'pid', 'value': p['id'], 'rows': rows},
           {'op': 'upsert', 'table': 'posts', 'rows': [post]},
           {'op': 'upsert', 'table': 'hist', 'rows': [{'id': '%s_h%s' % (p['id'], datetime.datetime.now().strftime('%y%m%d%H%M%S')), 'pid': p['id'], 'd': today.isoformat(), 't': histt.strip()}]}]
    if dry:
        print('[시험] 올릴 내용: %s · %s' % (p['co'], verlabel))
        for i, r in enumerate(rows):
            print('  문항 %d · 제한 %s자 · 답변 %d자 · %s…' % (i + 1, r['n'], len(r['a'].replace('\n', '')), r['t'][:30].replace('\n', ' ')))
        return
    api('batch', who='me', ops=ops)
    lens = '/'.join(str(len(q['a'].replace('\n', ''))) for q in qs)
    print('올렸어요: %s · 문항 %d개 (답변 %s자) · %s%s' % (p['co'], len(qs), lens, verlabel or '버전 없음',
          ' · 🔒 제출본, 단계 제출' if submit else ''))

def cmd_comments(argv):
    pid = args_opt(argv, '--post')
    me = load_me(); p = find_post(me['posts'], argv[0], pid)
    qs = sorted([q for q in me['qs'] if q['pid'] == p['id']], key=lambda q: int(q.get('i') or 0))
    cs = [c for c in me['comments'] if c['pid'] == p['id'] and c.get('resolved') != 'Y']
    print('%s · 해결 안 된 댓글 %d개 (지금 플래너 버전: %s)' % (p['co'], len(cs), (qs[0].get('ver') if qs else '') or '-'))
    for c in sorted(cs, key=lambda c: (str(c.get('qi')), c.get('at') or '')):
        qi = '공고' if c.get('qi') in ('', None) else '문항 %d' % (int(c['qi']) + 1)
        who = {'me': '민석', 'gh': '건희'}.get(c.get('by'), c.get('by') or '노션')
        print('- [%s] %s · %s %s%s' % (c['id'], qi, who, c.get('at') or '', (' · %s에 단 댓글' % c['ver']) if c.get('ver') else ''))
        if c.get('quote'): print('    “%s”' % c['quote'].replace('\n', ' ')[:200])
        print('    → %s' % c['text'].replace('\n', ' '))
        try:
            for r in json.loads(c.get('replies') or '[]'):
                print('      ↳ %s: %s' % ({'me': '민석', 'gh': '건희'}.get(r.get('by'), r.get('by')), str(r.get('text', '')).replace('\n', ' ')))
        except Exception:
            pass

def cmd_resolve(argv):
    pid = args_opt(argv, '--post')
    me = load_me(); p = find_post(me['posts'], argv[0], pid)
    ids = argv[1:]
    have = {c['id'] for c in me['comments'] if c['pid'] == p['id']}
    bad = [i for i in ids if i not in have]
    if bad: sys.exit('이 공고 댓글이 아니에요: ' + ', '.join(bad))
    api('batch', who='me', ops=[{'op': 'upsert', 'table': 'comments', 'rows': [{'id': i, 'resolved': 'Y'} for i in ids]}])
    print('해결로 접었어요: %d개' % len(ids))

if __name__ == '__main__':
    a = sys.argv[1:]
    if not a or a[0] not in ('push', 'comments', 'resolve') or len(a) < 2:
        print(__doc__); sys.exit(1)
    {'push': cmd_push, 'comments': cmd_comments, 'resolve': cmd_resolve}[a[0]](a[1:])

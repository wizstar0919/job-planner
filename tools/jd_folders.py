# -*- coding: utf-8 -*-
"""구직 플래너 공고 → 드라이브 지원서 폴더 자동 정리 (민석님 전용 도구, 앱 기능 아님)

  python jd_folders.py               자동 확인 1회 (작업 스케줄러가 30분마다 실행)
                                     ① 최근 공고 중 폴더 없는 것 → 폴더 + JD_원본(PDF 등) + JD.md(자동 추출본)
                                     ② 원본이 덜 담긴 공고 → 다른 방법으로 다시 받기
                                     ③ 폴더 위치가 플래너보다 앞선 단계면 → 플래너 단계를 폴더에 맞춤
  python jd_folders.py --now 회사명   기업조사 시작 때: 그 회사 공고 폴더가 없으면 바로 만들고 경로 출력
  python jd_folders.py --notice      대화 시작 알림: 원본 확인 필요 · 폴더 옮길 것 목록 (네트워크 안 씀)
  python jd_folders.py --retry 회사명  원본 다시 받기 (자동 방법 전부)
  python jd_folders.py --done 회사명   원본을 사람이 직접 확인·보완함 → 확인 필요 목록에서 뺌
  python jd_folders.py --dry         아무것도 바꾸지 않고 할 일만 보여 줌

규칙: 폴더 = 10_구직/10_지원작업/지원서/<단계>/<회사>_<직무>/  (지원서/README.md)
      단계 폴더: 시작 전·작성 중 → 01_진행중 / 제출 → 02_지원완료 / 전형 → 03_면접중
      기록: 지원서/_자동정리/ (연결.json = 공고 id ↔ 폴더, 확인필요.md, 기록.log)
플래너 접속은 jaso_sync.py 와 같은 도구 키(../config.local.json)를 씀.
"""
import io, json, os, re, sys, time, datetime, subprocess, urllib.request, urllib.parse, html as _html

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
if hasattr(sys.stdout, 'reconfigure'):
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass

BASE = r'G:\내 드라이브\10_구직\10_지원작업\지원서'
STATE = os.path.join(BASE, '_자동정리')
LINK_FILE = os.path.join(STATE, '연결.json')
CHECK_FILE = os.path.join(STATE, '확인필요.md')
LOG_FILE = os.path.join(STATE, '기록.log')
LOCK_FILE = os.path.join(STATE, '.lock')
CUTOFF = '2026-11-18'          # 이 날짜 이후 등록한 공고만 폴더를 새로 만듦 (끝난 옛 공고 제외)
STAGE_DIRS = ['01_진행중', '02_지원완료', '03_면접중', '04_불합격', '05_최종합격', '06_인재풀']
RANK = {'관심': 0, '작성중': 1, '제출': 2, '인적성': 3, '면접1': 3, '면접2': 3, '면접3': 3, '종료': 4}
STAGE_NAME = {'관심': '시작 전', '작성중': '작성 중', '제출': '제출', '인적성': '인적성·필기', '면접1': '1차 면접', '면접2': '2차 면접', '면접3': '3차 면접', '종료': '종료'}
CHROME = next((p for p in [os.environ.get('CHROME', ''), r'C:\Program Files\Google\Chrome\Application\chrome.exe',
              r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe', r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'] if p and os.path.exists(p)), None)
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
DRY = '--dry' in sys.argv
NOW = datetime.datetime.now()
TODAY = NOW.strftime('%Y-%m-%d')

# ---------------- 기록 ----------------
def log(msg):
    line = '%s  %s' % (datetime.datetime.now().strftime('%Y-%m-%d %H:%M'), msg)
    print(line)
    if DRY: return
    os.makedirs(STATE, exist_ok=True)
    with io.open(LOG_FILE, 'a', encoding='utf-8') as f: f.write(line + '\n')

def load_links():
    try: return json.load(io.open(LINK_FILE, encoding='utf-8'))
    except Exception: return {}

def save_links(L):
    if DRY: return
    os.makedirs(STATE, exist_ok=True)
    tmp = LINK_FILE + '.tmp'
    json.dump(L, io.open(tmp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    os.replace(tmp, LINK_FILE)

# ---------------- 이름 · 폴더 ----------------
def norm(s):
    s = re.sub(r'\(주\)|㈜|주식회사', '', str(s or ''))
    return re.sub(r'[\s\W_]+', '', s).lower()

def safe(s, n):
    s = re.sub(r'\(주\)|㈜|주식회사', '', str(s or ''))
    s = re.sub(r'\[[^\]]*\]|\([^)]*\)', ' ', s)           # [팀명] (신입) 같은 덧붙임 제거
    s = re.sub(r'[\\/:*?"<>|·・,]+', ' ', s)                # 파일명 금지 글자
    s = re.sub(r'\s+', '', s).strip('._-')
    return s[:n]

def folder_name(p):
    co = safe(p['co'], 30) or '회사'
    job = safe(p.get('role') or p.get('job'), 30) or safe(p.get('job'), 30) or '직무미기록'
    return '%s_%s' % (co, job)

def stage_dir_for(stage):
    return '01_진행중' if RANK.get(stage, 0) <= 1 else '02_지원완료' if stage == '제출' else '03_면접중' if RANK.get(stage) == 3 else None

def all_folders():
    out = []
    for st in STAGE_DIRS:
        d = os.path.join(BASE, st)
        if os.path.isdir(d):
            out += [(st, f) for f in sorted(os.listdir(d)) if os.path.isdir(os.path.join(d, f))]
    return out

def find_folder(rec, post_id, folders):
    """기록된 폴더를 찾음. 옮겼거나 이름을 바꿨으면 이름 → JD.md 의 '플래너_id' 순으로 다시 찾음"""
    if rec and rec.get('folder') and os.path.isdir(os.path.join(BASE, rec['folder'])):
        return rec['folder']
    name = (rec or {}).get('folder', '').split('/')[-1]
    for st, f in folders:
        if name and f == name: return st + '/' + f
    for st, f in folders:
        jd = os.path.join(BASE, st, f, 'JD.md')
        try:
            if ('플래너_id: ' + post_id) in io.open(jd, encoding='utf-8').read(3000): return st + '/' + f
        except Exception: pass
    return None

def match_existing(p, folders):
    """처음 연결할 때: 이름이 맞는 기존 폴더 (회사명 같고, 여러 개면 직무까지 비슷한 것)"""
    keys = [k for k in {norm(p['co']), norm(p.get('short'))} if k]
    def co_hit(f):
        c = norm(f.split('_')[0])
        return any(k == c or (len(k) >= 3 and len(c) >= 2 and (k in c or c in k)) for k in keys)
    # 처음 연결은 진행 중 폴더(01~03)에서만 — 예전에 떨어진 회사에 다시 지원한 공고가 옛 04 폴더에 붙어 '종료'로 바뀌지 않게
    cand = [(st, f) for st, f in folders if co_hit(f) and st in ('01_진행중', '02_지원완료', '03_면접중')]
    if len(cand) <= 1: return (cand[0][0] + '/' + cand[0][1]) if cand else None
    role = norm(p.get('role')) + norm(p.get('job'))
    best = [(st, f) for st, f in cand if norm(f.split('_', 1)[-1]) and (norm(f.split('_', 1)[-1]) in role or role[:4] in norm(f))]
    pick = best if len(best) == 1 else []
    return (pick[0][0] + '/' + pick[0][1]) if pick else None

# ---------------- 원본 받기 ----------------
def chrome(args, timeout=120):
    if not CHROME: return False
    try:
        subprocess.run([CHROME, '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run', '--user-agent=' + UA,
                        '--lang=ko-KR', '--virtual-time-budget=10000'] + args, capture_output=True, timeout=timeout,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return True
    except Exception as e:
        log('크롬 실행 실패: %s' % e); return False

def pdf_text(path):
    try:
        import pypdf
        return '\n'.join((pg.extract_text() or '') for pg in pypdf.PdfReader(path).pages)
    except Exception:
        return ''

def dump_dom(url):
    if not CHROME: return ''
    try:
        r = subprocess.run([CHROME, '--headless=new', '--disable-gpu', '--user-agent=' + UA, '--lang=ko-KR', '--virtual-time-budget=10000', '--dump-dom', url],
                           capture_output=True, timeout=120, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return r.stdout.decode('utf-8', 'ignore')
    except Exception:
        return ''

def download(url, path, referer=''):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': UA, 'Referer': referer or url})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read(20_000_000)
        if len(data) < 5000: return False
        io.open(path, 'wb').write(data); return True
    except Exception:
        return False

WORK = ['담당업무', '주요업무', '주요 업무', '업무내용', '업무 내용', '수행업무', '수행 업무', '하는 일', '하게 될', '이런 업무', '이런 일', '직무 소개', '직무소개',
        '직무내용', '직무 내용', '모집부문', '모집 부문', 'Responsibilities', "What you'll do", 'What you’ll do', 'Job Description', 'Your role', 'The role']
QUAL = ['자격요건', '자격 요건', '지원자격', '지원 자격', '필수', '이런 분', '찾고 있어요', 'Qualifications', 'Requirements', "What you'll bring",
        'What you’ll bring', 'Who you are', '우대사항', '우대 사항']
AD = ('criteo', 'doubleclick', 'googlesyndication', 'googletagmanager', 'google.com/recaptcha', 'facebook', 'kakao.com', 'channel.io', 'about:', 'youtube.com/embed')

INVIS = re.compile('[​‌‍﻿­]')

def jd_ok(text):
    """공고 본문이 담겼는지: 글이 충분하고 '하는 일' 쪽 말과 '자격' 쪽 말이 둘 다 있어야 통과"""
    t = re.sub(r'\s+', ' ', INVIS.sub('', text or ''))   # 보이지 않는 글자(폭 없는 공백 등)를 빼고 검사 — '업무​내용' 같은 표기
    return len(t) >= 400 and any(w in t for w in WORK) and any(w in t for w in QUAL)

def capture_pw(url, folder_abs, tries):
    """진짜 크롬(Playwright)으로 열어 끝까지 스크롤 → 전체 화면 사진 + PDF + 글(본문·상세 창) + 긴 공고 그림 원본. 반환 (글, 사진 받음?)"""
    from playwright.sync_api import sync_playwright
    texts, shot = [], False
    with sync_playwright() as pw:
        try: b = pw.chromium.launch(channel='chrome', headless=True)
        except Exception: b = pw.chromium.launch(headless=True)
        try:
            ctx = b.new_context(viewport={'width': 1280, 'height': 900}, locale='ko-KR', user_agent=UA)
            pg = ctx.new_page()
            pg.goto(url, wait_until='domcontentloaded', timeout=60000)
            try: pg.wait_for_load_state('networkidle', timeout=15000)
            except Exception: pass
            h = pg.evaluate('document.documentElement.scrollHeight') or 0
            for y in range(0, min(h, 40000), 700):                       # 끝까지 스크롤 (늦게 뜨는 내용 불러오기)
                pg.evaluate('window.scrollTo(0,%d)' % y); pg.wait_for_timeout(120)
            pg.evaluate('window.scrollTo(0,0)'); pg.wait_for_timeout(800)
            png = os.path.join(folder_abs, 'JD_원본.png')
            # 페이지가 아니라 안쪽 칸만 스크롤되는 사이트(나인하이어 등): 화면을 그 칸 길이만큼 늘려서 찍음
            inner = pg.evaluate("""() => { let m = 0; for (const e of document.querySelectorAll('*')) { const s = getComputedStyle(e);
                if ((s.overflowY === 'auto' || s.overflowY === 'scroll') && e.scrollHeight > e.clientHeight + 50) { m = Math.max(m, e.scrollHeight);
                  for (let y = 0; y < e.scrollHeight; y += 700) e.scrollTop = y; e.scrollTop = 0; } } return m; }""") or 0
            doc = pg.evaluate('document.documentElement.scrollHeight') or 0
            if inner > doc + 100:
                pg.set_viewport_size({'width': 1280, 'height': min(inner + 400, 30000)}); pg.wait_for_timeout(1500)
                pg.screenshot(path=png)
            else:
                pg.screenshot(path=png, full_page=True)
            shot = os.path.exists(png) and os.path.getsize(png) > 40000
            try: pg.pdf(path=os.path.join(folder_abs, 'JD_원본.pdf'), print_background=True, format='A4')
            except Exception: pass
            try: texts.append(pg.inner_text('body'))
            except Exception: pass
            frames = []
            for f in pg.frames[1:]:
                fu = f.url or ''
                if not fu.startswith('http') or any(a in fu for a in AD): continue
                try: ft = f.inner_text('body')
                except Exception: ft = ''
                if len(ft.strip()) >= 100 or re.search(r'detail|comt|view|recruit|job', fu, re.I):
                    texts.append(ft); frames.append(fu)
            for k, fu in enumerate(frames[:3]):                           # 상세 내용이 별도 창이면 그 창도 통째로 사진
                p2 = ctx.new_page()
                try:
                    p2.goto(fu, wait_until='domcontentloaded', timeout=60000)
                    try: p2.wait_for_load_state('networkidle', timeout=10000)
                    except Exception: pass
                    p2.screenshot(path=os.path.join(folder_abs, 'JD_원본_상세%s.png' % ('' if k == 0 else '_%d' % (k + 1))), full_page=True)
                except Exception: pass
                finally: p2.close()
            # 공고가 긴 그림으로 올라온 경우: 그림 원본 파일 받기 (세로로 긴 큰 그림만 — 로고·배너 제외)
            srcs = []
            for f in [pg.main_frame] + [x for x in pg.frames[1:] if (x.url or '') in frames]:
                try:
                    srcs += f.evaluate("[...document.images].filter(i=>i.naturalWidth>=500&&i.naturalHeight>=900).map(i=>i.currentSrc||i.src)")
                except Exception: pass
            n = 0
            for s in dict.fromkeys(srcs):
                if not s.startswith('http'): continue
                try:
                    r = ctx.request.get(s, timeout=60000)
                    if r.ok and len(r.body()) > 20000:
                        ct = (r.headers.get('content-type') or '').lower()
                        ext = 'png' if 'png' in ct else 'gif' if 'gif' in ct else 'webp' if 'webp' in ct else 'jpg'
                        n += 1; io.open(os.path.join(folder_abs, 'JD_원본_그림_%02d.%s' % (n, ext)), 'wb').write(r.body())
                except Exception: pass
                if n >= 15: break
            tries.append('크롬 전체 화면: 사진 %s · 상세 창 %d개 · 그림 원본 %d장 · 글 %s' % ('받음' if shot else '실패', len(frames), n, '본문 확인' if jd_ok('\n'.join(texts)) else '본문 부족'))
        finally:
            b.close()
    return '\n'.join(texts), shot

def fetch_original(p, folder_abs, tries):
    """여러 방법으로 공고 원본을 받음. 반환 (상태, 추출 글). 상태: ok(글까지 확인) / image(사진·그림으로 받음, 눈 확인 필요) / need(못 받음)"""
    url = (p.get('link') or '').strip()
    if not re.match(r'^https?://', url):
        tries.append('링크 없음'); return 'need', ''
    text, shot = '', False
    # 방법 1: 진짜 크롬으로 열어 전체 화면 사진·PDF·본문(상세 창 포함)
    try:
        text, shot = capture_pw(url, folder_abs, tries)
        if jd_ok(text): return 'ok', text
    except Exception as e:
        tries.append('크롬 전체 화면: 실패 (%s)' % str(e)[:60])
    # 방법 2: 다른 방식(크롬 인쇄·상세 창 직접 열기) — 방법 1이 실패했을 때 보완
    if not shot or not text.strip():
        out = os.path.join(folder_abs, 'JD_원본.pdf')
        if not os.path.exists(out): chrome(['--no-pdf-header-footer', '--print-to-pdf=' + out, url])
        t2 = pdf_text(out) if os.path.exists(out) else ''
        dom = dump_dom(url)
        for m in re.finditer(r'<iframe[^>]+src=["\']([^"\']+)["\']', dom, re.I):
            src = urllib.parse.urljoin(url, _html.unescape(m.group(1)))
            if src.startswith('http') and not any(a in src for a in AD) and re.search(r'detail|comt|view|recruit|job', src, re.I):
                o = os.path.join(folder_abs, 'JD_원본_상세.pdf')
                chrome(['--no-pdf-header-footer', '--print-to-pdf=' + o, src])
                t2 += '\n' + (pdf_text(o) if os.path.exists(o) else '')
                break
        tries.append('크롬 인쇄(PDF): %s' % ('본문 확인' if jd_ok(t2) else '본문 부족'))
        text = text + '\n' + t2
        if jd_ok(text): return 'ok', text
    if shot or any(f.startswith('JD_원본_그림') for f in os.listdir(folder_abs)):
        return 'image', text
    return 'need', text

# ---------------- JD.md (자동 추출본) ----------------
def jd_md(p, qs, status, text, tries):
    due = p.get('due') or ''
    dk = p.get('dueKind') or ''
    dues = (due.replace('T', ' ') if dk == '확정' and due else {'채용시': '채용 시 마감', '미확인': '마감 미확인'}.get(dk, dk))
    st_txt = {'ok': '원본 저장·본문 확인됨', 'image': '그림으로 받음 — 글자 확인 필요', 'need': '⚠️ 원본 확인 필요 (자동으로 못 받음)'}[status]
    L = ['# %s — %s (JD 자동 추출본)' % (p['co'], p.get('role') or p.get('job') or ''), '',
         '> ⚠️ **자동 추출본** (%s 자동 생성). 기업조사 때 `JD_원본` 기준으로 원문 그대로 정리·보완할 것' % TODAY,
         '> 플래너_id: %s' % p['id'],
         '> 공고 링크: %s' % (p.get('link') or '-'),
         '> 마감: %s ｜ 플래너 단계: %s' % (dues or '-', STAGE_NAME.get(p['stage'], p['stage'])),
         '> 원본: %s (%s)' % (st_txt, ' / '.join(tries)), '',
         '## 플래너 정보', '']
    for k, n in (('co', '회사'), ('job', '지원 직무'), ('role', '상세 직무명'), ('type', '유형'), ('ind', '업권'), ('loc', '근무지'), ('applyStart', '접수 시작'), ('steps', '전형 절차'), ('memo', '비고')):
        if p.get(k): L.append('- %s: %s' % (n, p[k]))
    if qs:
        L += ['', '## 자소서 문항 (플래너 기준)', '']
        for i, q in enumerate(qs):
            L.append('%d. %s%s' % (i + 1, q['t'].replace('\n', ' '), (' (%s%s)' % (q['n'], '바이트' if q.get('u') == 'byte' else '자')) if str(q.get('n') or '0') != '0' else ''))
    body = re.sub(r'[ \t]+\n', '\n', INVIS.sub('', text or ''))
    body = re.sub(r'\n{3,}', '\n\n', body).strip()[:30000]
    L += ['', '## 공고 글 (원본에서 자동 추출 — 사이트 메뉴·추천 공고가 섞여 있을 수 있음)', '', body or '(추출한 글 없음 — JD_원본 그림/파일 참고)', '']
    return '\n'.join(L)

# ---------------- 플래너 ----------------
def planner():
    import jaso_sync as J
    return J, J.api('loadAll')['data']['me']

def stage_of_step(s):
    s = str(s or '')
    if re.search(r'1차', s): return '면접1'
    if re.search(r'2차', s): return '면접2'
    if re.search(r'3차|최종|임원', s): return '면접3'
    if re.search(r'인적성|필기|AI|역량|SKCT|코딩|TEST|테스트|과제|검사', s, re.I): return '인적성'
    if re.search(r'면접|인터뷰', s): return '면접1'
    return '면접1'

def sync_stage(J, p, folder, checks):
    """폴더 위치가 더 앞선 단계면 플래너를 맞춤. 플래너가 더 앞서면 '폴더 옮길 것'에 올림"""
    st = folder.split('/')[0]
    target = {'02_지원완료': (2, '제출', ''), '03_면접중': (3, None, ''), '04_불합격': (4, '종료', '불합격'),
              '05_최종합격': (4, '종료', '최종합격'), '06_인재풀': (4, '종료', '인재풀')}.get(st)
    cur = RANK.get(p['stage'], 0)
    if target and target[0] > cur:
        row = {'id': p['id'], 'updated': NOW.strftime('%Y-%m-%d %H:%M')}
        if target[0] == 2:
            row['stage'] = '제출'
            if not p.get('submitted'): row['submitted'] = TODAY
        elif target[0] == 3:
            steps = [x.strip() for x in str(p.get('steps') or '서류').split('>') if x.strip()]
            idx = 1 if len(steps) > 1 else 0
            row['stage'] = stage_of_step(steps[idx]) if idx else '면접1'; row['cur'] = idx
            if not p.get('submitted'): row['submitted'] = TODAY
        else:
            row['stage'] = '종료'; row['result'] = target[2]
        msg = '폴더 위치(%s)에 맞춰 단계 변경: %s → %s%s' % (st, STAGE_NAME.get(p['stage']), STAGE_NAME.get(row['stage']), (' · ' + row['result']) if row.get('result') else '')
        if not DRY:
            J.api('batch', pid='me', ops=[{'op': 'upsert', 'table': 'posts', 'rows': [row]},
                                          {'op': 'upsert', 'table': 'hist', 'rows': [{'id': '%s_h%s' % (p['id'], NOW.strftime('%y%m%d%H%M%S')), 'pid': p['id'], 'd': TODAY, 't': msg}]}])
        log('%s: %s' % (p['co'], msg))
        return
    want = stage_dir_for(p['stage']) if p['stage'] != '종료' else None
    if p['stage'] == '종료' and st in ('01_진행중', '02_지원완료', '03_면접중'):
        checks['move'].append('%s — 플래너는 종료(%s)인데 폴더는 `%s`' % (p['co'], p.get('result') or '결과 미기록', folder))
    elif want and st in STAGE_DIRS and STAGE_DIRS.index(want) > STAGE_DIRS.index(st):
        checks['move'].append('%s — 플래너는 %s인데 폴더는 `%s` → `%s/`로 옮기기' % (p['co'], STAGE_NAME.get(p['stage']), folder, want))

# ---------------- 실행 ----------------
def make_folder(J, p, qs, links, folders):
    st = stage_dir_for(p['stage']) or '01_진행중'
    name = folder_name(p)
    path = st + '/' + name
    k = 2
    while os.path.exists(os.path.join(BASE, path)):
        path = '%s/%s_%d' % (st, name, k); k += 1
    log('%s: 폴더 만들기 → %s' % (p['co'], path))
    rec = {'folder': path, 'co': p['co'], 'made': TODAY, 'orig': 'need', 'tries': []}
    if DRY:
        links[p['id']] = rec; return rec
    absd = os.path.join(BASE, path)
    os.makedirs(absd, exist_ok=True)
    status, text = fetch_original(p, absd, rec['tries'])
    rec['orig'] = status
    io.open(os.path.join(absd, 'JD.md'), 'w', encoding='utf-8').write(jd_md(p, qs, status, text, rec['tries']))
    log('%s: 원본 %s (%s)' % (p['co'], status, ' / '.join(rec['tries'])))
    links[p['id']] = rec
    return rec

def retry_original(p, qs, rec):
    absd = os.path.join(BASE, rec['folder'])
    tries = []
    status, text = fetch_original(p, absd, tries)
    rec['tries'] = (rec.get('tries') or []) + ['[%s 다시] ' % TODAY + ' / '.join(tries)]
    rec['retried'] = rec.get('retried', 0) + 1
    if status != 'need' or rec.get('orig') == 'need':
        rec['orig'] = status if status != 'need' else rec.get('orig')
    jd = os.path.join(absd, 'JD.md')
    try:
        old = io.open(jd, encoding='utf-8').read()
        if '(JD 자동 추출본)' in old:      # 아직 사람이 정리 안 한 자동 추출본일 때만 새로 씀
            io.open(jd, 'w', encoding='utf-8').write(jd_md(p, qs, rec['orig'], text, rec['tries']))
    except Exception:
        pass
    log('%s: 원본 다시 받기 → %s' % (p['co'], rec['orig']))

def write_checks(links, checks):
    if DRY: return
    need = [(pid, r) for pid, r in links.items() if r.get('orig') in ('need', 'image') and not r.get('human')]
    L = ['# 자동 정리 — 확인 필요', '', '> 자동 생성 (%s). `python jd_folders.py --notice` 로도 볼 수 있음' % NOW.strftime('%Y-%m-%d %H:%M'), '']
    if need:
        L += ['## 원본 확인 필요', '']
        for pid, r in need:
            L.append('- **%s** `%s` — %s · 시도: %s' % (r['co'], r['folder'], '그림으로 받음(글자 눈으로 확인)' if r['orig'] == 'image' else '못 받음', ' / '.join(r.get('tries') or [])))
    if checks['move']:
        L += ['', '## 폴더 옮길 것', ''] + ['- ' + x for x in checks['move']]
    if checks['loose']:
        L += ['', '## 연결 애매 (폴더를 못 찾음)', ''] + ['- ' + x for x in checks['loose']]
    if not need and not checks['move'] and not checks['loose']:
        L.append('없음')
    os.makedirs(STATE, exist_ok=True)
    io.open(CHECK_FILE, 'w', encoding='utf-8').write('\n'.join(L) + '\n')

def lock():
    os.makedirs(STATE, exist_ok=True)
    try:
        if os.path.exists(LOCK_FILE) and time.time() - os.path.getmtime(LOCK_FILE) < 1200: return False
        io.open(LOCK_FILE, 'w').write(str(os.getpid())); return True
    except Exception:
        return False

def run(only=None):
    if not DRY and not lock():
        print('다른 자동 정리가 실행 중이에요'); return None
    try:
        J, me = planner()
        posts = me['posts']
        qs_by = {}
        for q in sorted(me['qs'], key=lambda q: int(q.get('i') or 0)): qs_by.setdefault(q['pid'], []).append(q)
        links = load_links()
        folders = all_folders()
        checks = {'move': [], 'loose': []}
        made = None
        for p in posts:
            if only and not (norm(only) in norm(p['co']) or norm(p['co']) in norm(only) or norm(only) == norm(p.get('short'))): continue
            if p['stage'] == '종료' and p['id'] not in links and not only: continue
            rec = links.get(p['id'])
            folder = find_folder(rec, p['id'], folders) if rec else match_existing(p, folders)
            if rec and not folder:
                checks['loose'].append('%s — 기록된 폴더 `%s`를 못 찾음 (지웠거나 이름을 바꿈)' % (p['co'], rec.get('folder')))
                continue
            if folder:
                if not rec:
                    links[p['id']] = rec = {'folder': folder, 'co': p['co'], 'made': '', 'orig': 'existing', 'tries': []}
                elif rec['folder'] != folder:
                    log('%s: 폴더 위치 바뀜 %s → %s' % (p['co'], rec['folder'], folder)); rec['folder'] = folder
                sync_stage(J, p, folder, checks)
                if rec.get('orig') in ('need', 'image') and not rec.get('human') and rec.get('retried', 0) < 3 and not DRY:
                    if rec.get('orig') == 'need' or rec.get('retried', 0) == 0:
                        retry_original(p, qs_by.get(p['id'], []), rec)
                made = made or folder
                continue
            if p['stage'] == '종료': continue
            if not only and (p.get('created') or '') < CUTOFF: continue
            rec = make_folder(J, p, qs_by.get(p['id'], []), links, folders)
            folders = all_folders()
            made = made or rec['folder']
        save_links(links)
        write_checks(links, checks)
        return made
    finally:
        if not DRY:
            try: os.remove(LOCK_FILE)
            except Exception: pass

def notice():
    try:
        t = io.open(CHECK_FILE, encoding='utf-8').read()
    except Exception:
        return
    if '## ' not in t: return
    print('[구직 지원서 자동 정리] 확인할 것이 있어요 (' + CHECK_FILE + '):')
    print(t.split('\n', 3)[-1].strip())
    print('→ 원본 확인 필요는 Claude in Chrome(로그인된 크롬)·다른 게시처 찾기까지 여러 방법을 다 해 본 뒤에만 민석님께 캡처를 요청할 것. 해결하면 --done 회사명')

def mark_done(name):
    links = load_links()
    hit = [r for r in links.values() if norm(name) in norm(r.get('co'))]
    for r in hit: r['human'] = TODAY; r['orig'] = 'ok'
    save_links(links); write_checks(links, {'move': [], 'loose': []})
    print('확인 완료로 표시: %d건 (다음 자동 확인 때 목록 다시 정리)' % len(hit))

if __name__ == '__main__':
    a = [x for x in sys.argv[1:] if x != '--dry']
    if a[:1] == ['--notice']: notice()
    elif a[:1] == ['--done'] and len(a) > 1: mark_done(' '.join(a[1:]))
    elif a[:1] == ['--retry'] and len(a) > 1:
        links = load_links(); J, me = planner()
        for p in me['posts']:
            r = links.get(p['id'])
            if r and norm(' '.join(a[1:])) in norm(p['co']):
                r['retried'] = 0; retry_original(p, [q for q in me['qs'] if q['pid'] == p['id']], r)
        save_links(links); write_checks(links, {'move': [], 'loose': []})
    elif a[:1] == ['--now'] and len(a) > 1:
        f = run(' '.join(a[1:]))
        print('폴더: ' + (os.path.join(BASE, f) if f else '(플래너에서 그 회사 공고를 못 찾았어요 — 앱에 먼저 등록하거나 회사명을 확인해 주세요)'))
    elif not a: run()
    else: print(__doc__)

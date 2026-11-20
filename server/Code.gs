/**
 * 구직 플래너 서버 (Google Apps Script 웹 앱)
 * - 민석 드라이브에 사람별 시트 2개(민석·건희)를 만들고 읽기·쓰기
 * - 공고 자동 정리: Claude API 호출 (API 키는 스크립트 속성 ANTHROPIC_API_KEY 에만 저장)
 * - 비밀 값(비밀번호·API 키·시트 id)은 코드에 넣지 않고 스크립트 속성에 보관
 *
 * 스크립트 속성
 *   APP_PW             앱 비밀번호 (편집기 > 프로젝트 설정 > 스크립트 속성에서 직접 정함)
 *   ANTHROPIC_API_KEY  Claude API 키 (민석님이 직접 입력)
 *   DAILY_LIMIT        공고 정리 하루 한도 (기본 30)
 *   SHEET_me, SHEET_gh 시트 id (자동 생성)
 */

const PEOPLE = { me: '민석', gh: '건희' };
const MODEL = 'claude-opus-5-5';

const SCHEMA = {
  posts: { tab: '공고', cols: [['id','id'],['co','회사'],['job','지원 직무'],['role','상세 직무명'],['type','유형'],['ind','업권'],['loc','근무지'],
    ['link','공고 링크'],['relLink','관련 자료'],['applyStart','접수 시작'],['dueKind','마감 종류'],['due','마감'],['recheck','재확인일'],
    ['stage','단계'],['result','결과'],['failAt','탈락 단계'],['submitted','제출일'],['steps','전형 절차'],['cur','현재 전형'],
    ['memo','비고'],['src','등록 경로'],['created','생성일'],['updated','수정일'],['short','달력 표시 이름']] },
  qs: { tab: '문항', cols: [['id','id'],['pid','공고 id'],['i','순번'],['t','문항'],['n','글자 수'],['a','답변'],['st','상태'],['lock','잠금']] },
  events: { tab: '일정', cols: [['id','id'],['pid','공고 id'],['d','날짜'],['k','종류'],['t','내용']] },
  tasks: { tab: '할 일', cols: [['id','id'],['pid','공고 id'],['t','내용'],['due','기한'],['done','완료'],['doneAt','완료일'],['auto','자동']] },
  comments: { tab: '댓글', cols: [['id','id'],['pid','공고 id'],['qi','문항 번호'],['quote','고른 문장'],['text','내용'],['by','작성자'],['at','작성일'],
    ['replies','답글'],['resolved','해결'],['read','읽음']] },
  hist: { tab: '이력', cols: [['id','id'],['pid','공고 id'],['d','날짜'],['t','내용']] },
  settings: { tab: '설정', cols: [['k','항목'],['v','값']] }
};

/* ---------- 진입점 ---------- */
function doGet() {
  return out_({ ok: true, app: 'job-planner', msg: '구직 플래너 서버가 동작 중이에요.' });
}

function doPost(e) {
  let req;
  try { req = JSON.parse(e.postData.contents); } catch (err) { return out_({ ok: false, error: 'bad_request' }); }
  try {
    const gate = checkPw_(req.pw);
    if (gate) return out_({ ok: false, error: gate });
    switch (req.action) {
      case 'ping': return out_({ ok: true, people: PEOPLE, usage: usage_() });
      case 'load': return out_({ ok: true, who: req.who, tables: loadAll_(who_(req.who)) });
      case 'loadAll': return out_({ ok: true, data: { me: loadAll_('me'), gh: loadAll_('gh') }, usage: usage_(),
        sheets: { me: book_('me').getUrl(), gh: book_('gh').getUrl() } });
      case 'batch': return out_(batch_(who_(req.who), req.ops || []));
      case 'extract': return out_(extract_(req.input || {}));
      default: return out_({ ok: false, error: 'unknown_action' });
    }
  } catch (err) {
    console.error(err && err.stack || err);
    return out_({ ok: false, error: 'server_error', detail: String(err && err.message || err) });
  }
}

/** 편집기에서 한 번 실행: 권한 허용 + 시트 2개 생성 + 기본 비밀번호 */
function setup() {
  const p = props_();
  if (!p.getProperty('APP_PW')) throw new Error('스크립트 속성 APP_PW(앱 비밀번호)를 먼저 정해 주세요');
  if (!p.getProperty('DAILY_LIMIT')) p.setProperty('DAILY_LIMIT', '30');
  Object.keys(PEOPLE).forEach(w => { const b = book_(w); Object.keys(SCHEMA).forEach(t => sheet_(b, t)); });
  UrlFetchApp.fetch('https://api.anthropic.com', { muteHttpExceptions: true }); // 외부 요청 권한 미리 받기
  console.log('완료: 민석 시트 ' + book_('me').getUrl() + ' / 건희 시트 ' + book_('gh').getUrl());
}

/* ---------- 공통 ---------- */
function out_(o) { return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON); }
function props_() { return PropertiesService.getScriptProperties(); }
function who_(w) { if (!PEOPLE[w]) throw new Error('알 수 없는 사람: ' + w); return w; }

function checkPw_(pw) {
  const cache = CacheService.getScriptCache();
  const fails = Number(cache.get('pw_fail') || 0);
  if (fails >= 20) return 'locked';
  const real = props_().getProperty('APP_PW');
  if (!real) return 'no_password_set';
  if (String(pw || '') !== real) { cache.put('pw_fail', String(fails + 1), 600); return 'bad_password'; }
  return '';
}

function book_(w) {
  const p = props_(), key = 'SHEET_' + w;
  const id = p.getProperty(key);
  if (id) { try { return SpreadsheetApp.openById(id); } catch (e) { /* 지워졌으면 새로 만듦 */ } }
  const b = SpreadsheetApp.create('구직 플래너 데이터 - ' + PEOPLE[w]);
  p.setProperty(key, b.getId());
  Object.keys(SCHEMA).forEach(t => sheet_(b, t));
  const first = b.getSheets().find(s => !Object.keys(SCHEMA).some(t => SCHEMA[t].tab === s.getName()));
  if (first && b.getSheets().length > 1) b.deleteSheet(first);
  return b;
}

function sheet_(b, table) {
  const def = SCHEMA[table];
  let sh = b.getSheetByName(def.tab);
  if (!sh) {
    sh = b.insertSheet(def.tab);
    sh.getRange(1, 1, 1, def.cols.length).setValues([def.cols.map(c => c[1])]).setFontWeight('bold');
    sh.setFrozenRows(1);
    sh.getRange(1, 1, sh.getMaxRows(), def.cols.length).setNumberFormat('@');
  } else if (sh.getLastColumn() < def.cols.length) { // 칸이 새로 생겼으면 머리글을 채움
    sh.getRange(1, 1, 1, def.cols.length).setValues([def.cols.map(c => c[1])]).setFontWeight('bold');
    sh.getRange(1, 1, sh.getMaxRows(), def.cols.length).setNumberFormat('@');
  }
  return sh;
}

function readTable_(b, table) {
  const def = SCHEMA[table], sh = sheet_(b, table);
  const last = sh.getLastRow();
  if (last < 2) return [];
  const vals = sh.getRange(2, 1, last - 1, def.cols.length).getDisplayValues();
  return vals.filter(r => r.some(v => v !== '')).map(r => { const o = {}; def.cols.forEach((c, i) => o[c[0]] = r[i]); return o; });
}

function writeTable_(b, table, rows) {
  const def = SCHEMA[table], sh = sheet_(b, table);
  const last = sh.getLastRow();
  if (last >= 2) sh.getRange(2, 1, last - 1, def.cols.length).clearContent();
  if (!rows.length) return;
  const vals = rows.map(o => def.cols.map(c => o[c[0]] == null ? '' : String(o[c[0]])));
  if (sh.getMaxRows() < vals.length + 1) sh.insertRowsAfter(sh.getMaxRows(), vals.length + 1 - sh.getMaxRows());
  sh.getRange(2, 1, vals.length, def.cols.length).setNumberFormat('@').setValues(vals);
}

function loadAll_(w) {
  const b = book_(w), t = {};
  Object.keys(SCHEMA).forEach(k => t[k] = readTable_(b, k));
  return t;
}

/**
 * ops: [{op:'replace', table, key, value, rows}, {op:'upsert', table, rows, key?}, {op:'remove', table, key, value}]
 * 표마다 한 번 읽고, 바꾼 뒤 한 번에 씀 (칸 하나씩 쓰지 않음)
 */
function batch_(w, ops) {
  const lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    const b = book_(w), cache = {};
    const get = t => { if (!SCHEMA[t]) throw new Error('알 수 없는 표: ' + t); if (!cache[t]) cache[t] = readTable_(b, t); return cache[t]; };
    ops.forEach(op => {
      const rows = get(op.table);
      if (op.op === 'replace') {
        cache[op.table] = rows.filter(r => r[op.key] !== String(op.value)).concat(op.rows || []);
      } else if (op.op === 'upsert') {
        const key = op.key || (op.table === 'settings' ? 'k' : 'id');
        (op.rows || []).forEach(n => {
          const i = rows.findIndex(r => r[key] === String(n[key]));
          if (i >= 0) rows[i] = Object.assign({}, rows[i], n); else rows.push(n);
        });
      } else if (op.op === 'remove') {
        cache[op.table] = rows.filter(r => r[op.key] !== String(op.value));
      }
    });
    Object.keys(cache).forEach(t => writeTable_(b, t, cache[t]));
    return { ok: true, at: new Date().toISOString() };
  } finally {
    lock.releaseLock();
  }
}

/* ---------- 공고 자동 정리 ---------- */
function usageKey_() { return 'USAGE_' + Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyyMMdd'); }
function usage_() {
  const p = props_();
  return { used: Number(p.getProperty(usageKey_()) || 0), limit: Number(p.getProperty('DAILY_LIMIT') || 30), hasKey: !!p.getProperty('ANTHROPIC_API_KEY') };
}

function pageText_(url) {
  const res = UrlFetchApp.fetch(url, { muteHttpExceptions: true, followRedirects: true,
    headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36', 'Accept-Language': 'ko-KR,ko;q=0.9' } });
  if (res.getResponseCode() >= 400) return '';
  let html = res.getContentText();
  const meta = [];
  html.replace(/<meta[^>]+(?:property|name)=["'](?:og:title|og:description|description)["'][^>]*content=["']([^"']+)["'][^>]*>/gi, (m, c) => { meta.push(c); return m; });
  const text = html.replace(/<script[\s\S]*?<\/script>/gi, ' ').replace(/<style[\s\S]*?<\/style>/gi, ' ').replace(/<noscript[\s\S]*?<\/noscript>/gi, ' ')
    .replace(/<br\s*\/?>/gi, '\n').replace(/<\/(p|div|li|tr|h\d)>/gi, '\n').replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'")
    .replace(/[ \t]+/g, ' ').replace(/\n\s*\n+/g, '\n').trim();
  return (meta.join('\n') + '\n' + text).trim().slice(0, 60000);
}

function extract_(input) {
  const p = props_(), u = usage_();
  const key = p.getProperty('ANTHROPIC_API_KEY');
  if (!key) return { ok: false, error: 'no_api_key' };
  if (u.used >= u.limit) return { ok: false, error: 'limit', usage: u };

  const content = [];
  let pageTxt = '';
  if (input.url) {
    pageTxt = pageText_(input.url);
    if (pageTxt.length < 400 && !(input.images && input.images.length) && !input.text) return { ok: false, error: 'need_capture' };
  }
  (input.images || []).slice(0, 8).forEach(img => {
    content.push({ type: 'image', source: { type: 'base64', media_type: img.type || 'image/jpeg', data: img.data } });
  });
  const today = Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd');
  const jobs = (input.jobs && input.jobs.length ? input.jobs : ['영업','자산운용','채권운용','자금','재무/회계','경영지원/기획','리스크/심사','사업개발']).join(', ');
  content.push({ type: 'text', text:
    '아래 채용 공고에서 정보를 뽑아 JSON으로 정리해 주세요. 오늘은 ' + today + ' (한국 시간)입니다.\n' +
    '규칙\n' +
    '- 공고에 없는 정보는 지어내지 말고 빈 문자열 "" (숫자는 0, 목록은 [])\n' +
    '- job: 다음 중 가장 가까운 것 하나 (맞는 게 없으면 ""): ' + jobs + '\n' +
    '- role: 공고에 적힌 직무명 그대로 · type: 인턴/정규직/계약직 중 하나(채용연계형·전환형 인턴도 "인턴") · ind: 은행/증권/자산운용/저축은행/캐피탈/카드/보험/공기업/일반기업/기타 중 하나\n' +
    '- 마감: 날짜와 시각이 있으면 dueKind "확정", due "YYYY-MM-DDTHH:MM" (시각이 없으면 23:59). "채용 시 마감"이면 dueKind "채용시". 알 수 없으면 "미확인". 연도가 없으면 오늘 이후 가장 가까운 날짜로\n' +
    '- applyStart: 접수 시작일 "YYYY-MM-DD" (없으면 "")\n' +
    '- steps: 전형 순서 (예: ["서류","인적성","1차 면접","최종 면접"])\n' +
    '- events: 공고에 날짜가 나온 전형 일정만 (k: apt=인적성·AI역량, int=면접, ann=결과 발표, etc=기타). 서류 마감은 넣지 않음\n' +
    '- qs: 자기소개서 문항을 **원문 그대로** (요약·수정 금지), n은 글자 수 제한 (없으면 0)\n' +
    '- memo: "고용형태 · 근무지 · 주요 업무 · 전형 · 우대 · 마감 시각" 순서로 한 줄 요약 (가운뎃점으로 구분, 공고에 있는 것만)\n' +
    '- short: 휴대폰 달력의 좁은 칸에 쓸 회사 줄임말. 한글 2~4자 또는 영문 약자 2~5자로 널리 쓰는 이름 (예: SK네트웍스서비스→SKNS, 고영테크놀러지→고영, 한국투자증권→한투)\n' +
    (input.text ? '\n[붙여넣은 공고 본문]\n' + String(input.text).slice(0, 60000) + '\n' : '') +
    (pageTxt ? '\n[링크에서 가져온 내용] ' + input.url + '\n' + pageTxt + '\n' : '') +
    ((input.images || []).length ? '\n[위 이미지는 공고 화면 캡처입니다]\n' : '')
  });

  const schema = { type: 'object', additionalProperties: false,
    required: ['co','short','job','role','type','ind','loc','applyStart','dueKind','due','steps','events','qs','memo'],
    properties: {
      co: { type: 'string' }, short: { type: 'string' }, job: { type: 'string' }, role: { type: 'string' },
      type: { type: 'string', enum: ['', '인턴', '정규직', '계약직'] },
      ind: { type: 'string', enum: ['', '은행', '증권', '자산운용', '저축은행', '캐피탈/카드', '보험', '공기업', '일반기업', '기타'] },
      loc: { type: 'string' }, applyStart: { type: 'string' },
      dueKind: { type: 'string', enum: ['확정', '채용시', '미확인'] }, due: { type: 'string' },
      steps: { type: 'array', items: { type: 'string' } },
      events: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['d','k','t'],
        properties: { d: { type: 'string' }, k: { type: 'string', enum: ['apt','int','ann','etc'] }, t: { type: 'string' } } } },
      qs: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['t','n'], properties: { t: { type: 'string' }, n: { type: 'integer' } } } },
      memo: { type: 'string' }
    } };

  const body = {
    model: MODEL, max_tokens: 8000,
    output_config: { effort: 'low', format: { type: 'json_schema', schema: schema } },
    fallbacks: 'default',
    messages: [{ role: 'user', content: content }]
  };
  const call = (b, beta) => UrlFetchApp.fetch('https://api.anthropic.com/v1/messages', {
    method: 'post', contentType: 'application/json', muteHttpExceptions: true,
    headers: Object.assign({ 'x-api-key': key, 'anthropic-version': '2026-10-21' }, beta ? { 'anthropic-beta': 'server-side-fallback-2026-07-01' } : {}),
    payload: JSON.stringify(b)
  });
  let res = call(body, true);
  if (res.getResponseCode() === 400 && /fallback/i.test(res.getContentText())) { // 거절 대비 옵션이 안 맞으면 옵션 없이 다시
    delete body.fallbacks; res = call(body, false);
  }
  const code = res.getResponseCode();
  const txt = res.getContentText();
  if (code !== 200) {
    console.error('Claude API ' + code + ' ' + txt.slice(0, 1000));
    return { ok: false, error: code === 429 ? 'rate_limited' : code === 401 ? 'bad_api_key' : 'api_error', detail: txt.slice(0, 300) };
  }
  const msg = JSON.parse(txt);
  p.setProperty(usageKey_(), String(u.used + 1));
  if (msg.stop_reason === 'refusal') return { ok: false, error: 'refusal' };
  if (msg.stop_reason === 'max_tokens') return { ok: false, error: 'too_long' };
  const t = (msg.content || []).filter(c => c.type === 'text').map(c => c.text).join('');
  let data;
  try { data = JSON.parse(t); } catch (e) { return { ok: false, error: 'parse_error' }; }
  return { ok: true, data: data, usage: usage_() };
}

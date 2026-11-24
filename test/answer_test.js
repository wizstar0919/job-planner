// 답변 바로 쓰기 시험: 공고 상세에서 [정보 수정] 없이 그 자리에서 답변 쓰기·고치기·취소, 잠금·공유 보기 제한 (jsdom)
//   node test/answer_test.js [index.html]   → 줄마다 OK/FAIL, 맨 끝에 ERRORS
const fs = require('fs'), path = require('path'), H = require('./harness');
const html = fs.readFileSync(process.argv[2] || path.join(__dirname, '..', 'index.html'), 'utf8');
const { sleep, T } = H;
const log = [], ck = (n, c) => log.push((c ? 'OK ' : 'FAIL ') + n);

function mkStore() {
  const t = T(), g = T();
  t.settings.push({ k: 'onb', v: '1' });
  t.posts.push({ id: 'p1', co: '답변회사', job: '제품영업', role: '영업', stage: '작성중', dueKind: '미확인', steps: '서류', cur: '0', rev: 'r1' });
  t.qs.push({ id: 'q1', pid: 'p1', i: '0', t: '빈 문항', n: '100', a: '', st: '미작성', ver: '' });
  t.qs.push({ id: 'q2', pid: 'p1', i: '1', t: '쓴 문항', n: '100', a: '예전 답변', st: '초안', ver: '' });
  t.qs.push({ id: 'q3', pid: 'p1', i: '2', t: '낸 문항', n: '100', a: '제출한 답변', st: '제출본', lock: 'Y', ver: '' });
  g.posts.push({ id: 'g1', co: '남의회사', stage: '작성중', dueKind: '미확인', steps: '서류', cur: '0', rev: 'r1' });
  g.qs.push({ id: 'gq1', pid: 'g1', i: '0', t: '남의 문항', n: '0', a: '', st: '미작성', ver: '' });
  return { me: t, gh: g };
}
const meta = { email: 'me@example.com', me: 'me', status: '승인', names: { me: '민석', gh: '건희' },
  planners: [{ id: 'me', name: '민석', owner: 'me@example.com', role: 'owner', shares: [] },
             { id: 'gh', name: '건희', owner: 'gh@example.com', role: 'comment', shares: [] }] };
const q = (A, id) => A.store.me.qs.find(x => x.id === id);
const typeA = (A, v) => { const ta = A.d.querySelector('#ansTa'); ta.value = v; ta.dispatchEvent(new A.w.Event('input', { bubbles: true })); };

(async () => { try {
  {
    const A = H.app(html, { store: mkStore(), meta, co: '답변회사' }); await sleep(80); A.openP1();
    const empty = A.d.querySelector('.q[data-qi="0"] [data-act="edit-a"]');
    ck('empty answer: click-to-write box (no 정보 수정 needed)', !!empty && empty.textContent.includes('답변 쓰기'));
    ck('written answer: 고치기 button', !!A.d.querySelector('.q[data-qi="1"] .qbar [data-act="edit-a"]'));
    ck('submitted (locked) answer: no edit button', !A.d.querySelector('.q[data-qi="2"] [data-act="edit-a"]'));
    A.click(empty);
    ck('textarea opens in place', !!A.d.querySelector('.q[data-qi="0"] #ansTa') && !A.d.querySelector('[data-act="ed-save"]'));
    typeA(A, '새 답변 열자');
    ck('counter updates while typing', A.d.querySelector('#ansCnt').textContent.replace(/\s/g, '').startsWith('7/'));
    A.click('[data-act="close"]');
    ck('close blocked while unsaved', !!A.d.querySelector('#ansTa'));
    A.click('.q[data-qi="1"] [data-act="edit-a"]');
    ck('switching question blocked while unsaved', !!A.d.querySelector('.q[data-qi="0"] #ansTa'));
    A.refresh && await A.refresh();
    ck('typing survives background refresh', A.d.querySelector('#ansTa') && A.d.querySelector('#ansTa').value === '새 답변 열자');
    A.click('[data-act="save-a"]'); await sleep(1600);
    ck('saved to server, 미작성 → 초안', q(A, 'q1').a === '새 답변 열자' && q(A, 'q1').st === '초안');
    ck('textarea closed after save', !A.d.querySelector('#ansTa'));
    A.click('.q[data-qi="1"] [data-act="edit-a"]');
    ck('고치기 opens with old text', A.d.querySelector('.q[data-qi="1"] #ansTa').value === '예전 답변');
    typeA(A, '바꾼 답변'); A.click('[data-act="cancel-a"]'); await sleep(300);
    ck('취소 keeps old answer', q(A, 'q2').a === '예전 답변' && !A.d.querySelector('#ansTa') && A.d.querySelector('.q[data-qi="1"] .ans').textContent.includes('예전 답변'));
    A.click('.q[data-qi="1"] [data-act="edit-a"]');
    A.d.dispatchEvent(new A.w.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    ck('Esc with no change closes editor only', !A.d.querySelector('#ansTa') && !!A.d.querySelector('.q[data-qi="1"]'));
    ck('no script errors', !A.errs.length);
  }
  {
    const A = H.app(html, { store: mkStore(), meta, co: '남의회사' }); await sleep(80);
    A.click('#profBtn'); A.click('[data-act="view"][data-v="gh"]'); await sleep(20);
    A.openP1();
    ck('shared planner: no write box, no 고치기', !!A.d.querySelector('.q') && !A.d.querySelector('[data-act="edit-a"]') && A.d.querySelector('.q .ans').textContent.includes('아직 답변이 없어요'));
  }
} catch (e) { log.push('ERROR ' + (e && e.stack || e)); }
  console.log(log.join('\n'));
  const bad = log.filter(x => !x.startsWith('OK'));
  console.log('ERRORS: ' + (bad.length ? JSON.stringify(bad) : 'none'));
  process.exit(bad.length ? 1 : 0);
})();

const {JSDOM}=require('jsdom');const fs=require('fs');
const html=fs.readFileSync(process.argv[2],'utf8');
// 가짜 서버 (Code.gs batch 규칙 흉내)
const store={me:{posts:[],qs:[],events:[],tasks:[],comments:[],hist:[],settings:[]},gh:{posts:[],qs:[],events:[],tasks:[],comments:[],hist:[],settings:[]}};
const str=o=>{const r={};for(const k in o)r[k]=o[k]==null?'':String(o[k]);return r};
let calls=[];
function server(body){const b=JSON.parse(body);calls.push(b.action);
 if(b.pw!=='0000')return {ok:false,error:'bad_password'};
 if(b.action==='loadAll')return {ok:true,data:JSON.parse(JSON.stringify(store)),usage:{used:0,limit:30,hasKey:true},sheets:{me:'https://docs.google.com/x',gh:'https://docs.google.com/y'}};
 if(b.action==='batch'){const T=store[b.who];b.ops.forEach(op=>{let rows=T[op.table];
   if(op.op==='replace')T[op.table]=rows.filter(r=>r[op.key]!==String(op.value)).concat(op.rows.map(str));
   else if(op.op==='upsert'){const key=op.table==='settings'?'k':'id';op.rows.forEach(n=>{n=str(n);const i=rows.findIndex(r=>r[key]===n[key]);if(i>=0)rows[i]=Object.assign({},rows[i],n);else rows.push(n)})}
   else if(op.op==='remove')T[op.table]=rows.filter(r=>r[op.key]!==String(op.value))});return {ok:true}}
 if(b.action==='extract')return {ok:true,usage:{used:1,limit:30,hasKey:true},data:{co:'테스트전자',job:'영업',role:'B2B 영업',type:'정규직',ind:'일반기업',loc:'서울',applyStart:'',dueKind:'확정',due:'2026-12-01T18:00',steps:['서류','면접'],events:[{d:'2026-12-10',k:'int',t:'1차 면접'}],qs:[{t:'지원 동기를 쓰시오.',n:800}],memo:'정규직 · 서울'}};
 return {ok:false,error:'unknown'}}
function makeDom(){const dom=new JSDOM(html,{runScripts:'outside-only',pretendToBeVisual:true,url:'https://wizstar0919.github.io/job-planner/#s=https%3A%2F%2Fscript.google.com%2Fmacros%2Fs%2FX%2Fexec'});
 const w=dom.window;w.fetch=async(url,opt)=>({json:async()=>server(opt.body)});
 return dom}
let dom=makeDom();let w=dom.window,d=w.document;const errs=[];w.addEventListener('error',e=>errs.push(e.message));
const runScripts=()=>{const s=[...d.querySelectorAll('script')].map(x=>x.textContent).join('\n');w.eval(s)};
runScripts();
const click=s=>{const el=typeof s==='string'?d.querySelector(s):s;if(!el)throw new Error('missing '+s);el.dispatchEvent(new w.MouseEvent('click',{bubbles:true}))};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));const log=[];const ck=(n,c)=>log.push((c?'OK ':'FAIL ')+n);
(async()=>{try{
 ck('start, server from hash (no server field)',!!d.querySelector('.start')&&!d.querySelector('#srvIn')&&!!d.querySelector('#pwIn'));
 d.querySelector('#pwIn').value='1111';click('.pcard[data-v="me"]');await sleep(50);ck('wrong pw msg',d.querySelector('#pwMsg').textContent.includes('비밀번호'));
 d.querySelector('#pwIn').value='0000';d.querySelector('#remember').checked=true;d.querySelector('#remember').dispatchEvent(new w.Event('change',{bubbles:true}));
 click('.pcard[data-v="me"]');await sleep(50);ck('entered (home on narrow)',d.querySelector('#profName').textContent==='민석');
 click('.side [data-act="add"]');d.querySelector('#aLink').value='https://example.com/job';click('[data-act="extract"]');await sleep(50);
 ck('review from extract',d.querySelector('#fCo')&&d.querySelector('#fCo').value==='테스트전자');
 click('[data-act="form-save"]');await sleep(800);
 ck('saved to server posts',store.me.posts.length===1&&store.me.posts[0].co==='테스트전자');
 ck('qs/events/tasks saved',store.me.qs.length===1&&store.me.events.length===1&&store.me.tasks.some(t=>t.t==='제출 전 최종 점검'));
 ck('view mode has no inputs',!d.querySelector('.sheet #evT')&&!d.querySelector('.sheet [data-f]'));
 click('[data-act="edit"]');ck('edit mode inline',!!d.querySelector('.sheet #fCo')&&!!d.querySelector('.sheet #evT'));
 d.querySelector('.sheet [data-q="0"][data-qf="a"]').value='제 지원 동기는 이렇습니다.';d.querySelector('.sheet #fLoc').value='판교';click('[data-act="ed-save"]');await sleep(800);
 ck('edit saved loc',store.me.posts[0].loc==='판교');
 ck('answer saved',store.me.qs[0].a==='제 지원 동기는 이렇습니다.'&&store.me.qs[0].st==='초안');
 click('[data-act="submit-done"]');await sleep(800);ck('stage 제출 + 결과 확인 task',store.me.posts[0].stage==='제출'&&store.me.tasks.some(t=>t.t==='결과 확인'));
 click('[data-act="close"]');
 // 건희로 전환 → 민석 공고에 댓글
 click('#profBtn');click('[data-act="switch"][data-v="gh"]');click('#peekBtn');click('.nav-btn[data-v="board"]');
 const card=[...d.querySelectorAll('.card')].find(c=>c.textContent.includes('테스트전자'))||d.querySelector('.card');
 S_open=card;click(card);
 const ans=d.querySelector('.ans[data-qi="0"]');const range=d.createRange();range.selectNodeContents(ans);const sel=w.getSelection();sel.removeAllRanges();sel.addRange(range);d.dispatchEvent(new w.Event('selectionchange'));
 click('[data-act="sel-c"]');d.querySelector('#cTxt').value='좋아요';click('[data-act="c-ok"]');await sleep(800);
 ck('comment saved to 민석 sheet by gh',store.me.comments.length===1&&store.me.comments[0].by==='gh'&&store.me.comments[0].read==='');
 ck('gh did not overwrite post',store.me.posts[0].stage==='제출');
 // 새 창(재접속) → 캐시/remember 로 바로 입장, 민석 새 댓글
 dom=makeDom();w=dom.window;d=w.document;
 // localStorage는 창마다 다르므로 복사
 runScripts();await sleep(50);
 ck('fresh device shows start',!!d.querySelector('.start'));
 d.querySelector('#pwIn').value='0000';click('.pcard[data-v="me"]');await sleep(50);
 click('.nav-btn[data-v="home"]');ck('민석 home new comment',d.querySelector('#main').textContent.includes('새 댓글'));
 click('[data-act="open-c"]');await sleep(800);ck('marked read',store.me.comments[0].read==='Y');
 click('[data-act="close"]');click('.nav-btn[data-v="board"]');click(d.querySelector('.card'));console.log('cards',d.querySelectorAll('.card').length,'sheet',!!d.querySelector('.sheet'),'delbtn',!!d.querySelector('[data-act="del"]'));click('[data-act="edit"]');click('[data-act="del"]');console.log('yes',!!d.querySelector('[data-act="del-yes"]'));click('[data-act="del-yes"]');await sleep(800);
 console.log(JSON.stringify({p:store.me.posts.length,q:store.me.qs.length,c:store.me.comments.length,t:store.me.tasks.map(x=>x.t),h:store.me.hist.length,sheet:!!d.querySelector(".sheet"),del:!!d.querySelector("[data-act=del-yes]")}));ck("deleted everywhere",store.me.posts.length===0&&store.me.qs.length===0&&store.me.comments.length===0&&store.me.tasks.length===0);
}catch(e){errs.push('TEST '+e.stack)}
 console.log(log.join('\n'));console.log('calls:',calls.join(','));console.log('ERRORS:',errs.length?errs:'none');process.exit(0)})();

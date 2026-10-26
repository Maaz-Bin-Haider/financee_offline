const assert = require('node:assert/strict');
const S = require('../static/js/spotlight.js');
const R = require('../static/js/record_link.js');
let n = 0;
function check(name, fn) { fn(); n++; console.log('PASS:', name); }
check('strict decimal record IDs', () => {
  for(const value of ['0','-1','1.0','1e2','²','01','9007199254740992','1;alert(1)']) assert.equal(R.number(value),null);
  assert.equal(R.number('9007199254740991'),'9007199254740991');
});
check('consume only link parameters and preserve other state', () => {
  assert.deepEqual(R.split('?open=7&foo=bar&open=8&report=serial',['open','report']),{
    values:{open:'7',report:'serial'},found:true,search:'?foo=bar'});
});
check('reject off-origin and control-character navigation', () => {
  for(const path of ['//example.test','https://example.test','javascript:alert(1)','/\\example.test','/x\ny']) assert.equal(S.safePath(path),false);
  assert.equal(S.safePath('/sale/sales/?open=4'),true);
});
check('recents persist identifiers only and deduplicate', () => {
  const row={kind:'party',id:'4',name:'PRIVATE CUSTOMER',meta:'PRIVATE BALANCE'};
  assert.deepEqual(S.remember(['party:4','item:3'],row),['party:4','item:3']);
  assert(!JSON.stringify(S.remember([],row)).includes('PRIVATE'));
});
check('recents are bounded and unsupported kinds cannot be saved', () => {
  assert.equal(S.remember(Array.from({length:15},(_,i)=>'party:'+i),{kind:'sale',id:'3'}).length,10);
  assert.deepEqual(S.remember([],{kind:'action',id:'sale:3'}),[]);
});
check('highlight keeps malicious content as plain text segments', () => {
  const text='<img src=x onerror=alert(1)>';
  assert.equal(S.segments(text,'img').map(part=>part.text).join(''),text);
  assert.equal(S.segments(text,'img').find(part=>part.mark).text,'img');
});
check('highlight matches separate words without regex interpretation', () => {
  assert.equal(S.segments('A+B Phone','a+b phone').filter(p=>p.mark).map(p=>p.text).join('|'),'A+B|Phone');
});
console.log(n + ' Spotlight core checks passed');

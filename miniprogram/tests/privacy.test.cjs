const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../utils/seller-api.js'),'utf8');
function setup(failLogout=false){
  const store=new Map(), calls=[];
  const config={apiBase:'https://seller.example.com/api/seller-agent/v1',authMode:'wechat'};
  const wx={getStorageSync:k=>store.get(k),setStorageSync:(k,v)=>store.set(k,v),removeStorageSync:k=>store.delete(k),
    login:o=>{calls.push('wx.login');o.success({code:'temporary-code'});},
    request:o=>{calls.push(o.url);if(failLogout&&o.url.endsWith('/logout/'))return o.fail({errMsg:'network'});
      o.success({statusCode:200,data:o.url.endsWith('/login/')?{token:'test-token',expires_at:new Date(Date.now()+3600000).toISOString()}: {}});}};
  const module={exports:{}};
  vm.runInNewContext(source,{module,require:n=>n==='../config'?config:{privacyVersion:'v1'},wx,Date,Math,Promise,Error,JSON});
  return {api:module.exports,calls,store};
}
test('no consent means no WeChat login or backend request, even with a cached token',async()=>{
  const {api,calls}=setup();api.write('session',{token:'old',expires_at:new Date(Date.now()+3600000).toISOString()});
  await assert.rejects(api.connect(),/privacy/);assert.equal(calls.length,0);
});
test('explicit current privacy consent permits login and session storage',async()=>{
  const {api,calls}=setup();api.write('privacy-consent','v1');await api.connect();
  assert.equal(calls.length,2);assert.equal(api.read('session').token,'test-token');
});
test('sign-out revokes the session and clears pending personal data',async()=>{
  const {api,store,calls}=setup();['session','conversation','pending:message','pending:change','privacy-consent'].forEach(k=>api.write(k,{token:'test'}));
  await api.logout();assert.equal(store.size,0);assert(calls[0].endsWith('/logout/'));
});
test('failed network revocation still clears all device credentials and consent',async()=>{
  const {api,store}=setup(true);api.write('session',{token:'test'});api.write('pending:message',{text:'private'});
  await assert.rejects(api.logout());assert.equal(store.size,0);
});

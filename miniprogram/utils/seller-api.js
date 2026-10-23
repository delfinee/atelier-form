const config=require('../config');
const publicInfo=require('../public-config');
const prefix='atelier-seller-v1:'+config.apiBase+':'+config.authMode+':';
const read=name=>wx.getStorageSync(prefix+name);
const write=(name,value)=>wx.setStorageSync(prefix+name,value);
const remove=name=>wx.removeStorageSync(prefix+name);
function request(path,method='GET',data,authenticated=true){const session=read('session');return new Promise((resolve,reject)=>wx.request({
  url:config.apiBase+path,method,data,timeout:45000,header:{'content-type':'application/json',...(authenticated&&session?{Authorization:'SellerWechat '+session.token}:{})},
  success(r){if(r.statusCode>=200&&r.statusCode<300)return resolve(r.data);if(r.statusCode===401)remove('session');const error=new Error(typeof r.data.detail==='string'?r.data.detail:JSON.stringify(r.data));error.status=r.statusCode;reject(error);},
  fail(e){const reason=String(e&&e.errMsg||'');let message;
    if(/url not in domain list/i.test(reason))message='WeChat blocked the API domain. Add '+config.apiBase.split('/api/')[0]+' to this Mini Program\'s request domain list, then reload.';
    else if(/timeout/i.test(reason))message='The server took too long to respond. Check the network and retry.';
    else if(/ssl|certificate|tls/i.test(reason))message='WeChat could not verify the server HTTPS connection. Please contact the app administrator.';
    else message=config.authMode==='developer'?'Cannot reach the server. Start the local seller agent and check the configured API address.':'Cannot reach the seller server. Check your network and make sure the phone backend is running.';
    reject(new Error(message));}
}));}
function hasConsent(){return config.authMode==='developer'||read('privacy-consent')===publicInfo.privacyVersion;}
async function connect(){if(!hasConsent())throw new Error('Please read and agree to the privacy notice before signing in.');let session=read('session');if(session&&Date.parse(session.expires_at)>Date.now())return session;
  if(config.authMode==='developer')session=await request('/session/developer/','POST',{},false);
  else if(config.authMode==='wechat'){const code=await new Promise((resolve,reject)=>wx.login({success:r=>r.code?resolve(r.code):reject(new Error('WeChat did not provide a login code.')),fail:reject}));session=await request('/session/login/','POST',{code},false);}
  else throw new Error('Unknown auth mode.');write('session',session);remove('conversation');return session;
}
function uuid(){return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g,c=>{const n=Math.floor(Math.random()*16);return(c==='x'?n:((n&3)|8)).toString(16);});}
async function submit(key,path,data){const signature=JSON.stringify(data);let pending=read('pending:'+key);if(!pending||pending.signature!==signature){pending={signature,request_id:uuid()};write('pending:'+key,pending);}const result=await request(path,'POST',{...data,request_id:pending.request_id});remove('pending:'+key);return result;}
async function logout(){try{if(read('session'))await request('/session/logout/','POST',{});}finally{['session','conversation','pending:message','pending:change','privacy-consent'].forEach(remove);}}
module.exports={config,read,write,remove,request,connect,submit,hasConsent,logout};

(() => {
  'use strict';
  const publicDemo=document.body.dataset.publicDemo==='true';
  const $=id=>document.getElementById(id), mode=document.body.dataset.mode, root='/api/seller-agent/v1/';
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const key='seller-agent:'+mode+':', state={me:null,conversation:null,detail:null,products:[],orders:[],busy:false};
  let token=sessionStorage.getItem(key+'token');
  const pending=new Map();
  function requestId(name,payload){const signature=JSON.stringify(payload),old=pending.get(name);if(old?.signature===signature)return old.id;const id=crypto.randomUUID();pending.set(name,{signature,id});return id;}
  function errorText(data){if(typeof data==='string')return data;if(Array.isArray(data))return data.map(errorText).join(' ');return Object.entries(data||{}).map(([k,v])=>(k==='detail'?'':k+': ')+errorText(v)).join(' ');}
  async function request(path,body){const headers={'Content-Type':'application/json','Accept-Language':'en'};
    if(mode==='mini'&&token)headers.Authorization='SellerWechat '+token;
    if(mode==='web'){const name=document.body.dataset.csrfCookie;headers['X-CSRFToken']=decodeURIComponent(document.cookie.split('; ').find(c=>c.startsWith(name+'='))?.slice(name.length+1)||'');}
    const r=await fetch(root+path,{method:body===undefined?'GET':'POST',headers,credentials:mode==='mini'?'omit':'same-origin',cache:'no-store',body:body===undefined?undefined:JSON.stringify(body)});
    if(r.status===204)return {};
    const data=await r.json().catch(()=>({detail:'The server could not complete this request.'}));if(!r.ok)throw new Error(errorText(data));return data;
  }
  function error(text){$('error').hidden=false;$('error').textContent=text;}
  async function run(fn,button){if(state.busy)return;state.busy=true;if(button)button.disabled=true;$('error').hidden=true;try{await fn();}catch(e){error(e.message);}finally{state.busy=false;if(button)button.disabled=false;}}
  function renderChanges(){
    const data=state.detail?.changes||[];if($('change-panel'))$('change-panel').hidden=!data.length;
    $('changes').innerHTML=data.length?[...data].reverse().map(d=>`<article class="change ${esc(d.status)}"><h3>${esc(d.action)} · ${esc(d.status)}</h3><small>${d.action==='listing'?'Creates an unpublished draft':'Review these values carefully'}</small><pre>${esc(d.summary)}</pre>${d.status==='pending'&&!d.expired?`<label class="check"><input type="checkbox" data-approve="${d.id}">I reviewed and approve this exact change.</label><button class="primary" data-confirm="${d.id}">Confirm change</button>`:d.status==='applied'?`<p>${esc(d.result.message)}</p>${d.result.url?`<a href="${esc(d.result.url)}" target="_blank" rel="noopener">Open product editor ↗</a>`:''}`:'<p class="muted">Prepare a fresh preview to make a change.</p>'}</article>`).join(''):'<p class="empty">Proposed changes appear here. Nothing is applied until you confirm.</p>';
  }
  function renderDetail(data){state.detail=data;$('messages').innerHTML=data.messages.map(m=>`<div class="bubble user"><small>You · ${esc(m.channel)}</small>${esc(m.text)}</div><div class="bubble assistant"><small>Seller assistant · ${esc(m.response.engine)}</small>${esc((m.response.notice?m.response.notice+'\n\n':'')+m.response.reply)}${m.response.missing?.length?'\nMissing: '+esc(m.response.missing.join(', ')):''}</div>`).join('')||'<div class="empty"><h3>How can I help with your shop?</h3><p>Ask for your stock or orders, or start a new product draft.</p></div>';$('messages').scrollTop=$('messages').scrollHeight;renderChanges();}
  async function openConversation(id){state.conversation=id;sessionStorage.setItem(key+'conversation',id);renderDetail(await request('conversations/'+id+'/'));$('conversation-select').value=id;}
  async function refresh(){const status=await request('status/');if($('wechat-status'))$('wechat-status').textContent=status.wechat_configured?'WeChat login is configured. Link your Mini Program to this website account to access the same shop.':'WeChat is not connected. AppID, developer access and a configured HTTPS domain are still required.';$('engine-label').textContent=publicDemo?(status.engine==='guided'?'Guided mode':'DeepSeek AI'):(status.engine==='guided'?'Guided mode · no AI-provider calls':'DeepSeek AI enabled · changes require your confirmation');
    if($('connect-mini'))$('connect-mini').hidden=mode!=='mini'||!status.developer_login||!!token;
    if(mode==='mini'&&!token){$('account-name').textContent='Local Mini Program preview';$('account-status').textContent='Start an unlinked session, then approve its link in your website account.';return;}
    state.me=await request('me/');$('account-name').textContent=status.shared_demo?'Main website catalogue':publicDemo?'Demo shop':state.me.account||'Unlinked WeChat session';$('account-status').textContent=publicDemo?'Sample shop · no account needed':state.me.linked?(state.me.is_seller?'Verified seller · the same shop is used by both channels':'Account linked · seller verification is still required'):state.me.onboarding;
    if($('link-mini'))$('link-mini').hidden=mode!=='mini'||state.me.linked;
    if(!state.me.linked)return;
    if($('link-result'))$('link-result').hidden=true;
    const list=(await request('conversations/')).conversations;
    if(!list.length){const c=await request('conversations/',{});list.push(c);}
    $('conversation-select').innerHTML=list.map((c,i)=>`<option value="${c.id}">Conversation ${c.id.slice(0,6)}</option>`).join('');
    const saved=state.conversation||sessionStorage.getItem(key+'conversation');await openConversation(list.some(c=>c.id===saved)?saved:list[0].id);
    if(mode==='web'&&!publicDemo){const links=(await request('links/')).links;$('linked-devices').innerHTML=links.map(l=>`<p>${esc(l.mode)} · ${esc(l.id.slice(0,8))} <button data-unlink="${l.id}">Unlink</button></p>`).join('')||'<p>No linked WeChat sessions.</p>';}
    const view=new URLSearchParams(location.search).get('view');
    if(view==='products'||view==='orders'||(status.shared_demo&&!view)){const snapshot=await request('snapshot/');if(view==='orders')showOrders(snapshot.orders);else showProducts(snapshot.products);if(view)$('records').scrollIntoView({block:'start'});}
  }
  function showProducts(records){state.products=records;$('records').hidden=false;$('records-title').textContent=publicDemo?'Products':'Your products and available stock';$('records-body').innerHTML=`<div class="record-grid">${records.map((p,i)=>`<article class="record"><h3>${esc(p.name)}</h3><p>${esc(p.currency)} ${esc(p.price)} · ${p.active?'Active':'Unpublished'} · ${p.made_to_order?'Made to order':p.quantity+' available'}</p><label>Option<select data-variant="${i}"><option value="">${p.variants.length?'Select an option for stock updates':'Standard'}</option>${p.variants.map(v=>`<option value="${v.id}">${esc(v.label)} · ${v.quantity} available</option>`).join('')}</select></label><label>New available quantity<input data-quantity="${i}" type="number" min="0" max="1000000" value="${p.quantity??0}"></label><button data-stock="${i}" ${p.made_to_order?'disabled':''}>Preview stock change</button><label>New price<input data-price="${i}" type="number" min="0" step="0.01" value="${esc(p.price)}"></label><button data-new-price="${i}">Preview price change</button><p><a href="${esc(p.url)}">Edit photos, options and publication</a></p></article>`).join('')||'<p class="empty">No matching products.</p>'}</div>`;}
  function showOrders(records){state.orders=records;$('records').hidden=false;$('records-title').textContent=publicDemo?'Orders':'Your part of each order';$('records-body').innerHTML=`<div class="record-grid">${records.map((o,i)=>`<article class="record"><h3>${esc(o.order_number)}</h3><p>${esc(publicDemo?o.payment_status+' (simulated)':o.payment_status)} · ${esc(o.fulfillment_status)} · ${esc(o.seller_subtotal)}</p>${o.items.map(l=>`<p>${l.quantity} × ${esc(l.product_name)}</p>`).join('')}<p>${esc(o.carrier)} ${esc(o.tracking_number)}</p><label>Carrier<input data-carrier="${i}" maxlength="80" placeholder="Carrier name"></label><label>Tracking number<input data-tracking="${i}" maxlength="80" placeholder="Tracking number"></label><button data-ship="${i}" ${!o.can_ship?'disabled':''}>${publicDemo?'Preview simulated shipment':'Preview shipment'}</button></article>`).join('')||'<p class="empty">No orders for your shop.</p>'}</div>`;}
  async function send(text){if(!state.me?.linked)throw new Error(publicDemo?'Your demo session has expired. Open the start page to continue.':'Link your website account before accessing private shop data.');const body={text};body.request_id=requestId('message',body);const result=await request('conversations/'+state.conversation+'/messages/',body);pending.delete('message');$('message').value='';await openConversation(state.conversation);if(result.products)showProducts(result.products);if(result.orders)showOrders(result.orders);}
  async function prepare(action,target,values){const body={action,target,values};body.request_id=requestId('change',body);await request('conversations/'+state.conversation+'/changes/',body);pending.delete('change');await openConversation(state.conversation);}
  $('chat-form').addEventListener('submit',e=>{e.preventDefault();run(()=>send($('message').value.trim()),e.submitter);});
  $('connect-mini')?.addEventListener('click',e=>run(async()=>{const s=await request('session/developer/',{});token=s.token;sessionStorage.setItem(key+'token',token);await refresh();},e.currentTarget));
  $('link-mini')?.addEventListener('click',e=>run(async()=>{const link=await request('link/start/',{});$('pair-code').textContent=link.verification_code;$('link-url').href=link.url;$('link-result').hidden=false;},e.currentTarget));
  $('refresh').addEventListener('click',e=>run(refresh,e.currentTarget));
  $('new-conversation').addEventListener('click',e=>run(async()=>{const c=await request('conversations/',{});state.conversation=c.id;await refresh();},e.currentTarget));
  $('conversation-select').addEventListener('change',()=>run(()=>openConversation($('conversation-select').value)));
  document.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;
    if(b.dataset.prompt)run(()=>send(b.dataset.prompt),b);
    if(b.dataset.confirm)run(async()=>{if(!document.querySelector(`[data-approve="${b.dataset.confirm}"]`).checked)throw new Error('Review the exact change and tick the approval box first.');await request('changes/'+b.dataset.confirm+'/confirm/',{confirmed:true});await openConversation(state.conversation);const snapshot=await request('snapshot/');if(state.orders.length)showOrders(snapshot.orders);else if(state.products.length)showProducts(snapshot.products);},b);
    if(b.dataset.stock!==undefined)run(()=>{const i=b.dataset.stock,p=state.products[i];return prepare('stock',p.slug,{quantity:Number(document.querySelector(`[data-quantity="${i}"]`).value),variant:document.querySelector(`[data-variant="${i}"]`).value||null});},b);
    if(b.dataset.newPrice!==undefined)run(()=>{const i=b.dataset.newPrice,p=state.products[i];return prepare('price',p.slug,{price:document.querySelector(`[data-price="${i}"]`).value,variant:document.querySelector(`[data-variant="${i}"]`).value||null});},b);
    if(b.dataset.ship!==undefined)run(()=>{const i=b.dataset.ship;return prepare('fulfillment',state.orders[i].uuid,{carrier:document.querySelector(`[data-carrier="${i}"]`).value,tracking_number:document.querySelector(`[data-tracking="${i}"]`).value});},b);
    if(b.dataset.unlink)run(async()=>{await request('links/'+b.dataset.unlink+'/unlink/',{confirmed:true});await refresh();},b);
  });
  run(refresh);
})();

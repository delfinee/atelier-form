(() => {
  'use strict';
  const ui=JSON.parse(document.getElementById('seller-i18n')?.textContent||'{}');
  const t=(key,values={})=>Object.entries(values).reduce((text,[name,value])=>text.replaceAll('{'+name+'}',String(value)),ui[key]||key);
  const language=(document.documentElement.lang||'en').startsWith('zh')?'zh-hans':'en';
  const publicDemo=document.body.dataset.publicDemo==='true';
  const $=id=>document.getElementById(id), mode=document.body.dataset.mode, root='/api/seller-agent/v1/';
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const key='seller-agent:'+mode+':', state={me:null,conversation:null,detail:null,products:[],orders:[],busy:false,recordsKind:null,dirtyRecords:false,epoch:0};
  let token=sessionStorage.getItem(key+'token');
  const pending=new Map();
  function requestId(name,payload){const signature=JSON.stringify(payload),old=pending.get(name);if(old?.signature===signature)return old.id;const id=crypto.randomUUID();pending.set(name,{signature,id});return id;}
  function errorText(data){if(typeof data==='string')return data;if(Array.isArray(data))return data.map(errorText).join(' ');return Object.entries(data||{}).map(([k,v])=>(k==='detail'?'':t(k==='quantity'?'quantityField':k)+': ')+errorText(v)).join(' ');}
  async function request(path,body){const headers={'Content-Type':'application/json','Accept-Language':language};
    if(mode==='mini'&&token)headers.Authorization='SellerWechat '+token;
    if(mode==='web'){const name=document.body.dataset.csrfCookie;headers['X-CSRFToken']=decodeURIComponent(document.cookie.split('; ').find(c=>c.startsWith(name+'='))?.slice(name.length+1)||'');}
    const r=await fetch(root+path,{method:body===undefined?'GET':'POST',headers,credentials:mode==='mini'?'omit':'same-origin',cache:'no-store',body:body===undefined?undefined:JSON.stringify(body)});
    if(r.status===204)return {};
    const data=await r.json().catch(()=>({detail:t('serverError')}));if(!r.ok)throw new Error(errorText(data));return data;
  }
  function error(text){$('error').hidden=false;$('error').textContent=text;}
  async function run(fn,button){if(state.busy)return;state.busy=true;state.epoch++;const oldLabel=button?.textContent;if(button){button.disabled=true;if(button.form?.id==='chat-form')button.textContent=t('thinking');}$('error').hidden=true;try{await fn();}catch(e){error(e.message);}finally{state.busy=false;if(button){button.disabled=false;button.textContent=oldLabel;}}}
  function renderChanges(){
    const data=state.detail?.changes||[];if($('change-panel'))$('change-panel').hidden=!data.length;
    $('changes').innerHTML=data.length?[...data].reverse().map(d=>`<article class="change ${esc(d.status)}"><h3>${esc(t(d.action))} · ${esc(t(d.status))}</h3><small>${d.action==='listing'?t('draft'):t('review')}</small><pre>${esc(d.summary)}</pre>${d.status==='pending'&&!d.expired?`<label class="check"><input type="checkbox" data-approve="${d.id}">${esc(t('approve'))}</label><button class="primary" data-confirm="${d.id}">${esc(t('confirm'))}</button>`:d.status==='applied'?`<p>${esc(d.result.message)}</p>${d.result.url?`<a href="${esc(d.result.url)}" target="_blank" rel="noopener">${esc(t('editor'))} ↗</a>`:''}`:`<p class="muted">${esc(t('retry'))}</p>`}</article>`).join(''):`<p class="empty">${esc(t('noChanges'))}</p>`;
  }
  function renderDetail(data){state.detail=data;$('messages').innerHTML=data.messages.map(m=>`<div class="bubble user"><small>${esc(t('you'))} · ${esc(t(m.channel))}</small>${esc(m.text)}</div><div class="bubble assistant"><small>${esc(t('assistant'))} · ${esc(t(m.response.engine))}</small>${esc((m.response.notice?m.response.notice+'\n\n':'')+m.response.reply)}${m.response.missing?.length?'\n'+esc(t('missing'))+': '+esc(m.response.missing.map(k=>t(k==='quantity'?'quantityField':k)).join(', ')):''}</div>`).join('')||`<div class="empty"><h3>${esc(t('helpTitle'))}</h3><p>${esc(t('helpText'))}</p></div>`;$('messages').scrollTop=$('messages').scrollHeight;renderChanges();}
  async function openConversation(id){state.conversation=id;sessionStorage.setItem(key+'conversation',id);renderDetail(await request('conversations/'+id+'/'));$('conversation-select').value=id;}
  async function refresh(){const status=await request('status/');if($('wechat-status'))$('wechat-status').textContent=status.wechat_configured?'WeChat login is configured. Link your Mini Program to this website account to access the same shop.':'WeChat is not connected. AppID, developer access and a configured HTTPS domain are still required.';$('engine-label').textContent=publicDemo?(status.engine==='guided'?t('guided'):t('deepseek')):(status.engine==='guided'?t('guidedStatus'):t('aiStatus'));
    if($('connect-mini'))$('connect-mini').hidden=mode!=='mini'||!status.developer_login||!!token;
    if(mode==='mini'&&!token){$('account-name').textContent='Local Mini Program preview';$('account-status').textContent='Start an unlinked session, then approve its link in your website account.';return;}
    state.me=await request('me/');$('account-name').textContent=status.shared_demo?(state.me.seller_name||t('catalogue')):publicDemo?t('demoShop'):state.me.account||t('unlinked');$('account-status').textContent=status.shared_demo?t('sharedStatus'):publicDemo?t('sampleStatus'):state.me.linked?(state.me.is_seller?t('verifiedStatus'):t('verificationRequired')):state.me.onboarding;
    if($('link-mini'))$('link-mini').hidden=mode!=='mini'||state.me.linked;
    if(!state.me.linked)return;
    if($('link-result'))$('link-result').hidden=true;
    const list=(await request('conversations/')).conversations;
    if(!list.length){const c=await request('conversations/',{});list.push(c);}
    $('conversation-select').innerHTML=list.map((c,i)=>`<option value="${c.id}">${esc(t('conversation'))} ${c.id.slice(0,6)}</option>`).join('');
    const saved=state.conversation||sessionStorage.getItem(key+'conversation');await openConversation(list.some(c=>c.id===saved)?saved:list[0].id);
    if(mode==='web'&&!publicDemo){const links=(await request('links/')).links;$('linked-devices').innerHTML=links.map(l=>`<p>${esc(l.mode)} · ${esc(l.id.slice(0,8))} <button data-unlink="${l.id}">Unlink</button></p>`).join('')||'<p>No linked WeChat sessions.</p>';}
    const view=new URLSearchParams(location.search).get('view');
    if(view==='products'||view==='orders'||(status.shared_demo&&!view)){const snapshot=await request('snapshot/');if(view==='orders')showOrders(snapshot.orders);else showProducts(snapshot.products);if(view)$('records').scrollIntoView({block:'start'});}
  }
  function showProducts(records){state.recordsKind='products';state.dirtyRecords=false;state.products=records;$('records').hidden=false;$('records-title').textContent=t('products');$('records-body').innerHTML=`<div class="record-grid">${records.map((p,i)=>`<article class="record"><h3>${esc(p.name)}</h3>${p.short_description||p.description?`<p class="product-description">${esc(p.short_description||p.description)}</p>`:""}<p>${esc(p.currency)} ${esc(p.price)} · ${p.active?t('active'):t('unpublished')} · ${p.made_to_order?t('madeToOrder'):t('available',{n:p.quantity})}</p><label>${esc(t('option'))}<select data-variant="${i}"><option value="">${p.variants.length?t('selectOption'):t('standard')}</option>${p.variants.map(v=>`<option value="${v.id}">${esc(v.label)} · ${esc(t('available',{n:v.quantity}))}</option>`).join('')}</select></label><label>${esc(t('quantity'))}<input data-quantity="${i}" type="number" min="0" max="1000000" value="${p.quantity??0}"></label><button data-stock="${i}" ${p.made_to_order?'disabled':''}>${esc(t('stockPreview'))}</button><label>${esc(t('price'))}<input data-price="${i}" type="number" min="0" step="0.01" value="${esc(p.price)}"></label><button data-new-price="${i}">${esc(t('pricePreview'))}</button><p><a href="${esc(p.url)}">${esc(t('editProduct'))}</a></p></article>`).join('')||`<p class="empty">${esc(t('noProducts'))}</p>`}</div>`;}
  function showOrders(records){state.recordsKind='orders';state.dirtyRecords=false;state.orders=records;$('records').hidden=false;$('records-title').textContent=t('orders');$('records-body').innerHTML=`<div class="record-grid">${records.map((o,i)=>`<article class="record"><h3>${esc(o.order_number)}</h3>${o.shop?`<p>${esc(o.shop)}</p>`:''}<p>${esc(t(o.payment_status))} · ${esc(t(o.status==='delivered'?'delivered':o.fulfillment_status))} · ${esc(o.seller_subtotal)}</p>${o.items.map(l=>`<p>${l.quantity} × ${esc(l.product_name)}</p>`).join('')}<p>${esc(o.carrier)} ${esc(o.tracking_number)}</p><label>${esc(t('carrier'))}<input data-carrier="${i}" maxlength="80" placeholder="${esc(t('carrierName'))}"></label><label>${esc(t('tracking'))}<input data-tracking="${i}" maxlength="80" placeholder="${esc(t('tracking'))}"></label><button data-ship="${i}" ${!o.can_ship?'disabled':''}>${t('shipPreview')}</button>${o.can_deliver?`<button class="primary" data-deliver="${i}">${esc(t('deliveryPreview'))}</button>`:''}</article>`).join('')||`<p class="empty">${esc(t('noOrders'))}</p>`}</div>`;}
  async function send(text){if(!state.me?.linked)throw new Error(t('sessionExpired'));const body={text};body.request_id=requestId('message',body);const result=await request('conversations/'+state.conversation+'/messages/',body);pending.delete('message');$('message').value='';await openConversation(state.conversation);if(result.products)showProducts(result.products);if(result.orders)showOrders(result.orders);}
  async function prepare(action,target,values){const body={action,target,values};body.request_id=requestId('change',body);await request('conversations/'+state.conversation+'/changes/',body);pending.delete('change');state.dirtyRecords=false;await openConversation(state.conversation);}
  $('chat-form').addEventListener('submit',e=>{e.preventDefault();run(()=>send($('message').value.trim()),e.submitter);});
  $('connect-mini')?.addEventListener('click',e=>run(async()=>{const s=await request('session/developer/',{});token=s.token;sessionStorage.setItem(key+'token',token);await refresh();},e.currentTarget));
  $('link-mini')?.addEventListener('click',e=>run(async()=>{const link=await request('link/start/',{});$('pair-code').textContent=link.verification_code;$('link-url').href=link.url;$('link-result').hidden=false;},e.currentTarget));
  $('refresh').addEventListener('click',e=>run(refresh,e.currentTarget));
  $('new-conversation').addEventListener('click',e=>run(async()=>{const c=await request('conversations/',{});state.conversation=c.id;await refresh();},e.currentTarget));
  $('conversation-select').addEventListener('change',()=>run(()=>openConversation($('conversation-select').value)));
  document.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;
    if(b.dataset.prompt)run(()=>send(b.dataset.prompt),b);
    if(b.dataset.confirm)run(async()=>{if(!document.querySelector(`[data-approve="${b.dataset.confirm}"]`).checked)throw new Error(t('approvalRequired'));await request('changes/'+b.dataset.confirm+'/confirm/',{confirmed:true});await openConversation(state.conversation);const snapshot=await request('snapshot/');if(state.recordsKind==='orders')showOrders(snapshot.orders);else if(state.recordsKind==='products')showProducts(snapshot.products);},b);
    if(b.dataset.stock!==undefined)run(()=>{const i=b.dataset.stock,p=state.products[i];return prepare('stock',p.slug,{quantity:Number(document.querySelector(`[data-quantity="${i}"]`).value),variant:document.querySelector(`[data-variant="${i}"]`).value||null});},b);
    if(b.dataset.newPrice!==undefined)run(()=>{const i=b.dataset.newPrice,p=state.products[i];return prepare('price',p.slug,{price:document.querySelector(`[data-price="${i}"]`).value,variant:document.querySelector(`[data-variant="${i}"]`).value||null});},b);
    if(b.dataset.ship!==undefined)run(()=>{const i=b.dataset.ship;return prepare('fulfillment',state.orders[i].uuid,{carrier:document.querySelector(`[data-carrier="${i}"]`).value,tracking_number:document.querySelector(`[data-tracking="${i}"]`).value});},b);
    if(b.dataset.deliver!==undefined)run(()=>prepare('delivery',state.orders[Number(b.dataset.deliver)].uuid,{}),b);
    if(b.dataset.unlink)run(async()=>{await request('links/'+b.dataset.unlink+'/unlink/',{confirmed:true});await refresh();},b);
  });
  document.addEventListener('input',e=>{if(e.target.closest('#records'))state.dirtyRecords=true;});
  document.addEventListener('change',e=>{if(e.target.closest('#records'))state.dirtyRecords=true;});
  async function refreshRecords(){
    if(document.hidden||state.busy||state.dirtyRecords||!state.me?.linked||!state.recordsKind)return;
    const epoch=state.epoch;
    try{
      const data=await request('snapshot/');
      if(state.busy||state.dirtyRecords||state.epoch!==epoch)return;
      if(state.recordsKind==='orders'&&JSON.stringify(data.orders)!==JSON.stringify(state.orders))showOrders(data.orders);
      if(state.recordsKind==='products'&&JSON.stringify(data.products)!==JSON.stringify(state.products))showProducts(data.products);
    }catch(_){/* Keep displayed data during a temporary disconnect. */}
  }
  setInterval(refreshRecords,5000);
  document.addEventListener('visibilitychange',refreshRecords);
  run(refresh);
})();

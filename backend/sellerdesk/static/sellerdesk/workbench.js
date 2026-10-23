(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const api = '/seller/workbench/api/';
  const state = {overview:null, page:'orders', filter:'all', conversation:null, detail:null, lines:[], busy:0};
  const labels = {review:'Awaiting confirmation',payment:'Awaiting payment',packing:'Picking & packing',dispatch:'Ready to ship',shipped:'Shipped',expired:'Quote expired',attention:'Needs attention'};
  const events = {draft_created:'Quote sent for review',confirm:'Order confirmed',pay:'Demo payment received',pack:'Picking started',packed:'Packing checks completed',ship:'Shipment recorded'};
  const pages = {orders:['Orders','Order operations','From the first customer message to the final parcel.'],inbox:['Customer inbox','Customer conversations','Reply, prepare a quote and keep the order moving.'],inventory:['Inventory','Your product inventory','Know what is available before you promise it to a customer.'],channel:['WeChat channel','Connect your customer experience','Prepare your Mini Program connection and test the flow today.']};
  const pending = new Map();
  function requestId(key, data) { const signature=JSON.stringify(data), old=pending.get(key); if(old?.signature===signature)return old.id; const id=crypto.randomUUID();pending.set(key,{signature,id});return id; }
  function errorText(data) { if(typeof data==='string')return data; if(Array.isArray(data))return data.map(errorText).join(' '); return Object.entries(data||{}).map(([k,v])=>(k==='detail'||k==='non_field_errors'?'':k.replaceAll('_',' ')+': ')+errorText(v)).join(' '); }
  function alert(text, success=false) { $('alert').textContent=text; $('alert').className='alert'+(success?' success':'');$('alert').hidden=false; }
  async function request(path, body) {
    const name=document.body.dataset.csrfCookie;
    const csrf=document.cookie.split('; ').find(c=>c.startsWith(name+'='))?.slice(name.length+1)||'';
    const r=await fetch(api+path,{method:body===undefined?'GET':'POST',credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json','X-CSRFToken':decodeURIComponent(csrf)},body:body===undefined?undefined:JSON.stringify(body)});
    const data=await r.json().catch(()=>({detail:'The server could not complete this request.'}));
    if(!r.ok)throw new Error(errorText(data));return data;
  }
  async function run(fn, button) { state.busy++;if(button)button.disabled=true;$('alert').hidden=true;try{await fn();}catch(e){alert(e.message);}finally{state.busy--;if(button)button.disabled=false;} }
  const money=value=>new Intl.NumberFormat('en',{style:'currency',currency:state.overview?.currency||'CNY'}).format(Number(value));
  const time=value=>new Date(value).toLocaleString('en',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
  const badge=d=>`<span class="badge ${escape(d.stage)}">${escape(labels[d.stage]||d.stage)}</span>`;
  function showPage(page) { state.page=page;for(const [name,copy] of Object.entries(pages)){ $('page-'+name).hidden=name!==page;if(name===page){$('breadcrumb').textContent=copy[0];$('page-title').textContent=copy[1];$('page-subtitle').textContent=copy[2];}}document.querySelectorAll('.nav-item').forEach(b=>b.classList.toggle('active',b.dataset.page===page)); }
  function filter(stage) {state.filter=stage;showPage('orders');renderOrders();}
  function renderOrders() {
    if(!state.overview)return;
    document.querySelectorAll('[data-filter]').forEach(b=>b.classList.toggle('active',b.dataset.filter===state.filter));
    const search=$('order-search').value.toLowerCase();
    const rows=state.overview.drafts.filter(d=>(state.filter==='all'||d.stage===state.filter||(state.filter==='attention'&&d.stage==='expired'))&&`${d.order?.number||''} ${d.customer_label} ${d.customer.email}`.toLowerCase().includes(search));
    $('order-total').textContent=state.overview.draft_total;
    if(!rows.length){$('order-table').innerHTML=`<div class="empty"><span class="empty-icon">▦</span><h3>${state.overview.drafts.length?'No orders match this view':'Your next order starts with a conversation'}</h3><p>${state.overview.drafts.length?'Try another stage or customer name.':'Create a customer preview, receive a message, then prepare your first quote from the inbox.'}</p>${state.overview.drafts.length?'':'<button class="button primary" data-create-preview>Create customer preview ↗</button>'}</div>`;return;}
    $('order-table').innerHTML=`<div class="table-scroll"><table><thead><tr><th>Order / quote</th><th>Customer</th><th>Items</th><th>Total</th><th>Next step</th><th></th></tr></thead><tbody>${rows.map(d=>`<tr><td><strong>${escape(d.order?.number||'Quote · '+d.id.slice(0,6).toUpperCase())}</strong><small>${escape(time(d.created_at))}</small></td><td>${escape(d.customer_label)}<small>${escape(d.customer.email)}</small></td><td>${d.lines.reduce((n,l)=>n+l.quantity,0)} item(s)<small>${escape(d.lines[0]?.name||'')}${d.lines.length>1?' + more':''}</small></td><td>${money(d.total)}</td><td>${badge(d)}</td><td><button class="button" data-open="${escape(d.conversation_id)}">Open →</button></td></tr>`).join('')}</tbody></table></div>`;
  }
  function renderConversations(){
    $('conversation-list').innerHTML=state.overview.conversations.map(c=>`<button class="conversation ${c.id===state.conversation?'selected':''}" data-open="${escape(c.id)}">${c.needs_reply?'<span class="unread" title="Awaiting seller reply"></span>':''}<strong>${escape(c.label)}</strong><p>${escape(c.preview)}</p><small>${escape(c.channel)}</small></button>`).join('')||'<div class="empty"><p>No conversations yet.</p></div>';
  }
  function renderInventory(){
    const rows=state.overview.catalog.flatMap(p=>p.variants.length?p.variants.map(v=>({p,option:v.label,stock:v.stock,price:v.price})):[{p,option:'Standard',stock:p.stock,price:p.price}]);
    $('inventory-table').innerHTML=`<div class="table-scroll"><table><thead><tr><th>Product</th><th>Option</th><th>Price</th><th>Available stock</th><th>Status</th></tr></thead><tbody>${rows.map(({p,option,stock,price})=>`<tr><td><strong>${escape(p.name)}</strong></td><td>${escape(option)}</td><td>${money(price)}</td><td>${p.made_to_order?'Made to order':stock}</td><td><span class="badge ${!p.made_to_order&&stock<=5?'payment':'shipped'}">${p.made_to_order?'Made to order':stock===0?'Out of stock':stock<=5?'Low stock':'In stock'}</span></td></tr>`).join('')}</tbody></table></div>`;
  }
  function refreshProducts(){
    const old=$('quote-product').value;
    const html=state.overview.catalog.map(p=>`<option value="${escape(p.product)}">${escape(p.name)} · ${money(p.price)}</option>`).join('');
    if($('quote-product').innerHTML!==html){$('quote-product').innerHTML=html;if(state.overview.catalog.some(p=>p.product===old))$('quote-product').value=old;refreshVariants();}
  }
  function refreshVariants(){const p=state.overview?.catalog.find(p=>p.product===$('quote-product').value);$('quote-variant').innerHTML=p?.variants.length?p.variants.map(v=>`<option value="${escape(v.id)}">${escape(v.label)} · ${v.stock} available</option>`).join(''):'<option value="">Standard</option>';}
  function renderLines(){
    $('quote-lines').innerHTML=state.lines.map((l,i)=>{const p=state.overview.catalog.find(p=>p.product===l.product),v=p?.variants.find(v=>v.id===l.variant);return `<div class="quote-line"><div>${l.quantity} × ${escape(p?.name||l.product)}<small>${escape(v?.label||'Standard')} · ${money(v?.price||p?.price||0)} each</small></div><button type="button" class="icon-button" aria-label="Remove ${escape(p?.name||'item')}" data-remove-line="${i}">×</button></div>`;}).join('');
  }
  function actionUI(d){
    if(d.stage==='review')return `<label class="check-label"><input type="checkbox" data-confirm="${d.id}">I have the customer's approval for the items, total and delivery details.</label><button class="button full" data-action="confirm" data-draft="${d.id}">Confirm on customer's behalf</button>`;
    if(d.stage==='payment')return `<p class="muted">Awaiting customer payment. No real money is collected in this demo.</p><button class="button full" data-action="pay" data-draft="${d.id}">Simulate payment received</button>`;
    if(d.stage==='packing'&&!d.packing_started)return `<button class="button primary full" data-action="pack" data-draft="${d.id}">Start picking & packing</button>`;
    if(d.stage==='packing')return `<label class="check-label"><input type="checkbox" data-packed="${d.id}">I checked all items, quantities and packaging.</label><button class="button primary full" data-action="packed" data-draft="${d.id}">Complete packing</button>`;
    if(d.stage==='dispatch')return `<label>Carrier<input data-carrier="${d.id}" placeholder="e.g. Demo Express" maxlength="80"></label><label>Tracking number<input data-tracking="${d.id}" placeholder="e.g. DEMO-123456" maxlength="80"></label><button class="button primary full" data-action="ship" data-draft="${d.id}">Record shipment</button>`;
    if(d.stage==='shipped')return `<p class="success">${escape(d.order.carrier)}<br>${escape(d.order.tracking_number)}</p>`;
    return '<p class="muted">Prepare a new quote if the customer still wants to order.</p>';
  }
  function renderDetail(detail,force=false){
    if(!force&&JSON.stringify(state.detail)===JSON.stringify(detail))return;
    state.detail=detail;$('thread-title').textContent=detail.label;$('thread-subtitle').textContent='Customer conversation · Replies and order updates stay together';
    $('reply-form').hidden=false;$('quote-panel').hidden=false;
    const role={customer:'Customer',assistant:'Shopping assistant',seller:'You · Seller'};
    $('thread-messages').innerHTML=detail.messages.map(m=>`<div class="message ${m.role}"><div class="role"><span>${role[m.role]}${m.engine==='offline'?' · Catalogue match':''}</span><time>${escape(time(m.at))}</time></div><div class="bubble">${escape(m.text)}</div>${m.lines?.length?`<button class="button" data-suggestion="${escape(m.id)}">Use suggested items →</button>`:''}</div>`).join('')||'<div class="empty"><h3>Ready for your customer</h3><p>Ask your teammate to send a message from the linked customer preview.</p></div>';
    $('thread-messages').scrollTop=$('thread-messages').scrollHeight;
    $('draft-cards').innerHTML=detail.drafts.map(d=>{const a=d.customer.shipping_address;return `<section class="panel draft-card"><div class="draft-head"><h3>${escape(d.order?.number||'Quote · '+d.id.slice(0,6).toUpperCase())}</h3>${badge(d)}</div>${d.lines.map(l=>`<div class="item"><span>${l.quantity} × ${escape(l.name)}<br><small>${escape(l.option)}</small></span><span>${money(l.line_total)}</span></div>`).join('')}<div class="item"><span>Shipping</span><span>${money(d.shipping)}</span></div><div class="total"><span>Total</span><span>${money(d.total)}</span></div><div class="delivery">${escape(a.first_name)} ${escape(a.last_name)}<br>${escape(a.address_line_1)}, ${escape(a.city)} ${escape(a.postal_code)}<br>${escape(d.customer.email)}</div>${d.stage==='review'?`<p class="muted">Valid until ${escape(time(d.expires_at))}</p>`:''}${actionUI(d)}<details><summary class="muted">Order history</summary><ol class="timeline">${d.events.map(e=>`<li>${escape(events[e.action]||e.action)}<time>${escape(time(e.at))}</time></li>`).join('')}</ol></details></section>`;}).join('');
  }
  async function refresh(){
    state.overview=await request('overview/');
    ['review','payment','packing','dispatch'].forEach(s=>$('count-'+s).textContent=state.overview.counts[s]);
    $('nav-orders').textContent=state.overview.draft_total;$('nav-inbox').textContent=state.overview.needs_reply;
    renderOrders();renderConversations();renderInventory();refreshProducts();
    if(state.conversation){const id=state.conversation;const d=await request('conversations/'+id+'/');if(id===state.conversation)renderDetail(d);}
    $('sync-status').textContent='Updated '+new Date().toLocaleTimeString('en',{hour:'2-digit',minute:'2-digit'})+' · Refreshes every 8 seconds';
  }
  async function openConversation(id){
    state.conversation=id;state.detail=null;state.lines=[];$('seller-reply').value='';renderLines();renderConversations();showPage('inbox');
    const detail=await request('conversations/'+id+'/');if(state.conversation===id)renderDetail(detail,true);
  }
  function inviteDialog(){ $('invite-form').hidden=false;$('invitation-result').hidden=true;$('preview-dialog').showModal();$('customer-name').focus(); }
  document.addEventListener('click',e=>{
    const button=e.target.closest('button');if(!button)return;
    if(button.dataset.page)showPage(button.dataset.page);
    if(button.dataset.stage)filter(button.dataset.stage);
    if(button.dataset.filter)filter(button.dataset.filter);
    if(button.dataset.open)run(()=>openConversation(button.dataset.open),button);
    if(button.hasAttribute('data-create-preview'))inviteDialog();
    if(button.dataset.removeLine!==undefined){state.lines.splice(Number(button.dataset.removeLine),1);renderLines();}
    if(button.dataset.suggestion){const m=state.detail.messages.find(m=>m.id===button.dataset.suggestion);state.lines=m.lines.map(l=>({...l}));renderLines();alert('Suggested items added. Review quantities and delivery details before sending a quote.',true);}
    if(button.dataset.action)run(async()=>{
      const id=button.dataset.draft,action=button.dataset.action,body={action};
      if(action==='confirm'){if(!document.querySelector(`[data-confirm="${id}"]`).checked)throw new Error('Confirm that you have the customer’s approval first.');body.confirmed=true;}
      if(action==='packed'&&!document.querySelector(`[data-packed="${id}"]`).checked)throw new Error('Complete the items and packaging check first.');
      if(action==='ship'){body.carrier=document.querySelector(`[data-carrier="${id}"]`).value.trim();body.tracking_number=document.querySelector(`[data-tracking="${id}"]`).value.trim();if(!body.carrier||!/^[A-Za-z0-9-]{6,80}$/.test(body.tracking_number))throw new Error('Enter a carrier and a tracking number of 6–80 letters, numbers or hyphens.');}
      await request('drafts/'+id+'/action/',body);await refresh();alert(events[action]+'.',true);
    },button);
  });
  $('quote-product').addEventListener('change',refreshVariants);
  $('add-line').addEventListener('click',()=>run(async()=>{const product=$('quote-product').value,variant=$('quote-variant').value||null,quantity=Number($('quote-quantity').value);if(!product||!Number.isInteger(quantity)||quantity<1||quantity>99)throw new Error('Choose a product and a quantity from 1 to 99.');const old=state.lines.find(l=>l.product===product&&l.variant===variant);if(old){if(old.quantity+quantity>99)throw new Error('The maximum combined quantity is 99.');old.quantity+=quantity;}else state.lines.push({product,variant,quantity});renderLines();}));
  $('quote-form').addEventListener('submit',e=>{e.preventDefault();run(async()=>{if(!state.lines.length)throw new Error('Add at least one product to the quote.');const body={lines:state.lines,email:$('quote-email').value,phone:$('quote-phone').value,delivery_method:$('quote-delivery').value,shipping_address:{first_name:$('quote-first').value,last_name:$('quote-last').value,address_line_1:$('quote-address').value,city:$('quote-city').value,postal_code:$('quote-postal').value}};body.request_id=requestId('quote:'+state.conversation,body);await request('conversations/'+state.conversation+'/quote/',body);pending.delete('quote:'+state.conversation);state.lines=[];renderLines();await refresh();alert('Quote sent. Your customer can review and confirm it in the preview.',true);},e.submitter);});
  $('reply-form').addEventListener('submit',e=>{e.preventDefault();run(async()=>{const text=$('seller-reply').value.trim();if(!text)return;await request('conversations/'+state.conversation+'/reply/',{text,request_id:requestId('reply:'+state.conversation,{text})});pending.delete('reply:'+state.conversation);$('seller-reply').value='';await refresh();},e.submitter);});
  $('order-search').addEventListener('input',renderOrders);
  $('refresh').addEventListener('click',e=>run(refresh,e.currentTarget));
  $('new-preview').addEventListener('click',inviteDialog);$('channel-preview').addEventListener('click',inviteDialog);$('close-dialog').addEventListener('click',()=>$('preview-dialog').close());
  $('invite-form').addEventListener('submit',e=>{e.preventDefault();run(async()=>{const result=await request('invitations/',{label:$('customer-name').value.trim()});state.invitation=result;$('preview-link').href=result.preview_url;$('invite-form').hidden=true;$('invitation-result').hidden=false;$('copy-preview').textContent='Copy link for a teammate';await refresh();},e.submitter);});
  $('copy-preview').addEventListener('click',e=>run(async()=>{await navigator.clipboard.writeText(new URL(state.invitation.preview_url,location.origin).href);$('copy-preview').textContent='Link copied';},e.currentTarget));
  $('go-inbox').addEventListener('click',e=>run(async()=>{$('preview-dialog').close();await openConversation(state.invitation.conversation_id);},e.currentTarget));
  run(refresh);
  setInterval(()=>{if(!state.busy&&!document.hidden)refresh().catch(()=>{$('sync-status').textContent='Connection interrupted · Use Refresh to retry';});},8000);
})();

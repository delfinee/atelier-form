const api=require('../../utils/seller-api');
const productCards=products=>products.map(p=>({...p,optionIndex:0,optionNames:[p.variants.length?'Select option':'Standard'].concat(p.variants.map(v=>v.label+' 路 '+v.quantity)),editQuantity:p.quantity==null?'':String(p.quantity),editPrice:p.price}));
const orderCards=orders=>orders.map(o=>({...o,canShip:!!o.can_ship,carrierInput:'',trackingInput:''}));
Page({
  data:{busy:false,error:'',me:null,tab:'chat',text:'',messages:[],changes:[],products:[],orders:[],link:null,conversation:'',engine:'guided',aiEnabled:false,local:api.config.authMode==='developer'},
  onLoad(){if(!api.hasConsent()){wx.redirectTo({url:'/pages/home/index'});return;}return this.run(async()=>{await api.connect();await this.refresh();});},
  onShow(){if(this.data.me&&!this.data.busy)return this.run(()=>this.refresh());},
  onPullDownRefresh(){return this.run(()=>this.refresh()).finally(()=>wx.stopPullDownRefresh());},
  async run(fn){if(this.data.busy)return;this.setData({busy:true,error:''});try{await fn();}catch(e){this.setData({error:e.message||'Please retry.'});}finally{this.setData({busy:false});}},
  async refresh(){const status=await api.request('/status/','GET',undefined,false);const me=await api.request('/me/');this.setData({me,aiEnabled:status.engine==='deepseek',...(me.linked?{link:null}:{})});if(!me.linked)return;
    const list=(await api.request('/conversations/')).conversations;let id=api.read('conversation');
    if(!list.some(c=>c.id===id))id=list.length?list[0].id:(await api.request('/conversations/','POST',{})).id;
    api.write('conversation',id);this.setData({conversation:id});await this.loadConversation();
    if(me.is_seller){const data=await api.request('/snapshot/');this.setData({products:productCards(data.products),orders:orderCards(data.orders)});}
  },
  async loadConversation(){const c=await api.request('/conversations/'+this.data.conversation+'/');this.setData({messages:c.messages,changes:c.changes.map(d=>({...d,preview:d.summary,canConfirm:d.status==='pending'&&!d.expired}))});},
  refreshSession(){return this.run(async()=>{await api.connect();await this.refresh();});},
  privacy(){wx.navigateTo({url:'/pages/privacy/index'});},
  signOut(){return this.run(async()=>{let warning='';try{await api.logout();}catch(e){warning='Local sign-in data was cleared. The server could not confirm revocation; its token expires within eight hours.';}this.setData({me:null,messages:[],changes:[],products:[],orders:[],link:null,conversation:'',text:''});if(warning)wx.showModal({title:'Signed out on this device',content:warning,showCancel:false});wx.reLaunch({url:'/pages/home/index'});});},
  beginLink(){return this.run(async()=>{const link=await api.request('/link/start/','POST',{});this.setData({link});});},
  copyLink(){wx.setClipboardData({data:this.data.link.url});},
  onText(e){this.setData({text:e.detail.value});},
  setTab(e){this.setData({tab:e.currentTarget.dataset.tab});},
  quick(e){this.setData({text:e.currentTarget.dataset.text});return this.send();},
  send(){return this.run(async()=>{const text=this.data.text.trim();if(!text)return;const r=await api.submit('message','/conversations/'+this.data.conversation+'/messages/',{text});this.setData({text:'',engine:r.engine});await this.loadConversation();if(r.products)this.setData({tab:'products',products:productCards(r.products)});if(r.orders)this.setData({tab:'orders',orders:orderCards(r.orders)});});},
  newConversation(){return this.run(async()=>{const c=await api.request('/conversations/','POST',{});api.write('conversation',c.id);this.setData({conversation:c.id,messages:[],changes:[],tab:'chat'});});},
  onOption(e){const i=Number(e.currentTarget.dataset.index),n=Number(e.detail.value),products=this.data.products;products[i].optionIndex=n;const selected=products[i].variants[n-1]||products[i];products[i].editQuantity=selected.quantity==null?'':String(selected.quantity);products[i].editPrice=selected.price;this.setData({products});},
  onProductField(e){const i=Number(e.currentTarget.dataset.index),products=this.data.products;products[i][e.currentTarget.dataset.field]=e.detail.value;this.setData({products});},
  onOrderField(e){const i=Number(e.currentTarget.dataset.index),orders=this.data.orders;orders[i][e.currentTarget.dataset.field]=e.detail.value;this.setData({orders});},
  prepareProduct(e){return this.run(async()=>{const p=this.data.products[Number(e.currentTarget.dataset.index)],action=e.currentTarget.dataset.action,variant=p.variants[p.optionIndex-1];const values={variant:variant?variant.id:null,...(action==='stock'?{quantity:Number(p.editQuantity)}:{price:p.editPrice})};await api.submit('change','/conversations/'+this.data.conversation+'/changes/',{action,target:p.slug,values});await this.loadConversation();this.setData({tab:'chat'});});},
  prepareShipment(e){return this.run(async()=>{const o=this.data.orders[Number(e.currentTarget.dataset.index)];await api.submit('change','/conversations/'+this.data.conversation+'/changes/',{action:'fulfillment',target:o.uuid,values:{carrier:o.carrierInput,tracking_number:o.trackingInput}});await this.loadConversation();this.setData({tab:'chat'});});},
  confirmChange(e){const d=this.data.changes.find(d=>d.id===e.currentTarget.dataset.id);if(!d)return;
    return this.run(async()=>{const confirmed=await new Promise(resolve=>wx.showModal({title:'Apply this exact change?',content:d.preview.slice(0,950),confirmText:'Confirm',success:r=>resolve(r.confirm),fail:()=>resolve(false)}));if(!confirmed)return;await api.request('/changes/'+d.id+'/confirm/','POST',{confirmed:true});await this.refresh();});},
  copyEditor(e){wx.setClipboardData({data:api.config.apiBase.split('/api/')[0]+e.currentTarget.dataset.path});}
});

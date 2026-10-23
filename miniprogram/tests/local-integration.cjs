/* Exercise the real Mini Program page handlers against the local Django API.
 * wx is mocked; this is not a WeChat platform or DevTools certification test. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const base=process.env.SELLER_TEST_BASE||'http://127.0.0.1:8780';
const email=process.env.SELLER_TEST_EMAIL,password=process.env.SELLER_TEST_PASSWORD;
assert(email&&password,'Set SELLER_TEST_EMAIL and SELLER_TEST_PASSWORD for a local test seller.');
const store=new Map();
global.wx={getStorageSync:k=>store.get(k),setStorageSync:(k,v)=>store.set(k,v),removeStorageSync:k=>store.delete(k),
  request:async o=>{try{const response=await fetch(o.url,{method:o.method,headers:o.header,body:o.data?JSON.stringify(o.data):undefined});const text=await response.text();o.success({statusCode:response.status,data:text?JSON.parse(text):{}});}catch(e){o.fail(e);}},
  showModal:o=>o.success({confirm:true}),stopPullDownRefresh(){},setClipboardData(){},login(){throw Error('Live wx.login must not be invoked in local tests.');}};
const api=require('../utils/seller-api');
let page;
const definition={};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../pages/seller/index.js'),'utf8'),{require:()=>api,wx:global.wx,Page:o=>Object.assign(definition,o),console});
page={...definition,data:structuredClone(definition.data),setData(values){Object.assign(this.data,values);}};
async function checked(result){assert.equal(page.data.error,'',page.data.error);return result;}
async function main(){
  const login=await fetch(base+'/api/auth/login/',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,password})});
  assert.equal(login.status,200,'Local seller credentials were rejected.');const user=await login.json();
  const web=async(route,body)=>{const r=await fetch(base+'/api/seller-agent/v1/'+route,{method:body?'POST':'GET',headers:{Authorization:'Bearer '+user.tokens.access,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});const d=await r.json();assert(r.ok,JSON.stringify(d));return d;};
  const originalLinks=(await web('links/')).links.map(l=>l.id);
  await checked(await page.onLoad());assert.equal(page.data.me.linked,false);
  await checked(await page.beginLink());
  const link=page.data.link;
  await web('link/approve/',{token:link.url.split('#token=')[1],verification_code:link.verification_code,confirmed:true});
  await checked(await page.refreshSession());assert.equal(page.data.me.is_seller,true);
  const conversation=page.data.conversation;
  page.setData({text:'name=Local seller validation '+Date.now()+'; category=ceramics; description=Unpublished local integration test; price=20; quantity=7'});
  await checked(await page.send());
  const listing=page.data.changes.find(d=>d.action==='listing'&&d.status==='pending');assert(listing);
  await checked(await page.confirmChange({currentTarget:{dataset:{id:listing.id}}}));
  const applied=page.data.changes.find(d=>d.id===listing.id);assert.equal(applied.status,'applied');
  const product=page.data.products.find(p=>p.slug===applied.result.product);assert(product);assert.equal(product.active,false);assert.equal(product.quantity,7);
  const index=page.data.products.findIndex(p=>p.slug===product.slug);
  page.onProductField({currentTarget:{dataset:{index,field:'editQuantity'}},detail:{value:'9'}});
  await checked(await page.prepareProduct({currentTarget:{dataset:{index,action:'stock'}}}));
  const stock=page.data.changes.find(d=>d.action==='stock'&&d.status==='pending');assert(stock);
  assert.equal((await web('snapshot/')).products.find(p=>p.slug===product.slug).quantity,7,'Preview changed stock before confirmation.');
  await checked(await page.confirmChange({currentTarget:{dataset:{id:stock.id}}}));
  assert.equal((await web('snapshot/')).products.find(p=>p.slug===product.slug).quantity,9);
  await web('changes/'+stock.id+'/confirm/',{confirmed:true});
  assert.equal((await web('snapshot/')).products.find(p=>p.slug===product.slug).quantity,9);
  const priceIndex=page.data.products.findIndex(p=>p.slug===product.slug);
  page.onProductField({currentTarget:{dataset:{index:priceIndex,field:'editPrice'}},detail:{value:'25.50'}});
  await checked(await page.prepareProduct({currentTarget:{dataset:{index:priceIndex,action:'price'}}}));
  const price=page.data.changes.find(d=>d.action==='price'&&d.status==='pending');assert(price);
  assert.equal((await web('snapshot/')).products.find(p=>p.slug===product.slug).price,'20.00');
  global.wx.showModal=o=>o.success({confirm:false});
  await checked(await page.confirmChange({currentTarget:{dataset:{id:price.id}}}));
  assert.equal((await web('snapshot/')).products.find(p=>p.slug===product.slug).price,'20.00','Cancel must not apply a price change.');
  global.wx.showModal=o=>o.success({confirm:true});
  await checked(await page.confirmChange({currentTarget:{dataset:{id:price.id}}}));
  assert.equal((await web('snapshot/')).products.find(p=>p.slug===product.slug).price,'25.50');
  const fromWeb=await web('conversations/'+conversation+'/');assert(fromWeb.messages.some(m=>m.channel==='developer'));assert(fromWeb.changes.some(c=>c.id===stock.id&&c.status==='applied'));
  const snapshot=await web('snapshot/');
  await checked(await page.quick({currentTarget:{dataset:{text:'low stock'}}}));
  assert.equal(page.data.tab,'products');
  assert.deepEqual(Array.from(page.data.products,p=>p.slug).sort(),snapshot.products.filter(p=>p.low_stock).map(p=>p.slug).sort(),'Mini Program must display only the low-stock results returned by the shared API.');
  await checked(await page.quick({currentTarget:{dataset:{text:'my products'}}}));
  assert.equal(page.data.products.length,snapshot.products.length,'Full catalogue query must restore all owned products.');
  await checked(await page.quick({currentTarget:{dataset:{text:'my orders'}}}));
  assert.equal(page.data.tab,'orders');
  assert.deepEqual(Array.from(page.data.orders,o=>o.uuid).sort(),snapshot.orders.map(o=>o.uuid).sort());
  let shipment=false;
  if(process.env.SELLER_TEST_ORDER){
    const index=page.data.orders.findIndex(o=>o.uuid===process.env.SELLER_TEST_ORDER);
    assert(index>=0,'Requested test order is missing.');
    const order=page.data.orders[index];
    assert(order.order_number.startsWith('DEMO-SELLER-'),'Only labelled demo orders may be dispatched by this harness.');
    assert(order.canShip,'The demo order has already shipped or is not eligible. Create a new run.');
    page.onOrderField({currentTarget:{dataset:{index,field:'carrierInput'}},detail:{value:'DEMO Courier - no delivery'}});
    page.onOrderField({currentTarget:{dataset:{index,field:'trackingInput'}},detail:{value:'DEMO123456789'}});
    await checked(await page.prepareShipment({currentTarget:{dataset:{index}}}));
    const change=page.data.changes.find(d=>d.action==='fulfillment'&&d.status==='pending'&&d.target===order.uuid);
    assert(change,'Shipment preview was not created.');
    assert.equal((await web('snapshot/')).orders.find(o=>o.uuid===order.uuid).can_ship,true);
    await checked(await page.confirmChange({currentTarget:{dataset:{id:change.id}}}));
    const shipped=(await web('snapshot/')).orders.find(o=>o.uuid===order.uuid);
    assert.equal(shipped.can_ship,false);assert.equal(shipped.fulfillment.tracking_number,'DEMO123456789');
    shipment=true;
  }
  const linked=(await web('links/')).links.find(l=>!originalLinks.includes(l.id));assert(linked);
  await web('links/'+linked.id+'/unlink/',{confirmed:true});
  await assert.rejects(()=>api.request('/me/'));
  const result={passed:true,realDjango:true,mockedWxRuntime:true,liveWechat:false,sharedConversation:true,
    unpublishedListing:true,stockBeforeConfirmation:7,stockAfterConfirmation:9,priceAfterConfirmation:'25.50',cancelPreservesPrice:true,shipment,idempotentConfirm:true,filteredLowStock:true,ownOrderQuery:true,unlinkRevokedSession:true,product:product.slug};
  console.log(JSON.stringify(result,null,2));
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});

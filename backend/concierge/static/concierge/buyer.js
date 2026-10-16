(() => {
  'use strict';
  const $ = id => document.getElementById(id), panel = $('buyer-panel');
  if (!panel) return;
  const config = JSON.parse($('af-config')?.textContent || '{}');
  const zh = document.documentElement.lang.startsWith('zh');
  const tr = (en, cn) => zh ? cn : en;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let busy = false, loaded = false, loading = false, pending = null, returnFocus = null;
  async function request(path, body) {
    const r = await fetch('/api/buyer-assistant/' + path + '/', {method:body === undefined ? 'GET' : 'POST', credentials:'same-origin', cache:'no-store', headers:{'Content-Type':'application/json','X-CSRFToken':config.csrf || ''}, body:body === undefined ? undefined : JSON.stringify(body)});
    const result = await r.json();
    if (!r.ok) throw new Error(result.detail || tr('Please retry.','请重试。'));
    return result;
  }
  function render(text, response) {
    const turn = document.createElement('div'); turn.className = 'buyer-turn';
    const cards = (response.products || []).map(p => {
      const rating = p.review_count ? `${Number(p.rating).toFixed(1)} / 5 · ${p.review_count} ${tr('reviews','条评价')}` : tr('No published reviews yet','暂无已发布评价');
      const stock = p.made_to_order ? tr('Made to order','按单制作') : p.available ? tr('Available','有货') : tr('Currently unavailable','暂时缺货');
      return `<a class="buyer-product" href="${esc(p.url)}"><img src="${esc(p.image)}" alt="" loading="lazy"><div><strong>${esc(p.name)}</strong><span>${esc(p.maker)}</span><span class="buyer-price">${p.price_label === 'from' ? tr('From ','起价 ') : ''}${esc(p.currency)} ${esc(p.price)}</span><span>${esc(stock)} · ${esc(rating)}</span><span>${esc((p.materials || []).join(' · '))}</span><span>${tr('View product →','查看商品 →')}</span></div></a>`;
    }).join('');
    turn.innerHTML = `<div class="buyer-user">${esc(text)}</div><p class="buyer-reply">${esc(response.reply)}</p>${cards}<small class="buyer-basis">${esc(response.comparison_basis || '')}</small>`;
    $('buyer-messages').append(turn); $('buyer-messages').scrollTop = $('buyer-messages').scrollHeight;
  }
  async function open() {
    returnFocus = document.activeElement; panel.hidden = false; $('buyer-open').setAttribute('aria-expanded','true'); $('buyer-text').focus();
    if (!loaded) {loaded = true; loading = true; $('buyer-form').querySelector('button').disabled = true; try {const data = await request('history'); if (data.messages.length) {$('buyer-messages').replaceChildren(); data.messages.forEach(m => render(m.text,m.response));}} catch (e) {loaded = false;} finally {loading = false; $('buyer-form').querySelector('button').disabled = busy;}}
  }
  function close() {panel.hidden = true; $('buyer-open').setAttribute('aria-expanded','false'); returnFocus?.focus();}
  async function send(text) {
    if (busy || loading || !text.trim()) return;
    busy = true; $('buyer-error').hidden = true; $('buyer-form').querySelector('button').disabled = true;
    if (pending?.text !== text) pending = {text,request_id:crypto.randomUUID()};
    try {const result = await request('messages',pending); if ($('buyer-messages').querySelector('.buyer-welcome')) $('buyer-messages').replaceChildren(); render(text,result); pending = null; $('buyer-text').value = '';}
    catch (e) {$('buyer-error').textContent = e.message; $('buyer-error').hidden = false;}
    finally {busy = false; $('buyer-form').querySelector('button').disabled = false; $('buyer-text').focus();}
  }
  $('buyer-open').addEventListener('click', () => panel.hidden ? open() : close());
  $('buyer-close').addEventListener('click', close);
  document.addEventListener('keydown', e => {if (e.key === 'Escape' && !panel.hidden) close();});
  $('buyer-form').addEventListener('submit', e => {e.preventDefault(); send($('buyer-text').value.trim());});
  document.querySelectorAll('[data-buyer-prompt]').forEach(button => button.addEventListener('click', () => send(button.dataset.buyerPrompt)));
  document.querySelectorAll('[data-buyer-start]').forEach(form => form.addEventListener('submit', async e => {e.preventDefault(); const input = form.querySelector('input'); const text = input.value.trim(); await open(); await send(text); input.value = '';}));
  $('buyer-reset').addEventListener('click', async () => {if (busy || loading) return; busy = true; $('buyer-form').querySelector('button').disabled = true; try {await request('reset',{}); $('buyer-messages').replaceChildren(); pending = null; $('buyer-text').focus();} catch(e) {$('buyer-error').textContent = e.message; $('buyer-error').hidden = false;} finally {busy = false; $('buyer-form').querySelector('button').disabled = false;}});
})();

(() => {
  'use strict';
  const $ = id => document.getElementById(id), panel = $('buyer-panel');
  if (!panel) return;
  const config = JSON.parse($('af-config')?.textContent || '{}');
  const zh = document.documentElement.lang.startsWith('zh');
  const tr = (en, cn) => zh ? cn : en;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const welcome = $('buyer-messages').firstElementChild?.cloneNode(true);
  const chips = [...document.querySelectorAll('[data-buyer-action]')];
  const menu = $('support-options'), launcher = $('support-open');
  let busy = false, loaded = false, loading = false, pending = null, returnFocus = null;

  function announce(kind) {
    document.dispatchEvent(new CustomEvent('atelier:support-open', {detail: {kind}}));
  }
  function closeMenu(restoreFocus = false) {
    menu.hidden = true;
    launcher.setAttribute('aria-expanded', 'false');
    if (restoreFocus) launcher.focus();
  }
  const messagesLauncher = $('crafty-launcher');
  if (messagesLauncher) {
    $('support-message-slot').append(messagesLauncher);
    messagesLauncher.classList.add('support-choice');
    messagesLauncher.addEventListener('click', () => closeMenu());
  }
  document.body.classList.add('support-ready');
  launcher.addEventListener('click', () => {
    if (!menu.hidden) return closeMenu(true);
    announce('chooser');
    menu.hidden = false;
    launcher.setAttribute('aria-expanded', 'true');
    $('buyer-open').focus();
  });
  $('support-close').addEventListener('click', () => closeMenu(true));
  document.addEventListener('click', event => {
    if (!menu.hidden && !$('support-hub').contains(event.target)) closeMenu();
  });
  document.addEventListener('atelier:support-open', event => {
    if (event.detail?.kind !== 'buyer' && !panel.hidden) close(false);
    if (event.detail?.kind !== 'chooser') closeMenu();
  });
  const unread = $('crafty-unread-badge');
  if (unread) {
    const updateUnread = () => {
      const badge = $('support-unread');
      badge.textContent = unread.textContent;
      badge.hidden = unread.style.display === 'none' || !unread.textContent.trim();
      badge.setAttribute('aria-label', tr('Unread seller messages: ', '未读卖家消息：') + unread.textContent);
    };
    new MutationObserver(updateUnread).observe(unread, {childList: true, characterData: true, subtree: true, attributes: true, attributeFilter: ['style']});
    updateUnread();
  }

  function engine(enabled) {
    $('buyer-engine').textContent = enabled ? tr('DeepSeek AI · Verified catalogue','DeepSeek AI · 真实商品目录') : tr('Catalogue matching · Current prices','目录匹配 · 实时价格');
    $('buyer-footnote').textContent = enabled ? tr('DeepSeek processes free-text requests and public catalogue data. Quick filters use catalogue facts. No orders or payments are executed.','DeepSeek 处理自然语言请求和公开商品信息，快捷筛选使用商品记录。不会代你下单或付款。') : tr('You choose and check out. The assistant never places an order or pays for you.','由你选择并结账。助手不会代你下单或付款。');
  }
  function controls() {
    $('buyer-form').querySelector('button').disabled = busy || loading;
    $('buyer-reset').disabled = busy || loading;
    chips.forEach(button => {button.disabled = busy || loading;});
    $('buyer-status').hidden = !(busy || loading);
  }
  async function request(path, body) {
    const r = await fetch('/api/buyer-assistant/' + path + '/', {method:body === undefined ? 'GET' : 'POST', credentials:'same-origin', cache:'no-store', headers:{'Content-Type':'application/json','X-CSRFToken':config.csrf || ''}, body:body === undefined ? undefined : JSON.stringify(body)});
    const result = await r.json();
    if (!r.ok) throw new Error(result.detail || tr('Please retry.','请重试。'));
    return result;
  }
  const price = p => `${p.price_label === 'from' ? tr('From ', '起价 ') : ''}${esc(p.currency)} ${esc(p.price)}`;
  const rating = p => p.review_count ? `${Number(p.rating).toFixed(1)} / 5 · ${esc(p.review_count)} ${tr(p.review_count === 1 ? 'published review' : 'published reviews','条已发布评价')}` : tr('No published reviews yet','暂无已发布评价');
  const availability = p => p.made_to_order ? tr('Made to order','按单制作') : p.available ? tr('Available','有货') : tr('Currently unavailable','暂时缺货');
  const productLink = p => `<a href="${esc(p.url)}">${esc(p.name)}</a>`;

  function cards(products, mode) {
    return products.map(p => {
      const options = (p.options || []).map(option => option.label).join(' · ');
      const excerpts = mode === 'reviews' ? (p.review_examples || []).map(review => `<blockquote class="buyer-review"><strong>${esc(review.rating)}/5${review.verified_purchase ? ' · ' + tr('Verified purchase','已验证购买') : ''}</strong>${review.title ? `<b>${esc(review.title)}</b>` : ''}<p>${esc(review.body || tr('Rating only; no written comment.','仅评分，未填写文字评价。'))}</p></blockquote>`).join('') : '';
      return `<article class="buyer-product ${mode === 'reviews' ? 'buyer-product--reviews' : ''}"><a class="buyer-product-image" href="${esc(p.url)}" tabindex="-1" aria-hidden="true"><img src="${esc(p.image)}" alt="" loading="lazy"></a><div><strong>${productLink(p)}</strong><span>${esc(p.maker)}</span><span class="buyer-price">${price(p)}</span><span>${esc(availability(p))} · ${rating(p)}</span><span>${esc((p.materials || []).join(' · '))}</span>${options ? `<span class="buyer-options">${tr('Matching options: ','匹配规格：')}${esc(options)}</span>` : ''}${excerpts}<a class="buyer-product-link" href="${esc(p.url)}">${tr('View product →','查看商品 →')}</a></div></article>`;
    }).join('');
  }
  function comparison(products, mode) {
    const headings = mode === 'price' ? [tr('Piece','商品'), tr('Item price','商品单价'), tr('Above lowest in its currency','比同币种最低价高')] : [tr('Piece','商品'), tr('Item price','商品单价'), tr('Reviews','评价'), tr('Materials','材质'), tr('Availability','供货情况')];
    const rows = products.map(p => {
      const cells = mode === 'price' ? [price(p), Number(p.price_difference) === 0 ? tr('Lowest in these results','这些结果中的最低价') : `${esc(p.currency)} +${esc(p.price_difference ?? '—')}`] : [price(p), rating(p), esc((p.materials || []).join(' · ') || tr('Not specified','未提供')), esc(availability(p))];
      return `<tr><th scope="row">${productLink(p)}<small>${esc(p.maker)}</small></th>${cells.map(value => `<td>${value}</td>`).join('')}</tr>`;
    }).join('');
    return `<div class="buyer-table-scroll" tabindex="0" role="region" aria-label="${tr('Product comparison table','商品对比表')}"><table class="buyer-comparison"><thead><tr>${headings.map(h => `<th scope="col">${h}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table></div>`;
  }
  function render(text, response) {
    const turn = document.createElement('div'); turn.className = 'buyer-turn';
    const view = response.presentation || {}, mode = view.mode || 'search', products = response.products || [];
    turn.dataset.resultMode = mode;
    const heading = view.title ? `<h3 class="buyer-result-title">${esc(view.title)}</h3><p class="buyer-result-summary">${esc(view.summary)}</p>` : '';
    const tags = (view.filters || []).map(filter => `<span>${esc(filter)}</span>`).join('');
    const content = products.length && (mode === 'price' || mode === 'compare') ? comparison(products, mode) : cards(products, mode);
    const showReply = !view.title || !products.length || response.engine === 'deepseek';
    turn.innerHTML = `<div class="buyer-user">${esc(text)}</div>${response.notice ? `<p class="buyer-notice">${esc(response.notice)}</p>` : ''}${heading}${tags ? `<div class="buyer-filter-tags" aria-label="${tr('Applied filters','当前筛选条件')}">${tags}</div>` : ''}${showReply ? `<p class="buyer-reply">${esc(response.reply || '')}</p>` : ''}${content}<small class="buyer-basis">${esc(response.comparison_basis || '')}</small>${response.has_more ? `<button type="button" class="buyer-more">${tr('Show two more','再看两件')}</button>` : ''}`;
    turn.querySelector('.buyer-more')?.addEventListener('click', () => send(tr('Show two more','再看两件')));
    $('buyer-messages').append(turn);
    $('buyer-messages').scrollTop = Math.max(0, turn.offsetTop - 12);
  }
  async function open() {
    returnFocus = document.activeElement;
    announce('buyer'); panel.hidden = false; $('buyer-open').setAttribute('aria-expanded','true'); $('buyer-text').focus();
    if (!loaded) {
      loaded = true; loading = true; controls();
      try {const data = await request('history'); engine(data.ai_enabled); if (data.messages.length) {$('buyer-messages').replaceChildren(); data.messages.forEach(m => render(m.text,m.response));}}
      catch (e) {loaded = false; $('buyer-error').textContent = e.message; $('buyer-error').hidden = false;}
      finally {loading = false; controls();}
    }
  }
  function close(restoreFocus = true) {
    panel.hidden = true; $('buyer-open').setAttribute('aria-expanded','false');
    if (restoreFocus) (returnFocus?.getClientRects().length ? returnFocus : launcher).focus();
  }
  async function send(text, action) {
    if (busy || loading || !text.trim()) return;
    busy = true; $('buyer-error').hidden = true; controls();
    chips.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.buyerAction === action)));
    if (pending?.text !== text || pending?.action !== action) pending = {text, ...(action ? {action} : {}), request_id:crypto.randomUUID()};
    try {const result = await request('messages',pending); if ($('buyer-messages').querySelector('.buyer-welcome')) $('buyer-messages').replaceChildren(); render(text,result); pending = null; $('buyer-text').value = '';}
    catch (e) {$('buyer-error').textContent = e.message; $('buyer-error').hidden = false;}
    finally {busy = false; controls(); if (!panel.hidden) $('buyer-text').focus();}
  }
  $('buyer-open').addEventListener('click', open);
  $('buyer-close').addEventListener('click', () => close());
  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    if (!menu.hidden) closeMenu(true);
    if (!panel.hidden) close();
  });
  $('buyer-form').addEventListener('submit', e => {e.preventDefault(); send($('buyer-text').value.trim());});
  chips.forEach(button => button.addEventListener('click', () => send(button.dataset.buyerPrompt, button.dataset.buyerAction)));
  document.querySelectorAll('[data-buyer-start]').forEach(form => form.addEventListener('submit', async e => {e.preventDefault(); const input = form.querySelector('input'); const text = input.value.trim(); await open(); await send(text); input.value = '';}));
  $('buyer-reset').addEventListener('click', async () => {
    if (busy || loading) return;
    busy = true; controls();
    try {await request('reset',{}); $('buyer-messages').replaceChildren(...(welcome ? [welcome.cloneNode(true)] : [])); pending = null; chips.forEach(button => button.setAttribute('aria-pressed','false')); $('buyer-error').hidden = true; $('buyer-text').focus();}
    catch(e) {$('buyer-error').textContent = e.message; $('buyer-error').hidden = false;}
    finally {busy = false; controls();}
  });
})();

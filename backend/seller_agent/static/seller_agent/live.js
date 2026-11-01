/* Open school-demo pages follow committed changes in the shared database. */
(() => {
  'use strict';
  const page = document.body.dataset.page;
  const cataloguePages = new Set(['home', 'shop', 'collection_detail', 'product_detail',
    'maker_detail', 'search', 'seller_product_list']);
  const orderPages = new Set(['account_overview', 'account_orders', 'account_order_detail']);
  const kind = orderPages.has(page) ? 'orders' : cataloguePages.has(page) ? 'catalogue' : null;
  if (!kind) return;
  let revision = null, pendingReload = false, busy = false, dirty = false;
  document.addEventListener('input', event => {
    if (event.target.closest('form')) dirty = true;
  });
  function mayReload() {
    return !dirty && !document.hidden &&
      !document.activeElement?.matches('input,textarea,select,[contenteditable="true"]') &&
      !document.querySelector('[aria-modal="true"].is-open,dialog[open],.drawer.is-open,[aria-modal="true"][aria-hidden="false"]');
  }
  async function poll() {
    if (document.hidden || busy) return;
    if (pendingReload && mayReload()) { location.reload(); return; }
    busy = true;
    try {
      const response = await fetch('/api/store-revisions/', {cache:'no-store', credentials:'same-origin'});
      if (!response.ok) return;
      const current = (await response.json())[kind];
      if (revision !== null && current && current !== revision) {
        pendingReload = true;
        if (mayReload()) location.reload();
      }
      revision = current;
    } catch (_) { /* Retry when the connection returns; keep the current page. */ }
    finally { busy = false; }
  }
  setInterval(poll, 5000);
  document.addEventListener('visibilitychange', poll);
  poll();
})();

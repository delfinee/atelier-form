/* Atelier Form storefront behaviour; cart totals stay server-side. */
(function () {
  "use strict";

  const CFG = JSON.parse(document.getElementById("af-config")?.textContent || "{}");
  const URLS = CFG.urls || {};
  const KEY = { wish: "af.wishlist.v1", recent: "af.recent.v1" };
  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  /* ------------------------------------------------------- local store --- */
  function read(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (e) {
      return fallback;                      // private mode, cleared data, quota
    }
  }
  function write(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* non-fatal */ }
  }

  const state = {
    cart: null,                             // server truth, loaded on boot
    // Signed-in wishlists come from the server; guests keep one locally.
    wish: CFG.authenticated ? (CFG.wishlist || []) : read(KEY.wish, []),
    recent: read(KEY.recent, []),
  };

  const listeners = [];
  const onChange = (fn) => listeners.push(fn);
  const emit = () => listeners.forEach((fn) => fn());

  /* -------------------------------------------------------------- api --- */
  async function api(url, { method = "GET", body } = {}) {
    const options = {
      method,
      credentials: "same-origin",
      headers: { "Accept": "application/json" },
    };
    if (body !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.headers["X-CSRFToken"] = CFG.csrf || "";
      options.body = JSON.stringify(body);
    } else if (method !== "GET") {
      options.headers["X-CSRFToken"] = CFG.csrf || "";
    }

    const response = await fetch(url, options);
    if (response.status === 204) return null;

    let data = null;
    try { data = await response.json(); } catch (e) { data = null; }
    if (!response.ok) {
      const error = new Error((data && data.detail) || "Something went wrong.");
      error.status = response.status;
      error.data = data;
      throw error;
    }
    return data;
  }

  function money(value) {
    const symbol = CFG.currency_symbol || "$";
    const n = Number(value) || 0;
    return symbol + n.toFixed(2).replace(/\.00$/, "");
  }

  /* ------------------------------------------------------------- cart --- */
  async function loadCart() {
    try {
      state.cart = await api(URLS.cart);
    } catch (e) {
      state.cart = { items: [], item_count: 0, subtotal: 0, shipping: 0, total: 0 };
    }
    emit();
    return state.cart;
  }

  async function addToCart(slug, variant, quantity) {
    state.cart = await api(URLS.cartItems, {
      method: "POST",
      body: { product_slug: slug, variant: variant || null, quantity: Number(quantity) || 1 },
    });
    emit();
    return state.cart;
  }

  async function setQty(itemId, quantity) {
    state.cart = await api(`${URLS.cartItems}${itemId}/`, {
      method: "PATCH", body: { quantity: Number(quantity) },
    });
    emit();
  }

  async function removeLine(itemId) {
    state.cart = await api(`${URLS.cartItems}${itemId}/`, { method: "DELETE" });
    emit();
  }

  const cartItems = () => (state.cart && state.cart.items) || [];
  const cartCount = () => (state.cart && state.cart.item_count) || 0;

  /* --------------------------------------------------------- wishlist --- */
  const inWish = (slug) => state.wish.indexOf(slug) !== -1;

  async function toggleWish(slug) {
    const adding = !inWish(slug);

    if (CFG.authenticated) {
      if (adding) await api(`${URLS.wishlist}${slug}/`, { method: "POST" });
      else await api(`${URLS.wishlist}${slug}/remove/`, { method: "DELETE" });
    }

    if (adding) state.wish.push(slug);
    else state.wish.splice(state.wish.indexOf(slug), 1);

    if (!CFG.authenticated) write(KEY.wish, state.wish);
    emit();
    return adding;
  }

  /* ---------------------------------------------------- recently seen --- */
  function noteViewed(slug) {
    state.recent = [slug].concat(state.recent.filter((s) => s !== slug)).slice(0, 8);
    write(KEY.recent, state.recent);
  }

  let catalogue = null;
  function loadCatalogue() {
    if (catalogue) return Promise.resolve(catalogue);
    return fetch(URLS.catalogue, { credentials: "same-origin" })
      .then((r) => (r.ok ? r.json() : {}))
      .then((data) => { catalogue = data; return data; })
      .catch(() => { catalogue = {}; return catalogue; });
  }

  /* ------------------------------------------------------------ toast --- */
  let toastHost = null;
  function toast(message) {
    if (!toastHost) {
      toastHost = document.createElement("div");
      toastHost.className = "toasts";
      toastHost.setAttribute("role", "status");
      toastHost.setAttribute("aria-live", "polite");
      document.body.appendChild(toastHost);
    }
    const el = document.createElement("div");
    el.className = "toast";
    el.textContent = message;
    toastHost.appendChild(el);
    setTimeout(() => {
      el.style.opacity = "0";
      setTimeout(() => el.remove(), 300);
    }, 2800);
  }

  /* ------------------------------------------------- overlay plumbing --- */
  let lastFocus = null;
  const lockScroll = (on) => document.body.classList.toggle("is-locked", on);

  function openPanel(el, focusTarget) {
    lastFocus = document.activeElement;
    el.classList.add("is-open");
    el.removeAttribute("hidden");
    lockScroll(true);
    (focusTarget || el.querySelector("input, button, a") || el).focus({ preventScroll: true });
  }
  function closePanel(el) {
    el.classList.remove("is-open");
    lockScroll(false);
    if (lastFocus) { lastFocus.focus({ preventScroll: true }); lastFocus = null; }
  }
  function trapTab(e, container) {
    if (e.key !== "Tab") return;
    const items = $$('a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])', container)
      .filter((el) => el.offsetParent !== null);
    if (!items.length) return;
    const first = items[0], last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }

  /* ---------------------------------------------------------- header --- */
  function initHeader() {
    const header = $(".site-header");
    if (header) {
      const onScroll = () => header.classList.toggle("is-stuck", window.scrollY > 8);
      onScroll();
      window.addEventListener("scroll", onScroll, { passive: true });
    }
    const mobileNav = $("#mobile-nav");
    $$("[data-nav-open]").forEach((b) => b.addEventListener("click", () => openPanel(mobileNav)));
    $$("[data-nav-close]").forEach((b) => b.addEventListener("click", () => closePanel(mobileNav)));
    if (mobileNav) {
      mobileNav.addEventListener("keydown", (e) => {
        if (e.key === "Escape") closePanel(mobileNav);
        trapTab(e, mobileNav);
      });
    }
  }

  /* ---------------------------------------------------- search overlay --- */
  function initSearch() {
    const overlay = $("#search-overlay");
    if (!overlay) return;
    const input = $("[data-search-input]", overlay);
    const results = $("[data-search-results]", overlay);
    const initial = $("[data-search-initial]", overlay);
    let timer = null;

    $$("[data-search-open]").forEach((b) => b.addEventListener("click", () => openPanel(overlay, input)));
    $$("[data-search-close]").forEach((b) => b.addEventListener("click", () => closePanel(overlay)));
    overlay.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closePanel(overlay);
      trapTab(e, overlay);
    });

    function render(data) {
      const blocks = [];
      if (data.products.length) {
        blocks.push('<div><h4>Products</h4>' + data.products.map((p) =>
          `<a class="search-hit" href="${p.url}"><img src="${p.image}" alt="" loading="lazy">
             <span><span class="search-hit__name">${p.name}</span>
             <span class="search-hit__meta">${p.label} · ${money(p.price)}</span></span></a>`).join("") + "</div>");
      }
      ["collections", "makers", "articles"].forEach((kind) => {
        const items = data[kind] || [];
        if (!items.length) return;
        const label = kind.charAt(0).toUpperCase() + kind.slice(1);
        blocks.push(`<div><h4>${label}</h4>` + items.map((i) =>
          `<a class="search-hit" href="${i.url}"><span>
             <span class="search-hit__name">${i.title || i.name}</span>
             ${i.discipline ? `<span class="search-hit__meta">${i.discipline}</span>` : ""}
           </span></a>`).join("") + "</div>");
      });
      results.innerHTML = blocks.length
        ? blocks.join("")
        : '<p class="muted">Nothing matched that. Try a material, a maker or a room.</p>';
    }

    input.addEventListener("input", () => {
      const q = input.value.trim();
      clearTimeout(timer);
      if (q.length < 2) {
        results.innerHTML = "";
        if (initial) initial.hidden = false;
        return;
      }
      if (initial) initial.hidden = true;
      timer = setTimeout(() => {
        fetch(URLS.search + "?q=" + encodeURIComponent(q), { credentials: "same-origin" })
          .then((r) => r.json()).then(render).catch(() => {});
      }, 180);
    });
  }

  /* ------------------------------------------------------- line items --- */
  function lineItemHTML(line) {
    const variant = line.variant_label
      ? `<div class="line-item__meta">${line.variant_label}</div>` : "";
    return `<div class="line-item" data-line data-item-id="${line.id}">
      <a class="media" href="/products/${line.product_slug}/" aria-hidden="true" tabindex="-1">
        <img src="${line.image}" alt="" loading="lazy">
      </a>
      <div>
        <a class="line-item__name" href="/products/${line.product_slug}/">${line.product_name}</a>
        ${variant}
        <div class="line-item__controls">
          <div class="qty">
            <button type="button" data-step="-1" aria-label="Decrease quantity">
              <svg class="icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M5 12h14"/></svg>
            </button>
            <input type="number" min="1" max="99" value="${line.quantity}" aria-label="Quantity for ${line.product_name}">
            <button type="button" data-step="1" aria-label="Increase quantity">
              <svg class="icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
            </button>
          </div>
          <button type="button" class="remove" data-remove>Remove</button>
        </div>
      </div>
      <div class="line-item__price">${money(line.line_total)}</div>
    </div>`;
  }

  function bindLineControls(root) {
    $$("[data-line]", root).forEach((el) => {
      const id = el.dataset.itemId;
      const input = $("input", el);
      $$("[data-step]", el).forEach((btn) => btn.addEventListener("click", () => {
        guard(setQty(id, Number(input.value) + Number(btn.dataset.step)));
      }));
      input.addEventListener("change", () => guard(setQty(id, input.value)));
      $("[data-remove]", el).addEventListener("click", () => {
        guard(removeLine(id).then(() => toast("Removed from your bag")));
      });
    });
  }

  /** Surface an API error as a toast and re-sync, rather than failing silently. */
  function guard(promise) {
    return promise.catch((error) => {
      toast(error.message || "Something went wrong.");
      return loadCart();
    });
  }

  /* ----------------------------------------------------- cart drawer --- */
  function initDrawer() {
    const drawer = $("#cart-drawer");
    const backdrop = $("#drawer-backdrop");
    if (!drawer) return;

    function open() {
      backdrop.classList.add("is-open");
      openPanel(drawer);
      renderDrawer();
    }
    function close() {
      backdrop.classList.remove("is-open");
      closePanel(drawer);
    }
    $$("[data-cart-open]").forEach((b) => b.addEventListener("click", (e) => { e.preventDefault(); open(); }));
    $$("[data-cart-close]").forEach((b) => b.addEventListener("click", close));
    dismissers.push(close);
    backdrop.addEventListener("click", () => dismissers.forEach((fn) => fn()));
    drawer.addEventListener("keydown", (e) => {
      if (e.key === "Escape") close();
      trapTab(e, drawer);
    });
    window.AF_openCart = open;
  }

  const dismissers = [];

  function renderDrawer() {
    const body = $("[data-drawer-body]");
    if (!body) return;
    const items = cartItems();
    const drawer = $("#cart-drawer");
    const emptyTitle = drawer?.dataset.emptyTitle || "Your bag is empty";
    const emptyNote = drawer?.dataset.emptyNote || "Nothing in here yet. The shop is a good place to start.";
    const browseShop = drawer?.dataset.browseShop || "Browse the shop";

    if (!items.length) {
      body.innerHTML = `<div class="empty-state"><h3>Your bag is empty</h3>
        <p class="muted">Nothing in here yet. The shop is a good place to start.</p>
        <a class="btn btn--outline" href="/shop/" style="margin-top:1.2rem">Browse the shop</a></div>`;
      body.innerHTML = `<div class="empty-state"><h3>${emptyTitle}</h3>
        <p class="muted">${emptyNote}</p>
        <a class="btn btn--outline" href="/shop/" style="margin-top:1.2rem">${browseShop}</a></div>`;
    } else {
      body.innerHTML = items.map(lineItemHTML).join("");
      bindLineControls(body);
    }

    const sub = $("[data-drawer-subtotal]");
    if (sub) sub.textContent = money(state.cart ? state.cart.subtotal : 0);
    const note = $("[data-drawer-note]");
    if (note) {
      const left = (CFG.free_shipping_threshold || 0) - Number(state.cart ? state.cart.subtotal : 0);
      note.textContent = !items.length ? ""
        : left > 0 ? `${money(left)} away from complimentary delivery`
                   : "Complimentary delivery applied";
    }
    const foot = $("[data-drawer-foot]");
    if (foot) foot.hidden = !items.length;
  }

  /* -------------------------------------------------------- bag page --- */
  function initBagPage() {
    const host = $("[data-cart-lines]");
    if (!host) return;

    function render() {
      const items = cartItems();
      const empty = $("[data-cart-empty]");
      const filled = $("[data-cart-filled]");

      if (!items.length) {
        if (empty) empty.hidden = false;
        if (filled) filled.hidden = true;
        return;
      }
      if (empty) empty.hidden = true;
      if (filled) filled.hidden = false;
      host.innerHTML = items.map(lineItemHTML).join("");
      bindLineControls(host);

      const cart = state.cart;
      const set = (sel, value) => { const el = $(sel); if (el) el.textContent = value; };
      set("[data-subtotal]", money(cart.subtotal));
      set("[data-shipping]", Number(cart.shipping) === 0 ? "Complimentary" : money(cart.shipping));
      set("[data-total]", money(cart.total));
      set("[data-item-count]", cart.item_count + " item" + (cart.item_count === 1 ? "" : "s"));

      const threshold = CFG.free_shipping_threshold || 0;
      const fill = $("[data-progress-fill]");
      const label = $("[data-progress-label]");
      if (fill) fill.style.width = Math.min(100, (Number(cart.subtotal) / threshold) * 100) + "%";
      if (label) {
        label.textContent = Number(cart.subtotal) >= threshold
          ? "Complimentary delivery applied"
          : `${money(threshold - Number(cart.subtotal))} away from complimentary delivery`;
      }
    }
    onChange(render);
    render();
  }

  /* --------------------------------------------- recently viewed rail --- */
  function initRecentRail() {
    const host = $("[data-recent-grid]");
    if (!host) return;
    const exclude = host.dataset.exclude || "";
    loadCatalogue().then(() => {
      const items = state.recent
        .filter((s) => s !== exclude)
        .map((s) => catalogue[s]).filter(Boolean).slice(0, 4);
      if (items.length < 2) { host.closest("[data-recent-section]")?.remove(); return; }
      host.innerHTML = items.map((p) => `
        <article class="card">
          <a class="media media--hover card__media" href="${p.url}">
            <img src="${p.image}" alt="${p.name}" loading="lazy">
          </a>
          <h3 class="card__name"><a href="${p.url}">${p.name}</a></h3>
          <p class="card__meta">${p.label}</p>
          <div class="card__price">${money(p.price)}</div>
        </article>`).join("");
    });
  }

  /* ------------------------------------------------------- checkout --- */
  function initCheckout() {
    const form = $("[data-checkout-form]");
    const summary = $("[data-checkout-summary]");
    if (!form || !summary) return;

    const newFields = $("[data-new-address-fields]");
    const addressRadios = $$('input[name="address"]');
    function syncAddressFields() {
      const chosen = $('input[name="address"]:checked');
      if (newFields) newFields.hidden = !!(chosen && chosen.value !== "new");
    }
    addressRadios.forEach((r) => r.addEventListener("change", syncAddressFields));
    syncAddressFields();

    function paint() {
      const items = cartItems();
      const guard = $("[data-checkout-empty]");
      const wrap = $("[data-checkout-form-wrap]");
      if (!items.length) {
        if (guard) guard.hidden = false;
        if (wrap) wrap.hidden = true;
        return;
      }
      if (guard) guard.hidden = true;
      if (wrap) wrap.hidden = false;

      summary.innerHTML = items.map((l) => `<div class="summary__row">
          <span>${l.product_name}${l.variant_label ? " · " + l.variant_label : ""} × ${l.quantity}</span>
          <span>${money(l.line_total)}</span></div>`).join("");

      // Express delivery changes the figure; the authoritative total still
      // comes back from the server when the order is created.
      const express = $('input[name="delivery"]:checked')?.value === "express";
      const subtotal = Number(state.cart.subtotal);
      const shipping = express ? Number(CFG.shipping_express || 0) : Number(state.cart.shipping);
      const set = (sel, v) => { const el = $(sel); if (el) el.textContent = v; };
      set("[data-subtotal]", money(subtotal));
      set("[data-shipping]", shipping === 0 ? "Complimentary" : money(shipping));
      set("[data-total]", money(subtotal + shipping));
    }
    $$('input[name="delivery"]').forEach((r) => r.addEventListener("change", paint));
    onChange(paint);
    paint();

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const errorBox = $("[data-checkout-error]");
      const submit = $('button[type="submit"]', form);
      if (errorBox) errorBox.hidden = true;

      const chosen = $('input[name="address"]:checked');
      const payload = {
        email: $("#co-email").value.trim(),
        phone: $("#co-phone")?.value.trim() || "",
        delivery_method: $('input[name="delivery"]:checked')?.value || "standard",
        gift_note: $("#co-note")?.value.trim() || "",
      };

      if (chosen && chosen.value !== "new") {
        payload.shipping_address_uuid = chosen.value;
      } else {
        payload.shipping_address = {
          first_name: $("#co-first").value.trim(),
          last_name: $("#co-last").value.trim(),
          address_line_1: $("#co-line1").value.trim(),
          address_line_2: $("#co-line2")?.value.trim() || "",
          city: $("#co-city").value.trim(),
          postal_code: $("#co-post").value.trim(),
          country: $("#co-country").value,
          phone: payload.phone,
        };
        payload.save_address = !!$('input[name="save_address"]')?.checked;
      }

      submit.disabled = true;
      submit.textContent = "Placing order…";
      try {
        const order = await api(URLS.checkout, { method: "POST", body: payload });
        window.location.href = order.payment?.checkout_url || ("/checkout/confirmation/" + order.uuid + "/");
      } catch (error) {
        submit.disabled = false;
        submit.textContent = "Place order";
        if (errorBox) {
          errorBox.textContent = error.message;
          errorBox.hidden = false;
          errorBox.scrollIntoView({ block: "center", behavior: "smooth" });
        } else {
          toast(error.message);
        }
        loadCart();
      }
    });
  }

  /* ---------------------------------------------------------- forms --- */
  const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/;

  function fieldError(input, message) {
    const holder = input.closest(".field") || input.parentElement;
    let note = holder.querySelector(".field-error");
    if (message) {
      if (!note) {
        note = document.createElement("p");
        note.className = "field-error";
        holder.appendChild(note);
      }
      note.textContent = message;
      input.classList.add("is-invalid");
      input.setAttribute("aria-invalid", "true");
    } else {
      if (note) note.remove();
      input.classList.remove("is-invalid");
      input.removeAttribute("aria-invalid");
    }
  }

  function validateForm(form) {
    let ok = true, firstBad = null;
    $$("input[required], select[required], textarea[required]", form).forEach((input) => {
      const value = input.value.trim();
      let message = "";
      if (!value) message = "This field is required.";
      else if (input.type === "email" && !EMAIL.test(value)) message = "Enter a valid email address.";
      else if (input.type === "password" && value.length < 8) message = "Use at least 8 characters.";
      fieldError(input, message);
      if (message) { ok = false; firstBad = firstBad || input; }
    });
    if (firstBad) firstBad.focus();
    return ok;
  }

  function initForms() {
    // Server-rendered forms: validate in the browser, then submit normally.
    $$("form[novalidate]").forEach((form) => {
      if (form.hasAttribute("data-checkout-form") || form.hasAttribute("data-newsletter")) return;
      form.addEventListener("submit", (e) => {
        if (!validateForm(form)) e.preventDefault();
      });
      $$("input, select, textarea", form).forEach((input) =>
        input.addEventListener("input", () => {
          if (input.classList.contains("is-invalid")) fieldError(input, "");
        }));
    });

    const news = $("[data-newsletter]");
    if (news) {
      news.addEventListener("submit", (e) => {
        e.preventDefault();
        const input = $("input[type=email]", news);
        const status = $("[data-newsletter-status]", news.parentElement) || $("[data-newsletter-status]");
        api(URLS.newsletter, { method: "POST", body: { email: input.value } })
          .then((data) => {
            if (status) {
              status.textContent = data.message;
              status.className = "newsletter__status is-ok";
            }
            news.reset();
          })
          .catch((error) => {
            if (status) {
              status.textContent = error.data?.error || error.message;
              status.className = "newsletter__status is-error";
            }
          });
      });
    }

    // Contact form posts to the API and stores a real message.
    const contact = $("[data-contact-form]");
    if (contact) {
      contact.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (!validateForm(contact)) return;
        const status = $("[data-contact-status]", contact);
        try {
          await api("/api/contact/", {
            method: "POST",
            body: {
              name: $("#c-name").value.trim(),
              email: $("#c-email").value.trim(),
              subject: $("#c-topic").value,
              order_number: $("#c-order")?.value.trim() || "",
              message: $("#c-message").value.trim(),
            },
          });
          contact.reset();
          if (status) { status.textContent = "Message sent. The studio will reply by email."; status.hidden = false; }
          else toast("Message sent.");
        } catch (error) {
          if (status) { status.textContent = error.message; status.hidden = false; }
          else toast(error.message);
        }
      });
    }
  }

  /* ------------------------------------------------------ accordions --- */
  function initAccordions() {
    $$("[data-accordion] .accordion__head, .filter-group__head").forEach((head) => {
      head.addEventListener("click", () => {
        head.setAttribute("aria-expanded", String(head.getAttribute("aria-expanded") !== "true"));
      });
    });
  }

  /* ---------------------------------------------------------- filters --- */
  function initFilters() {
    const panel = $("[data-filter-panel]");
    if (!panel) return;
    const backdrop = $("#drawer-backdrop");

    function open() {
      panel.classList.add("is-open");
      if (backdrop) backdrop.classList.add("is-open");
      lockScroll(true);
      ($(".filter-group__head", panel) || panel).focus({ preventScroll: true });
    }
    function close() {
      if (!panel.classList.contains("is-open")) return;
      panel.classList.remove("is-open");
      if (backdrop) backdrop.classList.remove("is-open");
      lockScroll(false);
    }
    $$("[data-filter-open]").forEach((b) => b.addEventListener("click", open));
    $$("[data-filter-close]").forEach((b) => b.addEventListener("click", close));
    dismissers.push(close);
    panel.addEventListener("keydown", (e) => {
      if (e.key === "Escape") close();
      else if (panel.classList.contains("is-open")) trapTab(e, panel);
    });

    const sort = $("[data-sort]");
    if (sort) sort.addEventListener("change", () => { window.location.href = sort.value; });
  }

  /* ------------------------------------------------------- pdp gallery --- */
  function initGallery() {
    const gallery = $("[data-gallery]");
    if (!gallery) return;
    const main = $("[data-gallery-main]", gallery);
    const thumbs = $$("[data-gallery-thumb]", gallery);
    thumbs.forEach((thumb) => {
      thumb.addEventListener("click", () => {
        thumbs.forEach((t) => t.setAttribute("aria-selected", "false"));
        thumb.setAttribute("aria-selected", "true");
        main.src = thumb.dataset.full;
      });
    });

    const box = $("#lightbox");
    if (box) {
      const img = $("img", box);
      $("[data-gallery-zoom]", gallery)?.addEventListener("click", () => {
        img.src = main.src;
        openPanel(box, $(".lightbox__close", box));
      });
      $$("[data-lightbox-close]", box).forEach((b) => b.addEventListener("click", () => closePanel(box)));
      box.addEventListener("click", (e) => { if (e.target === box) closePanel(box); });
      box.addEventListener("keydown", (e) => {
        if (e.key === "Escape") closePanel(box);
        trapTab(e, box);
      });
    }
  }

  function initVariants() {
    $$("[data-variant-group]").forEach((group) => {
      const output = $("[data-variant-value]", group);
      $$("[data-variant]", group).forEach((btn) => {
        btn.addEventListener("click", () => {
          $$("[data-variant]", group).forEach((b) => b.setAttribute("aria-pressed", "false"));
          btn.setAttribute("aria-pressed", "true");
          if (output) output.textContent = btn.dataset.variant;
        });
      });
    });
  }

  function initQtySteppers() {
    $$("[data-qty]").forEach((widget) => {
      const input = $("input", widget);
      $$("[data-step]", widget).forEach((btn) => btn.addEventListener("click", () => {
        input.value = Math.min(99, Math.max(1, Number(input.value) + Number(btn.dataset.step)));
      }));
    });
  }

  /* ------------------------------------------------- add / wish binding --- */
  function selectedVariant(scope) {
    // Only a colour/size chip is sent — the server resolves it to a variant row.
    const chosen = $$("[data-variant][aria-pressed='true']", scope || document);
    return chosen.length ? chosen[0].dataset.variant : null;
  }

  function bindAddButtons(root) {
    $$("[data-add-to-cart]", root || document).forEach((btn) => {
      if (btn.dataset.bound) return;
      btn.dataset.bound = "1";
      btn.addEventListener("click", async (e) => {
        e.preventDefault();
        const scope = btn.closest("[data-product-scope]");
        const qtyInput = scope ? $("[data-qty] input", scope) : null;
        btn.disabled = true;
        try {
          await addToCart(btn.dataset.slug,
                          btn.dataset.variant || selectedVariant(scope),
                          qtyInput ? qtyInput.value : 1);
          toast("Added to your bag");
          if (window.AF_openCart && btn.dataset.openDrawer !== "false") window.AF_openCart();
        } catch (error) {
          toast(error.message);
        } finally {
          btn.disabled = false;
        }
      });
    });
  }

  function bindWishButtons(root) {
    $$("[data-wish-toggle]", root || document).forEach((btn) => {
      if (btn.dataset.bound) return;
      btn.dataset.bound = "1";
      const slug = btn.dataset.slug;
      const paint = () => {
        const on = inWish(slug);
        btn.classList.toggle("is-active", on);
        btn.setAttribute("aria-pressed", String(on));
      };
      paint();
      onChange(paint);
      btn.addEventListener("click", async (e) => {
        e.preventDefault();
        try {
          const added = await toggleWish(slug);
          toast(added ? "Saved to your wishlist" : "Removed from your wishlist");
        } catch (error) {
          toast(error.status === 401 || error.status === 403
            ? "Sign in to save pieces to your wishlist."
            : error.message);
        }
      });
    });
  }

  /* ---------------------------------------------------------- counts --- */
  function paintCounts() {
    const count = cartCount();
    $$("[data-cart-count]").forEach((el) => {
      el.textContent = count;
      el.classList.toggle("is-visible", count > 0);
    });
    $$("[data-wish-count]").forEach((el) => {
      el.textContent = state.wish.length;
      el.classList.toggle("is-visible", state.wish.length > 0);
    });
  }

  /* ---------------------------------------------------------- reveal --- */
  function initReveal() {
    const targets = $$("[data-reveal]");
    if (!targets.length || !("IntersectionObserver" in window)) {
      targets.forEach((t) => t.classList.add("is-in"));
      return;
    }
    const io = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) { entry.target.classList.add("is-in"); io.unobserve(entry.target); }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.05 });
    targets.forEach((t) => io.observe(t));
  }

  function initToc() {
    const toc = $("[data-toc]");
    if (!toc || !("IntersectionObserver" in window)) return;
    const links = $$("a", toc);
    const sections = links.map((a) => document.getElementById(a.hash.slice(1))).filter(Boolean);
    const io = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        links.forEach((a) => a.classList.toggle("is-active", a.hash === "#" + entry.target.id));
      });
    }, { rootMargin: "-20% 0px -70% 0px" });
    sections.forEach((s) => io.observe(s));
  }

  /* ------------------------------------------------------------- boot --- */
  document.addEventListener("DOMContentLoaded", function () {
    initHeader();
    initSearch();
    initDrawer();
    initAccordions();
    initFilters();
    initGallery();
    initVariants();
    initQtySteppers();
    initForms();
    initReveal();
    initToc();

    bindAddButtons();
    bindWishButtons();

    onChange(paintCounts);
    onChange(renderDrawer);
    paintCounts();

    initBagPage();
    initRecentRail();
    initCheckout();

    const viewed = document.body.dataset.productSlug;
    if (viewed) noteViewed(viewed);

    loadCart();          // one request, then everything paints from server truth
  });
})();

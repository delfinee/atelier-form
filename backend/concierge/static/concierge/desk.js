(() => {
  "use strict";
  const english = document.documentElement.lang === "en";
  const locale = english ? "en-GB" : "zh-CN";
  const t = (zh, en) => english ? en : zh;
  const $ = (id) => document.getElementById(id);
  const escape = (value) =>
    String(value ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  const money = (value) => `¥${Number(value).toFixed(2)}`;
  const state = {
    catalog: [],
    conversation: null,
    lines: [],
    drafts: [],
    draft: null,
    pending: false,
  };
  const csrf = document.querySelector("[name=csrfmiddlewaretoken]").value;
  async function api(path, data) {
    const response = await fetch(`/seller/assistant/${path}`, {
      method: data ? "POST" : "GET",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
      ...(data ? { body: JSON.stringify(data) } : {}),
    });
    const payload = await response
      .json()
      .catch(() => ({ detail: t("会话已失效，请刷新页面重新登录。", "Your session has expired. Please refresh the page.") }));
    if (!response.ok)
      throw new Error(
        payload.errors ? JSON.stringify(payload.errors) : payload.detail,
      );
    return payload;
  }
  async function run(fn) {
    if (state.pending) return;
    state.pending = true;
    $("error").hidden = true;
    document.querySelectorAll("button").forEach((b) => (b.disabled = true));
    try {
      await fn();
    } catch (error) {
      $("error").textContent = error.message;
      $("error").hidden = false;
    } finally {
      state.pending = false;
      document.querySelectorAll("button").forEach((b) => (b.disabled = false));
      updateConfirm();
    }
  }
  function renderCatalog() {
    const query = $("search").value.toLowerCase();
    const catalog = state.catalog.filter(
      (p) => p.name.toLowerCase().includes(query) || p.product.includes(query),
    );
    $("catalog-count").textContent = `${catalog.length} ${t("件", "items")}`;
    $("catalog").innerHTML =
      catalog
        .map(
          (p) =>
            `<article class="product" data-product="${escape(p.product)}"><h3>${escape(p.name)}</h3><p><span class="price">${money(p.price)}</span><span class="small muted">${p.made_to_order ? t("按单制作", "Made to order") : t("库存 ", "Stock: ") + (p.variants.length ? p.variants.reduce((n, v) => n + v.stock, 0) : p.stock)}</span></p>${p.variants.length ? `<select aria-label="${escape(p.name)} ${t("规格", "option")}"><option value="">${t("请选择规格", "Choose an option")}</option>${p.variants.map((v) => `<option value="${escape(v.id)}">${escape(v.label)} · ${money(v.price)} · ${p.made_to_order ? t("按单制作", "Made to order") : t("余 ", "Left: ") + v.stock}</option>`).join("")}</select>` : ""}<button type="button" data-add="${escape(p.product)}">${t("加入待选商品 ＋", "Add to selection +")}</button></article>`,
        )
        .join("") || `<p class="empty">${t("没有匹配的商品。", "No matching products.")}</p>`;
  }
  function renderSelection() {
    $("selection").innerHTML =
      state.lines
        .map((line, i) => {
          const p = state.catalog.find((p) => p.product === line.product),
            v = p.variants.find((v) => v.id === line.variant);
          return `<div class="selected"><div><strong>${escape(p.name)}</strong><small>${escape(v?.label || t("默认规格", "Default option"))} · ${money(v?.price ?? p.price)}</small></div><input type="number" min="1" max="99" aria-label="${escape(p.name)} ${t("数量", "quantity")}" value="${line.quantity}" data-quantity="${i}"><button class="remove" type="button" data-remove="${i}" aria-label="${t("移除", "Remove")} ${escape(p.name)}">×</button></div>`;
        })
        .join("") ||
      `<p class="empty">${t("从目录加入商品，或让 AI 根据客户消息建议选品。", "Add products from the catalogue, or ask the assistant for recommendations.")}</p>`;
  }
  function bubble(text, customer = false) {
    const item = document.createElement("div");
    item.className = "bubble" + (customer ? " customer" : "");
    const caption = document.createElement("span");
    caption.className = "caption";
    caption.textContent = customer ? t("模拟客户", "Demo customer") : t("客服助手 · 建议", "Assistant \u00b7 Suggestion");
    item.append(caption, document.createTextNode(text));
    $("messages").append(item);
    $("messages").scrollTop = $("messages").scrollHeight;
  }
  function showReply(reply) {
    bubble(reply.reply);
    $("engine").textContent =
      reply.engine === "deepseek"
        ? t("● DeepSeek 在线建议", "\u25cf Live DeepSeek suggestions")
        : reply.notice || t("离线目录匹配", "Offline catalogue matching");
  }
  function renderDraft() {
    const d = state.draft;
    $("draft-area").hidden = !d;
    if (!d) {
      $("state").textContent = t("待选品", "Choose products");
      return;
    }
    $("draft-history").innerHTML = state.drafts
      .map(
        (x, i) =>
          `<option value="${escape(x.id)}">${escape(x.order?.number || `${t("草稿", "Draft")} ${i + 1}`)} · ${money(x.total)}</option>`,
      )
      .join("");
    $("draft-history").value = d.id;
    const o = d.order;
    $("state").textContent =
      o?.status === "shipped"
        ? t("已发货", "Shipped")
        : d.packed
          ? t("待发货", "Ready to ship")
          : d.packing_started
            ? t("打包中", "Packing")
            : o?.payment_status === "paid"
              ? t("待打包", "Ready to pack")
              : o
                ? t("待付款", "Awaiting payment")
                : d.expired
                  ? t("草稿已过期", "Draft expired")
                  : t("待确认", "Awaiting confirmation");
    const a = d.customer.shipping_address;
    $("draft").innerHTML =
      d.lines
        .map(
          (l) =>
            `<div class="draft-line"><span>${escape(l.name)} ${escape(l.option)} × ${l.quantity}</span><span>${money(l.line_total)}</span></div>`,
        )
        .join("") +
      `<div class="small muted">${t("运费", "Shipping")} ${money(d.shipping)}</div><div class="total"><span>${t("订单总额", "Order total")} · CNY</span><strong>${money(d.total)}</strong></div><p class="small">${escape(english ? a.first_name + " " + a.last_name : a.last_name + a.first_name)} · ${escape(d.customer.phone)}<br>${escape(a.city)} ${escape(a.address_line_1)}<br>${escape(d.customer.email)}</p><p class="small muted">${o ? t("订单 ", "Order ") + escape(o.number) : t("草稿有效至 ", "Draft valid until ") + new Date(d.expires_at).toLocaleTimeString(locale)}</p>`;
    if (!o)
      $("actions").innerHTML = d.expired
        ? `<p class="small">${t("草稿已过期，请重新生成。", "This draft has expired. Create a new draft.")}</p>`
        : `<label class="confirm-label"><input id="confirm-check" type="checkbox">${t("模拟买家已核对商品、数量、总额和收货信息，同意创建订单。", "I have checked the products, quantities, total and delivery details, and confirm this demo order.")}</label><button id="confirm-order" class="primary full" data-action="confirm" disabled>${t("确认订单", "Confirm order")}</button>`;
    else if (
      ["cancelled"].includes(o.status) ||
      ["failed", "refunded"].includes(o.payment_status)
    )
      $("actions").innerHTML = `<p>${t("该订单已关闭，请重新下单。", "This order is closed. Please create a new order.")}</p>`;
    else if (o.payment_status !== "paid")
      $("actions").innerHTML =
        `<button class="primary full" data-action="pay">${t("模拟付款成功 · 不产生扣款", "Simulate payment · No charge")}</button>`;
    else if (o.status === "shipped")
      $("actions").innerHTML =
        `<div class="tracking">${t("已登记发货", "Shipment recorded")}<br><strong>${escape(o.carrier)} · ${escape(o.tracking_number)}</strong><br><span class="small">${t("模拟运单，未连接真实物流查询。", "Simulated tracking. No real shipment is created.")}</span></div>`;
    else if (!d.packing_started)
      $("actions").innerHTML =
        `<button class="primary full" data-action="pack">${t("开始拣货打包", "Start picking and packing")}</button>`;
    else if (!d.packed)
      $("actions").innerHTML =
        `<p class="small">${t("请逐项核对上方商品与数量，完成包装后继续。", "Check each product and quantity above, then complete packing.")}</p><button class="primary full" data-action="packed">${t("确认已核对并完成打包", "Confirm checks and finish packing")}</button>`;
    else
      $("actions").innerHTML =
        `<label class="small">${t("物流公司", "Carrier")}<input id="carrier" value="${t("顺丰速运（模拟）", "Demo Express (simulated)")}" maxlength="80"></label><label class="small">${t("运单号", "Tracking number")}<input id="tracking" value="DEMO` +
        Date.now() +
        `" maxlength="100"></label><button class="primary full" data-action="ship">${t("登记发货并生成客户回执", "Record shipment and create receipt")}</button>`;
    const names = {
      draft_created: t("生成草稿", "Draft created"),
      confirm: t("模拟买家确认订单", "Demo buyer confirmed"),
      pay: t("模拟付款成功", "Simulated payment received"),
      pack: t("开始拣货打包", "Start picking and packing"),
      packed: t("核对打包完成", "Packing checked and completed"),
      ship: t("登记发货", "Shipment recorded"),
    };
    $("events").innerHTML = d.events
      .map(
        (e) =>
          `<li><span>${names[e.action] || escape(e.action)}</span><time>${new Date(e.at).toLocaleTimeString(locale)}</time></li>`,
      )
      .join("");
    updateConfirm();
  }
  function updateConfirm() {
    if ($("confirm-order"))
      $("confirm-order").disabled =
        state.pending || !$("confirm-check")?.checked;
  }
  function receipt(d) {
    bubble(
      english ? `Shipping receipt (demo): Order ${d.order.number} has been recorded as shipped via ${d.order.carrier}. Tracking number: ${d.order.tracking_number}.` : `发货回执（模拟）：订单 ${d.order.number} 已登记发货，${d.order.carrier}，运单号 ${d.order.tracking_number}。`,
    );
  }
  async function loadConversation(id) {
    state.conversation = id;
    state.lines = [];
    renderSelection();
    const data = await api(`conversations/${id}/`);
    $("messages").replaceChildren();
    for (const m of data.messages) {
      bubble(m.text, true);
      showReply(m);
    }
    if (!data.messages.length)
      bubble(t("你好，这里是手作客服。告诉我你想找什么，或从左侧目录挑选商品。", "Hello! Tell me what you are looking for, or choose a product from the catalogue."));
    state.drafts = data.drafts;
    for (const d of data.drafts) {
      if (d.order?.status === "shipped") receipt(d);
    }
    state.draft = data.drafts.at(-1) || null;
    renderDraft();
  }
  async function refreshList(selected) {
    const data = await api("conversations/");
    state.catalog = data.catalog;
    renderCatalog();
    $("conversation").innerHTML = data.conversations
      .map(
        (c, i) =>
          `<option value="${escape(c.id)}">${escape(c.label)} · ${new Date(c.at).toLocaleString(locale)}</option>`,
      )
      .join("");
    if (selected) $("conversation").value = selected;
  }
  async function newConversation() {
    const c = await api("conversations/", {});
    await refreshList(c.id);
    await loadConversation(c.id);
  }
  $("search").addEventListener("input", renderCatalog);
  $("new-chat").onclick = () => run(newConversation);
  $("conversation").onchange = () =>
    run(() => loadConversation($("conversation").value));
  $("draft-history").onchange = () => {
    state.draft = state.drafts.find((d) => d.id === $("draft-history").value);
    renderDraft();
  };
  $("catalog").onclick = (e) => {
    const button = e.target.closest("[data-add]");
    if (!button || state.pending) return;
    const p = state.catalog.find((p) => p.product === button.dataset.add),
      v = button.closest("article").querySelector("select")?.value || null;
    if (p.variants.length && !v) {
      $("error").textContent = t("请先选择商品规格。", "Please choose a product option first.");
      $("error").hidden = false;
      return;
    }
    $("error").hidden = true;
    const line = state.lines.find(
      (l) => l.product === p.product && l.variant === v,
    );
    if (line) line.quantity = Math.min(99, line.quantity + 1);
    else state.lines.push({ product: p.product, variant: v, quantity: 1 });
    renderSelection();
  };
  $("selection").onclick = (e) => {
    const b = e.target.closest("[data-remove]");
    if (b) {
      state.lines.splice(Number(b.dataset.remove), 1);
      renderSelection();
    }
  };
  $("selection").onchange = (e) => {
    if (e.target.dataset.quantity !== undefined)
      state.lines[Number(e.target.dataset.quantity)].quantity = Number(
        e.target.value,
      );
  };
  $("clear-selection").onclick = () => {
    state.lines = [];
    renderSelection();
  };
  $("chat-form").onsubmit = (e) => {
    e.preventDefault();
    const text = $("chat-text").value.trim();
    if (!text) return;
    run(async () => {
      const response = await api(
        `conversations/${state.conversation}/messages/`,
        { request_id: crypto.randomUUID(), text },
      );
      bubble(text, true);
      showReply(response);
      if (response.lines.length) {
        state.lines = response.lines;
        renderSelection();
      }
      $("chat-text").value = "";
    });
  };
  $("draft-form").onsubmit = (e) => {
    e.preventDefault();
    run(async () => {
      if (!state.lines.length) throw new Error(t("请先选择商品。", "Please choose a product first."));
      const f = Object.fromEntries(new FormData(e.target));
      const shipping_address = {
        first_name: f.first_name,
        last_name: f.last_name,
        address_line_1: f.address_line_1,
        city: f.city,
        postal_code: f.postal_code,
        country: "China",
        phone: f.phone,
      };
      state.draft = await api(`conversations/${state.conversation}/drafts/`, {
        request_id: crypto.randomUUID(),
        lines: state.lines,
        email: f.email,
        phone: f.phone,
        delivery_method: f.delivery_method,
        shipping_address,
      });
      state.drafts.push(state.draft);
      renderDraft();
    });
  };
  $("actions").onchange = updateConfirm;
  $("actions").onclick = (e) => {
    const b = e.target.closest("[data-action]");
    if (!b) return;
    run(async () => {
      const action = b.dataset.action;
      const data = { action, confirmed: !!$("confirm-check")?.checked };
      if (action === "ship") {
        data.carrier = $("carrier").value.trim();
        data.tracking_number = $("tracking").value.trim();
      }
      const d = await api(`drafts/${state.draft.id}/action/`, data);
      state.drafts = state.drafts.map((x) => (x.id === d.id ? d : x));
      state.draft = d;
      renderDraft();
      if (action === "ship") receipt(d);
      await refreshList(state.conversation);
    });
  };
  run(async () => {
    await refreshList();
    if ($("conversation").value)
      await loadConversation($("conversation").value);
    else await newConversation();
  });
})();

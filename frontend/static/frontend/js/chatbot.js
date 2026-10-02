/**
 * Crafty (匠心小助手) - Shopee-style Buyer ↔ Seller Direct Messaging Client
 * Integrates with Atelier Form storefront and Gemini AI service fallback.
 */

(function () {
  'use strict';

  // Determine language: check localStorage, then html lang attribute
  const pageLang = (document.documentElement.lang || 'en').toLowerCase().startsWith('zh') ? 'zh' : 'en';
  let currentLang = localStorage.getItem('crafty_lang') || pageLang;

  // Active Emoji category
  let activeEmojiTab = 'faces';

  // Comprehensive emoji catalog
  const emojiCatalog = {
    faces: [
      '😊', '😄', '😃', '😁', '🥰', '😍', '🤩',
      '😘', '😚', '😋', '😜', '🤗', '🤭', '😌',
      '😎', '🥳', '🧐', '🤔', '😳', '🥺', '😭',
      '😅', '😇', '😴', '🤤', '😷', '🤒', '🤕'
    ],
    gestures: [
      '👍', '👌', '🤝', '🙌', '👏', '🙏', '✌️',
      '👋', '🤙', '✊', '👊', '🤞', '🤟', '🤘',
      '💪', '👈', '👉', '👆', '👇', '✋', '🖐️'
    ],
    craft: [
      '🪵', '🌿', '🪵', '🍂', '🍁', '🌱', '🌾',
      '🪴', '🌲', '🌳', '🌸', '💐', '🌷', '🌻',
      '🎨', '📐', '📏', '🔨', '🪚', '🪓', '🖌️'
    ],
    objects: [
      '❤️', '🧡', '💛', '💚', '💙', '💜', '🤎',
      '🎁', '📦', '🏷️', '🛍️', '💎', '💍', '✨',
      '⭐', '🌟', '☕', '🍵', '🥂', '🎉', '🏮'
    ]
  };

  // Bilingual strings dictionary
  const i18n = {
    zh: {
      launcherText: "联系卖家 · Chat with Seller",
      widgetSellerTitle: "林师傅木作旗舰店",
      widgetSellerStatus: "47分钟前活跃",
      pinnedTitle: "北美黑胡桃手工燕尾榫首饰盒",
      pinnedPrice: "¥388 / $58.00",
      btnPinnedBuy: "立即购买",
      cardProductTitle: "北美黑胡桃手工燕尾榫首饰盒",
      cardProductVar: "规格: 黄铜刻字定制 >",
      cardProductPrice: "¥388",
      cardAuthenticBadge: "🛡️ 100% 正品手作",
      cardBuyNow: "立即购买",
      faqTitle: "您可能想问：",
      faq1: "现料排期与木材纹理 (Availability & Timber)",
      faq2: "定制黄铜片刻字誓言 (Bespoke Initials & Brass Inlay)",
      faq3: "木蜡油阴干固化与保养 (OSMO Hardwax Curing & Care)",
      faqFooter: "由工坊小助手自动发送 · 22:39",
      btnChatWithSeller: "🗣️ 联系卖家",
      inputPlaceholder: "向卖家发送消息...",
      toolPhoto: "发送图片",
      toolProduct: "发送商品",
      toolBrief: "定制需求",
      toolOrder: "订单进度",
      todayDate: "今日 (Today)",
      autoBadge: "⚡ 系统自动回复 · 非人工卖家",
      humanBadge: "🏪 卖家客服 (人工)",
      autoDisclaimer: "此条消息由系统自动生成触发，卖家人工在线中",
      autoReplyGreeting: "【工坊自动应答】您好！已接收到您的留言。当前客服正在手作工作台雕琢器物，稍后将由人工掌柜为您亲切回复。\n\n如需即时查询，请点击下方快捷服务或告知您的具体问题（客服服务时间：09:00 - 22:00）：",
      autoChips: ["🪵 原木材质与现货", "✒️ 黄铜刻字定制", "⏳ 制作发货工期", "🛡️ 终身质保与退换", "🗣️ 转接人工掌柜"],
      langToggleText: "EN",
      settingsSaved: "设置已保存！",
    },
    en: {
      launcherText: "Chat with Seller",
      widgetSellerTitle: "Lin Woodcraft Flagship Store",
      widgetSellerStatus: "Active 47 minutes ago",
      pinnedTitle: "FAS Black Walnut Dovetail Keepsake Box",
      pinnedPrice: "$58.00 / ¥388",
      btnPinnedBuy: "Buy Now",
      cardProductTitle: "FAS Black Walnut Dovetail Keepsake Box",
      cardProductVar: "Select Variation >",
      cardProductPrice: "$58.00",
      cardAuthenticBadge: "🛡️ 100% Authentic Handcrafted",
      cardBuyNow: "Buy Now",
      faqTitle: "You may want to ask:",
      faq1: "Availability & Timber Details",
      faq2: "Bespoke Engraving & Initials",
      faq3: "Hardwax Curing, Care & Returns",
      faqFooter: "Sent by Chat AI Assistant · 22:39",
      btnChatWithSeller: "🗣️ Chat with Seller",
      inputPlaceholder: "Type a message...",
      toolPhoto: "Photos",
      toolProduct: "Send Item",
      toolBrief: "Custom Brief",
      toolOrder: "My Order",
      todayDate: "Today",
      autoBadge: "⚡ Auto Reply · Not Seller",
      humanBadge: "🏪 Seller Support (Human)",
      autoDisclaimer: "This message is automatically generated; seller is on standby.",
      autoReplyGreeting: "【Store Auto-Reply】Hello! We received your message. Our master artisan is currently at the workbench; human seller customer care will reply shortly.\n\nFor immediate inquiries, please tap the quick options below or specify your question (Live hours: 09:00 - 22:00):",
      autoChips: ["🪵 Timber & Availability", "✒️ Bespoke Engraving", "⏳ Lead Time & ETA", "🛡️ Warranty & Care", "🗣️ Live Master Craftsman"],
      langToggleText: "中文",
      settingsSaved: "Settings saved!",
    }
  };

  // Default seed messages for Shopee conversation
  function getDefaultMessages() {
    const isZh = currentLang === 'zh';
    return [
      {
        id: 'shopee-prod-1',
        type: 'shopee_product',
        sender: 'buyer',
        time: '22:39',
        status: '22:39 ✓'
      },
      {
        id: 'shopee-faq-1',
        type: 'shopee_faq',
        sender: 'assistant',
        time: '22:39'
      }
    ];
  }

  // Conversation history in widget
  let messages = [];

  function loadMessages() {
    const stored = localStorage.getItem('crafty_shopee_buyer_messages');
    if (stored) {
      try {
        messages = JSON.parse(stored);
      } catch (e) {
        messages = getDefaultMessages();
      }
    } else {
      messages = getDefaultMessages();
    }
  }

  function saveMessages() {
    localStorage.setItem('crafty_shopee_buyer_messages', JSON.stringify(messages));
  }

  function getCurrentTimeStr() {
    const d = new Date();
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/[&<>'"]/g, tag => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      "'": '&#39;',
      '"': '&quot;'
    }[tag] || tag));
  }

  // Helper getters for settings modal
  function getClientApiKey() {
    return (localStorage.getItem('crafty_gemini_api_key') || '').trim();
  }

  function getActiveModel() {
    const stored = localStorage.getItem('crafty_gemini_model');
    if (stored && (stored.includes('1.5') || stored.includes('2.0') || stored.includes('1.0'))) {
      localStorage.setItem('crafty_gemini_model', 'gemini-3.8-flash');
      return 'gemini-3.8-flash';
    }
    return stored || 'gemini-3.8-flash';
  }

  // --- Initialize UI ---
  function init() {
    const isFullPage = Boolean(document.querySelector('.crafty-fullpage'));
    const launcher = document.getElementById('crafty-launcher');
    const drawer = document.getElementById('crafty-drawer');
    const backdrop = document.getElementById('crafty-backdrop');
    const closeBtn = document.getElementById('crafty-close');
    const backBtn = document.getElementById('crafty-back-btn');
    const input = document.getElementById('crafty-input');
    const form = document.getElementById('crafty-form');
    const langBtn = document.getElementById('crafty-lang-toggle');
    const settingsBtn = document.getElementById('crafty-settings-toggle');
    const settingsModal = document.getElementById('crafty-settings-modal');
    const settingsClose = document.getElementById('crafty-settings-close');
    const settingsSave = document.getElementById('crafty-settings-save');
    const settingsClear = document.getElementById('crafty-settings-clear');

    const btnPlus = document.getElementById('btnPlusTool');
    const btnBag = document.getElementById('btnBagInquiry');
    const btnEmoji = document.getElementById('btnEmojiToggle');
    const btnPinnedBuy = document.getElementById('btnPinnedBuy');
    const emojiPicker = document.getElementById('emojiPicker');

    loadMessages();
    updateStaticUI();
    renderMessages();
    renderEmojiGrid(activeEmojiTab);

    // Open & Close Widget
    function openWidget() {
      if (!drawer) return;
      drawer.classList.add('is-open');
      drawer.classList.remove('is-hidden');
      if (launcher) launcher.style.display = 'none';
      if (backdrop) backdrop.classList.add('is-open');
      input?.focus();
    }

    function closeWidget() {
      if (!drawer) return;
      drawer.classList.remove('is-open');
      drawer.classList.add('is-hidden');
      if (launcher) launcher.style.display = 'inline-flex';
      if (backdrop) backdrop.classList.remove('is-open');
      if (emojiPicker) emojiPicker.style.display = 'none';
      const tray = document.getElementById('toolsTray');
      if (tray) tray.style.display = 'none';
      if (settingsModal) settingsModal.hidden = true;
    }

    launcher?.addEventListener('click', openWidget);
    closeBtn?.addEventListener('click', closeWidget);
    backBtn?.addEventListener('click', closeWidget);
    backdrop?.addEventListener('click', closeWidget);

    // Global triggers
    document.querySelectorAll('[data-crafty-open]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        openWidget();
      });
    });

    // Close on Escape key
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        if (emojiPicker && emojiPicker.style.display !== 'none') {
          emojiPicker.style.display = 'none';
        } else if (drawer?.classList.contains('is-open')) {
          closeWidget();
        }
      }
    });

    // Language Toggle
    langBtn?.addEventListener('click', () => {
      currentLang = currentLang === 'zh' ? 'en' : 'zh';
      localStorage.setItem('crafty_lang', currentLang);
      updateStaticUI();
      renderMessages();
    });

    // Plus Tool Toggle
    btnPlus?.addEventListener('click', (e) => {
      e.stopPropagation();
      const tray = document.getElementById('toolsTray');
      if (!tray) return;
      tray.style.display = tray.style.display === 'none' ? 'grid' : 'none';
    });

    // Bag Inquiry Button (Quickly send product card into chat)
    btnBag?.addEventListener('click', () => {
      sendProductInquiryCard();
    });

    // Pinned bar Buy button
    btnPinnedBuy?.addEventListener('click', () => {
      sendProductInquiryCard();
    });

    // Tool item handlers
    document.getElementById('toolBtnPhoto')?.addEventListener('click', () => {
      const isZh = currentLang === 'zh';
      const promptText = isZh ? '输入您要发送的设计手稿或参考图描述：' : 'Enter sketch or reference photo description:';
      const sketchName = prompt(promptText, isZh ? '婚戒定制刻字手稿.jpg' : 'monogram_sketch.jpg');
      if (sketchName) {
        messages.push({
          id: 'att-' + Date.now(),
          sender: 'buyer',
          time: getCurrentTimeStr(),
          text: (isZh ? '📎 发送图片：' : '📎 Sent Photo: ') + sketchName,
          status: getCurrentTimeStr() + ' ✓'
        });
        saveMessages();
        renderMessages();
      }
    });

    document.getElementById('toolBtnProduct')?.addEventListener('click', () => {
      sendProductInquiryCard();
    });

    document.getElementById('toolBtnBrief')?.addEventListener('click', () => {
      const isZh = currentLang === 'zh';
      messages.push({
        id: 'brief-' + Date.now(),
        sender: 'buyer',
        time: getCurrentTimeStr(),
        text: isZh ? "我想提交定制需求单：需要盒盖内侧刻写 “J & M · 2026.10.18”，加装深灰色丝绒衬里。" : "Custom brief: Engrave 'J & M · 2026.10.18' inside lid with dark grey suede lining.",
        status: getCurrentTimeStr() + ' ✓'
      });
      saveMessages();
      renderMessages();
    });

    document.getElementById('toolBtnOrder')?.addEventListener('click', () => {
      const isZh = currentLang === 'zh';
      messages.push({
        id: 'order-inq-' + Date.now(),
        sender: 'buyer',
        time: getCurrentTimeStr(),
        text: isZh ? "帮我查询手作订单 #AF-8921 的当前制作进度？" : "Check current progress for my order #AF-8921?",
        status: getCurrentTimeStr() + ' ✓'
      });
      saveMessages();
      renderMessages();

      setTimeout(() => {
        messages.push({
          id: 'order-rep-' + Date.now(),
          sender: 'seller',
          time: getCurrentTimeStr(),
          text: isZh
            ? "【订单进度反馈】您的黑胡桃手工首饰盒已完成 1500 目精细砂光，正在阴干第二遍德国 OSMO 木蜡油，预计明日完成礼盒打包并顺丰发出！"
            : "【Order Status】Your box has completed 1500-grit progressive sanding and is curing coat 2 of OSMO hardwax-oil. Dispatched tomorrow via express courier!"
        });
        saveMessages();
        renderMessages();
      }, 700);
    });

    // Emoji Picker Toggle
    btnEmoji?.addEventListener('click', (e) => {
      e.stopPropagation();
      if (!emojiPicker) return;
      const isVisible = emojiPicker.style.display !== 'none';
      if (isVisible) {
        emojiPicker.style.display = 'none';
      } else {
        renderEmojiGrid(activeEmojiTab);
        emojiPicker.style.display = 'flex';
      }
    });

    // Emoji Tabs
    document.querySelectorAll('.shopee-emoji-tab').forEach(tabBtn => {
      tabBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        const tabKey = tabBtn.getAttribute('data-tab');
        if (!tabKey) return;
        activeEmojiTab = tabKey;
        document.querySelectorAll('.shopee-emoji-tab').forEach(t => t.classList.remove('is-active'));
        tabBtn.classList.add('is-active');
        renderEmojiGrid(tabKey);
      });
    });

    // Dismiss Emoji Picker on outside click
    document.addEventListener('click', (e) => {
      if (emojiPicker && emojiPicker.style.display !== 'none') {
        if (!emojiPicker.contains(e.target) && e.target !== btnEmoji) {
          emojiPicker.style.display = 'none';
        }
      }
    });

    // Form submit
    form?.addEventListener('submit', (e) => {
      e.preventDefault();
      const val = input ? input.value.trim() : '';
      if (!val) return;
      input.value = '';

      // User sends message as Buyer
      messages.push({
        id: 'msg-' + Date.now(),
        sender: 'buyer',
        time: getCurrentTimeStr(),
        text: val,
        status: getCurrentTimeStr() + ' ✓'
      });
      saveMessages();
      renderMessages();

      // Seller / Auto-attendant replies after 1s
      setTimeout(() => {
        handleIncomingBuyerMessage(val);
      }, 1000);
    });

    // Settings Modal
    settingsBtn?.addEventListener('click', () => {
      if (!settingsModal) return;
      const keyInput = document.getElementById('crafty-modal-key');
      const modelSelect = document.getElementById('crafty-modal-model');
      if (keyInput) keyInput.value = getClientApiKey();
      if (modelSelect) modelSelect.value = getActiveModel();
      settingsModal.hidden = false;
    });

    settingsClose?.addEventListener('click', () => {
      if (settingsModal) settingsModal.hidden = true;
    });

    settingsSave?.addEventListener('click', () => {
      const keyInput = document.getElementById('crafty-modal-key');
      const modelSelect = document.getElementById('crafty-modal-model');
      const key = keyInput ? keyInput.value.trim() : '';
      const model = modelSelect ? modelSelect.value.trim() : '';
      if (key) localStorage.setItem('crafty_gemini_api_key', key);
      else localStorage.removeItem('crafty_gemini_api_key');
      if (model) localStorage.setItem('crafty_gemini_model', model);
      if (settingsModal) settingsModal.hidden = true;
    });

    settingsClear?.addEventListener('click', () => {
      localStorage.removeItem('crafty_gemini_api_key');
      const keyInput = document.getElementById('crafty-modal-key');
      if (keyInput) keyInput.value = '';
    });

    // Auto-open if #open in URL
    if (window.location.hash === '#open' || new URLSearchParams(window.location.search).has('open')) {
      openWidget();
    }
  }

  // --- Update Static UI Elements ---
  function updateStaticUI() {
    const t = i18n[currentLang] || i18n.en;
    
    const launcherText = document.getElementById('crafty-launcher-text');
    if (launcherText) launcherText.textContent = t.launcherText;

    const sellerTitle = document.getElementById('widgetSellerTitle');
    if (sellerTitle) sellerTitle.textContent = t.widgetSellerTitle;

    const sellerStatus = document.getElementById('widgetSellerStatus');
    if (sellerStatus) sellerStatus.textContent = t.widgetSellerStatus;

    const pinnedTitle = document.getElementById('pinnedTitle');
    if (pinnedTitle) pinnedTitle.textContent = t.pinnedTitle;

    const pinnedPrice = document.getElementById('pinnedPrice');
    if (pinnedPrice) pinnedPrice.textContent = t.pinnedPrice;

    const btnPinnedBuyText = document.getElementById('btnPinnedBuyText');
    if (btnPinnedBuyText) btnPinnedBuyText.textContent = t.btnPinnedBuy;

    const input = document.getElementById('crafty-input');
    if (input) input.placeholder = t.inputPlaceholder;

    const toolPhoto = document.getElementById('toolPhoto');
    if (toolPhoto) toolPhoto.textContent = t.toolPhoto;

    const toolProduct = document.getElementById('toolProduct');
    if (toolProduct) toolProduct.textContent = t.toolProduct;

    const toolBrief = document.getElementById('toolBrief');
    if (toolBrief) toolBrief.textContent = t.toolBrief;

    const toolOrder = document.getElementById('toolOrder');
    if (toolOrder) toolOrder.textContent = t.toolOrder;

    const langToggle = document.getElementById('crafty-lang-toggle');
    if (langToggle) langToggle.textContent = t.langToggleText;
  }

  // --- Render Emoji Grid ---
  function renderEmojiGrid(tabKey) {
    const grid = document.getElementById('emojiGrid');
    if (!grid) return;
    grid.innerHTML = '';
    const list = emojiCatalog[tabKey] || emojiCatalog.faces;
    const input = document.getElementById('crafty-input');

    list.forEach(emoji => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'shopee-emoji-btn';
      btn.textContent = emoji;
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        if (input) {
          input.value += emoji;
          input.focus();
        }
      });
      grid.appendChild(btn);
    });
  }

  // --- Send In-Chat Product Inquiry Card ---
  function sendProductInquiryCard() {
    messages.push({
      id: 'shopee-prod-' + Date.now(),
      type: 'shopee_product',
      sender: 'buyer',
      time: getCurrentTimeStr(),
      status: getCurrentTimeStr() + ' ✓'
    });
    saveMessages();
    renderMessages();
  }

  // --- Render Message Thread ---
  function renderMessages() {
    const container = document.getElementById('crafty-messages');
    if (!container) return;
    container.innerHTML = '';
    const t = i18n[currentLang] || i18n.en;
    const isZh = currentLang === 'zh';

    // 1. Centered Date Divider: "Today"
    const dateDivider = document.createElement('div');
    dateDivider.className = 'shopee-date-divider';
    dateDivider.innerHTML = `<span class="shopee-date-pill">${t.todayDate}</span>`;
    container.appendChild(dateDivider);

    // 2. Render all messages
    messages.forEach(m => {
      // A. In-Chat Shopee Product Card (Sent by Buyer)
      if (m.type === 'shopee_product') {
        const wrapper = document.createElement('div');
        wrapper.className = 'crafty-msg crafty-msg--user';
        wrapper.innerHTML = `
          <div class="shopee-chat-product-card">
            <div class="shopee-card-main">
              <div class="shopee-card-imgbox">🪵</div>
              <div class="shopee-card-meta">
                <h4 class="shopee-card-title">${t.cardProductTitle}</h4>
                <div class="shopee-card-variation">${t.cardProductVar}</div>
                <div class="shopee-card-price">${t.cardProductPrice}</div>
                <div class="shopee-trust-badge">${t.cardAuthenticBadge}</div>
              </div>
            </div>
            <button type="button" class="shopee-buy-btn-lg" onclick="alert(localStorage.getItem('crafty_lang')==='zh'?'跳转至结算收银台':'Proceeding to checkout ($58)...')">
              🛒 <span>${t.cardBuyNow}</span>
            </button>
          </div>
          <div style="font-size:0.65rem; color:var(--crafty-muted); text-align:right; margin-top:2px;">
            ${m.status || (m.time + ' ✓')}
          </div>
        `;
        container.appendChild(wrapper);
        return;
      }

      // B. Shopee Assistant FAQ Card ("You may want to ask:")
      if (m.type === 'shopee_faq') {
        const wrapper = document.createElement('div');
        wrapper.className = 'crafty-msg crafty-msg--bot';
        const defaultFaqList = [
          { id: 'q1', text: t.faq1 },
          { id: 'q2', text: t.faq2 },
          { id: 'q3', text: t.faq3 }
        ];

        let listHtml = '';
        defaultFaqList.forEach((q) => {
          listHtml += `
            <div class="shopee-faq-item" data-qid="${q.id}" data-text="${escapeHtml(q.text)}">
              <span>${escapeHtml(q.text)}</span>
              <span style="font-size:0.8rem; opacity:0.6;">›</span>
            </div>
          `;
        });

        wrapper.innerHTML = `
          <div class="shopee-faq-card">
            <div class="shopee-faq-title">${t.faqTitle}</div>
            <div class="shopee-faq-list">
              ${listHtml}
            </div>
            <div class="shopee-faq-foot">
              <span>${t.faqFooter}</span>
            </div>
          </div>
          <button type="button" class="shopee-live-agent-btn" id="btnConnectLiveSeller">
            ${t.btnChatWithSeller}
          </button>
        `;

        wrapper.querySelectorAll('.shopee-faq-item').forEach(item => {
          item.addEventListener('click', () => {
            const qid = item.getAttribute('data-qid');
            const qtext = item.getAttribute('data-text');
            handleFaqClick(qid, qtext);
          });
        });

        wrapper.querySelector('#btnConnectLiveSeller')?.addEventListener('click', () => {
          connectLiveSeller();
        });

        container.appendChild(wrapper);
        return;
      }

      // C. Standard Dialogue Message (Buyer, Seller, or System Auto-Reply)
      const msgEl = document.createElement('div');
      msgEl.className = `crafty-msg crafty-msg--${m.sender === 'buyer' ? 'user' : 'bot'}`;

      let metaHtml = '';
      if (m.sender === 'buyer') {
        metaHtml = `
          <div class="crafty-msg-meta">
            <span>${m.time}</span>
            ${m.status ? `<span class="crafty-receipt">${m.status}</span>` : ''}
          </div>
        `;
      } else if (m.isAutoReply) {
        metaHtml = `
          <div class="crafty-msg-meta">
            <span class="crafty-auto-badge">${t.autoBadge}</span>
            <span>•</span>
            <span>${m.time}</span>
          </div>
        `;
      } else {
        metaHtml = `
          <div class="crafty-msg-meta">
            <span class="crafty-maker-badge">${t.humanBadge}</span>
            <span>•</span>
            <span>${m.time}</span>
          </div>
        `;
      }

      let chipsHtml = '';
      if (m.chips && m.chips.length > 0) {
        chipsHtml = `
          <div class="crafty-quick-chips">
            ${m.chips.map(chip => `
              <button type="button" class="crafty-quick-chip" data-chip="${escapeHtml(chip)}">
                ${escapeHtml(chip)}
              </button>
            `).join('')}
          </div>
        `;
      }

      let autoFootHtml = '';
      if (m.isAutoReply) {
        autoFootHtml = `
          <div class="crafty-auto-disclaimer">
            <span>🤖</span>
            <span>${t.autoDisclaimer}</span>
          </div>
        `;
      }

      msgEl.innerHTML = `
        ${metaHtml}
        <div class="crafty-bubble">
          <p style="white-space:pre-line; margin:0;">${escapeHtml(m.text)}</p>
          ${chipsHtml}
          ${autoFootHtml}
        </div>
      `;

      msgEl.querySelectorAll('.crafty-quick-chip').forEach(btn => {
        btn.addEventListener('click', () => {
          const chipVal = btn.getAttribute('data-chip');
          if (chipVal) {
            const input = document.getElementById('crafty-input');
            if (input) input.value = chipVal;
            document.getElementById('crafty-form')?.dispatchEvent(new Event('submit'));
          }
        });
      });

      container.appendChild(msgEl);
    });

    container.scrollTop = container.scrollHeight;
  }

  // --- FAQ Click Handler ---
  function handleFaqClick(qid, questionText) {
    const isZh = currentLang === 'zh';
    messages.push({
      id: 'user-faq-' + Date.now(),
      sender: 'buyer',
      time: getCurrentTimeStr(),
      text: questionText,
      status: getCurrentTimeStr() + ' ✓'
    });

    let replyText = '';
    if (qid === 'q1') {
      replyText = isZh 
        ? "【现料与真伪保证】本店所有黑胡桃木盒均为 100% 正品 FAS 级北美原木手工榫卯开料。当前批次料子充足，开榫至阴干约需 3-4 个工作日，顺丰包邮发出！"
        : "【Availability & Authenticity】All dovetail keepsake boxes are 100% authentic FAS black walnut. Timbers are currently in stock; handcrafted joinery and curing take 3-4 business days.";
    } else if (qid === 'q2') {
      replyText = isZh
        ? "【定制黄铜刻字与保修】支持内盖手工开槽嵌拉丝纯黄铜片，激光精刻纪念誓言（定制费 ¥60 / $10）。木器提供终身榫卯结构质保与免费调校！"
        : "【Bespoke Engraving & Warranty】Inner lid can be hand-recessed with brushed solid brass laser-engraved with custom vows ($10). We provide a lifetime joinery warranty.";
    } else {
      replyText = isZh
        ? "【退换说明】未雕刻名字的现货商品支持 7 天无理由退换；个性化刻字定制商品发出前会提供工作台高清确认照片，确认满意后再打包发出。"
        : "【Return & Refund】Standard in-stock items are eligible for returns within 7 days. Personalized monogram items will have workbench photos confirmed with you prior to dispatch.";
    }

    setTimeout(() => {
      messages.push({
        id: 'bot-faq-reply-' + Date.now(),
        sender: 'assistant',
        isAutoReply: true,
        time: getCurrentTimeStr(),
        text: replyText
      });
      saveMessages();
      renderMessages();
    }, 400);

    saveMessages();
    renderMessages();
  }

  // --- "Chat with Seller" Button Action ---
  function connectLiveSeller() {
    const isZh = currentLang === 'zh';
    messages.push({
      id: 'conn-req-' + Date.now(),
      sender: 'buyer',
      time: getCurrentTimeStr(),
      text: isZh ? "您好，我想直接联系卖家人工客服。" : "Hello, I would like to chat directly with the seller.",
      status: getCurrentTimeStr() + ' ✓'
    });

    setTimeout(() => {
      messages.push({
        id: 'conn-reply-' + Date.now(),
        sender: 'seller',
        isAutoReply: false,
        time: getCurrentTimeStr(),
        text: isZh
          ? "您好！我是林师傅木作旗舰店的卖家客服 🌿 看到您关于这款黑胡桃首饰盒的咨询，请问需要定制刻字、了解具体木纹还是核对发货工期呢？随时为您服务！"
          : "Hello there! This is the Lin Woodcraft Flagship Store seller representative 🌿 How can I help you customize or order this dovetail keepsake box today?"
      });
      saveMessages();
      renderMessages();
    }, 600);

    saveMessages();
    renderMessages();
  }

  // --- Inbound Buyer Message Response Logic ---
  function handleIncomingBuyerMessage(userText) {
    const isZh = currentLang === 'zh';
    const textLower = userText.trim().toLowerCase();
    const t = i18n[currentLang] || i18n.en;
    let replyText = '';
    let replyChips = null;
    let isAutomatic = false;

    // 1. Custom Engraving (Direct Seller Response)
    if (textLower.includes('刻字') || textLower.includes('engrav') || textLower.includes('brass') || textLower.includes('定制')) {
      replyText = isZh 
        ? "收到您的刻字定制需求！我们选用 1.2mm 加厚实心黄铜拉丝片，内嵌在盒盖内侧并激光微雕纪念誓言与姓名首字母（定制周期 +1 工作日）。字样已为您记录至工作台排单。"
        : "Noted your custom engraving request! We use 1.2mm brushed solid brass plaques inset into the inner lid, laser-engraved with your initials or date. Lead time is +1 business day.";
      replyChips = isZh 
        ? ["查看黄铜刻字样照", "刻字内容格式", "确认加入定制"]
        : ["View Plaque Sample", "Engraving Format", "Confirm Bespoke"];
      isAutomatic = false;
    }
    // 2. Dispatch / Lead Time (Direct Seller Response)
    else if (textLower.includes('工期') || textLower.includes('发货') || textLower.includes('几天') || textLower.includes('lead time') || textLower.includes('eta') || textLower.includes('ship') || textLower.includes('deliver')) {
      replyText = isZh
        ? "卖家为您核对了工坊排期：北美黑胡桃现料充足！手工开榫至两道天然木蜡油阴干渗透固化约需 3-5 个工作日，出厂前拍摄实物照片供您确认，顺丰包邮直发！"
        : "Our workshop checked the schedule: FAS Black walnut timber is in stock! Hand-chiseled joinery and two-coat hardwax curing take 3-5 business days. Workbench photos are sent before dispatch!";
      replyChips = isZh 
        ? ["加急制作", "顺丰时效", "现货立即发货"]
        : ["Rush Production", "Courier ETA", "In-Stock Ready"];
      isAutomatic = false;
    }
    // 3. Timber & Authenticity (Direct Seller Response)
    else if (textLower.includes('材质') || textLower.includes('真木') || textLower.includes('胡桃') || textLower.includes('木头') || textLower.includes('walnut') || textLower.includes('material') || textLower.includes('wood') || textLower.includes('authentic')) {
      replyText = isZh
        ? "本店首饰盒 100% 采用北美进口 FAS 特级单块黑胡桃原木，绝非贴皮或密度板。榫卯接缝处顺应天然木纹，触感如丝绸般温润。"
        : "All keepsake boxes are 100% solid North American FAS black walnut (never veneer or composite). Continuous grain flows around the hand-planed through-dovetails.";
      replyChips = isZh 
        ? ["木蜡油保养方法", "木材纹理差异", "查看检测凭证"]
        : ["Hardwax Care", "Grain Variations", "Wood Origin"];
      isAutomatic = false;
    }
    // 4. Greetings (Live Seller greeting)
    else if (/^(hi|hello|hey|hola|你好|您好|哈喽|在吗|有人在吗|早|早上好|晚上好)[\s!！?？.~]*$/i.test(textLower)) {
      replyText = isZh
        ? "您好！我是林师傅木作旗舰店的卖家在线客服 🌿 很高兴为您服务！看到您在浏览我们的黑胡桃燕尾榫手作首饰盒，请问需要了解哪方面信息呢？"
        : "Hello there! This is Master Lin's Woodcraft Flagship Store representative 🌿 Great to connect with you! How can we assist you with our bespoke dovetail keepsake boxes today?";
      replyChips = isZh
        ? ["现货排期", "黄铜片刻字", "退换质保政策", "直接下单"]
        : ["Lead Time & ETA", "Bespoke Engraving", "Warranty & Returns", "Order Now"];
      isAutomatic = false;
    }
    // 5. UNMATCHED / RANDOM MESSAGE: 3-in-1 Automatic System Reply
    else {
      replyText = t.autoReplyGreeting;
      replyChips = t.autoChips;
      isAutomatic = true;
    }

    messages.push({
      id: 'reply-' + Date.now(),
      sender: isAutomatic ? 'system' : 'seller',
      isAutoReply: isAutomatic,
      time: getCurrentTimeStr(),
      text: replyText,
      chips: replyChips
    });

    saveMessages();
    renderMessages();
  }

  // Initialize once DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();

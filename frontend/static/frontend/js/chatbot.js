/**
 * Atelier Form - Buyer-to-Seller Messaging Widget
 *
 * Real server-side communication backed by /api/conversations/
 * - Messages persisted in database
 * - Scoped by authenticated buyer & artisan maker
 * - Simple polling for incoming replies
 * - Automatic context from active product page
 */

(function () {
  'use strict';

  // Read site configuration
  const CFG = JSON.parse(document.getElementById('af-config')?.textContent || '{}');
  const URLS = CFG.urls || {};

  // DOM Elements
  const launcher = document.getElementById('crafty-launcher');
  const backdrop = document.getElementById('crafty-backdrop');
  const drawer = document.getElementById('crafty-drawer');
  const closeBtn = document.getElementById('crafty-close');
  const backBtn = document.getElementById('crafty-back-btn');
  const form = document.getElementById('crafty-form');
  const input = document.getElementById('crafty-input');
  const sendBtn = document.getElementById('crafty-send-btn');
  const messagesContainer = document.getElementById('crafty-messages');
  const unreadBadge = document.getElementById('crafty-unread-badge');

  const sellerTitle = document.getElementById('widgetSellerTitle');
  const sellerStatus = document.getElementById('widgetSellerStatus');
  const pinnedBar = document.getElementById('pinnedProductBar');
  const pinnedTitle = document.getElementById('pinnedTitle');
  const pinnedPrice = document.getElementById('pinnedPrice');

  const btnPlusTool = document.getElementById('btnPlusTool');
  const toolsTray = document.getElementById('toolsTray');
  const toolBtnProduct = document.getElementById('toolBtnProduct');
  const toolBtnOrder = document.getElementById('toolBtnOrder');

  const btnEmojiToggle = document.getElementById('btnEmojiToggle');
  const emojiPicker = document.getElementById('emojiPicker');
  const emojiGrid = document.getElementById('emojiGrid');
  const langToggle = document.getElementById('crafty-lang-toggle');

  // Active state
  let currentLang = (document.documentElement.lang || 'en').toLowerCase().startsWith('zh') ? 'zh' : 'en';
  let activeConversation = null;
  let lastMessageUuid = null;
  let pollInterval = null;
  let currentContext = {};

  // i18n Dictionary
  const i18n = {
    zh: {
      launcher: '联系卖家',
      defaultTitle: '联系卖家',
      connected: '在线',
      loginPrompt: '请先登录以直接联系手作人。',
      loginBtn: '立即登录',
      inputPlaceholder: '输入消息...',
      send: '发送',
      sendItem: '发送当前商品',
      myOrder: '咨询订单',
      noMessages: '暂无消息记录。发送一条消息开启与手作人的对话吧！',
      today: '今天',
      you: '您',
      artisan: '手作人',
      buyer: '买家',
      sending: '发送中...',
      langToggleText: 'EN'
    },
    en: {
      launcher: 'Messages',
      defaultTitle: 'Chat with Seller',
      connected: 'Active',
      loginPrompt: 'Please sign in to message artisans directly.',
      loginBtn: 'Sign In',
      inputPlaceholder: 'Type a message...',
      send: 'Send',
      sendItem: 'Send Item',
      myOrder: 'My Order',
      noMessages: 'No messages yet. Send a message to start chatting with the maker!',
      today: 'Today',
      you: 'You',
      artisan: 'Artisan',
      buyer: 'Buyer',
      sending: 'Sending...',
      langToggleText: '中文'
    }
  };

  const emojiCatalog = {
    faces: ['😊', '🥰', '🌿', '🪵', '✨', '☕', '👍', '🙏', '❤️', '🙌', '🌸', '🎁'],
    gestures: ['👍', '👋', '🤝', '🙌', '👌', '✌️', '👏', '🙏'],
    craft: ['🪵', '🏺', '🧵', '🔨', '📐', '✂️', '🎨', '🖌️', '🌿'],
    objects: ['🎁', '📦', '💌', '💎', '🍵', '☕', '🕯️', '🔖']
  };

  function getCsrfToken() {
    if (CFG.csrf) return CFG.csrf;
    const match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? match[1] : '';
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/[&<>'"]/g, tag => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      "'": '&#39;',
      '"': '&quot;'
    }[tag] || tag));
  }

  function formatTime(isoStr) {
    if (!isoStr) return '';
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return '';
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  }

  // --- Open / Close Drawer ---
  function openDrawer() {
    if (drawer) drawer.classList.add('is-open');
    if (backdrop) backdrop.classList.add('is-open');
    document.body.style.overflow = 'hidden';

    readPageContext();
    initConversation();
  }

  function closeDrawer() {
    if (drawer) drawer.classList.remove('is-open');
    if (backdrop) backdrop.classList.remove('is-open');
    document.body.style.overflow = '';
    stopPolling();
  }

  // --- Read Page Context ---
  function readPageContext(explicitContext = {}) {
    currentContext = {
      productSlug: explicitContext.productSlug || document.body.dataset.productSlug || '',
      productName: explicitContext.productName || document.body.dataset.productName || '',
      productPrice: explicitContext.productPrice || document.body.dataset.productPrice || '',
      makerSlug: explicitContext.makerSlug || document.body.dataset.makerSlug || '',
      makerName: explicitContext.makerName || document.body.dataset.makerName || '',
      orderId: explicitContext.orderId || '',
      orderNumber: explicitContext.orderNumber || ''
    };

    const t = i18n[currentLang] || i18n.en;

    // Header Title
    if (sellerTitle) {
      sellerTitle.textContent = currentContext.makerName || t.defaultTitle;
    }

    // Pinned Bar
    if (pinnedBar) {
      if (currentContext.productName) {
        pinnedBar.style.display = 'flex';
        if (pinnedTitle) pinnedTitle.textContent = currentContext.productName;
        if (pinnedPrice) pinnedPrice.textContent = currentContext.productPrice;
      } else {
        pinnedBar.style.display = 'none';
      }
    }
  }

  // --- Initialize or Fetch Active Conversation ---
  async function initConversation() {
    const t = i18n[currentLang] || i18n.en;

    if (!CFG.authenticated) {
      if (messagesContainer) {
        messagesContainer.innerHTML = `
          <div style="text-align:center; padding:3rem 1.5rem; color:var(--crafty-muted);">
            <div style="font-size:2rem; margin-bottom:1rem;">💬</div>
            <p style="margin-bottom:1.5rem; font-size:0.95rem;">${t.loginPrompt}</p>
            <a href="${URLS.login || '/account/login/'}?next=${encodeURIComponent(window.location.pathname)}" class="btn btn--sm" style="display:inline-block; text-decoration:none;">
              ${t.loginBtn}
            </a>
          </div>
        `;
      }
      return;
    }

    if (messagesContainer) {
      messagesContainer.innerHTML = `
        <div style="text-align:center; padding:2rem; color:var(--crafty-muted); font-size:0.85rem;">
          ...
        </div>
      `;
    }

    try {
      let conv = null;

      // If we have a product or maker from current context, get or create that thread
      if (currentContext.productSlug || currentContext.makerSlug || currentContext.orderId) {
        const payload = {};
        if (currentContext.productSlug) payload.product = currentContext.productSlug;
        if (currentContext.makerSlug) payload.maker = currentContext.makerSlug;
        if (currentContext.orderId) payload.order = currentContext.orderId;

        const res = await fetch('/api/conversations/', {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken(),
            'Accept': 'application/json'
          },
          body: JSON.stringify(payload)
        });

        if (res.ok) {
          conv = await res.json();
        }
      }

      // If no context or thread creation didn't return, fetch most recent thread
      if (!conv) {
        const listRes = await fetch('/api/conversations/', {
          credentials: 'same-origin',
          headers: { 'Accept': 'application/json' }
        });
        if (listRes.ok) {
          const listData = await listRes.json();
          const items = Array.isArray(listData) ? listData : (listData.items || []);
          if (items.length > 0) {
            conv = items[0];
          }
        }
      }

      // If buyer has no existing conversations, initialize a new thread with the studio
      if (!conv) {
        const createRes = await fetch('/api/conversations/', {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken(),
            'Accept': 'application/json'
          },
          body: JSON.stringify({})
        });
        if (createRes.ok) {
          conv = await createRes.json();
        }
      }

      activeConversation = conv;

      if (activeConversation) {
        if (sellerTitle && activeConversation.maker_name) {
          sellerTitle.textContent = activeConversation.maker_name;
        }
        await loadMessages(activeConversation.uuid);
        startPolling();
      } else {
        if (messagesContainer) {
          messagesContainer.innerHTML = `
            <div style="text-align:center; padding:3rem 1.5rem; color:var(--crafty-muted); font-size:0.9rem;">
              ${t.noMessages}
            </div>
          `;
        }
      }
    } catch (err) {
      console.error('Failed to initialize conversation:', err);
    }
  }

  // --- Load Full Message History ---
  async function loadMessages(convUuid) {
    if (!convUuid) return;
    try {
      const res = await fetch(`/api/conversations/${convUuid}/messages/`, {
        credentials: 'same-origin',
        headers: { 'Accept': 'application/json' }
      });
      if (!res.ok) return;

      const msgs = await res.json();
      renderAllMessages(msgs);
    } catch (err) {
      console.error('Failed to load messages:', err);
    }
  }

  // --- Render Messages Stream ---
  function renderAllMessages(msgs) {
    if (!messagesContainer) return;
    const t = i18n[currentLang] || i18n.en;
    messagesContainer.innerHTML = '';

    if (!Array.isArray(msgs) || msgs.length === 0) {
      messagesContainer.innerHTML = `
        <div style="text-align:center; padding:2.5rem 1rem; color:var(--crafty-muted); font-size:0.9rem;">
          ${t.noMessages}
        </div>
      `;
      return;
    }

    // Date Divider
    const dateDivider = document.createElement('div');
    dateDivider.className = 'shopee-date-divider';
    dateDivider.innerHTML = `<span class="shopee-date-pill">${t.today}</span>`;
    messagesContainer.appendChild(dateDivider);

    msgs.forEach(m => {
      appendMessageToDOM(m);
    });

    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  function appendMessageToDOM(m) {
    if (!messagesContainer) return;
    const t = i18n[currentLang] || i18n.en;
    lastMessageUuid = m.uuid;

    const isUser = Boolean(m.is_sender);
    const msgEl = document.createElement('div');
    msgEl.className = `crafty-msg ${isUser ? 'crafty-msg--user' : 'crafty-msg--bot'}`;
    msgEl.setAttribute('data-msg-uuid', m.uuid);

    const timeStr = formatTime(m.created_at);
    let metaHtml = '';
    if (isUser) {
      metaHtml = `
        <div class="crafty-msg-meta">
          <span>${timeStr}</span>
          <span class="crafty-receipt">✓</span>
        </div>
      `;
    } else {
      const defaultBadge = m.is_seller ? t.artisan : (t.buyer || 'Buyer');
      const badgeText = m.sender_name || defaultBadge;
      metaHtml = `
        <div class="crafty-msg-meta">
          <span class="crafty-maker-badge">${escapeHtml(badgeText)}</span>
          <span>•</span>
          <span>${timeStr}</span>
        </div>
      `;
    }

    msgEl.innerHTML = `
      ${metaHtml}
      <div class="crafty-bubble">
        <p style="white-space:pre-wrap; margin:0;">${escapeHtml(m.body)}</p>
      </div>
    `;

    messagesContainer.appendChild(msgEl);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  // --- Send Message ---
  async function sendMessage(textOverride) {
    const raw = textOverride !== undefined ? textOverride : (input ? input.value : '');
    const text = (raw || '').trim();
    if (!text) return;

    if (!activeConversation) {
      await initConversation();
      if (!activeConversation) {
        console.warn('Could not establish conversation with artisan.');
        return;
      }
    }

    if (textOverride === undefined && input) {
      input.value = '';
    }

    try {
      const res = await fetch(`/api/conversations/${activeConversation.uuid}/messages/`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrfToken(),
          'Accept': 'application/json'
        },
        body: JSON.stringify({ body: text })
      });

      if (res.ok) {
        const savedMsg = await res.json();
        // Remove empty placeholder message if present
        const emptyPlaceholder = messagesContainer?.querySelector('.shopee-date-divider') ? null : messagesContainer?.firstElementChild;
        if (emptyPlaceholder && !emptyPlaceholder.classList.contains('crafty-msg')) {
          emptyPlaceholder.remove();
        }
        appendMessageToDOM(savedMsg);
      }
    } catch (err) {
      console.error('Failed to send message:', err);
    }
  }

  // --- Polling for New Messages ---
  function startPolling() {
    stopPolling();
    pollInterval = setInterval(async () => {
      if (!activeConversation || !drawer?.classList.contains('is-open')) return;
      try {
        const url = lastMessageUuid
          ? `/api/conversations/${activeConversation.uuid}/messages/?after=${lastMessageUuid}`
          : `/api/conversations/${activeConversation.uuid}/messages/`;

        const res = await fetch(url, {
          credentials: 'same-origin',
          headers: { 'Accept': 'application/json' }
        });
        if (!res.ok) return;

        const newMsgs = await res.json();
        if (Array.isArray(newMsgs) && newMsgs.length > 0) {
          newMsgs.forEach(m => {
            if (!messagesContainer?.querySelector(`[data-msg-uuid="${m.uuid}"]`)) {
              appendMessageToDOM(m);
            }
          });
        }
      } catch (e) {}
    }, 4000);
  }

  function stopPolling() {
    if (pollInterval) {
      clearInterval(pollInterval);
      pollInterval = null;
    }
  }

  // --- Render Emoji Grid ---
  function renderEmojiGrid(tabKey) {
    if (!emojiGrid) return;
    emojiGrid.innerHTML = '';
    const list = emojiCatalog[tabKey] || emojiCatalog.faces;

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
      emojiGrid.appendChild(btn);
    });
  }

  // --- Wire Event Listeners ---
  function init() {
    // 1. Launcher button
    launcher?.addEventListener('click', openDrawer);

    // 2. Close buttons
    closeBtn?.addEventListener('click', closeDrawer);
    backBtn?.addEventListener('click', closeDrawer);
    backdrop?.addEventListener('click', closeDrawer);

    // 3. Form submit & send button
    form?.addEventListener('submit', (e) => {
      e.preventDefault();
      sendMessage();
    });

    sendBtn?.addEventListener('click', (e) => {
      e.preventDefault();
      sendMessage();
    });

    input?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        sendMessage();
      }
    });

    // 4. Global buttons with [data-open-chat]
    document.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-open-chat]');
      if (btn) {
        e.preventDefault();
        const ctx = {
          productSlug: btn.dataset.productSlug || '',
          productName: btn.dataset.productName || '',
          productPrice: btn.dataset.productPrice || '',
          makerSlug: btn.dataset.makerSlug || '',
          makerName: btn.dataset.makerName || '',
          orderId: btn.dataset.orderId || '',
          orderNumber: btn.dataset.orderNumber || ''
        };
        readPageContext(ctx);
        openDrawer();
      }
    });

    // 5. Tools tray toggle
    btnPlusTool?.addEventListener('click', () => {
      if (toolsTray) {
        toolsTray.style.display = toolsTray.style.display === 'none' ? 'flex' : 'none';
      }
    });

    toolBtnProduct?.addEventListener('click', () => {
      if (currentContext.productName) {
        sendMessage(`Inquiring about ${currentContext.productName} (${currentContext.productPrice})`);
      } else {
        sendMessage('Hello! I would like to inquire about your craft work.');
      }
      if (toolsTray) toolsTray.style.display = 'none';
    });

    toolBtnOrder?.addEventListener('click', () => {
      if (currentContext.orderNumber) {
        sendMessage(`Inquiring about order #${currentContext.orderNumber}`);
      } else {
        sendMessage('Hello, could you help me check my order status?');
      }
      if (toolsTray) toolsTray.style.display = 'none';
    });

    // 6. Emoji Picker
    renderEmojiGrid('faces');
    btnEmojiToggle?.addEventListener('click', (e) => {
      e.stopPropagation();
      if (emojiPicker) {
        emojiPicker.style.display = emojiPicker.style.display === 'none' ? 'block' : 'none';
      }
    });

    document.querySelectorAll('.shopee-emoji-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('.shopee-emoji-tab').forEach(t => t.classList.remove('is-active'));
        tab.classList.add('is-active');
        renderEmojiGrid(tab.getAttribute('data-tab'));
      });
    });

    document.addEventListener('click', (e) => {
      if (emojiPicker && !emojiPicker.contains(e.target) && e.target !== btnEmojiToggle) {
        emojiPicker.style.display = 'none';
      }
    });

    // 7. Language toggle
    langToggle?.addEventListener('click', () => {
      currentLang = currentLang === 'zh' ? 'en' : 'zh';
      const t = i18n[currentLang] || i18n.en;
      if (langToggle) langToggle.textContent = t.langToggleText;
      if (input) input.placeholder = t.inputPlaceholder;
      if (sellerTitle && !currentContext.makerName) sellerTitle.textContent = t.defaultTitle;
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();

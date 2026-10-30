/**
 * Atelier Form - Buyer-to-Seller Messaging Widget
 *
 * Real server-side communication backed by /api/conversations/
 * - Messages persisted in database
 * - Scoped by authenticated buyer & artisan maker
 * - Simple polling for incoming replies
 * - Automatic context from active product or artisan page
 * - Manual seller selection from general chat launcher
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
  const sellerSelect = document.getElementById('crafty-seller-select');
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
  let unreadInterval = null;
  let currentContext = {};
  let isSending = false;
  let cachedMakers = [];
  let returnFocus = null;

  // Fallback makers if /api/makers/ is unavailable
  const DEFAULT_MAKERS = [
    { slug: 'chen-meilin', name: 'Chen Meilin', discipline: 'Ceramicist' },
    { slug: 'lu-wenjing', name: 'Lu Wenjing', discipline: 'Woodcraft' },
    { slug: 'zhao-hesheng', name: 'Zhao Hesheng', discipline: 'Metalwork' },
    { slug: 'xu-anying', name: 'Xu Anying', discipline: 'Textiles' },
    { slug: 'ye-ruolan', name: 'Ye Ruolan', discipline: 'Glassblower' }
  ];

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
      langToggleText: 'EN',
      chooseArtisan: '选择手作人...',
      startChatPrompt: '请从上方选择一位手作人或直接发送消息开启对话。'
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
      langToggleText: '中文',
      chooseArtisan: 'Select an artisan...',
      startChatPrompt: 'Select an artisan above or type a message below to start.'
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
    const inputToken = document.querySelector('input[name="csrfmiddlewaretoken"]')?.value;
    if (inputToken) return inputToken;
    const metaToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
    if (metaToken) return metaToken;
    const match = document.cookie.match(/(?:csrftoken|__Host-[^=]*-csrf|csrf|[^;]*csrf[^=]*)=([^;]+)/i);
    return match ? decodeURIComponent(match[1]) : '';
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

  // --- Bilingual Translation Service (EN ⇄ ZH) ---
  const CLIENT_TRANSLATION_PAIRS = [
    [/\[automated\]\s*hello!\s*welcome to ([^.]+)\.\s*how can we help you today with our items or custom commissions\?\s*leave a message and the maker will reply here!?/i,
     "[自动回复] 您好！欢迎光临 $1。今天我们在商品或定制委托方面能为您提供什么帮助？请留言，手作人将在此回复！"],
    [/\[automated\]\s*hello!\s*welcome to ([^.]+)\.\s*i see you're viewing our ([^.]+)\.\s*feel free to ask about materials, dimensions, or custom crafting, and the maker will reply here!?/i,
     "[自动回复] 您好！欢迎光临 $1。看到您正在浏览我们的 $2。欢迎咨询材质、尺寸或定制工艺，手作人将在此回复！"],
    [/hello,?\s*is this (?:keepsake box|product|item) currently in stock\??/i,
     "您好，请问这件作品目前有现货吗？"],
    [/is this (?:in stock|available)\??/i,
     "请问有现货吗？"],
    [/can you engrave initials on the lid\??/i,
     "请问可以在盖子上刻首字母吗？"],
    [/yes,?\s*we can engrave on the inner lid!?/i,
     "是的，我们可以在内盖上刻字！"],
    [/can this be customized\??/i,
     "请问这个可以定制吗？"],
    [/when will this be shipped\??/i,
     "请问什么时候可以发货？"],
    [/inquiring about order #?([A-Za-z0-9-]+)/i,
     "咨询订单 #$1"],
    [/inquiring about ([^()]+)(?:\s*\(([^)]+)\))?/i,
     "咨询关于 $1"],
    [/could you help me check my order status\??/i,
     "您能帮我查询一下订单状态吗？"],
    [/hello!?\s*i would like to inquire about your craft work\.?/i,
     "您好！我想咨询关于您的手工作品。"],
    [/thank you very much!?/i,
     "非常感谢！"],
    [/thank you!?/i,
     "谢谢！"],
    [/you're welcome!?/i,
     "不客气！"],
    [/it is high-fired porcelain,?\s*excellent for retaining heat\.?/i,
     "这是高温烧制瓷器，保温性能极佳。"],
    [/in stock,?\s*can be shipped today\.?/i,
     "有现货，今天即可发货。"]
  ];

  const CLIENT_ZH_TO_EN_PAIRS = [
    [/\[自动回复\]\s*您好！欢迎光临\s*([^。]+)。今天我们在商品或定制委托方面能为您提供什么帮助？请留言，手作人将在此回复！/,
     "[Automated] Hello! Welcome to $1. How can we help you today with our items or custom commissions? Leave a message and the maker will reply here!"],
    [/\[自动回复\]\s*您好！欢迎光临\s*([^。]+)。看到您正在浏览我们的\s*([^。]+)。欢迎咨询材质、尺寸或定制工艺，手作人将在此回复！/,
     "[Automated] Hello! Welcome to $1. I see you're viewing our $2. Feel free to ask about materials, dimensions, or custom crafting, and the maker will reply here!"],
    [/您好，请问这件作品目前有现货吗[？?]?/, "Hello, is this piece currently in stock?"],
    [/请问有现货吗[？?]?/, "Is this in stock?"],
    [/请问可以在盖子上刻首字母吗[？?]?/, "Can you engrave initials on the lid?"],
    [/是的，我们可以在内盖上刻字[！!。]?/, "Yes, we can engrave on the inner lid!"],
    [/请问这个可以定制吗[？?]?/, "Can this be customized?"],
    [/请问什么时候可以发货[？?]?/, "When will this be shipped?"],
    [/咨询订单\s*#?([A-Za-z0-9-]+)/, "Inquiring about order #$1"],
    [/您能帮我查询一下订单状态吗[？?]?/, "Could you help me check my order status?"],
    [/您好！我想咨询关于您的手工作品[。！]?/, "Hello! I would like to inquire about your craft work."],
    [/非常感谢[！!。]?/, "Thank you very much!"],
    [/谢谢[！!。]?/, "Thank you!"],
    [/不客气[！!。]?/, "You are welcome!"],
    [/好的[，！]没问题[！!。]?/, "Sure, no problem!"],
    [/有现货，今天即可发货[。！]?/, "In stock, can be shipped today."]
  ];

  const CLIENT_ZH_TO_EN_VOCAB = [
    ['你好', 'hello'], ['您好', 'hello'], ['在吗', 'are you there'],
    ['现货', 'in stock'], ['有货', 'in stock'], ['库存', 'inventory'],
    ['定制', 'customize'], ['刻字', 'engrave'], ['首字母', 'initials'],
    ['发货', 'shipment'], ['配送', 'delivery'], ['运费', 'shipping fee'],
    ['包邮', 'free shipping'], ['多少钱', 'how much'], ['价格', 'price'],
    ['茶杯', 'tea cup'], ['杯子', 'cup'], ['陶瓷', 'ceramic'],
    ['瓷器', 'porcelain'], ['木作', 'woodcraft'], ['盖子', 'lid'],
    ['手工', 'handmade'], ['手作', 'handcrafted'], ['真皮', 'genuine leather'],
    ['材质', 'material'], ['尺寸', 'dimensions'], ['谢谢', 'thank you'],
    ['好的', 'okay'], ['可以', 'can'], ['没问题', 'no problem']
  ];

  function clientFallbackTranslate(text, sourceLang, targetLang, context) {
    const prodName = context?.product_name || '';

    if (sourceLang === 'en' && targetLang === 'zh') {
      if (/when will (?:it|the piece|the item) be ready/i.test(text)) {
        return prodName ? `请问这款${prodName}大概什么时候能制作完成？` : '请问作品大概什么时候能制作完成？';
      }
      if (/is (?:this|the) (?:piece|item)?\s*(?:in stock|available)/i.test(text)) {
        return prodName ? `请问这款${prodName}目前有现货吗？` : '请问这件作品目前有现货吗？';
      }
      for (const [re, repl] of CLIENT_TRANSLATION_PAIRS) {
        if (re.test(text)) {
          return text.replace(re, repl);
        }
      }
      return text;
    } else if (sourceLang === 'zh' && targetLang === 'en') {
      // Contextual disambiguation
      if (/(?:什么时候能好|什么时候做好|做好了吗|大概需要多久|几天能好)/.test(text)) {
        return prodName ? `When will the ${prodName} be ready?` : 'When will the handcrafted piece be ready?';
      }
      if (/^(?:请问)?(?:这个|这款|这件作品|这个作品)(?:多少钱|价格|怎么卖)[？?]*$/.test(text)) {
        return prodName ? `How much is the ${prodName}?` : 'How much is this handcrafted piece?';
      }
      if (/^(?:请问)?(?:这个|这款|这件作品|这个作品)?(?:目前)?(?:还)?有现货吗[？?]*$/.test(text)) {
        return prodName ? `Is the ${prodName} currently in stock?` : 'Hello, is this piece currently in stock?';
      }
      if (/^(?:请问)?(?:这个|这款)?可以定制(?:刻字)?吗[？?]*$/.test(text)) {
        return prodName ? `Can the ${prodName} be customized with engraving?` : 'Can this piece be customized with engraving?';
      }
      if (/内盖.*刻字/.test(text)) {
        return 'Can the inner lid be custom engraved?';
      }
      if (/开窑/.test(text)) {
        return 'The piece will be shipped once the kiln firing is completed.';
      }
      if (/(?:已经拍下|拍下了|刚下单|已下单)/.test(text)) {
        return 'I have placed the order for this piece.';
      }
      const mVar = text.match(/那([^\s？?]+)的呢/);
      if (mVar) {
        return prodName ? `What about the ${mVar[1]} ${prodName}?` : `What about the ${mVar[1]} option?`;
      }

      for (const [re, repl] of CLIENT_ZH_TO_EN_PAIRS) {
        if (re.test(text)) {
          return text.replace(re, repl);
        }
      }

      const isQuestion = /[？?]/.test(text) || /(?:吗|请问|多少|多久|几|何|怎么|能否|是否|何时|什么时候)/.test(text);

      // Semantic Intent Recognizers (never auto-replies questions with answers)
      if (/(?:多少钱|价格|怎么卖|什么价|报价)/.test(text)) {
        return prodName ? `How much is the ${prodName}?` : 'How much is this item?';
      }
      if (/(?:现货|有货|库存)/.test(text)) {
        return isQuestion ? (prodName ? `Is the ${prodName} currently in stock?` : 'Hello, is this piece currently in stock?') : 'In stock, can be shipped today.';
      }
      if (/(?:定制|刻字|刻名字)/.test(text)) {
        return isQuestion ? 'Can this piece be customized or engraved?' : 'Yes, we support custom commissions.';
      }
      if (/(?:运费|包邮)/.test(text)) {
        return 'How much is the shipping fee?';
      }
      if (/(?:发货|几天到|多久到)/.test(text)) {
        return isQuestion ? 'When will this item be shipped?' : 'Your order will be shipped soon.';
      }
      if (/(?:材质|手工|真皮|纯银|青瓷|木作|陶瓷|纯手工)/.test(text)) {
        return isQuestion ? 'What material is this handcrafted from?' : 'This piece is meticulously handcrafted.';
      }
      if (/(?:你好|您好|在吗|有人在吗)/.test(text)) {
        return 'Hello! How can I help you today?';
      }
      if (/(?:谢谢|多谢|非常感谢|感谢)/.test(text)) {
        return 'Thank you very much!';
      }
      if (/(?:好的|没问题|可以的|收到|明白了)/.test(text) && !isQuestion) {
        return 'Sure, no problem!';
      }

      // Safe vocabulary replacement that strips unmapped Chinese so it never echoes Chinese
      let assembled = text;
      for (const [zh, en] of CLIENT_ZH_TO_EN_VOCAB) {
        assembled = assembled.split(zh).join(' ' + en + ' ');
      }
      assembled = assembled.replace(/[\u4e00-\u9fff]+/g, ' ').replace(/\s+/g, ' ').trim();
      if (!assembled) assembled = 'inquiry details';
      return isQuestion ? `Inquiry: ${assembled}?` : assembled;
    }
    return text;
  }

  async function translateMessage(text, targetLang, contextInfo) {
    if (!text) return { translated: '', target_lang: 'zh' };

    const ctx = contextInfo || {};
    try {
      const res = await fetch('/api/conversations/translate/', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrfToken(),
          'Accept': 'application/json'
        },
        body: JSON.stringify({
          text,
          target_lang: targetLang,
          conversation: activeConversation?.uuid,
          context: ctx
        })
      });
      if (res.ok) {
        const data = await res.json();
        if (data && data.translated) return data;
      }
    } catch (e) {}

    const hasChinese = /[\u4e00-\u9fff]/.test(text);
    const sourceLang = hasChinese ? 'zh' : 'en';
    const resolvedTarget = targetLang || (hasChinese ? 'en' : 'zh');
    return {
      original: text,
      translated: clientFallbackTranslate(text, sourceLang, resolvedTarget, ctx),
      source_lang: sourceLang,
      target_lang: resolvedTarget,
      context_applied: (ctx.maker_name || ctx.product_name) ? {
        summary: [ctx.maker_name, ctx.product_name].filter(Boolean).join(' · ')
      } : null
    };
  }

  // --- Load Makers into Selector Dropdown ---
  async function loadMakersList() {
    if (cachedMakers.length > 0) return cachedMakers;

    try {
      const res = await fetch('/api/makers/', {
        credentials: 'same-origin',
        headers: { 'Accept': 'application/json' }
      });
      if (res.ok) {
        const data = await res.json();
        cachedMakers = Array.isArray(data) ? data : (data.results || data.items || []);
      }
    } catch (e) {
      console.warn('Failed to fetch makers via API; falling back to default list.', e);
    }

    if (!cachedMakers || cachedMakers.length === 0) {
      cachedMakers = DEFAULT_MAKERS;
    }

    populateSellerDropdown(cachedMakers);
    return cachedMakers;
  }

  function populateSellerDropdown(makers) {
    if (!sellerSelect) return;
    const t = i18n[currentLang] || i18n.en;
    const currentVal = sellerSelect.value || currentContext.makerSlug;

    sellerSelect.innerHTML = `<option value="">-- ${t.chooseArtisan} --</option>`;

    makers.forEach(m => {
      const opt = document.createElement('option');
      opt.value = m.slug;
      opt.dataset.name = m.name;
      opt.textContent = `${m.name}${m.discipline ? ' (' + m.discipline + ')' : ''}`;
      sellerSelect.appendChild(opt);
    });

    if (currentVal) {
      sellerSelect.value = currentVal;
    }
  }

  // --- Render Default Empty Chat State (No card bubbles) ---
  function renderEmptyState(promptText) {
    if (!messagesContainer) return;
    const t = i18n[currentLang] || i18n.en;
    messagesContainer.innerHTML = `
      <div class="crafty-empty-placeholder" style="text-align:center; padding:2.5rem 1rem; color:var(--crafty-muted); font-size:0.9rem;">
        <div style="font-size:2rem; margin-bottom:0.5rem;">🏺</div>
        <p>${escapeHtml(promptText || t.startChatPrompt || t.noMessages)}</p>
      </div>
    `;
  }

  // --- Switch Active Seller ---
  async function switchSeller(makerSlug, makerName) {
    if (!makerSlug) return;
    stopPolling();
    activeConversation = null;
    lastMessageUuid = null;

    currentContext.makerSlug = makerSlug;
    currentContext.makerName = makerName || '';
    // Reset product context on manual seller switch
    currentContext.productSlug = '';
    currentContext.productName = '';
    currentContext.productPrice = '';
    currentContext.orderId = '';
    currentContext.orderNumber = '';

    if (sellerSelect) {
      sellerSelect.value = makerSlug;
    }
    if (sellerTitle) {
      sellerTitle.textContent = currentContext.makerName || makerSlug;
    }
    if (pinnedBar) {
      pinnedBar.style.display = 'none';
    }

    await initConversation();
  }

  // --- Unread Badge & Background Notification ---
  async function updateUnreadBadge() {
    if (!CFG.authenticated || !unreadBadge) return;
    try {
      const res = await fetch('/api/conversations/', {
        credentials: 'same-origin',
        headers: { 'Accept': 'application/json' }
      });
      if (!res.ok) return;
      const listData = await res.json();
      const items = Array.isArray(listData) ? listData : (listData.items || listData.results || []);
      let totalUnread = 0;
      items.forEach(c => {
        totalUnread += (c.unread_count || 0);
      });

      if (totalUnread > 0 && !drawer?.classList.contains('is-open')) {
        unreadBadge.textContent = totalUnread > 99 ? '99+' : String(totalUnread);
        unreadBadge.style.display = 'inline-block';
        unreadBadge.style.background = '#e11d48';
        unreadBadge.style.color = '#ffffff';
        unreadBadge.style.boxShadow = '0 0 8px rgba(225, 29, 72, 0.6)';
      } else if (drawer?.classList.contains('is-open')) {
        unreadBadge.style.display = 'none';
      } else {
        unreadBadge.style.display = 'none';
      }
    } catch (e) {}
  }

  // --- Open / Close Drawer ---
  function openDrawer(explicitContext) {
    returnFocus = document.activeElement;
    document.dispatchEvent(new CustomEvent('atelier:support-open', {detail: {kind: 'messages'}}));
    if (drawer) drawer.classList.add('is-open');
    if (backdrop) backdrop.classList.add('is-open');
    document.body.style.overflow = 'hidden';
    drawer?.focus();

    // Clear unread badge immediately when opening chat
    if (unreadBadge) unreadBadge.style.display = 'none';

    readPageContext(explicitContext || {});
    loadMakersList().then(() => {
      initConversation();
    });
  }

  function closeDrawer(restoreFocus = true) {
    if (drawer) drawer.classList.remove('is-open');
    if (backdrop) backdrop.classList.remove('is-open');
    document.body.style.overflow = '';
    stopPolling();
    updateUnreadBadge();
    if (restoreFocus) {
      const target = returnFocus?.getClientRects().length ? returnFocus : document.getElementById('support-open') || launcher;
      target?.focus();
    }
  }

  document.addEventListener('atelier:support-open', event => {
    if (event.detail?.kind !== 'messages' && drawer?.classList.contains('is-open')) closeDrawer(false);
  });

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

    // Seller Dropdown Sync
    if (sellerSelect && currentContext.makerSlug) {
      sellerSelect.value = currentContext.makerSlug;
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

  // --- Helper to clean up empty state placeholders ---
  function removeEmptyPlaceholder() {
    if (!messagesContainer) return;
    const t = i18n[currentLang] || i18n.en;
    const placeholders = messagesContainer.querySelectorAll('.crafty-empty-placeholder');
    placeholders.forEach(el => el.remove());

    const firstChild = messagesContainer.firstElementChild;
    if (firstChild && !firstChild.classList.contains('crafty-msg') && !firstChild.classList.contains('shopee-date-divider')) {
      firstChild.remove();
    }

    if (!messagesContainer.querySelector('.shopee-date-divider')) {
      const dateDivider = document.createElement('div');
      dateDivider.className = 'shopee-date-divider';
      dateDivider.innerHTML = `<span class="shopee-date-pill">${t.today}</span>`;
      messagesContainer.prepend(dateDivider);
    }
  }

  // --- Initialize or Fetch Active Conversation ---
  async function initConversation() {
    const t = i18n[currentLang] || i18n.en;

    if (!CFG.authenticated) {
      if (messagesContainer) {
        messagesContainer.innerHTML = `
          <div class="crafty-empty-placeholder" style="text-align:center; padding:3rem 1.5rem; color:var(--crafty-muted);">
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

    try {
      let conv = null;

      // 1. If we have a maker or product from current context, get or create that thread
      if (currentContext.makerSlug || currentContext.productSlug || currentContext.orderId) {
        const payload = {};
        if (currentContext.makerSlug) payload.maker = currentContext.makerSlug;
        if (currentContext.productSlug) payload.product = currentContext.productSlug;
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

      // 2. If no explicit maker context, inspect existing conversations for this user
      if (!conv) {
        const listRes = await fetch('/api/conversations/', {
          credentials: 'same-origin',
          headers: { 'Accept': 'application/json' }
        });
        if (listRes.ok) {
          const listData = await listRes.json();
          const items = Array.isArray(listData) ? listData : (listData.items || listData.results || []);
          if (items.length > 0) {
            // Priority: unread conversation, then most recently updated
            const unreadConv = items.find(c => (c.unread_count || 0) > 0);
            conv = unreadConv || items[0];
          }
        }
      }

      // 3. If buyer has NO existing conversations and opened general chat, show clean empty state
      if (!conv) {
        activeConversation = null;
        if (sellerTitle) {
          sellerTitle.textContent = currentContext.makerName || t.defaultTitle;
        }
        if (sellerSelect) {
          sellerSelect.value = currentContext.makerSlug || '';
        }
        renderEmptyState();
        return;
      }

      // Conversation successfully selected or initialized
      activeConversation = conv;
      lastMessageUuid = null;

      if (activeConversation.uuid) {
        sessionStorage.setItem('crafty_active_conv_uuid', activeConversation.uuid);
      }
      if (activeConversation.maker_slug) {
        currentContext.makerSlug = activeConversation.maker_slug;
        currentContext.makerName = activeConversation.maker_name || activeConversation.maker_slug;
        if (sellerSelect) {
          sellerSelect.value = activeConversation.maker_slug;
        }
      }
      if (sellerTitle && activeConversation.maker_name) {
        sellerTitle.textContent = activeConversation.maker_name;
      }
      if (pinnedBar && !currentContext.productName && activeConversation.product_name) {
        pinnedBar.style.display = 'flex';
        if (pinnedTitle) pinnedTitle.textContent = activeConversation.product_name;
        if (pinnedPrice) pinnedPrice.textContent = activeConversation.product_price || '';
      }

      await loadMessages(activeConversation.uuid);
      startPolling();
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
        <div class="crafty-empty-placeholder" style="text-align:center; padding:2.5rem 1rem; color:var(--crafty-muted); font-size:0.9rem;">
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

    if (msgs.length > 0) {
      lastMessageUuid = msgs[msgs.length - 1].uuid;
    }
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  function appendMessageToDOM(m) {
    if (!messagesContainer || !m || !m.uuid) return;
    // Prevent duplicate rendering
    if (messagesContainer.querySelector(`[data-msg-uuid="${m.uuid}"]`)) return;

    const t = i18n[currentLang] || i18n.en;
    lastMessageUuid = m.uuid;

    removeEmptyPlaceholder();

    const isUser = Boolean(m.is_sender);
    const msgEl = document.createElement('div');
    msgEl.className = `crafty-msg ${isUser ? 'crafty-msg--user' : 'crafty-msg--bot'}`;
    msgEl.setAttribute('data-msg-uuid', m.uuid);

    const timeStr = formatTime(m.created_at);
    const translateBtnHtml = `
      <button type="button" class="crafty-translate-btn" data-translate-btn title="${currentLang === 'zh' ? '翻译此消息 (中英互译)' : 'Translate message (EN ⇄ ZH)'}">
        🌐 文/A
      </button>
    `;

    let metaHtml = '';
    if (isUser) {
      metaHtml = `
        <div class="crafty-msg-meta">
          ${translateBtnHtml}
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
          ${translateBtnHtml}
        </div>
      `;
    }

    msgEl.innerHTML = `
      ${metaHtml}
      <div class="crafty-bubble">
        <p class="crafty-bubble-body" style="white-space:pre-wrap; margin:0;">${escapeHtml(m.body)}</p>
        <div class="crafty-translation-box" style="display:none;"></div>
      </div>
    `;

    // Wire translation button click
    const translateBtn = msgEl.querySelector('[data-translate-btn]');
    const translationBox = msgEl.querySelector('.crafty-translation-box');

    translateBtn?.addEventListener('click', async (e) => {
      e.stopPropagation();
      if (!translationBox) return;

      // Toggle off if already displayed
      if (translationBox.style.display !== 'none') {
        translationBox.style.display = 'none';
        return;
      }

      // Re-show cached translation if already loaded
      if (translationBox.dataset.translated === 'true') {
        translationBox.style.display = 'block';
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
        return;
      }

      const origText = translateBtn.innerHTML;
      translateBtn.innerHTML = '...';
      translateBtn.disabled = true;

      try {
        const contextInfo = {
          maker_name: currentContext.makerName || (sellerTitle ? sellerTitle.textContent.trim() : ''),
          maker_discipline: currentContext.makerDiscipline || '',
          product_name: currentContext.productTitle || (pinnedTitle ? pinnedTitle.textContent.trim() : ''),
          is_sender: Boolean(m.is_sender)
        };
        const result = await translateMessage(m.body, null, contextInfo);
        const isTargetZh = result.target_lang === 'zh';
        const badgeLabel = isTargetZh ? '🌐 翻译 (中文)' : '🌐 Translation (English)';
        const contextSummary = result.context_applied?.summary || (contextInfo.product_name ? `${contextInfo.maker_name || 'Artisan'} · ${contextInfo.product_name}` : '');
        const contextBadgeHtml = contextSummary ? `
          <div class="crafty-context-badge" title="Contextually resolved with active artisan & product dialogue">
            <span>📌 Context: ${escapeHtml(contextSummary)}</span>
          </div>
        ` : '';

        translationBox.innerHTML = `
          <div class="crafty-translation-header">
            <span>${badgeLabel}</span>
            <button type="button" class="crafty-translation-hide-btn" title="Hide">✕</button>
          </div>
          ${contextBadgeHtml}
          <div class="crafty-translation-content">${escapeHtml(result.translated)}</div>
        `;
        translationBox.dataset.translated = 'true';
        translationBox.style.display = 'block';

        translationBox.querySelector('.crafty-translation-hide-btn')?.addEventListener('click', () => {
          translationBox.style.display = 'none';
        });

        messagesContainer.scrollTop = messagesContainer.scrollHeight;
      } catch (err) {
        console.error('Translation error:', err);
      } finally {
        translateBtn.innerHTML = origText;
        translateBtn.disabled = false;
      }
    });

    messagesContainer.appendChild(msgEl);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  // --- Send Message ---
  async function sendMessage(textOverride) {
    if (isSending) return;

    const raw = textOverride !== undefined ? textOverride : (input ? input.value : '');
    const text = (raw || '').trim();
    if (!text) return;

    if (!activeConversation) {
      if (!currentContext.makerSlug) {
        if (sellerSelect && sellerSelect.value) {
          currentContext.makerSlug = sellerSelect.value;
          const opt = sellerSelect.options[sellerSelect.selectedIndex];
          currentContext.makerName = opt?.dataset?.name || opt?.text || sellerSelect.value;
        } else if (sellerSelect && sellerSelect.options.length > 1) {
          for (let i = 0; i < sellerSelect.options.length; i++) {
            if (sellerSelect.options[i].value) {
              sellerSelect.selectedIndex = i;
              currentContext.makerSlug = sellerSelect.options[i].value;
              currentContext.makerName = sellerSelect.options[i].dataset?.name || sellerSelect.options[i].text;
              break;
            }
          }
        }
      }

      if (!currentContext.makerSlug) {
        if (sellerSelect) {
          sellerSelect.focus();
          sellerSelect.style.borderColor = '#e11d48';
          setTimeout(() => { sellerSelect.style.borderColor = ''; }, 2000);
        }
        return;
      }
      await initConversation();
      if (!activeConversation) {
        console.warn('Could not establish conversation with artisan.');
        return;
      }
    }

    isSending = true;
    if (sendBtn) {
      sendBtn.disabled = true;
      sendBtn.style.opacity = '0.6';
    }
    if (textOverride === undefined && input) {
      input.value = '';
    }

    try {
      const csrfToken = getCsrfToken();
      const res = await fetch(`/api/conversations/${activeConversation.uuid}/messages/`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
          'Accept': 'application/json'
        },
        body: JSON.stringify({ body: text })
      });

      if (res.ok) {
        const savedMsg = await res.json();
        removeEmptyPlaceholder();
        appendMessageToDOM(savedMsg);
      } else {
        const err = await res.json().catch(() => ({}));
        console.error('Failed to send message:', res.status, err);
        if (textOverride === undefined && input) {
          input.value = text;
        }
      }
    } catch (err) {
      console.error('Failed to send message:', err);
      if (textOverride === undefined && input) {
        input.value = text;
      }
    } finally {
      isSending = false;
      if (sendBtn) {
        sendBtn.disabled = false;
        sendBtn.style.opacity = '';
      }
      if (input) {
        input.focus();
      }
    }
  }

  // --- Polling for New Messages in Open Drawer (Fast 2s Polling) ---
  function startPolling() {
    stopPolling();
    pollInterval = setInterval(async () => {
      if (!activeConversation || !drawer?.classList.contains('is-open')) return;
      try {
        const url = lastMessageUuid
          ? `/api/conversations/${activeConversation.uuid}/messages/?after=${encodeURIComponent(lastMessageUuid)}`
          : `/api/conversations/${activeConversation.uuid}/messages/`;

        const res = await fetch(url, {
          credentials: 'same-origin',
          headers: { 'Accept': 'application/json' }
        });
        if (!res.ok) return;

        const newMsgs = await res.json();
        if (Array.isArray(newMsgs) && newMsgs.length > 0) {
          newMsgs.forEach(m => {
            appendMessageToDOM(m);
          });
          lastMessageUuid = newMsgs[newMsgs.length - 1].uuid;
        }
      } catch (e) {}
    }, 2000);
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
    launcher?.addEventListener('click', () => {
      openDrawer();
    });

    // 2. Close buttons
    closeBtn?.addEventListener('click', closeDrawer);
    backBtn?.addEventListener('click', closeDrawer);
    backdrop?.addEventListener('click', closeDrawer);
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && drawer?.classList.contains('is-open')) closeDrawer();
    });

    // 3. Manual seller selection dropdown
    sellerSelect?.addEventListener('change', (e) => {
      const selectedSlug = e.target.value;
      if (!selectedSlug) return;
      const selectedOpt = e.target.options[e.target.selectedIndex];
      const selectedName = selectedOpt?.dataset?.name || selectedOpt?.text || selectedSlug;
      switchSeller(selectedSlug, selectedName);
    });

    // 4. Send button click & form submission & enter key
    sendBtn?.addEventListener('click', (e) => {
      e.preventDefault();
      sendMessage();
    });

    form?.addEventListener('submit', (e) => {
      e.preventDefault();
      sendMessage();
    });

    input?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });

    // 5. Global buttons with [data-open-chat]
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
        openDrawer(ctx);
      }
    });

    // 6. Tools tray toggle
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

    // 7. Emoji Picker
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

    // 8. Language toggle
    langToggle?.addEventListener('click', () => {
      currentLang = currentLang === 'zh' ? 'en' : 'zh';
      const t = i18n[currentLang] || i18n.en;
      if (langToggle) langToggle.textContent = t.langToggleText;
      if (input) input.placeholder = t.inputPlaceholder;
      if (sellerTitle && !currentContext.makerName) sellerTitle.textContent = t.defaultTitle;
      populateSellerDropdown(cachedMakers.length > 0 ? cachedMakers : DEFAULT_MAKERS);
    });

    // 9. Pre-fetch makers list
    loadMakersList();

    // 10. Start background unread checking for authenticated buyers (every 4s)
    if (CFG.authenticated) {
      updateUnreadBadge();
      unreadInterval = setInterval(updateUnreadBadge, 4000);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();

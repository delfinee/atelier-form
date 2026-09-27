/**
 * Crafty (匠心小助手) - Artisan AI Concierge Client
 * Integrates with Atelier Form via /api/chat/ or direct Gemini API fallback.
 */

(function () {
  'use strict';

  // Read Atelier Form configuration from page
  let afConfig = {};
  try {
    const configEl = document.getElementById('af-config');
    if (configEl) afConfig = JSON.parse(configEl.textContent || '{}');
  } catch (e) {
    console.warn('Could not read af-config:', e);
  }

  // Determine language from page HTML lang attribute ('zh' or 'en')
  const pageLang = (document.documentElement.lang || 'en').toLowerCase().startsWith('zh') ? 'zh' : 'en';
  let currentLang = localStorage.getItem('crafty_lang') || pageLang;

  // Local conversation history
  let conversationHistory = [];
  let isThinking = false;

  // Bilingual strings dictionary
  const i18n = {
    zh: {
      botName: "Crafty · 匠心小助手",
      botSubtitle: "慢工坊在线手作顾问",
      statusServer: "Gemini 3.8 Flash (工坊已接入)",
      statusClient: "Gemini 3.8 Flash (自定义密钥)",
      statusDemo: "演示模式 (可接入 Gemini)",
      launcherText: "咨询小助手",
      inputPlaceholder: "询问材质、定制皮具、挑选礼物或养护...",
      sendBtnText: "发送",
      thinking: "Crafty 正在工作台前细细斟酌...",
      welcome: "您好！我是 Atelier Form 慢工坊的手作顾问 **Crafty** 🌿\n\n在这个流水线轰鸣的世界里，愿我们能重拾手心相传的温度。无论是寻找独一无二的心意礼物、定制刻字植鞣皮具，还是打理温润的木器与陶器，我都愿为您悉心解答。",
      quickChips: [
        { label: "🎁 选礼顾问", text: "我想选一份 80 元以内有心意的结婚礼物，希望带有专属定制感" },
        { label: "✂️ 定制皮具", text: "我想定制一款手工植鞣皮手账本，刻上名字首字母" },
        { label: "📦 追踪订单", text: "帮我查询手作订单 #AF-8921 的制作进度" },
        { label: "🏺 器物养护", text: "柴烧茶杯和胡桃木托盘日常要如何保养避免开裂？" }
      ],
      settingsTitle: "Gemini AI 智能设置",
      modelLabel: "模型版本：",
      apiKeyLabel: "客户端自定义 API 密钥 (可选)：",
      apiKeyHelp: "若工坊服务器已配置密钥，此项可留空；留空时默认使用工坊 API。",
      saveBtn: "保存设置",
      cancelBtn: "取消",
      clearBtn: "清除本地密钥",
      settingsSaved: "设置已保存！",
      orderFoundTitle: "订单进度追踪 · #AF-8921",
      customizerTitle: "定制工坊 · 植鞣皮手账配置",
    },
    en: {
      botName: "Crafty · Artisan Concierge",
      botSubtitle: "Slow-craft Studio Guide",
      statusServer: "Gemini 3.8 Flash (Studio Active)",
      statusClient: "Gemini 3.8 Flash (Custom Key)",
      statusDemo: "Demo Mode (Gemini Ready)",
      launcherText: "Chat with Crafty",
      inputPlaceholder: "Ask about makers, gifts, custom leather, or care...",
      sendBtnText: "Send",
      thinking: "Crafty is pondering at the artisan workbench...",
      welcome: "Hello there! I'm **Crafty**, your artisan concierge at Atelier Form 🌿\n\nIn a fast-paced, mass-produced world, welcome to the deliberate warmth of handcrafted goods. Whether you're searching for an unforgettable gift, commissioning bespoke leatherwork, or curious about caring for wood and clay, I'm here to guide you.",
      quickChips: [
        { label: "🎁 Gift Concierge", text: "I'm looking for a meaningful wedding gift under $80 with custom initials" },
        { label: "✂️ Bespoke Leather", text: "I'd like to customize a bespoke leather journal with embossed initials" },
        { label: "📦 Track Order", text: "Track progress for my handmade order #AF-8921" },
        { label: "🏺 Studio Care", text: "How should I care for wood-fired ceramics and olive wood boards?" }
      ],
      settingsTitle: "Gemini AI Settings",
      modelLabel: "Gemini Model:",
      apiKeyLabel: "Custom Client API Key (Optional):",
      apiKeyHelp: "If the studio server has a key configured, leave this blank.",
      saveBtn: "Save Settings",
      cancelBtn: "Cancel",
      clearBtn: "Clear Key",
      settingsSaved: "Settings saved!",
      orderFoundTitle: "Artisan Order Tracker · #AF-8921",
      customizerTitle: "Bespoke Leather Studio · Customizer",
    }
  };

  // Helper getters
  function getClientApiKey() {
    return (localStorage.getItem('crafty_gemini_api_key') || '').trim();
  }

  function getActiveModel() {
    const stored = localStorage.getItem('crafty_gemini_model');
    if (stored && (stored.includes('1.5') || stored.includes('2.0') || stored.includes('1.0'))) {
      localStorage.setItem('crafty_gemini_model', 'gemini-3.8-flash');
      return 'gemini-3.8-flash';
    }
    return stored || afConfig.chatbot?.defaultModel || 'gemini-3.8-flash';
  }

  // Light Markdown to HTML Converter
  function renderMarkdown(md) {
    if (!md) return '';
    let html = escapeHtml(md);

    // Bold
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    // Inline code
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    // Unordered lists
    html = html.replace(/(?:^|\n)[*-]\s+(.+)/g, '\n<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>');
    // Numbered lists
    html = html.replace(/(?:^|\n)\d+\.\s+(.+)/g, '\n<li>$1</li>');
    // Paragraphs & Linebreaks
    html = html.replace(/\n\n+/g, '</p><p>');
    html = html.replace(/\n/g, '<br/>');

    return `<p>${html}</p>`.replace(/<p><\/p>/g, '');
  }

  function escapeHtml(str) {
    return str.replace(/[&<>'"]/g, tag => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      "'": '&#39;',
      '"': '&quot;'
    }[tag] || tag));
  }

  // --- UI Controller ---
  function initCrafty() {
    const launcher = document.getElementById('crafty-launcher');
    const drawer = document.getElementById('crafty-drawer');
    const backdrop = document.getElementById('crafty-backdrop');
    const closeBtn = document.getElementById('crafty-close');
    const input = document.getElementById('crafty-input');
    const form = document.getElementById('crafty-form');
    const langBtn = document.getElementById('crafty-lang-toggle');
    const settingsBtn = document.getElementById('crafty-settings-toggle');
    const settingsModal = document.getElementById('crafty-settings-modal');
    const settingsClose = document.getElementById('crafty-settings-close');
    const settingsSave = document.getElementById('crafty-settings-save');
    const settingsClear = document.getElementById('crafty-settings-clear');

    if (!launcher || !drawer) return;

    // Toggle Drawer
    function openDrawer() {
      drawer.classList.add('is-open');
      if (backdrop) backdrop.classList.add('is-open');
      input?.focus();
      updateStatusBadge();
    }

    function closeDrawer() {
      drawer.classList.remove('is-open');
      if (backdrop) backdrop.classList.remove('is-open');
      if (settingsModal) settingsModal.hidden = true;
    }

    launcher.addEventListener('click', openDrawer);
    closeBtn?.addEventListener('click', closeDrawer);
    backdrop?.addEventListener('click', closeDrawer);

    // Global trigger buttons (e.g., from header)
    document.querySelectorAll('[data-crafty-open]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        openDrawer();
      });
    });

    // Close on Escape key
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && drawer.classList.contains('is-open')) {
        closeDrawer();
      }
    });

    // Language Toggle
    langBtn?.addEventListener('click', () => {
      currentLang = currentLang === 'zh' ? 'en' : 'zh';
      localStorage.setItem('crafty_lang', currentLang);
      renderStaticUI();
    });

    // Settings Modal
    settingsBtn?.addEventListener('click', () => {
      if (!settingsModal) return;
      document.getElementById('crafty-modal-key').value = getClientApiKey();
      document.getElementById('crafty-modal-model').value = getActiveModel();
      settingsModal.hidden = false;
    });

    settingsClose?.addEventListener('click', () => {
      if (settingsModal) settingsModal.hidden = true;
    });

    settingsSave?.addEventListener('click', () => {
      const key = document.getElementById('crafty-modal-key').value.trim();
      const model = document.getElementById('crafty-modal-model').value.trim();
      if (key) localStorage.setItem('crafty_gemini_api_key', key);
      else localStorage.removeItem('crafty_gemini_api_key');
      if (model) localStorage.setItem('crafty_gemini_model', model);
      if (settingsModal) settingsModal.hidden = true;
      updateStatusBadge();
    });

    settingsClear?.addEventListener('click', () => {
      localStorage.removeItem('crafty_gemini_api_key');
      document.getElementById('crafty-modal-key').value = '';
      updateStatusBadge();
    });

    // Form Submit
    form?.addEventListener('submit', (e) => {
      e.preventDefault();
      const text = input.value.trim();
      if (!text || isThinking) return;
      input.value = '';
      sendMessage(text);
    });

    // Auto-expand and Enter-to-send in textarea
    input?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        form?.dispatchEvent(new Event('submit'));
      }
    });

    // Initial render
    renderStaticUI();
    if (conversationHistory.length === 0) {
      appendBotMessage(i18n[currentLang].welcome);
    }
  }

  function updateStatusBadge() {
    const badge = document.getElementById('crafty-status');
    const dot = document.getElementById('crafty-status-dot');
    if (!badge || !dot) return;

    const clientKey = getClientApiKey();
    const hasServerKey = Boolean(afConfig.chatbot?.hasServerKey);

    if (clientKey) {
      badge.textContent = i18n[currentLang].statusClient;
      dot.style.background = '#10b981';
    } else if (hasServerKey) {
      badge.textContent = i18n[currentLang].statusServer;
      dot.style.background = '#10b981';
    } else {
      badge.textContent = i18n[currentLang].statusDemo;
      dot.style.background = '#f59e0b';
    }
  }

  function renderStaticUI() {
    const t = i18n[currentLang];
    const launcherText = document.getElementById('crafty-launcher-text');
    if (launcherText) launcherText.textContent = t.launcherText;

    const title = document.getElementById('crafty-title');
    if (title) title.textContent = t.botName;

    const subtitle = document.getElementById('crafty-subtitle');
    if (subtitle) subtitle.textContent = t.botSubtitle;

    const input = document.getElementById('crafty-input');
    if (input) input.placeholder = t.inputPlaceholder;

    const sendBtn = document.getElementById('crafty-send-btn');
    if (sendBtn) sendBtn.title = t.sendBtnText;

    const langBtn = document.getElementById('crafty-lang-toggle');
    if (langBtn) langBtn.textContent = currentLang === 'zh' ? 'EN' : '中文';

    // Render quick chips
    const chipsBar = document.getElementById('crafty-chips');
    if (chipsBar) {
      chipsBar.innerHTML = '';
      t.quickChips.forEach(chip => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'crafty-chip';
        btn.textContent = chip.label;
        btn.addEventListener('click', () => sendMessage(chip.text));
        chipsBar.appendChild(btn);
      });
    }

    updateStatusBadge();
  }

  function appendUserMessage(text) {
    const container = document.getElementById('crafty-messages');
    if (!container) return;

    const msg = document.createElement('div');
    msg.className = 'crafty-msg crafty-msg--user';
    msg.innerHTML = `<div class="crafty-bubble">${renderMarkdown(text)}</div>`;
    container.appendChild(msg);
    container.scrollTop = container.scrollHeight;

    conversationHistory.push({ role: 'user', parts: [{ text }] });
  }

  function appendBotMessage(text, extraHtml = '') {
    const container = document.getElementById('crafty-messages');
    if (!container) return;

    const msg = document.createElement('div');
    msg.className = 'crafty-msg crafty-msg--bot';
    msg.innerHTML = `<div class="crafty-bubble">${renderMarkdown(text)}${extraHtml}</div>`;
    container.appendChild(msg);
    container.scrollTop = container.scrollHeight;

    conversationHistory.push({ role: 'model', parts: [{ text }] });
  }

  function showThinking() {
    const container = document.getElementById('crafty-messages');
    if (!container) return;

    const el = document.createElement('div');
    el.id = 'crafty-thinking-el';
    el.className = 'crafty-thinking';
    el.innerHTML = `<span>${i18n[currentLang].thinking}</span><div class="crafty-dots"><span></span><span></span></div>`;
    container.appendChild(el);
    container.scrollTop = container.scrollHeight;
    isThinking = true;
  }

  function hideThinking() {
    const el = document.getElementById('crafty-thinking-el');
    if (el) el.remove();
    isThinking = false;
  }

  // --- Send Message & Router ---
  async function sendMessage(text) {
    appendUserMessage(text);
    showThinking();

    // Check for Scenario match (Order tracker, Leather customizer)
    if (text.includes('8921') || text.toLowerCase().includes('af-8921')) {
      setTimeout(() => {
        hideThinking();
        respondOrderTracking();
      }, 700);
      return;
    }

    if (text.includes('定制') || text.toLowerCase().includes('bespoke') || text.toLowerCase().includes('journal')) {
      setTimeout(() => {
        hideThinking();
        respondBespokeCustomizer();
      }, 750);
      return;
    }

    // Attempt 1: Call Django backend /api/chat/
    const apiEndpoint = afConfig.urls?.chatApi || '/api/chat/';
    const clientKey = getClientApiKey();
    const model = getActiveModel();

    try {
      const response = await fetch(apiEndpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': afConfig.csrf || '',
        },
        body: JSON.stringify({
          message: text,
          history: conversationHistory.slice(-6),
          model: model,
          apiKey: clientKey,
        }),
      });

      const data = await response.json();
      if (response.ok && data.status === 'ok' && data.reply) {
        hideThinking();
        appendBotMessage(data.reply);
        return;
      }

      // If backend reports no server key and client has key, try direct Google API
      if (data.fallback && clientKey) {
        await callDirectGemini(text, clientKey, model);
        return;
      }
    } catch (err) {
      console.warn('Backend chat API failed, trying client fallback:', err);
      if (clientKey) {
        await callDirectGemini(text, clientKey, model);
        return;
      }
    }

    // Attempt 2: Built-in Slow-craft Artisan Response Engine
    setTimeout(() => {
      hideThinking();
      respondArtisanDemo(text);
    }, 800);
  }

  // Direct Google Gemini API caller (client-side fallback)
  async function callDirectGemini(userPrompt, apiKey, model) {
    const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`;
    const systemPrompt = `
You are "Crafty" (匠心小助手), the warm, poetic, and knowledgeable artisan e-commerce concierge for Atelier Form (an independent handmade crafts and bespoke studio).
- Voice: sensory, passionate, honest about slow craft timelines, unhurried makers.
- Tone: warm, respectful, poetic yet practical.
- Language: Reply in ${currentLang === 'zh' ? 'Chinese' : 'English'}.
- Length: 120-220 words with clear bullet lists and gentle emojis.
`;

    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          systemInstruction: { parts: [{ text: systemPrompt }] },
          contents: conversationHistory.slice(-6).map(h => ({
            role: h.role === 'model' ? 'model' : 'user',
            parts: [{ text: h.parts[0].text }],
          })),
          generationConfig: { temperature: 0.7, maxOutputTokens: 900 }
        })
      });

      hideThinking();
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error?.message || `HTTP ${res.status}`);
      }
      const data = await res.json();
      const reply = data.candidates?.[0]?.content?.parts?.[0]?.text;
      if (reply) {
        appendBotMessage(reply);
      } else {
        respondArtisanDemo(userPrompt);
      }
    } catch (e) {
      hideThinking();
      appendBotMessage(`⚠️ Gemini API: ${e.message}\n\n*Switching to studio demo guide...*`);
      respondArtisanDemo(userPrompt);
    }
  }

  // Scenario 1: Order Tracker #AF-8921
  function respondOrderTracking() {
    const isZh = currentLang === 'zh';
    const reply = isZh
      ? "为您查询到手作订单 **#AF-8921** 的当前进度。这件双耳柴烧陶盘正在徐安英老师的景德镇柴窑中静待出窑，预计 3 个工作日内完成质检与棉麻包覆包装。"
      : "Found progress details for bespoke order **#AF-8921**. This wood-fired ceramic platter is currently cooling in Master Xu Anying's reduction kiln in Jingdezhen, scheduled for final inspection in 3 business days.";

    const card = `
      <div class="crafty-card">
        <h4>📦 ${isZh ? '订单当前制作状态' : 'Studio Production Status'}</h4>
        <div class="crafty-card-row"><span>${isZh ? '订单号' : 'Order ID'}</span><strong>#AF-8921</strong></div>
        <div class="crafty-card-row"><span>${isZh ? '手作匠人' : 'Master Maker'}</span><span>徐安英 (Xu Anying)</span></div>
        <div class="crafty-card-row"><span>${isZh ? '定制器物' : 'Item'}</span><span>柴烧宽口陶盘 (Wood-fired Platter)</span></div>
        <div class="crafty-timeline">
          <div class="crafty-step crafty-step--done"><div class="crafty-step-dot">✓</div><span>${isZh ? '拉胚成型 & 阴干修胚 (已完成)' : 'Hand-thrown & Trimmed (Done)'}</span></div>
          <div class="crafty-step crafty-step--done"><div class="crafty-step-dot">✓</div><span>${isZh ? '素烧与天然植物落灰釉 (已完成)' : 'Natural Ash Glazing (Done)'}</span></div>
          <div class="crafty-step crafty-step--active"><div class="crafty-step-dot">3</div><span>${isZh ? '松木柴窑 1,300°C 还原烧结 (进行中)' : 'Wood-kiln 1,300°C Firing (Current)'}</span></div>
          <div class="crafty-step crafty-step--pending"><div class="crafty-step-dot">4</div><span>${isZh ? '缓慢冷却出窑 & 木箱加固包装' : 'Studio Cooling & Packing'}</span></div>
        </div>
      </div>
    `;
    appendBotMessage(reply, card);
  }

  // Scenario 2: Bespoke Leather Customizer
  function respondBespokeCustomizer() {
    const isZh = currentLang === 'zh';
    const reply = isZh
      ? "很荣幸为您推荐 Atelier Form 的植鞣皮手账本定制方案！每件手账均精选意大利托斯卡纳植鞣牛皮，由手作匠人以双手马鞍针法缝制，随岁月使用会渐变出温润的蜜糖色泽。"
      : "Delighted to guide you through commissioning a bespoke leather journal! Crafted from certified Tuscan vegetable-tanned leather and saddle-stitched by hand, it develops a deep honey-amber patina through your daily journeys.";

    const card = `
      <div class="crafty-card">
        <h4>✂️ ${isZh ? '专属皮具配置卡' : 'Bespoke Customizer Specs'}</h4>
        <div class="crafty-card-row"><span>${isZh ? '皮料产地' : 'Leather Origin'}</span><span>意大利托斯卡纳植鞣皮 (Badalassi Carlo)</span></div>
        <div class="crafty-card-row"><span>${isZh ? '缝线工艺' : 'Stitching'}</span><span>双针马鞍缝线 · 天然亚麻蜡线</span></div>
        <div class="crafty-card-row"><span>${isZh ? '专属印记' : 'Monogram'}</span><span>黄铜热压印 (首字母 2-4 位免收工本费)</span></div>
        <div class="crafty-card-row"><span>${isZh ? '制作周期' : 'Lead Time'}</span><span>7-10 个工作日慢工细作</span></div>
      </div>
    `;
    appendBotMessage(reply, card);
  }

  // Built-in Domain Knowledge Fallback
  function respondArtisanDemo(prompt) {
    const isZh = currentLang === 'zh';
    const p = prompt.toLowerCase();

    if (p.includes('礼') || p.includes('gift') || p.includes('wedding')) {
      const reply = isZh
        ? "为婚礼或乔迁准备心意礼物，我特别推荐以下两件富有手温与寓意的器物：\n\n1. **双耳柴烧手握对杯** (¥76) — 经五天四夜松木落灰，每只杯身皆有独特的火痕与流釉，象征彼此独一无二的陪伴。\n2. **托斯卡纳植鞣皮手工托盘** (¥88) — 可免费黄铜压印新人姓名缩写与纪念日期。\n\n需要我为您搭配手作和纸礼盒与手写致意卡吗？"
        : "For a meaningful wedding or housewarming gift, I wholeheartedly recommend:\n\n1. **Wood-fired Stoneware Cup Pair** ($76) — Kissed by 5 days of natural pine-ash flames, symbolizing an unrepeatable bond.\n2. **Hand-stitched Vegetable-Tanned Tray** ($88) — Complimentary brass hot-stamping with couple initials and wedding date.\n\nWould you like me to pair this with handmade mulberry gift wrapping?";
      appendBotMessage(reply);
      return;
    }

    if (p.includes('养护') || p.includes('care') || p.includes('保养') || p.includes('洗')) {
      const reply = isZh
        ? "慢工器物的日常打理其实非常简单，善待它们就是最好的陪伴：\n\n- 🏺 **陶器 & 柴烧**：初次使用建议淘米水温和浸泡 15 分钟闭合微孔；勿用洗碗机与钢丝球，清洗后在阴凉通风处自然晾干。\n- 🪵 **实木 & 橄榄木**：表面渐现哑光感时，取少许食品级核桃油或天然蜂蜡均匀薄涂，静置吸收一晚即可恢复油脂温润。\n- 🍃 **亚麻织物**：温水轻柔手洗，平铺阴干，其自然的微皱正是天然纤维的从容质感。"
        : "Caring for slow-crafted objects is an intimate ritual:\n\n- 🏺 **Handmade Ceramics**: Gentle hand-wash with warm water. Avoid abrasive scourers or harsh dishwashers; air-dry in open circulation.\n- 🪵 **Olive & Walnut Wood**: When the surface looks matte, massage lightly with food-grade walnut oil or natural beeswax, allowing overnight absorption.\n- 🍃 **Natural Linen**: Wash gently in cold or lukewarm water, dry flat; natural slub and gentle creases celebrate the fabric's soul.";
      appendBotMessage(reply);
      return;
    }

    // Default warm artisan reply
    const reply = isZh
      ? `收到您的心意：“${escapeHtml(prompt)}”。在工坊里，我们深信每件手作器物都蕴含着匠人指尖的体温与时光的印记。\n\n无论您想了解哪位手作匠人的工坊故事、挑选一件打动人心的礼物，或是了解定制周期，我随时在工作台前倾听与协助。`
      : `Thank you for sharing your thoughts: "${escapeHtml(prompt)}". Here at Atelier Form, we believe every piece carries the maker's heartbeat and quiet patience.\n\nWhether you wish to learn about our makers' techniques, select an unforgettable gift, or commission custom leatherwork, I am right here at the bench to assist you.`;
    appendBotMessage(reply);
  }

  // Initialize once DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initCrafty);
  } else {
    initCrafty();
  }
})();

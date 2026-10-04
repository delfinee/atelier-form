# Bohan Chatbot / Buyer–Seller Messaging Review Handover

**Initial review date:** 3 October 2026  
**GitHub recheck:** 4 October 2026 — branch head unchanged  
**Reviewer context:** Integration / QA review for buyer–seller communication work  
**Repository:** `delfinee/dip-new-repo-test`  
**Reviewed branch:** `feature/bohan-chatbot`  
**Branch head:** `ab1e7e61e9068fa477e0ffb0e557679f5e5505cd`  
**Latest reviewed commit:** `feat(chatbot): integrate Shopee-style Buyer-to-Seller chat widget with auto-reply badges and emoji picker`  
**Current main at review time:** `6c98cfb2e2f397caaed82ff660aee3d241edd276`  
**Merge base:** `4cec2e593506a4c154f1416254229e97d78c3413`

Repository link: <https://github.com/delfinee/dip-new-repo-test>  
Branch link: <https://github.com/delfinee/dip-new-repo-test/tree/feature/bohan-chatbot>

---

## 1. Executive summary

The branch has a substantial and visually polished chat **prototype**, but it does **not yet implement real buyer–seller communication**.

The intended project feature is buyer–seller threaded messaging, linked to products/orders, with a conversation page and simple polling/refresh. The current branch instead stores messages in browser `localStorage`, generates canned replies in JavaScript, simulates a human seller, uses hard-coded seller/product/order details, and includes a Gemini API endpoint that the current browser code no longer calls.

### Merge readiness

**Not ready to merge yet as functional buyer–seller messaging.**

The existing chat UI is a strong reusable prototype. Before merge, the branch should be synchronized with current `main` and the core communication path should be made functional: persistent server-side messages, seller access/replies, ownership permissions and basic polling/refresh. UI, AI and quality-of-life polish can be handled in a later editing round.

This review is therefore split into two levels:

- **Round 1 — required before merge:** fixes needed so `main` does not receive a misleading or non-functional communication feature.
- **Round 2 — follow-up after core integration:** improvements that can safely be polished after the real buyer–seller flow has merged.

### Most important findings

| Round | Finding | Why it matters |
|---|---|---|
| **Round 1** | Messages are browser-local only | The seller never receives the buyer's message; messages exist only in that browser's `localStorage`. |
| **Round 1** | UI can present simulated replies/order/product facts as a human seller | A buyer can be shown invented fulfilment status, seller availability, warranties, lead times and product claims. |
| **Round 1** | Branch is **7 commits ahead / 22 commits behind** `main` | It must be brought up to date carefully; current `main` added recommendation integration in shared files that the branch version does not contain. |
| **Round 1** | No buyer/seller authorization model | A real messaging backend must ensure buyers and sellers can only access their own permitted threads. |
| **Round 1** | Drawer send button sits outside the `<form>` | Clicking the visible send button does not submit the drawer form in normal HTML semantics. |
| **Round 1** | Gemini test / public endpoint need a merge-safe decision | Either mock/secure the AI path or remove/defer it so `main` does not gain flaky tests or an exposed quota-consuming endpoint. |
| **Round 2** | Current JavaScript does not call `/api/chat/` | If AI is retained later, the Gemini service and visible UI should be reconnected deliberately. |
| **Round 2** | Accessibility, richer unread state, attachments and translation cleanup | These improve the feature but do not need to block the first functional merge. |

---

## 2. Intended scope used for this review

The project planning documents describe the later messaging scope as:

- buyer–seller **threaded messaging**;
- a **conversation page**;
- **product/order-linked messages**;
- **simple polling or refresh** for new messages;
- an eventual module such as `backend/messaging/` plus message templates;
- project tracker default: **ordinary HTTP polling** rather than WebSockets for the student-scale implementation.

The scope was later reassigned from Delfine to Bohan. This review therefore evaluates the branch primarily as a buyer–seller communication feature, not merely as an AI concierge demo.

---

## 3. Branch state and integration risk

GitHub comparison at review time:

```text
feature/bohan-chatbot vs main
status: diverged
ahead: 7 commits
behind: 22 commits
merge base: 4cec2e593506a4c154f1416254229e97d78c3413
branch head: ab1e7e61e9068fa477e0ffb0e557679f5e5505cd
main head: 6c98cfb2e2f397caaed82ff660aee3d241edd276
```

The branch changes 16 files and adds roughly 2.7k lines, mostly chat CSS/JS and templates.

### Shared-file conflict to handle explicitly

`main` has changed two files that Bohan's branch also changes:

1. `backend/config/settings.py`
2. `frontend/templates/frontend/base.html`

Current `main` now includes the recommendation feature integration:

- `"recommendations"` in `INSTALLED_APPS`;
- `{% load ... recommendations %}` in `base.html`;
- `{% recommendation_block 4 %}` inside `<main>`.

Bohan's branch was created before those updates and its versions do not contain them. During rebase/merge, **do not resolve conflicts by taking the chatbot branch wholesale**, or recommendation integration can be accidentally removed.

### Recommended integration order

1. Rebase or merge current `main` into `feature/bohan-chatbot`.
2. Preserve recommendation app/template integration.
3. Redesign messaging backend and wire the existing chat UI to it.
4. Run chat-specific tests.
5. Run the full regression suite.
6. Only then open/merge a PR.

---

## 4. What the branch currently implements

### New/changed pieces

- `frontend/chatbot_service.py`
  - Gemini `generateContent` HTTP client.
  - Artisan concierge system prompt.
  - server API key plus optional client-supplied key.

- `frontend/static/frontend/js/chatbot.js`
  - Shopee-style drawer interactions.
  - local browser message history.
  - emoji picker.
  - quick product/order/customisation buttons.
  - canned buyer/seller/auto-reply flows.

- `frontend/static/frontend/css/chatbot.css`
  - large dedicated chat UI stylesheet.

- `frontend/templates/frontend/chat.html`
  - full-page Crafty concierge experience.

- `frontend/templates/frontend/partials/chatbot.html`
  - floating launcher and drawer.

- `frontend/templates/frontend/partials/crafty_settings_modal.html`
  - model/API-key settings UI.

- `frontend/views.py`
  - `/chat/`, `/concierge/`, `/api/chat/`.

- `frontend/context_processors.py`
  - chat URLs and Gemini settings added to `af_config`.

- `frontend/tests.py`
  - rendering/duplicate-ID checks and one chat API test.

### Useful work worth retaining

The branch is not a throwaway. Several pieces can be reused after the architecture is corrected:

- the drawer/full-page visual design;
- responsive chat styling;
- emoji picker and quick-action UX patterns;
- HTML escaping in rendered user message text;
- separation of the Gemini HTTP client into `chatbot_service.py`;
- server-side environment configuration for a Gemini key;
- render tests that check for duplicate IDs;
- bilingual copy ideas, after moving them into the project's proper translation flow.

---

## 5. Detailed review findings

## 5.1 ROUND 1 / MERGE REQUIRED — Messages are currently browser-local only

**Evidence:** `frontend/static/frontend/js/chatbot.js`

`loadMessages()` and `saveMessages()` use:

```text
localStorage['crafty_shopee_buyer_messages']
```

There is no conversation/message database model, migration, serializer, message service, polling endpoint, seller inbox, or server-side send/receive flow in the branch.

### Current behaviour

Buyer types a message → JavaScript writes it to that browser's `localStorage` → JavaScript fabricates a response locally.

### Consequences

- seller never receives it;
- buyer cannot see it on another device/browser;
- signing out does not create a real account boundary;
- another account using the same browser can inherit the same local chat history;
- there is no server audit trail or conversation ownership;
- no unread state or real delivery/read status exists.

### Required before merge

Treat the existing browser flow as the frontend prototype, then add a real messaging domain, ideally `backend/messaging/`, with persistent `Conversation` and `ConversationMessage` records plus buyer/seller permissions and polling endpoints. The visual drawer does not need to be rebuilt; the main change is replacing local-only persistence with server-backed send/read operations.

---

## 5.2 ROUND 1 / MERGE REQUIRED — Simulated seller replies must not appear as real seller facts

**Evidence:** `frontend/templates/frontend/partials/chatbot.html` and `frontend/static/frontend/js/chatbot.js`

Hard-coded examples include:

- `Lin Woodcraft Flagship Store`;
- `Active 47 minutes ago`;
- `FAS Black Walnut Dovetail Keepsake Box`;
- fixed `$58.00 / ¥388` pricing;
- fake `100% authentic` claims;
- fixed production lead times;
- `lifetime joinery warranty`;
- fixed return policies;
- fake courier/dispatch promises;
- fixed order `#AF-8921`.

`connectLiveSeller()` waits briefly and then adds a message marked as a **human seller** even though it is generated entirely in browser JavaScript.

`toolBtnOrder` produces a fabricated production status for `#AF-8921` without querying `Order`, `SellerFulfillment`, or the authenticated buyer.

### Why this must be fixed before merge

This is more than placeholder styling. The interface presents invented operational facts as if they came from the real seller.

### Required fix

- Never label generated/demo text as a real human seller.
- Read seller name from `Product.maker` / `Maker.owner`.
- Read product title/price from the actual selected `Product`.
- Read order/fulfilment status only from an authenticated order that belongs to the buyer.
- If AI is retained, label it clearly as an assistant and prevent it from inventing order state, stock, warranties, delivery dates or seller commitments.

---

## 5.3 ROUND 1 / MERGE REQUIRED — Missing seller side

The feature has a buyer-facing drawer but no real seller messaging workspace.

A complete communication feature needs at minimum:

- seller conversation list;
- thread view;
- ability to reply;
- maker ownership scoping;
- unread state or clear latest-message ordering;
- polling/refresh for new buyer messages.

The repository already links seller accounts through `Maker.owner`. That relationship should be used for authorization.

---

## 5.4 ROUND 1 / MERGE REQUIRED — No authorization or horizontal-access protection

There are no message records to protect yet, but the design needs permissions before persistence is added.

The current marketplace already has the relevant identities:

```text
User.is_seller
Maker.owner -> User
Product.maker -> Maker
Order.user -> buyer
OrderItem.maker -> Maker
SellerFulfillment(order, maker)
```

### Required rules

A buyer may read/write only conversations where `conversation.buyer == request.user`.

A seller may read/write only conversations where:

```text
conversation.maker.owner == request.user
```

If a conversation is linked to an order, the server must also verify:

```text
order.user == buyer
and the order contains at least one OrderItem for conversation.maker
```

Do not trust buyer-submitted maker/order IDs without these checks.

---

## 5.5 ROUND 1 IF AI REMAINS — Public Gemini quota/cost endpoint

**Evidence:** `frontend/views.py -> chat_api`

The endpoint is:

- `@csrf_exempt`;
- not login protected;
- not DRF-throttled;
- not otherwise rate-limited;
- capable of using the server's Gemini API key.

If `GEMINI_API_KEY` is configured in production, any caller who can reach `/api/chat/` can make the server spend Gemini quota.

### Required fix if AI remains

- Require an authenticated session, or deliberately define anonymous usage with strict throttling.
- Add a dedicated rate limit.
- Bound message length and history size.
- Validate history structure.
- Whitelist permitted model IDs server-side.
- Avoid `@csrf_exempt` for the same-origin browser flow; send the existing CSRF token.
- Record safe usage metrics without logging secrets or full private conversations.

---

## 5.6 ROUND 1 IF AI REMAINS — Client API key handling should be removed

**Evidence:** settings modal + `chatbot.js` + `chat_api`

The UI stores a user-supplied Gemini key in browser `localStorage` under:

```text
crafty_gemini_api_key
```

and the server endpoint accepts `apiKey` as an override.

### Problems

- long-lived secret is stored in browser JavaScript-accessible storage;
- any XSS on the origin could read it;
- user secret is sent through the Atelier Form server;
- the feature adds security/privacy complexity unrelated to buyer–seller messaging;
- in the latest JS flow the key is effectively unused anyway because messages are answered locally.

### Recommended fix

Remove custom client API keys entirely. If AI is kept, use only a server-controlled key with authentication, quotas and clear feature boundaries.

---

## 5.7 ROUND 2 / AI FOLLOW-UP — The Gemini API is disconnected from the latest client

`frontend/context_processors.py` exposes `chatApi`, server-key availability and default model in `af_config`.

`frontend/chatbot_service.py` implements the Gemini call.

`frontend/views.py` exposes `/api/chat/`.

But the current `chatbot.js` no longer reads `af_config` or performs a `fetch()` to `/api/chat/`. Normal message handling ends in `handleIncomingBuyerMessage()`, which returns hard-coded JavaScript responses.

### Consequence

The project currently has two different chatbot implementations:

1. an unused server/Gemini path; and
2. the visible local canned-response path.

Choose one clear purpose. For the assigned buyer–seller feature, the visible client should primarily talk to the messaging backend, not to Gemini.

---

## 5.8 ROUND 1 / MERGE REQUIRED — Drawer send button is outside its form

**Evidence:** `frontend/templates/frontend/partials/chatbot.html`

The drawer closes the `<form>` immediately after the text `<input>`, then renders the visible submit button afterward:

```html
<form id="crafty-form"> ... </form>
...
<button type="submit" id="crafty-send-btn">...</button>
```

A submit button outside the form and without `form="crafty-form"` does not submit that form.

### User-visible effect

- pressing Enter in the input can submit;
- clicking the visible send arrow does not reliably invoke the form submit handler.

### Fix

Place the button inside the form, or add `form="crafty-form"` and test click submission explicitly.

---

## 5.9 ROUND 1 / MERGE REQUIRED — Current API test is broken/flaky by design

**Evidence:** `frontend/tests.py -> CraftyChatbotTests.test_chat_api_endpoint`

The test posts to the real `/api/chat/` endpoint and asserts:

```python
self.assertEqual(data.get("status"), "ok")
```

But the default `.env.example` has:

```text
GEMINI_API_KEY=
```

and `call_gemini()` returns `status="error"` when no key is configured.

Therefore a clean test environment cannot satisfy the assertion.

If a real key is injected, the test becomes an external network integration test that consumes quota and can fail due to network/provider conditions.

### Fix

Unit-test the view by mocking `frontend.chatbot_service.call_gemini`.

Separately, add an optional provider smoke test that is explicitly skipped unless a test API key is configured.

---

## 5.10 ROUND 2, OR ROUND 1 IF AI REMAINS — Request payload validation is insufficient

`chat_api` checks only that `message` is non-empty.

`call_gemini()` assumes `history` is iterable and that every item has `.get()`.

Examples such as:

```json
{"message":"hi", "history":"not-a-list"}
```

can cause an unhandled exception rather than a clean 400 response.

There is also no limit on:

- message size;
- number of history turns;
- individual history content size;
- total request size at application level.

### Fix

Use a Django form or DRF serializer to validate shape, allowed roles and length caps before calling the provider.

---

## 5.11 ROUND 2 — Hard-coded bilingual JavaScript conflicts with the project localisation approach

`chatbot.js` contains a large hand-maintained `i18n = { zh: ..., en: ... }` dictionary and keeps a separate language value in `localStorage`.

This duplicates Django's translation system and can drift from the page's active locale. Current project localisation guidance is to use Django translation/catalogue flow rather than create a second independent English/Chinese source in JavaScript.

### Fix

Prefer either:

- translated strings emitted into `af_config` / `json_script`; or
- translated HTML templates and small data attributes for JS labels.

Use `document.documentElement.lang` as the source of truth rather than a separate chatbot language preference unless the product explicitly requires an independent chat language.

---

## 5.12 ROUND 2 — Full-page AI concierge and seller chat are conceptually inconsistent

`chat.html` says:

- `Artisan AI Concierge`;
- `Artisan Studio Assistant`;
- `Crafty · Artisan Concierge`;

while the drawer says:

- `Chat with Seller`;
- `Seller Support (Human)`;
- seller-specific store identity.

This creates an unclear product promise: is Crafty an AI assistant, an automated seller responder, or a direct human seller channel?

### Recommendation

Separate the concepts:

- **Buyer–Seller Messages** — persistent real communication.
- Optional **Crafty AI Assistant** — clearly labelled, separate entry point, never impersonates a seller.

If there is only time for one, complete the real buyer–seller messaging requirement first.

---

## 5.13 ROUND 2 — Product and order tools are demo-only

Current buttons simulate features rather than executing platform actions:

- photo tool asks for a filename/description via `prompt()`;
- product tool inserts a fixed walnut product card;
- `Buy Now` triggers an `alert()`;
- custom brief inserts a fixed example;
- order tool queries no order and returns a fake result.

These should be presented as prototype-only until connected to real product/order data.

---

## 5.14 ROUND 1 — Conversation state can leak across account changes on a shared browser

Because `crafty_shopee_buyer_messages` is a single global `localStorage` key, it is not scoped by user, maker or conversation.

Even before server persistence is completed, this is unsafe for a login-based marketplace demo on a shared machine.

The real fix is server-side account-scoped messaging, not merely changing the key name.

---

## 5.15 ROUND 2 — Accessibility and interaction completeness

The drawer has good use of several labels, but still needs:

- focus trapping while `aria-modal="true"` is active;
- returning focus to the launcher after close;
- `aria-live` or equivalent announcement for incoming messages;
- keyboard testing for tool tray and emoji picker;
- explicit labels for icon-only buttons that currently rely mainly on `title`;
- reliable send-button keyboard/mouse behaviour.

---

## 5.16 ROUND 2 — Gemini 3.8 API configuration should be updated to current guidance

`chatbot_service.py` sends:

```python
"generationConfig": {
    "temperature": 0.7,
    "maxOutputTokens": 2500,
}
```

Google's current Gemini 3.8 Flash migration guidance says deprecated sampling parameters such as `temperature`, `top_p` and `top_k` should be removed when migrating to 3.8 Flash.

Reference: <https://ai.google.dev/gemini-api/docs/latest-model>

This is secondary to the messaging architecture issues, but should be cleaned up if Gemini remains.

---

## 6. Recommended target architecture

Keep this small. The project does not need WebSockets for the DIP demo.

### 6.1 Data model

Suggested app:

```text
backend/messaging/
    models.py
    serializers.py
    api.py
    urls.py
    services.py
    tests.py
    migrations/
```

Suggested model shape:

```python
class Conversation(UUIDModel, TimeStampedModel):
    buyer = models.ForeignKey(User, ...)
    maker = models.ForeignKey(Maker, ...)
    product = models.ForeignKey(Product, null=True, blank=True, ...)
    order = models.ForeignKey(Order, null=True, blank=True, ...)
    is_closed = models.BooleanField(default=False)


class ConversationMessage(UUIDModel, TimeStampedModel):
    conversation = models.ForeignKey(Conversation, related_name="messages", ...)
    sender = models.ForeignKey(User, ...)
    body = models.TextField()
    read_at = models.DateTimeField(null=True, blank=True)
```

Do not store a free-form seller ID supplied by the browser. Derive seller authorization from `conversation.maker.owner`.

### 6.2 Conversation creation rules

From a product page:

```text
buyer + product.maker + product
```

From an order page:

```text
buyer + selected maker + order
```

For an order-linked conversation, the server must prove the order belongs to the buyer and contains an order item for that maker.

### 6.3 API shape

A simple version is enough:

```text
GET  /api/conversations/
POST /api/conversations/
GET  /api/conversations/<uuid>/messages/?after=<cursor>
POST /api/conversations/<uuid>/messages/
```

The polling request can run every 3–5 seconds while the thread is open, or use a manual refresh button if the team wants the simplest acceptable implementation.

### 6.4 Seller UI

Suggested routes:

```text
/seller/messages/
/seller/messages/<conversation_uuid>/
```

Seller list should show:

- buyer display name;
- product/order context;
- latest message preview;
- latest timestamp;
- unread indicator.

### 6.5 Buyer UI

Reuse Bohan's drawer styling, but populate it from real API data.

On a product page, open a thread scoped to that product/maker.

On an order page, allow the buyer to contact the seller responsible for the selected order item / seller fulfilment.

---

## 7. AI assistant: recommended boundary

The AI concierge is optional relative to the direct messaging requirement.

If the team keeps it, use a strict boundary:

### Allowed AI tasks

- explain general care instructions from known catalogue content;
- help a user phrase a question to the seller;
- summarize a conversation for the current authenticated participant;
- suggest which product details to ask about.

### AI must not invent

- order status;
- payment status;
- stock availability;
- seller online status;
- shipping date;
- warranty policy;
- refunds/returns eligibility;
- seller commitments or quotes.

Those values must come from database-backed platform state or a human seller.

The UI should say **AI Assistant** for AI output and **Seller** only for messages actually written by the seller account.

---

## 8. Round 1 acceptance criteria — required before merge

The goal of Round 1 is **not** to finish every possible chat enhancement. It is to make the existing prototype a real, permission-safe buyer–seller communication feature and integrate it cleanly with current `main`.

### Core communication

- [ ] Authenticated buyer can start/open a real conversation with the maker of a product.
- [ ] Buyer message is saved in PostgreSQL rather than only `localStorage`.
- [ ] Correct seller can see the buyer message from a seller-facing page/API.
- [ ] Seller can reply and buyer receives the reply after refresh/polling.
- [ ] Conversation persists across logout/login and different browser sessions.
- [ ] Product context uses actual `Product` / `Maker` data.
- [ ] Order-linked messaging, if included in Round 1, uses an actual order owned by the buyer and only a maker present in that order.
- [ ] No generated/demo reply is labelled as a human seller.
- [ ] Visible send button works by mouse and keyboard.

### Permissions / privacy

- [ ] Buyer cannot read or write another buyer's thread.
- [ ] Seller cannot read or write another maker's thread.
- [ ] Buyer cannot forge seller/maker/order linkage.
- [ ] Message body has a sensible maximum length.
- [ ] Session-authenticated POSTs use normal CSRF protection.
- [ ] The global cross-account `localStorage` chat history is removed from the production messaging path.

### Integration / tests

- [ ] Branch is rebased/merged with current `main`.
- [ ] `recommendations` remains in `INSTALLED_APPS`.
- [ ] Recommendation template load/block remains in `base.html`.
- [ ] `test_chat_api_endpoint` is mocked, removed, or otherwise made deterministic.
- [ ] If the Gemini endpoint remains enabled, it is authenticated/rate-limited and does not accept browser-stored client secrets.
- [ ] Relevant messaging tests pass.
- [ ] Full regression suite passes before merge.

### Round 2 — follow-up improvements after the core merge

These are useful improvements, but they do **not** all need to block the first functional merge:

- richer unread/read indicators and conversation sorting;
- accessibility/focus trapping and live-region announcements;
- attachments/photo upload and richer product cards;
- translation cleanup and moving JS strings into Django's localisation flow;
- clearer separation or refinement of the optional Crafty AI assistant;
- stronger AI request validation, usage metrics and provider error UX;
- advanced seller presence/read receipts;
- WebSockets, only if the team later decides polling is insufficient.

---

## 9. Recommended test plan

## 9.1 Model/service tests

- create conversation buyer + maker;
- optional product belongs to selected maker;
- optional order belongs to buyer;
- order includes selected maker;
- message body validation;
- message chronological ordering.

## 9.2 Buyer permission tests

- buyer can list own conversations;
- buyer cannot fetch another buyer's conversation;
- buyer can send to own conversation;
- logged-out user rejected;
- forged conversation UUID rejected.

## 9.3 Seller permission tests

- seller sees only conversations for `maker_profile` they own;
- seller cannot read another seller's conversation;
- seller cannot reply as a different maker;
- non-seller user rejected from seller inbox/API.

## 9.4 Order/product linkage tests

- product thread uses actual maker;
- valid buyer order + maker accepted;
- another buyer's order rejected;
- maker absent from the order rejected;
- deleted/inactive product handling defined.

## 9.5 Polling tests

- initial GET returns thread messages;
- `after` cursor returns only newer messages;
- no duplicate messages across repeated polls;
- deterministic ordering for same/near timestamps.

## 9.6 Frontend tests

- launcher opens drawer;
- send button click submits;
- Enter submits once;
- buyer message renders once after server success;
- server failure restores/enables retry state;
- incoming seller reply appears after poll;
- HTML/script text is rendered as text, not executed;
- current product/seller names appear instead of fixed demo names;
- logout/login with another user does not expose previous user's thread.

## 9.7 AI tests, only if AI remains

Mock the provider for normal unit tests:

- success response;
- timeout;
- provider 4xx/5xx;
- malformed/blocked provider response;
- message/history validation;
- rate limit;
- no provider call when not needed.

Do **not** make the default Django unit suite depend on a real Gemini key or public network access.

---

## 10. Suggested implementation sequence for Bohan

### Round 1 — complete before merge

#### Step 1 — Synchronize branch

1. Bring `feature/bohan-chatbot` up to date with current `main`.
2. Resolve `settings.py` and `base.html` while preserving recommendation integration.
3. Run the existing suite before further chat changes.

#### Step 2 — Add the minimum real messaging backend

1. Create `backend/messaging/` or an equivalent clearly scoped module.
2. Add conversation/message models and migration.
3. Add ownership-aware service/permission functions.
4. Add thread/send/poll endpoints.
5. Add the seller conversation list/thread surface.
6. Add focused backend permission tests.

#### Step 3 — Connect the existing UI instead of rebuilding it

1. Keep the current drawer/message styling where practical.
2. Replace `messages.push(...)` + global `localStorage` persistence as the real delivery path with server POST/GET calls.
3. Load actual maker/product/order context.
4. Add polling/refresh for incoming seller messages.
5. Fix the drawer send button.
6. Stop generated/demo messages from being presented as a human seller.

#### Step 4 — Make the AI path merge-safe

Choose one:

- **Defer AI for Round 2:** disable/remove the exposed Gemini path from the functional messaging flow; or
- **Keep AI now:** use a server-only key, normal CSRF/authentication, rate limiting, mocked tests and clear AI labelling.

#### Step 5 — Re-review and merge

1. Browser-test buyer → seller → buyer using two accounts.
2. Run messaging/permission tests.
3. Run the full regression suite.
4. Record exact test results.
5. Request integration re-review.

### Round 2 — polish after the core merge

After Round 1 is merged successfully, create a fresh follow-up branch from updated `main` for non-blocking improvements such as unread/read UX, richer attachments, accessibility, localisation cleanup and optional AI refinement. This keeps `main` stable and makes the second review smaller and easier to reason about.

---

## 11. Suggested PR review note to Bohan

> The Shopee-style chat UI is a strong reusable prototype, so there is no need to rebuild the frontend. For this first round, please focus only on the merge-required items: bring the branch up to current `main`, preserve the recommendation changes in `settings.py` and `base.html`, persist conversations/messages server-side, let the correct seller read and reply, enforce buyer/maker permissions, and add basic polling/refresh. Please also fix the drawer send button and make the Gemini test/path merge-safe — either mock and secure it, or defer AI to the next round. The remaining UX, AI, accessibility and localisation improvements can be handled after the core messaging flow is merged.

---

## 12. Verification notes / limits of this review

- Review was performed against the **live GitHub branch** `feature/bohan-chatbot`, not only the older repository ZIP.
- GitHub showed the branch as 7 commits ahead and 22 behind `main` at initial review time. A live recheck on **4 October 2026** found the branch head still at `ab1e7e61e9068fa477e0ffb0e557679f5e5505cd` with no new commits or changed files since the initial review.
- No PR-triggered GitHub Actions workflow runs were associated with the reviewed head commit when checked.
- I did **not** claim a successful full branch test run because this environment does not have a checked-out live branch with its exact Git history/database setup.
- The broken/flaky `test_chat_api_endpoint` conclusion comes from direct static inspection of the branch: the test expects `status="ok"` while the default Gemini key is blank and the service returns `status="error"` without a key.
- Current Gemini 3.8 model/API guidance was checked against Google's official Gemini API documentation on 3 October 2026.

---

## 13. Handover status

**Recommended status:** `Round 1 changes requested before merge`  
**Code-quality assessment:** `Good frontend/prototype base; core messaging architecture is incomplete`  
**Reusable component status:** `Keep and reuse the existing chat UI where practical`  
**Merge strategy:** `Do not merge yet; fix Round 1 on feature/bohan-chatbot, re-review, then merge. Handle Round 2 polish from a fresh branch after integration.`  
**Next owner action:** Bohan to synchronize with `main`, implement the minimum real persistent buyer↔seller flow + permissions/polling, make the AI path merge-safe, then request integration re-review.

# Current implementation and acceptance status

Reviewed against `544c3e6a979e7e903f623c7aa14b0bf0edbed23e` on 26 October 2026. This replaces the 8 September checklist. “Implemented” means evidence exists in current source; test files alone do not prove execution or release readiness.

## Reconciliation of the previous tracker

| Previous task or decision | Current evidence and disposition |
| --- | --- |
| Seller create/edit forms, image management, variants, price and stock | Implemented in `frontend/views_seller.py`, `frontend/forms_seller.py` and seller templates; covered by `frontend/tests_seller.py`. |
| Seller order detail, status, carrier and tracking | Implemented in `frontend/views.py`, `backend/orders/api.py` and `backend/orders/services.py`; seller/API regression cases exist. |
| Per-seller fulfilment / multi-vendor order structure | `SellerFulfillment` and migration `orders/0004` exist. One commercial order can have separate seller fulfilments; no split-payment settlement is established. |
| Full buyer-to-seller browser test: sign-in, bag, mock payment, seller visibility, dispatch and buyer tracking | Django checkout, seller API, fulfilment and frontend tests cover portions of the flow. No standalone full-browser automation suite was found. Run and record the complete browser journey on a local/staging instance. |
| Remaining template/validation/static-copy translations | Translation catalogue, presentation helpers and extensive `frontend/test_catalogue_i18n.py` coverage now exist. Do not treat the old unchecked boxes as missing implementation; complete linguistic coverage still requires review. |
| Seed catalogue, makers, FAQs and journal translation | Implemented through `frontend/catalogue_i18n.py` and gettext catalogue, with English/Chinese tests and guards preserving customised content. |
| Chinese address and phone validation | `frontend/forms.py` and account serializers contain validation; localisation tests cover address input contracts. A comprehensive China-specific address/phone acceptance standard is not established by this audit; team review remains. |
| Fluent-speaker review | Cannot be inferred from code or historical checkboxes. Record reviewer, flows and date. |
| Change-password form | `account_change_password` view, route and profile form exist. |
| Reset token, confirmation and completion pages | Django auth views, routes and templates exist. Real email delivery requires SMTP; local console mode prints the reset email. |
| In-app order/fulfilment notifications | Account overview includes notification presentation; commerce services emit order/shipment/delivery notifications through an email abstraction. A separate persistent notification inbox/read-state service is not established. |
| Seller analytics | Seller dashboard aggregates current order/product data in `frontend/views.py`. |
| No-key recommendations / recommendation decision | `backend/recommendations/services.py` implements popular/similar/user/guest ranking with tests. Model-provider credentials are not required for these rankings. |
| Buyer–seller threaded messaging / transport decision | `backend/messaging/` and `frontend/static/frontend/js/chatbot.js` implement persistent conversations and HTTP polling. This is separate from optional AI assistance. |
| Could-tier scope decision | Several optional features are integrated. The team should approve the demonstrated scope and acceptance evidence rather than reopen old implementation tasks. |
| Chinese search decision | Current database text matching remains; a dedicated segmentation/search engine is not established. Evaluate search quality before choosing an extension/service. |
| Payment splitting | Per-seller fulfilment does not settle funds. Merchant/settlement design remains an external decision. |
| Real Stripe WeChat Pay | Provider implementation and signature verification exist in `backend/payments/services.py`. Keys, merchant eligibility, payment-method setup and sandbox/live verification remain external gates. |
| Transactional email | Commerce sender defaults to console; a real commerce sender needs integration. Password-reset SMTP is separately configurable. |
| Cloud image storage | Database image storage and SVG fallbacks exist. Cloud storage is an optional capacity decision, not required for the current demo. |
| Custom domain | `demo.maijiax.cn` is referenced by hosted demo configuration and Windows build tooling. This does not establish a custom domain for the buyer storefront or a released native app. |
| Commissioned photography | Placeholder assets and Openverse storage/fetching exist. Original studio photography and rights review remain team inputs. |
| Legal/regulatory review | Not established by source inspection. Actual operator, hosting and platform declarations must be reviewed before public release. |
| Vercel/Neon deployment, migrations, seed catalogue, 130 photos and image credits previously marked complete | Historical deployment claims are not current verification. Source supports Vercel, PostgreSQL and image credits; exact live database contents, region and photo count were not queried. See the cleanup report for current reachability checks. |
| Separate staging deployment and tested local fallback | Local/isolated demo profiles and launchers exist. Current staging availability and a fresh-machine fallback rehearsal still need recorded acceptance. |

## Acceptance still requiring evidence

The former “project-ready” checklist is now an evidence request:

- Run the complete local regression suite and record the commit, database isolation and results. No tracked GitHub Actions workflow was found; remote CI success is unverified.
- Exercise the complete buyer-to-seller browser journey, including multi-seller access boundaries, mock payment and fulfilment visibility.
- Review English and Simplified Chinese primary flows with a fluent speaker.
- Verify the intended staging deployment and a fresh local fallback.
- Perform a dedicated secrets/release review before distribution; this documentation audit is not a repository-wide security certification.
- Keep demonstrations explicit about mock payments and simulated shipping.
- Record WeChat upload/review/publication separately from successful local or phone previews.

## Historical review findings

The original reviews are retained in [docs/archive](docs/README.md). Their “OPEN” labels refer to older branch snapshots. In current source, fulfilment eligibility is enforced centrally, product form writes are transactional, and localisation regression coverage exists. Remaining seller wording/extraction quality and formset UX should be reviewed separately; no application refactoring was performed here.

See [cleanup validation](docs/CLEANUP_REPORT.md) for checks actually executed during this update.

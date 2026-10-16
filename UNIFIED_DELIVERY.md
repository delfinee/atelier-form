# Unified buyer website and seller WeChat delivery

The main website is for buyers. Seller operations are in the native WeChat Mini
Program, using the same Django models and validated services. The website retains
secure account linking and product-editor handoffs needed by the Mini Program.
The old seller web console is not the main delivery entry point.

## Start

Windows: `START-ATELIER.cmd`. Other systems: `python launch_seller.py --storefront`.
The prepared local address is `http://127.0.0.1:8780/` (or the explicitly selected
port). Open the homepage shopping assistant or its persistent corner button.
An existing installation can use `python run_seller_agent.py --storefront
--env-file /path/to/platform.env --port 8782`.

The main-page assistant queries public, active products. It supports product
type/material, price ceilings, colour and matching variants, cheapest ordering,
published review averages/counts, follow-up refinement, comparison and more results.
Prices are item prices before shipping. Currencies are never silently converted.
No reviews means no rating; sold-out and made-to-order records are distinguished.
Product cards link into the existing product, bag and checkout pages. The assistant
cannot place an order, report payment, grant seller rights or change stock.

`BUYER_AI_USE_LLM=1` with a private `DEEPSEEK_API_KEY` allows the retained DeepSeek
adapter to help with otherwise unmatched requests. Guided catalogue queries work
without paid calls. Model text never becomes price/review/payment authority.

## Preserved earlier work

`backend/concierge/` and `backend/sellerdesk/` retain the earlier customer dialogue,
order preview/confirmation, mock payment, packing and shipment demonstration.
Their original tests remain in the repository. The only legacy schema adjustment
is an explicit reverse relation name to coexist with the seller-agent conversation.
These demo consoles require explicit `CONCIERGE_DEMO=1` and the mock payment provider;
they are not exposed by `config.marketplace_urls`. Do not enable them in production.
Normal buyer checkout uses the existing `orders` and `payments` services.

## Seller channel and deployment

The current native client, identity linking, confirmations, audit records, revocation
and seller scoping are preserved. `/api/seller-agent/v1/` is unchanged. The combined
deployment uses `config.marketplace_production` in `deploy/compose.yml`, serving the
buyer homepage and WeChat APIs from one backend/database. `/seller/ai/` points to
Mini Program information; `/seller/ai/link/` and authenticated product editing remain.
Do not confuse this source integration with an already published WeChat release.
The phone-tested development version and the prepared permanent-domain version
remain separate until platform release steps are completed.

The optional `deploy/marketplace-demo.compose.yml` runs an isolated group acceptance
site. It contains synthetic public catalogue/review data, disables account and
WeChat linking, and uses simulated payments. `seed_buyer_demo` refuses other databases
and never resets an existing catalogue. It does not read a private local `.env`.

## Validation

`python manage.py test concierge sellerdesk seller_agent accounts products orders
payments reviews recommendations messaging frontend imagery --settings=config.marketplace_test
--noinput` includes the retained legacy flows and the integrated buyer acceptance cases.
`concierge.test_shopping` explicitly tests the new homepage, multi-turn filters,
current variant prices, review visibility, CSRF/session separation, retry handling,
and a seller confirmation immediately changing the buyer's catalogue result.
Use a test database; no paid model calls are needed by these tests.

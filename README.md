# Atelier Form

A handmade-goods marketplace for buyers and independent makers in China, developed for **NTU EE3180 Design & Innovation Project, Group E006**.

The integrated project combines a Django buyer storefront, seller management tools and a shared PostgreSQL database. Optional AI assistants and a WeChat Mini Program extend the same commerce services; a separate Windows/web coursework demo uses synthetic shops.

## Features and scope

| Area | Implemented in the current source |
| --- | --- |
| Buyer storefront | Catalogue search/filtering, collections and maker pages, bag, checkout, accounts, addresses, wishlists, order history and purchase-linked reviews. |
| Seller workspace | Product creation/editing, images and variants, inventory, analytics, seller-scoped orders, and per-seller fulfilment/tracking. |
| Localisation | English/Simplified Chinese switching, gettext catalogues and presentation-time translations for seeded catalogue and site content. Custom seller content is preserved; complete linguistic approval is not claimed. |
| Payments | Default mock WeChat-style payment simulator, payment records and reservation expiry. Stripe WeChat Checkout and signed-webhook handling also exist; credentials and provider validation are required. No live settlement is claimed. |
| Recommendations | Popularity, product similarity and user/guest recommendations without a model-provider key. |
| Messaging | Persistent buyer–seller conversations, ownership checks, replies and HTTP polling; separate from the shopping assistant. |
| Buyer assistant | Catalogue-grounded discovery, filtering, comparisons and follow-ups. Optional DeepSeek calls require explicit configuration and a server-side key. |
| Seller assistant | Owner-scoped queries and proposed stock, price, listing and fulfilment changes, with explicit confirmation. Available through the authenticated web workspace and linked WeChat client. |
| Windows demo | WebView2 client for the hosted synthetic seller demo. Internet is required; payments and shipping are simulated. |

Source presence does not establish release approval or a passing deployment. See [current status](OUTSTANDING_TASKS.md) for evidence and remaining verification.

## Architecture and repository

Python 3.12, Django 5.2, Django REST Framework, JWT/session authentication and PostgreSQL form the core stack. Django templates, CSS and JavaScript serve the website; WhiteNoise serves collected static assets. Dependencies are pinned in [requirements.txt](requirements.txt).

```text
backend/
  config/           settings profiles, URL maps and WSGI
  accounts/         identity, addresses and wishlists
  products/         catalogue, makers, images and variants
  orders/payments/  checkout, inventory, fulfilment and payment providers
  reviews/content/  reviews, editorial content and notification services
  recommendations/  ranking and product-view history
  messaging/        persistent human conversations
  concierge/        buyer assistant and guarded earlier demos
  seller_agent/     seller queries, previews, confirmations and WeChat linking
  sellerdesk/       retained earlier demonstration workflows
  imagery/          database-backed photography and attribution
frontend/           templates, forms, views, static assets and seed content
locale/             Simplified Chinese translation catalogue
miniprogram/        native WeChat seller client and JavaScript checks
desktop/windows/   WebView2 client source and build tooling
deploy/             Docker, Caddy, backup and deployment profiles
api/index.py        Vercel WSGI entry point
docs/               documentation index, audit and historical reviews
```

Buyer and authenticated seller channels share Django models and services. Checkout derives prices from stored records and reserves inventory transactionally. Seller fulfilment is recorded per seller within an order; this is not payment splitting. Public demo profiles use separate synthetic data.

## Local quick start

Install Git, Python 3.12 and PostgreSQL (the supplied Docker profiles use PostgreSQL 16). Use a dedicated local database; the schema requires PostgreSQL-native fields. Node.js is only needed for JavaScript checks, and WeChat/Windows tooling is optional.

From the repository root, on Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Create the local database and a private `.env` using [the development setup guide](BEGINNER_SETUP.md). Verify the connection targets your local database and select the mock payment provider before continuing:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

On macOS/Linux use `python3.12 -m venv .venv` and `.venv/bin/python` for subsequent commands. Seed only a disposable local development database; it creates demonstration accounts and updates fixture records.

| Local page | Address |
| --- | --- |
| Storefront | <http://127.0.0.1:8000/> |
| Seller dashboard | <http://127.0.0.1:8000/seller/> |
| Seller assistant | <http://127.0.0.1:8000/seller/ai/> |
| API documentation | <http://127.0.0.1:8000/api/docs/> |
| OpenAPI schema | <http://127.0.0.1:8000/api/schema/> |
| Database health | <http://127.0.0.1:8000/api/health/> |
| Admin | <http://127.0.0.1:8000/admin/> |

The optional `START-ATELIER.cmd` / `python launch_seller.py --storefront` route prepares a local integrated demo on port 8780. It installs/prepares data and applies migrations; inspect its selected environment before running it. See [unified delivery](UNIFIED_DELIVERY.md).

## Configuration and tests

[backend/config/settings.py](backend/config/settings.py) defines environment settings. `DIP_ENV_FILE` selects an environment file; otherwise settings read root `.env`. Existing process variables take precedence.

- Set `DATABASE_URL`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS` and a private stable `DJANGO_SECRET_KEY`.
- Use `PAYMENT_BACKEND=payments.services.MockPaymentProvider` locally.
- Set `BUYER_AI_USE_LLM=0` and `SELLER_AGENT_USE_LLM=0` for keyless local work. Provider-backed modes require private keys and send limited context to DeepSeek.
- Password-reset email uses Django's `EMAIL_BACKEND`/SMTP settings. Commerce notifications use the separate `EMAIL_BACKEND_CLASS` abstraction and default to console logging.
- Real WeChat login requires server-side AppID/AppSecret, account linking and an approved HTTPS request domain. Local developer login does not verify real WeChat identity.

Run tests only against a dedicated local PostgreSQL instance with permission to create a test database:

```powershell
.\.venv\Scripts\python.exe manage.py collectstatic --settings=config.marketplace_test --noinput
.\.venv\Scripts\python.exe manage.py test --settings=config.marketplace_test --noinput
node --test miniprogram/tests/privacy.test.cjs
```

See [development setup](BEGINNER_SETUP.md) for isolation, targeted checks and troubleshooting. Historical test counts are not current results; the [cleanup report](docs/CLEANUP_REPORT.md) records checks performed during this documentation update.

## Deployment and external dependencies

- **Vercel storefront:** `api/index.py` exposes Django WSGI; `vercel.json` selects `sin1`. Configure PostgreSQL, production secrets, hosts and trusted origins. Static collection and schema preparation must be handled by the deployment process; the checked-in Vercel configuration has no build command.
- **Combined server deployment:** [RELEASE.md](RELEASE.md) describes Docker/PostgreSQL/Gunicorn/Caddy using `config.marketplace_production`.
- **Separate hosted seller demo:** [WINDOWS_SELLER.md](WINDOWS_SELLER.md) describes `config.seller_hosted_demo`, isolated sample shops and the Windows client.
- **WeChat:** [SELLER_WECHAT.md](SELLER_WECHAT.md) and [SELLER_PHONE.md](SELLER_PHONE.md) describe local integration and phone preview. Public publication requires the platform release process.

Previously documented application addresses are [the storefront](https://dip-new-repo.vercel.app) and [the synthetic seller demo](https://demo.maijiax.cn). Their current availability and verification scope are recorded in the [cleanup report](docs/CLEANUP_REPORT.md); do not infer uptime or live-payment readiness from these links.

Real payment processing, email delivery, model-provider calls and public WeChat release depend on external accounts/configuration. Photography can be fetched through Openverse; bundled SVG placeholders work without it. Search uses database text matching rather than a dedicated Chinese segmentation engine. Multi-vendor payment settlement and automatic courier integration are not claimed.

## Documentation

Start at the [documentation index](docs/README.md), including setup, operational guides, current status and archived team contributions. The [post-rename checklist](docs/REPOSITORY_RENAME.md) records the completed move to `delfinee/atelier-form` and the external integration checks still pending.

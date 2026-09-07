# Atelier Form

A handmade-goods marketplace for the China market: a Django web platform with a
server-rendered buyer frontend, a JSON API, PostgreSQL persistence and Django's
built-in admin. NTU EE3180 Design & Innovation Project, group **E006**.

The stack follows the **Project Charter**, which is authoritative for this project
(see `CLAUDE.md`): Django + PostgreSQL, with modular apps `accounts`, `products`,
`orders`, `payments`, `reviews`.

---

## Quick start

Requires **Python 3.12** (pinned in `.python-version`) and **PostgreSQL 14+**. Nothing else — no third-party
API key is needed to run the whole application.

```bash
# 1. PostgreSQL. Either use a local install…
createdb atelier_form
psql -d postgres -c "CREATE ROLE atelier LOGIN PASSWORD 'atelier' CREATEDB;"
psql -d postgres -c "GRANT ALL PRIVILEGES ON DATABASE atelier_form TO atelier;"
psql -d atelier_form -c "GRANT ALL ON SCHEMA public TO atelier;"

#    …or use any local PostgreSQL installation.

# 2. Dependencies
python -m venv .venv
.venv/bin/pip install -r requirements.txt

# 3. Configuration
cp .env.example .env          # defaults already point at the database above

# 4. Schema and content
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed

# 5. Run
.venv/bin/python manage.py runserver
```

| | |
|---|---|
| Frontend | <http://127.0.0.1:8000/> |
| API docs (Swagger) | <http://127.0.0.1:8000/api/docs/> |
| OpenAPI schema | <http://127.0.0.1:8000/api/schema/> |
| Health | <http://127.0.0.1:8000/api/health/> |
| Django admin | <http://127.0.0.1:8000/admin/> |

### Development accounts

Created by `manage.py seed`. **Development only** — they exist solely in a locally
seeded database and must never be created in any deployed environment.

| Role | Email | Password |
|---|---|---|
| Customer | `customer@atelierform.test` | `demo-customer-2026` |
| Seller | `seller@atelierform.test` | `demo-seller-2026` |
| Admin | `admin@atelierform.test` | `demo-admin-2026` |

---

## Architecture

One Django project, one database, no microservices.

```
manage.py          Django command-line entry point
api/index.py       Vercel serverless entry point
vercel.json        Vercel deployment configuration
backend/           Django backend package directory
  config/          settings, URL maps, WSGI entry point, API pagination/errors
  accounts/        users, addresses, and wishlists
  products/        catalogue, makers, variants, and seller products
  orders/          carts, checkout, orders, and stock handling
  payments/        payment records and payment-provider abstraction
  reviews/         product reviews
  content/         journal, FAQs, newsletter subscribers, and contact messages
  imagery/         stored photography, Openverse fetching, image serving, credits
frontend/          server-rendered buyer website Django app
  views.py         frontend page and form views
  templates/       HTML templates
  static/          CSS, JavaScript, and placeholder imagery
  mockdata/        seed catalogue and site copy
locale/            Simplified Chinese translation files
staticfiles/       generated production assets from `collectstatic` (not source)
```

`backend/content/` is an addition to the charter's five apps: the journal, FAQs, newsletter
and contact inbox are editorial concerns that belong to none of them.

Each domain app owns its `models.py`, `serializers.py`, `api.py` and `admin.py`.
`backend/config/api_urls.py` only wires them together. There is no repository layer —
Django's ORM already is one — but genuine business logic lives in services
(`backend/orders/services.py`, `backend/payments/services.py`,
`backend/content/services.py`) rather than in views, because checkout is used by
both the API and the frontend.

### Two rules the whole design rests on

1. **Prices come from the database, never the request.** A client says *what* and
   *how many*; the server decides *how much*. Posting `price` or `total` to any
  endpoint has no effect; prices are always calculated from database values.
2. **Stock is checked and decremented in one locked transaction.** `create_order`
   takes `SELECT … FOR UPDATE` on the product and variant rows, re-validates
   against those locked rows, and decrements with a guarded `F()` expression, so
   two concurrent checkouts cannot both take the last piece and stock can never
   go negative. If any line fails, the whole order is rolled back.

### Why Django, not FastAPI/SQLAlchemy/Alembic

`CLAUDE.md` and the charter mandate Django + PostgreSQL on the "PyShop" baseline,
and the frontend is server-rendered Django templates. Django's ORM and its
migration framework are used instead of SQLAlchemy and Alembic — Alembic is a
SQLAlchemy tool and has no role in a Django project. `manage.py migrate` is the
equivalent of `alembic upgrade head`, and the schema is never created with
`create_all()`-style syncing.

---

## Database

PostgreSQL only. The schema uses Postgres-native `ArrayField` and `JSONB`, which
have no SQLite equivalent.

| App | Tables |
|---|---|
| accounts | `accounts_user`, `accounts_address`, `accounts_wishlistitem` |
| products | `products_category`, `products_collection`, `products_maker`, `products_product`, `products_product_collections`, `products_productimage`, `products_productvariant` |
| orders | `orders_cart`, `orders_cartitem`, `orders_order`, `orders_orderitem`, `orders_ordernumbersequence` |
| payments | `payments_payment` |
| reviews | `reviews_review` |
| content | `content_article`, `content_faqgroup`, `content_faq`, `content_newslettersubscriber`, `content_contactmessage` |
| imagery | `imagery_siteimage` |

Conventions: UTC timestamps (`USE_TZ`), `created_at`/`updated_at` on every table,
a public `uuid` alongside the integer primary key on anything a URL or API exposes,
unique slugs for everything the frontend routes to, and database-level constraints
rather than application-only checks — one default address per user, one active cart
per user or session, no duplicate wishlist entry, positive quantities, non-negative
prices.

**Orders are immutable.** `OrderItem` stores a snapshot (name, variant, SKU, image,
unit price, line total) and its `product`/`variant` foreign keys are `SET_NULL`. An
order from last year still reads correctly after the product is renamed, repriced
or deleted.

**Order numbers** are `AF-2026-000001`, allocated from a locked per-year counter row
rather than `COUNT(*) + 1`, which would hand two concurrent checkouts the same number.

### Migrations

```bash
.venv/bin/python manage.py makemigrations     # after changing a model
.venv/bin/python manage.py migrate            # apply
.venv/bin/python manage.py showmigrations     # what is applied
```

### Seed data

```bash
.venv/bin/python manage.py seed            # idempotent: updates, never duplicates
.venv/bin/python manage.py seed --flush    # wipe commerce data and rebuild
```

Inserts 4 categories, 3 collections, 5 makers, 21 products (47 variants, 63 images),
5 journal articles, 24 FAQs in 6 groups, 2 addresses, 3 historic orders, 3 wishlist
entries, 2 reviews and the three demo accounts. Content comes from
`frontend/mockdata/`, which is now **the seed fixture and the home of static site
copy** — it no longer serves a single request.

### Photography

```bash
.venv/bin/python manage.py fetch_images              # fill every empty image slot
.venv/bin/python manage.py fetch_images --dry-run    # list the slots and their queries
.venv/bin/python manage.py fetch_images --group product-speckled-breakfast-bowl --refresh
```

Fetches openly licensed photographs from [Openverse](https://openverse.org/) — no
API key, no cost — crops each to the box its layout expects, and stores the bytes in
`imagery_siteimage`. Every slot the catalogue defines is derived from the database,
so the command needs no manifest of its own.

Photographs are keyed by image name, not by a foreign key, so `seed --flush` and
re-seeding leave them in place — the catalogue can be rebuilt without re-fetching.
Anything not yet fetched keeps rendering its generated SVG, so the site is never
broken mid-run. Attribution is published at `/credits/`; search responses are cached
under `.imagery-cache/` so a re-run costs no API quota. The generated SVG fallbacks
live under `frontend/static/frontend/img/placeholders/` and are committed as site
assets.

---

## API

Everything lives under `/api/` and is documented at `/api/docs/`. Errors are always
`{"detail": "..."}`, with an `errors` object added for field-level validation
failures. Lists are paginated as
`{"items": [], "page": 1, "limit": 20, "total": 21, "pages": 2}`.

```
GET    /api/health/

POST   /api/auth/register/            POST /api/auth/login/
GET    /api/auth/me/    PATCH /api/auth/me/
POST   /api/auth/logout/              POST /api/auth/change-password/
POST   /api/auth/token/refresh/       POST /api/auth/token/verify/

GET    /api/products/                 ?category= &collection= &maker= &material=
                                      &colour= &availability= &min_price= &max_price=
                                      &featured= &new_arrival= &search=
                                      &sort=featured|newest|price_asc|price_desc
                                      &page= &limit=
GET    /api/products/{slug}/          GET /api/products/facets/
GET    /api/categories/               GET /api/categories/{slug}/  …/products/
GET    /api/collections/              GET /api/collections/{slug}/ …/products/
GET    /api/makers/                   GET /api/makers/{slug}/      …/products/

GET    /api/cart/                     DELETE /api/cart/
POST   /api/cart/items/               PATCH|DELETE /api/cart/items/{id}/
POST   /api/checkout/
POST   /api/payments/webhook/

GET    /api/orders/                   GET /api/orders/{uuid}/
GET    /api/seller/orders/            GET /api/seller/orders/{uuid}/
GET|POST /api/seller/products/        GET|PATCH|DELETE /api/seller/products/{slug}/
GET|POST /api/reviews/                GET|PATCH|DELETE /api/reviews/{uuid}/
GET    /api/wishlist/                 POST|DELETE /api/wishlist/{slug}/[remove/]
GET    /api/addresses/                POST|PATCH|DELETE /api/addresses/[{uuid}/]

GET    /api/journal/    GET /api/journal/{slug}/
GET    /api/faqs/       GET /api/faqs/groups/
POST   /api/newsletter/subscribe/     POST /api/contact/

/api/admin/{products,categories,collections,makers,orders,journal,faqs,contact}/
POST   /api/admin/products/{slug}/stock/     # absolute stock level, idempotent
```

Admin routes require `is_admin`. Every per-user resource is queryset-scoped to the
caller, so another user's order, address, cart or wishlist returns 404, not 403 —
existence is not disclosed.

### Authentication

Two mechanisms over one user model:

- **Session cookies** for the frontend, which is server-rendered. Signing in at
  `/account/login/` also merges whatever is in the guest bag into the account.
- **JWT** (`djangorestframework-simplejwt`) for any other client: 30-minute access
  tokens, 7-day rotating refresh tokens.

Passwords are hashed with **Argon2** (`argon2-cffi`), first in `PASSWORD_HASHERS`.
Sign-in failures return one message for a wrong password, an unknown address and a
deactivated account alike, so the endpoint cannot be used to enumerate accounts.

### Search

`ILIKE` against a denormalised `search_blob` (name, descriptions, story, materials,
category, maker), maintained on save. Deliberately **not** `to_tsvector`:
PostgreSQL's default text-search configuration does not segment Simplified Chinese,
so full-text search would silently fail to match `陶瓷杯` once the catalogue is
localised — the gap flagged in `DIP_E006_Charter_Review.md` §4.5. The upgrade path
is a `pg_trgm` GIN index, then `zhparser`/`pg_jieba`.

---

## Storefront integration

The frontend was built against `frontend/mockdata/`, behind a documented seam:
`frontend/services.py`. That module now reads the ORM instead, and the models
carry compatibility properties (`Product.images`, `Product.variants`,
`Collection.title`) so the templates did not need rewriting.

| Area | Before | Now |
|---|---|---|
| Products, categories, collections, makers | `mockdata` dicts | ORM via `services.py` |
| Journal, FAQs | `mockdata` | `content` models |
| Cart | `localStorage` | `POST /api/cart/…`, one cart row per user or session |
| Wishlist | `localStorage` | `WishlistItem` when signed in; `localStorage` for guests |
| Auth | forms that only validated | Django session auth, real users |
| Checkout | validated and stopped | `POST /api/checkout/` → real order → confirmation page |
| Orders | a fixed dict | the signed-in user's orders |
| Newsletter, contact | acknowledged and discarded | stored rows |

Still browser-local, deliberately: recently-viewed slugs, and a guest wishlist.

Static page copy (brand details, navigation, the Our Story / Shipping / Care text)
stays in `frontend/mockdata/content.py` as site configuration.

---

## Configuration

Configuration is centralised in `backend/config/settings.py`. Values are read
through typed `django-environ` helpers from the process environment or `.env`.
The defaults declared there keep local development runnable, while production
requires an explicit `DJANGO_SECRET_KEY`.

### Required

| Variable | Notes |
|---|---|
| `DATABASE_URL` | `postgres://user:pass@host:5432/dbname`. Defaults to the local dev database. |
| `DJANGO_SECRET_KEY` | **Required in production.** Blank in development, where an ephemeral per-process key is generated. |

### Optional

| Variable | Default | Notes |
|---|---|---|
| `DJANGO_DEBUG` | `1` | Set `0` in production; that alone turns on SSL redirect, HSTS and secure cookies. |
| `DJANGO_ALLOWED_HOSTS` | `*` | Comma-separated. |
| `JWT_SECRET` | falls back to `DJANGO_SECRET_KEY` | |
| `JWT_ALGORITHM` | `HS256` | |
| `ACCESS_TOKEN_LIFETIME_MINUTES` | `30` | |
| `REFRESH_TOKEN_LIFETIME_DAYS` | `7` | |
| `CORS_ALLOWED_ORIGINS` | empty | Only needed for a separate frontend origin. Never `*` with credentials. |
| `CSRF_TRUSTED_ORIGINS` | valid CORS origins | Explicit origins for trusted form POSTs; when omitted, HTTP(S) origins from `CORS_ALLOWED_ORIGINS` are used. |
| `CURRENCY` / `CURRENCY_SYMBOL` | `CNY` / `¥` | China-market default. |
| `FREE_SHIPPING_THRESHOLD` | `80` | |
| `SHIPPING_STANDARD` / `SHIPPING_EXPRESS` | `8` / `18` | |
| `LOW_STOCK_THRESHOLD` | `5` | |
| `ORDER_NUMBER_PREFIX` | `AF` | |
| `PAYMENT_BACKEND` | `backend/payments/services.py` (`MockPaymentProvider`) | |
| `PAYMENT_RESERVATION_MINUTES` | `30` | Run `manage.py expire_payments` periodically. |
| `EMAIL_BACKEND_CLASS` | `backend/content/services.py` (`ConsoleEmailSender`) | |
| `DJANGO_LANGUAGE_CODE` | `en-us` | Simplified Chinese is available as `zh-hans`. |
| `LOG_LEVEL` | `INFO` | |

### Development only

`SECURE_SSL_REDIRECT` and `SECURE_HSTS_SECONDS` are production overrides. They
apply automatically with secure cookies, HSTS and proxy HTTPS handling whenever
`DJANGO_DEBUG=0`.

`.env` is gitignored. No secret is committed, and passwords, tokens and payment
identifiers are never logged.

To verify configuration changes locally, run:

```bash
.venv/bin/python manage.py check
.venv/bin/python -m compileall -q backend/config
```

---

## API keys

**None are required.** The application runs completely — including checkout — with
no third-party account.

| Integration | Needed now? | Would require |
|---|---|---|
| Payments (Stripe native WeChat Pay) | No — `MockPaymentProvider` is the default | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`. Implement `StripeWeChatProvider` in `backend/payments/services.py` and point `PAYMENT_BACKEND` at it. |
| Transactional email | No — logs a safe line instead | Resend (`RESEND_API_KEY`), SendGrid (`SENDGRID_API_KEY`) or SES (`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`). Implement an `EmailSender` and set `EMAIL_BACKEND_CLASS`. |
| Image hosting | No — photographs are rows in `imagery_siteimage`, with generated SVGs as the fallback | Cloudinary or S3, once the database grows past a few hundred megabytes. Only `backend/imagery/resolver.py` would change. |
| Image search (Openverse) | No — keyless and free | Nothing. Registering a client raises the anonymous 200/day quota, which only matters when re-fetching the whole catalogue repeatedly. |
| Search | No — PostgreSQL ILIKE | Nothing external. The Chinese-segmentation upgrade is a Postgres extension, not a service. |
| AI recommendations (charter "Could") | No — not built | Would need a model provider key. |

### Payment flow, once a provider is wired in

```
Backend creates a payment session   →   provider    →   customer pays
                                                              ↓
        order marked paid   ←   signature verified   ←   provider webhook
```

`POST /api/checkout/` already creates the order **unpaid** and opens a session. The
only thing that can mark an order paid is `POST /api/payments/webhook/`. No card
number, CVV or expiry is ever accepted or stored.

In development, checkout redirects to an interactive **WeChat Pay sandbox simulator**.
It moves no money, but exercises the provider callback, success/failure transitions,
confirmation notification and idempotent inventory release. A failed reservation is
cancelled and its stock is returned exactly once.

Run `.venv/bin/python manage.py expire_payments` from a scheduler to release mock
reservations abandoned for longer than `PAYMENT_RESERVATION_MINUTES`.

---

## Deployment

Vercel runs the Django application through `api/index.py`, which exposes the same
WSGI application defined in `backend/config/wsgi.py`.

### Vercel

The whole application goes to Vercel — frontend, API and images are one Django
process, so there is no separate frontend to deploy. Vercel's zero-config Python
runtime sends requests to `api/index.py`; WhiteNoise serves the hashed static assets.

**This is a serverless host, so two things must be true or it will not work.**
Postgres connections must not be held between invocations (`DJANGO_CONN_MAX_AGE=0`
plus a *pooled* connection string), and each image is a function invocation on a
cold cache. Images and static assets are sent with `Cache-Control: immutable` and
a content-hashed URL, so Vercel's edge answers repeat requests and the function
sees each asset roughly once — that caching is what makes this viable, and it
breaks if those headers are removed.

**1. A pooled Postgres.** Vercel has no database. [Neon](https://neon.tech)'s free
tier suits this: create a project, then copy the **pooled** connection string (it
contains `-pooler`), not the direct one.

**2. Load the data.** Migrations and seeding cannot run inside a serverless
function. Push the local database, which already holds the 130 photographs:

```bash
pg_dump "postgres://atelier:atelier@127.0.0.1:5432/atelier_form" \
  --no-owner --no-acl -Fc -f atelier.dump
pg_restore -d "<neon-connection-string>" --no-owner --no-acl atelier.dump
```

Or build it remotely instead:

```bash
export DATABASE_URL="<neon-connection-string>"
python manage.py migrate && python manage.py seed && python manage.py fetch_images
```

**3. Environment variables.** Set these in the Vercel project for **both** the
Build and Runtime environments — `collectstatic` runs at build time and reads the
same settings module, so a missing `DJANGO_SECRET_KEY` fails the build:

| Variable | Value |
|---|---|
| `DATABASE_URL` | the **pooled** Neon string, `?sslmode=require` |
| `DJANGO_CONN_MAX_AGE` | `0` — serverless must not keep connections open |
| `DJANGO_SECRET_KEY` | `python -c "import secrets;print(secrets.token_urlsafe(64))"` |
| `DJANGO_DEBUG` | `0` |
| `DJANGO_ALLOWED_HOSTS` | `your-project.vercel.app` |
| `CSRF_TRUSTED_ORIGINS` | `https://your-project.vercel.app` |

`CSRF_TRUSTED_ORIGINS` is not optional the moment a request arrives from anything
but the canonical host. Vercel gives every preview deployment its own URL, and a
form POST from one is rejected with 403 unless that origin is listed — add each
preview domain, or test only on the production URL.

**4. Deploy.** Run `python manage.py collectstatic --noinput` first — `vercel.json`
carries no `buildCommand`, so the `staticfiles/` directory is uploaded as built
locally. Then `vercel --prod`. Check `/api/health/` first; it exercises the database.

#### Two things that will bite you

**Keep `vercel.json` minimal.** It must contain `regions` and nothing that touches
routing:

```json
{ "$schema": "https://openapi.vercel.sh/vercel.json", "regions": ["sin1"] }
```

Vercel's zero-config Python detection already routes every path to `api/index.py`.
Adding an explicit `"rewrites": [{"source": "/(.*)", "destination": "/api/index"}]`
*breaks the site*: Django then receives `/api/index` as the path for every request
and returns its 404 page for the whole site, while still looking healthy — the
function boots, renders and answers quickly, just with 404 for every URL.

**`regions` must match the database.** Vercel defaults functions to `iad1`
(Washington DC). With Postgres in `ap-southeast-1`, every query crossed the Pacific
at roughly 200 ms, and opening a connection cost about 1.9 s — the homepage took
5 s to serve 12 queries. Pinning the function to `sin1` beside the database took
the same page to 0.4 s and a cold image from 3 s to 0.05 s. If the database moves,
this value moves with it.

Measured on the live deployment, before and after:

| | `iad1` (default) | `sin1` (beside the DB) |
|---|---|---|
| Homepage | 5.0 s | 0.41 s |
| `/shop/` | 5.9 s | 0.43 s |
| `/api/health/` | 2.2 s | 0.10 s |
| Cold image | 3.1 s | 0.05 s |

---

## Not built yet

Honest scope. The charter lists more than this phase covers:

The prioritised, dependency-aware tracker is in
[`OUTSTANDING_TASKS.md`](OUTSTANDING_TASKS.md).

- **Full seller dashboard UX** — seller identity, ownership-scoped product CRUD,
  seller-only order views and a dashboard summary exist. Image/variant editing,
  per-seller fulfilment state and richer browser forms are not built yet.
- **Multi-vendor cart and payment splitting** — one cart produces one order. The
  charter's split-settlement decision (Stripe Connect vs. a ledger) is still open.
- **Complete Simplified Chinese translation** — locale switching, a compiled
  Simplified Chinese catalogue and translated primary/account navigation exist;
  most page copy and seeded catalogue content still need translation.
- **Custom-order chat, notifications, AI recommendations, seller analytics** — the
  charter's "Could" tier.
- **Password reset email** — the request is accepted and logged; no mail is sent.

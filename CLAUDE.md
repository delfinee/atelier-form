# CLAUDE.md — DIP Project E006

NTU EE3180 Design & Innovation Project, Group **E006**, AY2026/27 Semester 1.
Supervisor: Assoc Prof Wang Lipo. PM: Shi Bohan. Treasurer: Delfine Yew Jia En.
Team (6): Bohan, Delfine, JunJie, Min, Samuel, Yi Jun.

## Source of truth

**`DIP_Project_Charter (E006).pdf` is authoritative.** Where it conflicts with the
original supervisor brief (`photo_2026-09-05 12.22.50.jpeg`), **the charter wins** —
follow the charter and do not re-raise the conflict as a blocker.

The known, settled deviations from the brief:

| | Brief (superseded) | Charter (authoritative) |
|---|---|---|
| Deliverable | Cross-platform mobile app | **Web platform** |
| Frontend | React Native + Expo | **Django templates** |
| Backend | Medusa.js (headless) | **Django + PostgreSQL** ("PyShop" repo baseline) |
| Payments | WeChat Pay + Alipay | **WeChat Pay only**, via Stripe sandbox |

Treat the JPEG as historical context only.

## Read this before answering questions about the project

**[DIP_E006_Charter_Review.md](DIP_E006_Charter_Review.md)** — full summary of both
documents plus the gap analysis and improvement backlog. When I'm asked about the
charter, the project plan, what's missing, what to fix, or what to work on next,
start from that file rather than re-reading the PDF from scratch. Section 5 is the
prioritised action list; section 4 has the detailed findings by area.

Keep that file current — if the charter is revised, update the review to match.

## Project shape (from the charter)

- Three surfaces over one Django backend: **buyer frontend**, **seller dashboard**,
  **administrator interface** (Django's built-in admin).
- Modular Django apps under `backend/`: `accounts`, `products`, `orders`, `payments`, `reviews`.
- PostgreSQL. Secrets in environment variables, never committed.
- China market: Simplified Chinese, RMB, Chinese address/phone formats,
  WeChat Pay-compatible sandbox checkout.
- Budget cap **500 SGD**; any paid service needs the professor's approval first.
- Timeline: charter W4, feature build W5–W10, integration + testing + demo W11,
  final report W12, completion W13.

## The codebase

`README.md` is the engineering entry point — setup commands, architecture, the API
surface, environment variables and what is deliberately not built yet. Start there
before changing code.

Shape as built:

- **Django + PostgreSQL**, one project, no microservices. Apps under `backend/`: `accounts`,
  `products`, `orders`, `payments`, `reviews` (the charter's five) plus `content`
  for the journal, FAQs, newsletter and contact inbox, `imagery` for site
  photography, and `frontend` for the server-rendered buyer surface.
- **JSON API** under `/api/` (Django REST Framework), documented at `/api/docs/`.
  Session auth serves the frontend; JWT serves other clients.
- **Django migrations**, not Alembic — Alembic is a SQLAlchemy tool and has no
  place here. `manage.py migrate` is the equivalent of `alembic upgrade head`.
- **`manage.py seed`** loads the catalogue from `frontend/mockdata/`, which is
  now the seed fixture and the home of static site copy, not a runtime source.
- Sellers use `User.is_seller` and a one-to-one `Maker.owner`; `/api/seller/…`
  querysets must always remain scoped to that owner.
- Images are addressed everywhere by **name** (`product-<slug>-1`,
  `maker-<slug>`). `imagery.resolver.image_url` is the only place that decides
  what a name resolves to: the JPEG bytes stored in `imagery_siteimage`, or the
  generated SVG under `frontend/static/.../placeholders/` when none exists yet.
  `manage.py fetch_images` fills those slots from Openverse; `/credits/` publishes
  the attribution the licences require, so do not remove it.
- Two invariants worth not breaking: prices are always read from the database and
  never from a request, and stock is validated and decremented inside one locked
  transaction in `backend/orders/services.create_order`.

## Working conventions

- Git branches + pull requests; review major changes before merging.
- Track bugs and open work on the shared issue board.
- Escalate blockers early to the PM, supervisor or TA.

# Archived seller-only acceptance (16 October)

> Historical acceptance record. Dates, tunnel links, test counts and release-archive filenames below describe the original delivery; they were not revalidated by the 26 October documentation audit. Some evidence files belong to that external archive, not this repository. For a fresh installation use [development setup](BEGINNER_SETUP.md). This filename is retained because `launch_seller.py` references it.

**Current delivery:** See [UNIFIED_DELIVERY.md](UNIFIED_DELIVERY.md). The buyer
assistant is now integrated into the main website; seller operations are in the
WeChat Mini Program. The notes below record the earlier seller-only acceptance.

This delivery contains the seller assistant, native Mini Program, shared Django
API and the existing marketplace source. It is a team test build, not a public
production release. Buyer shopping AI was outside that earlier delivery.

## Test the running website

Open https://beans-summaries-brilliant-labs.trycloudflare.com/seller/ai/.
Demo account: **seller@atelierform.test** / **demo-seller-2026**.
Download this build from https://beans-summaries-brilliant-labs.trycloudflare.com/seller/download/ after signing in.
This is a shared demo shop: use uniquely named test products. Do not enter real
customer details or treat demo orders as actual payments or deliveries.

The temporary URL needs the host computer, backend and tunnel to stay running.
It is not a permanent deployment. Login is required for private seller data.

## Start on another computer

1. Extract the complete ZIP, preferably on D: on Windows.
2. Install Python 3.11+ and Docker Desktop, and start Docker Desktop. Alternatively
   use an existing PostgreSQL database and supply its private `.env` with
   `DATABASE_URL` and a stable `DJANGO_SECRET_KEY`.
3. Windows: double-click `START-SELLER-WECHAT.cmd`. Other platforms:
   `python3 launch_seller.py`.
4. On a new installation the launcher creates a private `.env`, starts the
   PostgreSQL container on **127.0.0.1:55433**, installs Python packages inside
   `.venv`, applies migrations and adds labelled acceptance records. The
   website and Mini Program use this same database. With an existing environment:
   `python launch_seller.py --env-file /absolute/path/to/platform.env`.
5. Open http://127.0.0.1:8780/seller/ai/ and sign in with the demo account above.
   The command does not change a password or reset records if the account exists.
6. `STOP-SELLER-WECHAT.cmd` stops only the web process. For the optional Docker
   database, `docker compose -f compose.seller-demo.yml stop` preserves the data.

The launcher creates a local development environment. Do not expose port 8780
publicly: it intentionally supports local developer identities. Keep `.env`,
`.venv` and `.seller-agent-runtime` out of shared archives.

## WeChat modes

**Local development:** import `miniprogram/` in WeChat DevTools and use an AppID
your developer account can access. The source config uses localhost:8780 and
`authMode: developer`. Its linking and business requests still reach real Django,
but it does not test WeChat login. A phone cannot use your computer's localhost.

**Real phone:** see [SELLER_PHONE.md](SELLER_PHONE.md). Configure server-only
AppID/AppSecret and an approved HTTPS request domain. Run
`python launch_seller.py --phone --origin https://YOUR-APPROVED-DOMAIN`.
The ZIP also includes `phone-preview-client/`, preconfigured for the current
AppID and temporary HTTPS host. Import it for this shared test, or import the
generated `.seller-agent-runtime/phone-miniprogram/` for your own host, whose domain
checks remain enabled. Use the official DevTools Preview QR. A preview is not a
publicly released Mini Program; team members must have the access required by
the Mini Program account. Add them through the account's member management and
use a permitted preview or experience version. No experience/public release has
been uploaded by this delivery.

Real login, website-account linking and product/order display were confirmed
on the owner's phone. After developer re-login, the updated preview QR was
generated successfully on 16 October 2026 at 22:44 China time. The archive
includes `phone-preview-client/PREVIEW-QR.jpg`. Preview codes are temporary;
regenerate in DevTools when needed. The owner completed all four phone write
confirmations; backend audit and resulting state passed. Evidence is recorded
in `DELIVERY-VERIFICATION.json` and `PHONE-ACCEPTANCE.json`.

## Acceptance checklist

| Step | Action | Expected result |
|---|---|---|
| Link | Generate secure linking request; sign in on the copied website link; enter the six-character code; refresh Mini Program | Same seller account on both channels; no new seller privileges granted |
| Read | `my products`, `low stock`, `my orders`, `pending orders` | Only this seller's records; pending list includes only eligible unshipped orders |
| Draft | `new listing`, then supply name, category, description, price and quantity | Missing fields requested; preview shown; no product before confirmation |
| Create | Confirm draft | One unpublished product; repeat confirmation creates no duplicate |
| Stock | Set the new test product's stock to 9; preview; cancel once, then confirm | No change at preview/cancel; both channels show 9 after confirmation |
| Price | Set test price to 25.50 and confirm | Both channels show 25.50; stale previews are rejected |
| Options | Use **Copy product editor link** or website editor link; add a unique SKU and option stock | Option saved; future stock changes require selecting that option |
| Photos | Upload JPEG/PNG/WebP in editor, save, reopen | Photo visible; invalid/oversized files rejected; other sellers' products inaccessible |
| Publish | Review the test listing in the editor; explicitly set **Is active**, save | Product active; uncheck and save to return the test item to a draft |
| Fulfill | Select a `DEMO-SELLER-…` order; carrier `DEMO Courier`, tracking `DEMO123456`; preview and confirm | This seller's parcel updated; another seller's parcel and parent carrier unchanged |
| Revoke | Unlink only your test device from website | That device can no longer access private data |

Use `python manage.py seed_seller_acceptance --new-run` with local settings and
your configured `.env` for another disposable product and simulated paid order.
The fixture command never processes money, contacts a courier or resets an
existing test. Its `DEMO-SELLER-…` labels and test address are intentional.

## Validation and limits

The full isolated Django regression passed **466 tests**. The delivery checks also cover real HTTP requests from
the native page-handler harness (mocked `wx`), and browser photo/option saving
through the public HTTPS host. A fresh temporary PostgreSQL database passed
migration, startup preparation and repeatable seeding. The Docker deployment
path is supplied but was not executed on this host, which has no Docker CLI.
Real-phone confirmation checks also passed: stock 7 -> 9, price 20 -> 25.50,
unpublished listing creation and a demo shipment. All four audit records show
`confirmed_channel=wechat`. The listing remains unpublished and the parent
order's carrier is unchanged. The final phone-host/download suite passed 9 tests.

The default assistant uses guided commands with no paid model calls. Optional
bounded intent extraction already exists behind server configuration; arbitrary
free-text understanding is not claimed by guided mode. No WeChat Pay, refund,
bulk operation, customer notification or automatic product publication is added.

Source provenance: `origin/main` base `83e1a9e`, branch
`codex/seller-wechat-agent`, including local uncommitted delivery changes. The
archive excludes Git history, databases, private environments and runtimes.
`SHA256-MANIFEST.json` verifies all included source files.

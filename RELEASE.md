# Seller Mini Program release

The current combined deployment uses `config.marketplace_production`: the root
serves the buyer storefront, while the seller Mini Program uses the same API and
database. See [UNIFIED_DELIVERY.md](UNIFIED_DELIVERY.md). Do not launch a second
business database for the buyer site.

This is release preparation, not proof of upload, review submission or publication.
The accepted October 16 team build remains a separate preview.

## Deployment

Use a dedicated server and database for the public release. Do not import the
public demo credentials or copy a developer environment file to production.
The baseline target is a Linux server with at least 2 CPU cores and 4 GB RAM,
Docker Engine and its Compose plugin. Only SSH and HTTPS/HTTP are exposed;
PostgreSQL and Gunicorn stay on the private Docker network.

1. Set up the owned domain and the platform/hosting filing requirements before
   serving the public application. Point the chosen host to the server IP.
2. Copy `deploy/seller.production.env.example` to `deploy/.env.production` and
   populate the real public origin, actual operator name, monitored support
   email, certificate contact, and unique random database/Django secrets.
   Use URL-safe characters for `POSTGRES_PASSWORD`. The existing AppSecret
   remains server-only and must be supplied privately.
   To enable natural-language seller operations, set `SELLER_AGENT_USE_LLM=1`
   and `SELLER_AGENT_API_KEY` (or reuse the existing `DEEPSEEK_API_KEY`).
   `SELLER_AGENT_MODEL=deepseek-flash` selects the model; the shared daily limit
   defaults to 500 calls. Production refuses to start with AI enabled and no key.
   The native privacy notice explains DeepSeek processing and has a new consent
   version. Quick actions still work if the provider is unavailable.
3. Run `sh deploy/start.sh`. Caddy obtains/renews HTTPS certificates. Review
   `docker compose --env-file .env.production -f compose.yml logs` from `deploy/`
   if issuance or startup fails. Do not expose port 8000 or PostgreSQL.
   If the host cannot reliably download from PyPI, set `PIP_INDEX_URL` to a
   trusted HTTPS PyPI mirror before building. Package versions remain pinned
   in `requirements.txt`; do not disable certificate verification.
4. Verify `/healthz/`, public home, privacy page, cookie/CSRF behavior, seller
   login and the real WeChat code exchange through the permanent origin.
5. Provision accounts only after operator verification using
   `python -m django provision_seller --email EMAIL --shop NAME --password-file PRIVATE_PATH`.
   It refuses to modify existing accounts and never grants admin access.
   For a separate reviewer account only, `--review-fixtures` adds a visibly
   labelled synthetic product and simulated-paid order with no payment call.
   Never expose reviewer credentials on the public homepage.
6. Run `sh deploy/backup.sh` before every upgrade and on the chosen backup
   schedule. Copy the restricted dump off the server and rehearse restoration
   into a separate database. No backup retention/deletion is automated here.

`check --deploy` also emits existing OpenAPI schema warnings and HSTS
subdomain/preload advice. The deployment does not opt other subdomains into
HSTS or submit the domain to a browser preload list. TLS, secure cookies,
CSRF protection and one-year HSTS for this host remain enabled. A successful
configuration check is not a substitute for a live TLS/deployment test.

## Native release build

After the permanent origin and real operator details are verified:

```text
python prepare_seller_release.py --origin https://OWNED-HOST --operator ACTUAL-OPERATOR --contact SUPPORT-EMAIL --version 1.0.0
```

The output is `.seller-agent-runtime/releases/1.0.0`. It contains public client
files, the real AppID and HTTPS API origin, and no server environment. Each
release has a SHA-256 manifest. Existing release directories cannot be silently
overwritten. The builder rejects temporary tunnel hosts and placeholder data.

The public home and privacy page do not log in automatically. The user must
read/agree before WeChat login. Private seller pages remain excluded from page
indexing. This sitemap does not itself publish the Mini Program or guarantee
that its name appears in WeChat search.

Configure this AppID's request-domain allowlist to the permanent HTTPS origin.
Keep domain checking enabled. Perform a phone preview test before uploading.
Use the official DevTools upload command with this generated directory and
version 1.0.0. Record its real result; an upload is not a review submission.

## Review submission content

Name: 卖家智能X助手

Description draft (check against the final platform profile):
为已认证卖家提供商品、库存、价格和订单履约管理。连接已有卖家账号后，可查询店铺资料、预览并确认操作，与卖家网站同步。

Category: choose the actual office/business-management category available for
the registered entity. Do not claim payment or shipping-provider integration.
Check platform eligibility and any filing requirements in the account itself.

Entry page: `pages/home/index`

Reviewer instructions:

1. Read the public introduction and privacy notice, agree, and enter the seller
   workspace. Sign-in uses WeChat and grants no seller privileges by itself.
2. Generate a secure linking request, copy its website link and note the code.
3. Open the link in a browser. Sign in using the separate reviewer credentials
   supplied privately in the review form. Confirm the exact code from the
   reviewer phone. Return to the Mini Program and tap Refresh connection.
4. Products and Orders show only the reviewer shop. Its records are explicitly
   synthetic; no payment or courier service is called.
5. Preview a stock or price change and confirm it. Draft a new unpublished
   listing. Record shipment for the labelled test order. Confirm each preview.
6. Sign out clears local credentials and consent. Website WeChat connection
   controls can unlink the account and revoke its sessions.

Privacy declaration must match the real processing: hashed WeChat identifier,
linked account email/permissions, shop/order/delivery information, messages and
confirmation history; essential storage/cookies and user-initiated clipboard
write; website-selected photo upload. No native location, contacts, microphone,
camera or photo-library permissions. No external LLM in this release.

The actual operator, hosting arrangement and contact details must be verified
before submission. Do not invent registration or filing information. Keep the
review account and backend available during review. Record the submission ID
and actual platform status. After approval, publish and verify discoverability
in WeChat; neither approval time nor search indexing time is guaranteed.

# Development setup

NTU EE3180 DIP Group E006. This guide covers the current Django/PostgreSQL application, with Windows PowerShell commands and macOS/Linux equivalents. The filename is retained for existing links.

## Tools and checkout

Use Git, Python 3.12 (see `.python-version`) and a local PostgreSQL server. PostgreSQL 17 Windows paths are used below; adjust them to your installation. Docker is optional for the supplied launcher database. Node.js is optional for Mini Program JavaScript tests; GNU gettext is needed when regenerating translations.

Clone the current repository into a conveniently named local folder:

```powershell
git clone https://github.com/delfinee/atelier-form.git atelier-form
cd atelier-form
```

The GitHub repository was renamed from `delfinee/dip-new-repo-test` on 26 October 2026. Existing clones do not need a new directory or checkout; update their remote URL using the [post-rename checklist](docs/REPOSITORY_RENAME.md).

## Python environment

Run from the directory containing `manage.py`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

Keep an existing working environment. Calling Python directly avoids PowerShell activation-policy changes. On macOS/Linux create it with `python3.12 -m venv .venv`, then use `.venv/bin/python`.

## Local PostgreSQL

Start the installed PostgreSQL service, then connect as its administrator:

```powershell
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -h 127.0.0.1 -p 5432 -U postgres -d postgres
```

Enter the administrator password privately. For a fresh local installation, run these SQL statements individually:

```sql
CREATE ROLE atelier LOGIN PASSWORD 'atelier' CREATEDB;
CREATE DATABASE atelier_form OWNER atelier;
```

These published credentials are only for local development. The role owns the schema and can create Django's disposable test database. If the role/database already exists, inspect and reuse its intended configuration; do not drop it or reset another person's password. Exit psql with `\q`.

Verify the application login:

```powershell
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -h 127.0.0.1 -p 5432 -U atelier -d atelier_form -c "SELECT current_user, current_database();"
```

On macOS/Linux use `psql` from PATH with the same arguments. SQLite is unsuitable because the application uses PostgreSQL-native fields.

## Private environment configuration

Create root `.env` from the tracked sample only if absent:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Review the copied file privately. For keyless local work, ensure these values are set (the sample enables the buyer AI switch, so explicitly turn it off):

```dotenv
DJANGO_DEBUG=1
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
DATABASE_URL=postgres://atelier:atelier@127.0.0.1:5432/atelier_form
DJANGO_SECRET_KEY=replace-with-a-private-generated-value
PAYMENT_BACKEND=payments.services.MockPaymentProvider
BUYER_AI_USE_LLM=0
SELLER_AGENT_USE_LLM=0
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
EMAIL_BACKEND_CLASS=content.services.ConsoleEmailSender
```

Generate a private key locally and paste it into that file:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(50))"
```

Never commit or share the resulting key or environment file. Do not overwrite an existing `.env`; review it privately. `DIP_ENV_FILE` can select another file, and existing process environment variables override file values. Ensure neither points to production before running migrations, seed commands or tests.

A blank key is accepted in debug mode but changes on restart, invalidating sessions. Production requires an explicit key. CNY is the default currency. The full settings reference is [backend/config/settings.py](backend/config/settings.py).

## Schema, fixtures and startup

After confirming the database target is local:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Seed is an intentional fixture update, not a daily startup step. Do not use `seed --flush` for routine setup. Images initially use bundled SVG placeholders; optional `manage.py fetch_images` downloads photography and writes it to the local database. Attribution appears at `/credits/`.

Open the [storefront](http://127.0.0.1:8000/), [API health](http://127.0.0.1:8000/api/health/) and [API docs](http://127.0.0.1:8000/api/docs/). Health should report both status and database as `ok`; `manage.py check` alone does not establish database connectivity. Stop the development server with Ctrl+C.

Local seed accounts:

| Role | Email | Password |
| --- | --- | --- |
| Buyer | customer@atelierform.test | demo-customer-2026 |
| Seller | seller@atelierform.test | demo-seller-2026 |
| Admin | admin@atelierform.test | demo-admin-2026 |

Use `/account/login/` for buyer/seller and `/admin/` for admin. These accounts belong only in disposable development environments. Test the mock checkout, then inspect the seller's own order lines and fulfilment in `/seller/`. Use separate browser profiles to test different roles.

## Optional integrated launcher and clients

`python launch_seller.py --storefront --env-file /absolute/path/to/local.env` prepares and starts the integrated site, normally on port 8780. Windows users can use `START-ATELIER.cmd` after configuring root `.env`.

The launcher can select an existing sibling checkout's environment, install packages, apply migrations and seed acceptance records. When no environment exists, it creates one and uses Docker PostgreSQL on port 55433. Inspect its selection before running it; do not point it at a remote business database. For an already prepared installation, see [UNIFIED_DELIVERY.md](UNIFIED_DELIVERY.md).

[SELLER_WECHAT.md](SELLER_WECHAT.md) covers developer linking; [SELLER_PHONE.md](SELLER_PHONE.md) covers real-login previews. [WINDOWS_SELLER.md](WINDOWS_SELLER.md) covers the separate hosted sample-data client. A phone cannot reach your laptop using the phone's `127.0.0.1`.

## Checks and tests

Use a dedicated local PostgreSQL database and role with `CREATEDB`. `config.marketplace_test` changes application settings but **does not isolate the database URL**: it inherits environment configuration. Verify the host first. Django creates/destroys a test database; `--noinput` may replace an existing test database, so never use shared or valuable test data.

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py collectstatic --settings=config.marketplace_test --noinput
.\.venv\Scripts\python.exe manage.py test --settings=config.marketplace_test --noinput
node --test miniprogram/tests/privacy.test.cjs
```

The test profile uses manifest static storage, so collect its assets before template tests; its generated output is under `.seller-agent-runtime/static`. Targeted Django suites include `frontend orders payments messaging recommendations seller_agent concierge`. The Node privacy tests mock WeChat and HTTP. `miniprogram/tests/local-integration.cjs` is different: it requires a prepared local backend and performs acceptance writes. See [the cleanup report](docs/CLEANUP_REPORT.md) for known errors from the latest documented localisation run; these commands are not a claim that the full suite passes.

For model changes, use `manage.py makemigrations --check --dry-run` to detect missing migrations, then follow the team's migration review process. This cleanup does not change models. Translation work uses `manage.py makemessages -l zh_Hans` and `manage.py compilemessages`, followed by `frontend.test_catalogue_i18n` and a fluent-speaker review.

## Daily workflow

Start PostgreSQL and rerun `manage.py runserver`; installation and seeding are unnecessary each day. Restart after environment changes. Edit static source under `frontend/static/`, not generated `staticfiles/`.

Before starting a task, inspect `git status` and preserve any existing changes. From a clean checkout:

```powershell
git switch main
git pull --ff-only
git switch -c docs/short-description
```

Review the diff, run relevant checks and submit a small pull request after the team authorizes committing/pushing. Do not force-push shared branches or commit private environments. Apply newly reviewed migrations locally after pulling changes; reinstall pinned requirements only when needed.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Python/psql not found | Reopen the terminal after installation; use the full executable path and correct PostgreSQL version. |
| PowerShell activation blocked | Use `.\.venv\Scripts\python.exe` directly. |
| Connection refused | PostgreSQL service, host and port; the launcher Docker database uses 55433 rather than 5432. |
| Password/permission error | Verify the local role, database owner and private connection string. Do not reset shared credentials. |
| Tables missing | Confirm the local target and apply checked-in migrations. |
| Test database creation denied | Use a dedicated local role with `CREATEDB`; do not weaken production access. |
| CSRF rejection | Confirm the scheme/host and trusted origins; do not disable CSRF protection. |
| Images are placeholders | Optional photos have not been fetched; this does not prevent local development. |
| Reset email not received | Debug mode uses console delivery; production needs SMTP settings. Commerce notification configuration is separate. |
| Assistant uses guided mode | LLM flags/keys are optional. Provider failures or quota limits can cause fallback. |
| Stale CSS or logged-out session | Hard refresh assets; use a stable private Django key and restart after changing configuration. |

Current limitations and acceptance work are recorded in [OUTSTANDING_TASKS.md](OUTSTANDING_TASKS.md).

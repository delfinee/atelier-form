# Atelier Form: beginner setup and team coding guide

For the NTU EE3180 Design & Innovation Project team (E006).

**Goal:** everyone can run the shop on their own laptop, sign in, test a code change, and share work before the team meeting.

This guide uses **Windows PowerShell, Python 3.12, and PostgreSQL 17**. The project supports PostgreSQL 14+, but version 17 keeps our example paths consistent. Mac and Linux users should use the adaptation prompt in Section 3.

Read this file on GitHub, or open it in VS Code and press **Ctrl+Shift+V** for a formatted preview.

## Contents

1. [What you are setting up](#1-what-you-are-setting-up)
2. [Install tools and get the repo](#2-install-tools-and-get-the-repo)
3. [Set up with Codex](#3-set-up-with-codex)
4. [Manual setup](#4-manual-setup)
5. [Open the links and test the shop](#5-open-the-links-and-test-the-shop)
6. [Everyday coding](#6-everyday-coding)
7. [Share changes with Git](#7-share-changes-with-git)
8. [Copy-and-paste Codex prompts](#8-copy-and-paste-codex-prompts)
9. [Troubleshooting](#9-troubleshooting)
10. [Before the team meeting](#10-before-the-team-meeting)

## 1. What you are setting up

The repo is the folder containing the project's code. Downloading it does not start the website or create its database.

```text
Your browser opens http://127.0.0.1:8000/
                    |
                    v
           Django on YOUR laptop
                    |
                    v
         PostgreSQL on YOUR laptop
     (products, accounts, orders, photographs)
```

| Term | Meaning |
|---|---|
| VS Code | The editor where you open and change project files. |
| PowerShell / terminal | Where you type commands to install packages and start the app. |
| Python | The programming language that runs this project. |
| Django | The Python framework serving the website and API. |
| PostgreSQL | The database program storing the app's data. |
| pgAdmin | An optional graphical tool for managing PostgreSQL. Opening it does not start Django. |
| `.venv` | This project's private Python environment and packages. Everyone creates their own. |
| `.env` | Your laptop's app settings, including its database connection. |
| Migration | A versioned instruction that creates or updates database tables. |
| Seed | The command adding initial demo products, content, and accounts. |
| Git / GitHub | Git tracks code changes; GitHub hosts the shared copy. |
| Codex | A coding assistant that can inspect files, make edits, and run commands when its environment permits. |

**Local and Vercel are separate installations.** `127.0.0.1` means the computer opening the link. Port `8000` is where Django accepts local requests. Sending a local link to a friend points to their laptop, not yours.

Each person needs their own local setup. Local code changes appear locally first; they reach Vercel through the team's deployment process. Local accounts and photographs do not automatically come from Vercel's database.

For this guide, keep `DATABASE_URL` pointing to `127.0.0.1`. Do not copy the production database connection into your local `.env`.

## 2. Install tools and get the repo

### 2.1 Install these once

Skip tools whose required versions are already installed.

| Tool | Installation instructions |
|---|---|
| [VS Code](https://code.visualstudio.com/docs/setup/windows) | Install the Windows User setup. This is the editor, not the larger Visual Studio application. |
| [Git for Windows](https://git-scm.com/install/windows) | Install Git for cloning the repo and sharing changes. Default options are suitable for getting started. |
| [Python for Windows](https://www.python.org/downloads/windows/) | Choose **Python 3.12** to match `.python-version`. Include the Python launcher and enable the option to add Python to PATH when offered. |
| [PostgreSQL for Windows](https://www.postgresql.org/download/windows/) | Use the installer linked by PostgreSQL. Choose **17** for these examples. Include the server, command-line tools, and pgAdmin. |
| Codex | Follow the [official Codex extension instructions](https://developers.openai.com/codex/ide/) for VS Code, then open the extension and sign in through its supported sign-in flow. |

During PostgreSQL installation, keep port **5432** unless it is already occupied. **Choose and privately save the password for the `postgres` administrator account.** You will need it when creating the project's database. Extra Stack Builder packages are not required here.

The [Python 3.12.10 release page](https://www.python.org/downloads/release/python-31210/) has a traditional Windows installer if you cannot find a 3.12 installer in the general list. The repo pins the 3.12 series, not a specific patch version.

After installing, reopen PowerShell and VS Code so they can see the new commands.

**Run in PowerShell:**

```powershell
py -3.12 --version
git --version
```

Expected: `Python 3.12.x` and a Git version. Fix a missing command before proceeding.

The app itself does not require Node.js, Docker, a Vercel account, or a paid API key for local setup. Codex has separate account/access requirements; the manual route works without Codex.

To find Codex in VS Code, press **Ctrl+Shift+X** to open Extensions, search for **Codex**, and install the extension published by **OpenAI**. Open its icon in the sidebar and follow the sign-in prompts. If the icon is hidden, press **Ctrl+Shift+P** and run **Codex: Open Codex Sidebar**. Keep normal VS Code running as your regular Windows user; individual installers may request administrator permission.

### 2.2 Get the shared repository

Ask the team owner for the **agreed GitHub repository URL** and access if it is private. Use that URL rather than assuming a similarly named test repo is the shared repo.

In PowerShell, replace `PASTE-TEAM-REPOSITORY-URL-HERE` with the real clone URL, keeping the quotes:

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\Projects"
cd "$env:USERPROFILE\Projects"
git clone "PASTE-TEAM-REPOSITORY-URL-HERE" atelier-form
cd atelier-form
```

Do not clone again if you already have a working clone. Open the existing folder instead.

In VS Code, select **File > Open Folder** and choose `atelier-form`. You should see `manage.py`, `README.md`, `requirements.txt`, `backend`, and `frontend` directly inside it.

If you received a ZIP, extract it first and open the folder containing `manage.py`. There may be two nested folders with similar names. ZIPs work for exploration, but use a Git clone before sharing code changes. Do not copy a friend's `.venv`, `.env`, `.vercel`, or database files into your setup.

### 2.3 Where to type things

In VS Code, choose **Terminal > New Terminal**. Use the **PowerShell** terminal profile.

| What the guide shows | Where it goes |
|---|---|
| A `powershell` code block | PowerShell; press Enter to run it. |
| A `sql` code block | The PostgreSQL terminal after connecting; its prompt says `postgres=#`. |
| A Codex prompt | The Codex chat box. |
| A URL | Your browser's address bar. |
| A `.env` setting | The `.env` file in VS Code; save after editing. |

Copy only the code inside a block. Do not copy surrounding backticks, the word `powershell`, or prefixes such as `PS C:\...>`.

Run commands one at a time. If one fails, fix it before continuing. The final lines of a long error message often contain the cause.

## 3. Set up with Codex

Open the repo in a Codex session connected to your **local folder**, then paste the prompt below. This is an alternative to manually completing Section 4; do not run duplicate commands while Codex is doing them.

A remote/cloud task runs elsewhere and does not automatically make your laptop's local links work. The [official Windows sandbox guide](https://developers.openai.com/codex/windows/) explains local execution permissions; downloads and system changes may require approval.

**Copy into Codex:**

```text
I am new to coding. Set up this Atelier Form repo locally on my Windows
laptop so I can open all five localhost links in README.md.

Read BEGINNER_SETUP.md, README.md, requirements.txt, .python-version,
.env.example, and applicable repository instructions. Inspect what is
already installed and preserve existing work and data.

Use native Windows PowerShell and Python 3.12. Install missing project
packages in this repo's .venv using requirements.txt. If Python, Git, or
PostgreSQL is missing, help install it from an official source using the
available tools and required approvals. If I must use an installer,
explain which fields to select and continue afterward.

Use PostgreSQL on 127.0.0.1, normally port 5432, with database atelier_form
and a dedicated atelier login matching .env. Create .env from .env.example
only if missing. Preserve existing settings and verify the database target
is local before writing data.

If an administrator password is needed, let me enter it privately in an
interactive terminal. Do not ask me to paste it into chat or print it.
Do not reset passwords or change authentication rules as a routine setup
step. Explain any necessary recovery action first.

Create or repair only this project's local role/database. Run migrations
and seed demo data for a fresh setup. Never use seed --flush. Start Django
on 127.0.0.1:8000 and verify the homepage, API docs, schema, health, and
admin login page. Health must report database: ok. Fetch missing images
if internet access permits and report any remaining placeholders.

Do not connect to production, deploy, push commits, change architecture,
or upgrade pinned dependencies to bypass errors. Finish with working
links, local demo logins, verification results, and commands to start and
stop the server next time. Distinguish completed steps from anything you
could not verify.
```

If Codex cannot interact with an installer or password dialog, complete that step yourself and tell it to continue. Do not send private passwords to the team chat.

After it finishes, complete Section 5 yourself so you understand how to use the app.

**Mac/Linux adaptation — prepend this to the prompt:**

```text
I use [macOS/Linux], not Windows. Adapt this guide to my operating system,
shell, and installed tools. Use Python 3.12 and local PostgreSQL. Do not
run Windows service commands or use Windows paths. Keep the same local
app behavior and verification checklist.
```

## 4. Manual setup

Use this route to set up yourself or understand what Codex is doing. It assumes a fresh local project database.

### 4.1 Confirm the folder

**PowerShell:**

```powershell
Get-Location
Test-Path .\manage.py
```

The second command must return `True`. Otherwise, open the correct repo folder and create a terminal there. Do not run project commands from `C:\Windows\System32`.

### 4.2 Create the Python environment

**PowerShell; run each line separately:**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

Skip the first line if `.venv` already works with Python 3.12. Expected final output: `No broken requirements found.`

We call `.venv`'s Python directly, so there is no need to activate it or change PowerShell's script execution policy. The prefix is **`.\.venv`**, not `..venv`.

Optional editor improvement: install Microsoft's Python extension, then use **Ctrl+Shift+P > Python: Select Interpreter** and select `.venv\Scripts\python.exe`.

### 4.3 Create local configuration

**PowerShell:**

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Open `.env` in VS Code. These settings should be present:

```dotenv
DJANGO_DEBUG=1
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
DATABASE_URL=postgres://atelier:atelier@127.0.0.1:5432/atelier_form
```

Keep the other example settings. The default mock payment provider supports checkout without moving money. A blank `DJANGO_SECRET_KEY` is supported locally: Django generates a temporary key, so restarting may require signing in again.

| Connection-string part | Meaning |
|---|---|
| First `atelier` | Database username used by Django. |
| Second `atelier` | Its local development password. |
| `127.0.0.1:5432` | PostgreSQL on this laptop. |
| `atelier_form` | Database name. |

These published development values are for local use. Your private `postgres` administrator password is different and does not go in this connection string.

### 4.4 Create the database login and database

We use PostgreSQL's terminal, so no pgAdmin Execute button is needed.

**PowerShell:**

```powershell
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -h 127.0.0.1 -p 5432 -U postgres -d postgres
```

Adjust `17` or the folder if your installation differs. The leading `&` tells PowerShell to run the quoted program path.

At `Password for user postgres:`, enter the password chosen during installation. Characters will not appear while typing. Press Enter.

When the prompt is **`postgres=#`**, run these **SQL statements separately**, pressing Enter after each:

```sql
CREATE ROLE atelier LOGIN PASSWORD 'atelier' CREATEDB;
```

Expected: `CREATE ROLE`.

```sql
CREATE DATABASE atelier_form OWNER atelier;
```

Expected: `CREATE DATABASE`. Making `atelier` the owner lets Django create tables. `CREATEDB` also allows Django to create a separate test database when needed.

Return to PowerShell by entering:

```text
\q
```

The prompt should begin with `PS` again. See the [official psql reference](https://www.postgresql.org/docs/17/app-psql.html) for terminal commands.

If a role/database already exists, or you forgot the password, use Section 9 rather than deleting anything.

### 4.5 Verify the app's database login

**PowerShell:**

```powershell
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -h 127.0.0.1 -p 5432 -U atelier -d atelier_form -c "SELECT current_user, current_database();"
```

This time enter **`atelier`**, the app's local database password. Expected output includes `atelier` and `atelier_form`. Fix this login before proceeding if it fails.

### 4.6 Create tables and load demo data

**PowerShell; run each line separately:**

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed
```

Expected: no system-check issues; migrations marked `OK` or none left to apply; a seed summary listing products and demo accounts. This version seeds 21 products.

`check` alone does not verify the database connection. Successful migrations and the health page provide additional verification.

Seed updates demo records when run again. Use it for initial setup or intentional refreshes, not every morning. Avoid `seed --flush`: it deletes commerce data.

### 4.7 Download photographs

Photographs are stored in PostgreSQL. The repo includes placeholder illustrations, but a fresh database does not automatically contain Vercel's photographs.

**PowerShell:**

```powershell
.\.venv\Scripts\python.exe manage.py fetch_images
```

This uses the project's Openverse integration and needs internet access. No image-search key is required by the current implementation. Downloads may take a while.

Read the final counts of stored images and remaining placeholders. Some downloads may fail even if the command finishes. Rerunning the same command skips slots already filled; avoid `--refresh` unless intentionally replacing images.

You can begin coding with placeholders. Note any failed downloads for the meeting. Local search results may differ from Vercel's photographs; attribution is available at `/credits/`.

### 4.8 Start Django

**PowerShell:**

```powershell
.\.venv\Scripts\python.exe manage.py runserver
```

Wait for:

```text
Starting development server at http://127.0.0.1:8000/
```

**Leave this terminal open.** It is running the website and showing request logs. Use a second terminal for other commands. Press **Ctrl+C in the server terminal** to stop it.

## 5. Open the links and test the shop

One running Django server provides all five pages:

| Page | Local link | Successful result |
|---|---|---|
| Frontend | [Open the shop](http://127.0.0.1:8000/) | Homepage loads; products can be browsed. |
| API docs (Swagger) | [Open API docs](http://127.0.0.1:8000/api/docs/) | Interactive page lists API operations. Documentation assets may need internet access. |
| OpenAPI schema | [Open schema](http://127.0.0.1:8000/api/schema/) | API information appears or downloads as a file; this is expected. |
| Health | [Check health](http://127.0.0.1:8000/api/health/) | Both `status` and `database` say `ok`. |
| Django admin | [Open admin](http://127.0.0.1:8000/admin/) | Administrator sign-in page loads. |

Expected health response:

```json
{"status":"ok","database":"ok"}
```

### Local demo accounts

Created by local `seed`; they do not automatically exist on Vercel.

| Role | Email | Password | Sign-in location |
|---|---|---|---|
| Customer | `customer@atelierform.test` | `demo-customer-2026` | [Website sign-in](http://127.0.0.1:8000/account/login/) |
| Seller | `seller@atelierform.test` | `demo-seller-2026` | [Website sign-in](http://127.0.0.1:8000/account/login/), then [seller dashboard](http://127.0.0.1:8000/seller/) |
| Admin | `admin@atelierform.test` | `demo-admin-2026` | [Django admin](http://127.0.0.1:8000/admin/) |

Website passwords are different from both PostgreSQL passwords. Sign out between roles or use separate browser profiles so sessions do not get mixed up.

### Try the application

1. Open the homepage and a product page.
2. Sign in as customer and add a product to the bag.
3. Complete checkout using the development payment simulator; it moves no money.
4. Find the confirmation page and the order in your order history.
5. Sign in as seller and open the dashboard. Some seller editing features remain unfinished; see `OUTSTANDING_TASKS.md`.
6. Sign in to Django admin and confirm that products and orders are listed.

## 6. Everyday coding

### Start work tomorrow

Open the repo folder in VS Code, open PowerShell there, and run:

```powershell
.\.venv\Scripts\python.exe manage.py runserver
```

PostgreSQL's Windows service must be running, but pgAdmin does not need to be open. You do not reinstall packages, recreate the database, or seed it every day.

### Where code lives

| Task | Starting point |
|---|---|
| Page structure and text | `frontend/templates/frontend/` |
| CSS, browser JavaScript, placeholders | `frontend/static/frontend/` |
| Page handling and forms | `frontend/views.py` |
| Frontend data access | `frontend/services.py` |
| Accounts, products, orders, payments, reviews | The matching folder under `backend/` |
| Initial demo content and static copy | `frontend/mockdata/`; seed changes may require an intentional reseed to update existing records |
| URL routing and configuration | `backend/config/` |
| Prioritised team work | `OUTSTANDING_TASKS.md` |

The frontend is served by Django; there is no separate `npm run dev` server. `staticfiles/` is generated output: edit source assets under `frontend/static/`.

For your first change, create a branch using Section 7. Ask Codex to find one visible sentence on the homepage, explain the template, and change only that sentence. Save, refresh the local page, and inspect the change in VS Code's Source Control panel.

Templates usually update on refresh; the development server reloads most Python changes. Restart it after `.env` changes. For cached CSS/JavaScript, try **Ctrl+F5** in your browser.

### After getting new team code

Preserve or commit your current work before pulling. If `requirements.txt` changed, run:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Apply new migrations:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
```

When intentionally changing a model, ask Codex to create and inspect the appropriate migration. Commit the model and migration together. Do not delete migrations to resolve an error.

## 7. Share changes with Git

Agree on one shared repo, a base branch, and who reviews and deploys. These examples assume the base branch is `main`; use your team's actual branch if different.

| Term | Meaning |
|---|---|
| Branch | A named line of work for one task. |
| Commit | A saved snapshot of selected code changes on your computer. |
| Push | Upload commits to GitHub. |
| Pull | Bring shared commits into your local branch. |
| Pull request (PR) | Ask teammates to review and merge your branch. |

### Set your identity once in this repo

Replace the name and email. You can use the no-reply email in your GitHub account settings.

```powershell
git config user.name "Your Name"
git config user.email "YOUR-GITHUB-EMAIL"
```

### Start a task

Run `git status` first. If you have uncommitted work, finish or save it before switching branches; do not discard it just to make these commands pass.

```powershell
git status
git switch main
git pull --ff-only
git switch -c yourname/homepage-copy
```

Replace the last name with a unique branch for your task.

### Review, commit, and share

After editing and checking the affected pages:

```powershell
git diff
.\.venv\Scripts\python.exe manage.py check
git diff --check
```

These checks do not replace browser testing. For behavior changes, ask Codex to find and run relevant tests, or add meaningful tests when needed. A run discovering zero tests does not prove the feature works.

Stage only intended files. This example assumes you edited the homepage template:

```powershell
git add frontend/templates/frontend/home.html
git diff --cached
git commit -m "Clarify homepage introduction"
git push -u origin yourname/homepage-copy
```

Use your actual files, branch, and message. The staged diff should not include `.env`, credentials, `.venv`, database exports, generated assets, or unrelated work.

On GitHub, create a pull request from your branch into the agreed base branch. Explain the problem, resulting behavior, and how you tested it. Get a teammate's review before merging. Private repo access requires accepting the owner's invitation and signing in when Git prompts.

If Git reports conflicts or `--ff-only` fails, ask Codex to inspect the branch state while preserving everyone's work. Do not force-push or use `git reset --hard` as a routine fix.

**Git shares code, not database contents.** Admin edits on your laptop do not appear on another laptop. Teammates apply migrations and create their own demo data.

Vercel may automatically deploy connected branches after pushes or merges. Confirm which branch affects production before sharing changes.

## 8. Copy-and-paste Codex prompts

Specify one task, expected behavior, and how success should be checked. Read the resulting diff so you can explain your change.

### Learn before editing

```text
Explain how a browser request reaches a Django view, reads a model, and
renders a template in this repo. Use one real product page as an example
and show the relevant files. Explain unfamiliar terms simply. Do not
change code yet.
```

### Implement an agreed task

```text
Our agreed task is: [one task from OUTSTANDING_TASKS.md].
Expected behavior: [what the user should be able to do].
Inspect the implementation first. Preserve the Django/PostgreSQL design
and related behavior. Make the change locally, explain the changed files,
and run appropriate checks. Tell me how to verify it in the browser.
Do not deploy or push changes.
```

### Diagnose an error

```text
I ran: [exact command]
In this folder: [project path]
I expected: [result]
I got: [error with private passwords/tokens removed]

Find the cause using this repo and local environment. Explain it simply,
apply the smallest appropriate fix, and verify it. Preserve existing data
and unrelated changes. If you need my input, explain which window to use.
```

### Prepare for review

```text
Review my current Git diff for [task]. Check for bugs, missing validation,
unintended changes, and secrets. Run appropriate checks and report what
was actually tested. Draft a short PR description with the problem,
resulting behavior, and verification. Do not push or merge.
```

## 9. Troubleshooting

### Commands and installation

| Symptom | Next step |
|---|---|
| `py` or `git` not recognized | Install the tool, reopen VS Code/PowerShell, and check its version again. |
| `.venv` Python not recognized | Confirm `Test-Path .\manage.py` is `True`, create `.venv` if missing, and use `.\.venv\Scripts\python.exe`. |
| Terminal in `C:\Windows\System32` | Open the repo in VS Code and start a new terminal there. |
| `No module named django` | Install `requirements.txt` using `.venv`'s Python, not another Python installation. |
| Pip update notice | `[notice]` is informational. Look for actual `ERROR` lines to decide whether installation failed. |
| Package download/certificate error | Check connectivity and ask Codex to diagnose the precise error. Do not disable certificate verification or randomly change pinned versions. |
| `psql` not recognized | Use the full quoted path and leading `&` from Section 4.4. |

### Database errors

**The two database accounts are different:** `postgres` administers PostgreSQL; `atelier` is Django's login. Resetting one does not reset the other. Neither is a website account.

For `password authentication failed for user "atelier"`, connect as `postgres` using Section 4.4. If `atelier` is this project's existing local role, make its password match the guide:

```sql
ALTER ROLE atelier WITH LOGIN PASSWORD 'atelier' CREATEDB;
```

If the role does not exist, use Section 4.4's `CREATE ROLE` instead. Retest Section 4.5 afterward.

If the database already exists, do not delete it. Try the login check and migrations. For `permission denied for schema public`, ask Codex to inspect database ownership and grants. Existing tables may also need ownership checks; avoid permission changes to unrelated databases.

If the connection is refused entirely, check the service:

```powershell
Get-Service -Name '*postgres*'
```

Expected: `Running`. If stopped, open Windows **Services**, find your PostgreSQL service, and start it; administrator permission may be needed. A password error means the server responded, so reinstalling it is not the first fix.

For a missing table/relation, run `manage.py migrate`. For missing demo products, check that seed completed on the local database.

### Forgotten administrator password

Try pgAdmin once in case it has a saved connection. If it also asks for an unknown password, use this prompt instead of repeatedly guessing or reinstalling over existing data:

```text
I forgot the postgres administrator password for my own local PostgreSQL.
Help recover access without deleting databases or changing the deployed
site. Inspect the service, data directory, and authentication configuration.
Explain the recovery action and obtain required system permissions.
Let me enter a new password privately.

If temporary authentication changes are needed, limit them to the local
postgres connection, back up the original configuration, and restore it
immediately after opening the recovery connection, including on failure.
Verify password authentication is required again. Do not leave trust
enabled or put passwords into chat or repository files.
```

Recovery may involve `pg_hba.conf`, an existing login-configuration file to open, not a new file containing its path. Temporary `trust` rules bypass passwords and must be removed. See [PostgreSQL's authentication-file documentation](https://www.postgresql.org/docs/17/auth-pg-hba-conf.html).

### Pages, accounts, and photographs

| Symptom | Next step |
|---|---|
| Site cannot be reached | Start `manage.py runserver` and inspect its terminal for errors. Opening pgAdmin is not enough. |
| Port 8000 already in use | Check whether your earlier server works. Stop it with Ctrl+C in its terminal, or run `manage.py runserver 8001` and change every local URL to port 8001. |
| Health reports database unavailable | Inspect the server error and check the local database login. |
| Demo login fails | Check you are on `127.0.0.1`, using the correct role/password, and seed completed. PostgreSQL roles are not website accounts. |
| Customer cannot enter admin | Use the admin demo account at `/admin/`; customer/seller accounts use `/account/login/`. |
| Illustrations instead of photographs | Run `fetch_images`, check remaining placeholders, and restart Django if freshly fetched photos do not appear. |
| Broken images instead of placeholders | Check image/static request errors. Ask Codex to inspect the actual URL and asset resolution. |
| Schema downloads a file | Expected. Use `/api/docs/` for interactive documentation. |
| CSS changes do not appear | Save, use Ctrl+F5, and check you edited `frontend/static/`, not generated `staticfiles/`. |
| Vercel lacks your local change | Expected until code is shared and deployed through the team's workflow. |

## 10. Before the team meeting

### Each teammate's checklist

- [ ] I can open the agreed repo and identify `manage.py`.
- [ ] Python reports 3.12, Git works, and `.venv` packages are installed.
- [ ] My `.env` points to a local database, not production.
- [ ] PostgreSQL runs and the `atelier` login works.
- [ ] Migrations and initial seeding completed.
- [ ] I can start and stop Django myself.
- [ ] All five links work; health reports `database: ok`.
- [ ] I can sign in as customer, seller, and admin in the appropriate places.
- [ ] I completed a mock checkout and found the order afterward.
- [ ] Photos loaded, or I have noted remaining download issues.
- [ ] I can make a small change, refresh, and explain the Git diff.
- [ ] I read `OUTSTANDING_TASKS.md` and have a task or question to discuss.
- [ ] I know how to create a branch and request review before merging.

Send this update to the team without passwords:

```text
Name:
Operating system:
Python / PostgreSQL versions:
Shared branch and commit (git rev-parse --short HEAD):
Homepage and health working: yes / no
Demo logins and checkout tested: yes / no
Photographs or remaining placeholders:
Setup blocker, if any:
Task I would like to discuss:
```

### Team owner's preparation

- Share the agreed repo URL, access invitations, and this guide.
- Pick a base branch and known starting commit so everyone begins with the same code.
- Confirm which branches trigger Vercel deployments and who merges/deploys.
- Share source through Git, not a laptop folder containing credentials, `.env`, `.venv`, or production database exports.
- Ask everyone to complete setup and send their readiness update before the meeting.

### Suggested first session

| Time | Activity |
|---|---|
| First 10 minutes | Everyone starts their app and shows the healthy database response. |
| Next 10 minutes | Walk through customer checkout, seller dashboard, and admin together. |
| Next 10 minutes | Review `OUTSTANDING_TASKS.md`; choose small tasks with clear owners and dependencies. |
| Remaining time | Work on separate branches, review changes, and agree on the next check-in. |

Assign one owner per task. Agree before editing the same feature or creating competing migrations. Complete required buyer/seller workflows before expanding into optional features.

---

Checked against this repo's configuration and commands on 8 September 2026. Dependency checks, migrations, seeding, and the five endpoints were verified on the maintainer's Windows setup; this does not mean every fresh Windows installation was tested. Installer and Codex interfaces can change; consult the linked official documentation if a screen differs.

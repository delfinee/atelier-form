# Repository cleanup report

Date: 26 October 2026. Baseline: `544c3e6a979e7e903f623c7aa14b0bf0edbed23e` (`Ship hosted seller demo and refine shopping assistant`). Branch: `chore/atelier-form-repo-cleanup`.

## Scope and repository audit

The initial working tree was clean. GitHub metadata identified `main` as the default branch, and a remote HEAD check matched the local baseline before branching. No commit, push or merge was performed.

The audit covered the tracked file inventory, all root documentation, nested operational documentation, requirements, settings profiles, URL maps, launcher scripts, test inventory, payment/recommendation/messaging services, seller views, localisation coverage, deployment manifests and ignore rules. No applicable `AGENTS.md` or tracked `.github` workflow was found. Local private environment values were not printed or used for validation.

The old README incorrectly described seller editing, recommendations, messaging, password reset and Stripe integration as absent. The old task tracker mixed historical deployment claims with tasks already implemented. Current guides now distinguish source evidence, optional providers, synthetic demos and release approval.

## File decisions

| File(s) | Action and reason |
| --- | --- |
| `README.md` | Rewritten as a concise current overview, architecture, local quick start, configuration, testing, deployment scope and documentation entry point. Removed stale charter links and unsupported historical performance/status claims. |
| `BEGINNER_SETUP.md` | Rewritten as the development guide, retaining its filename. Preserves Windows PostgreSQL setup, troubleshooting and Git workflow; removes AI prompts, exercises and meeting logistics. Uses the tracked environment sample with explicit keyless local overrides. |
| `OUTSTANDING_TASKS.md` | Replaced old checkboxes with a task-by-task reconciliation and concrete acceptance evidence still needed. |
| `HANDOVER_MIN_SELLER_DASHBOARD.md` | Moved to `docs/archive/`; retains the original API/UI handover and team attribution, with a historical notice. Seller implementation now exists. |
| `BOHAN_CHATBOT_REVIEW_HANDOVER.md` | Moved to `docs/archive/`; preserves review findings for an earlier branch without presenting them as today's messaging status. |
| `JUNJIE_LOCALISATION_CODE_REVIEW_HANDOVER.md` | Moved to `docs/archive/`; preserves translation review and architectural guidance. Current helpers and extensive tests supersede its missing-test claims. |
| `SELLER_FRONTEND_REVIEW.md` | Moved to `docs/archive/`; preserves review/ownership evidence. Current fulfilment guards and transactional editor writes supersede several old findings. |
| `TEAM_ACCEPTANCE.md` | Retained at root with a historical notice. It contains unique acceptance evidence and is referenced by `launch_seller.py`; moving it would require a functional-script edit or compatibility stub. |
| `SELLER_WECHAT.md` | Retained API/linking instructions; labelled dated delivery evidence and corrected the “current” acceptance link description. |
| `SELLER_PHONE.md` | Retained real-phone procedure/evidence; labelled historical results and replaced one machine-specific invocation with root-local Python/environment paths. |
| `INTEGRATION_NOTES.md` | Preserved integration provenance and unique module boundaries; added a current-status pointer. |
| `UNIFIED_DELIVERY.md` | Preserved operational instructions; clarified that base buyer AI defaults are off while the tracked environment sample enables the switch. |
| `RELEASE.md` | Preserved deployment/release procedure; reconciled contradictory AI privacy wording with the existing optional DeepSeek configuration. |
| `WINDOWS_SELLER.md` | Intentionally retained unchanged: distinct hosted-demo and Windows build instructions. |
| `desktop/windows/README.txt`, `deploy/PUBLIC-DEMO.txt` | Intentionally retained unchanged: packaging/user instructions and earlier demo operations are still useful. |
| `docs/README.md`, `docs/REPOSITORY_RENAME.md`, this report | Added navigation, precise rename follow-up and a reviewable audit record. |

No content-bearing document was discarded. The four old root paths disappear only because their full contents are archived, with an added notice. Before moving them, tracked repository references were searched across source, scripts, configuration, tests and documentation; only the localisation review's textual reference to the seller review was found. Those documents remain adjacent in the archive. Root operational paths referenced by scripts were retained. New archive links use paths appropriate to their location.

All source code, migrations, dependencies, tests, scripts, deployment configuration, assets, `.agents`, `skills-lock.json`, local environments and generated directories were retained. No generated clutter was deleted: it may support local deployment or handover, and none was established as safely disposable. No database migration, seed, reset or production write was performed during cleanup.

## External state and rename

The GitHub repository is **not yet renamed**. Admin access was confirmed, but the connected toolset has no repository rename operation and `gh` is unavailable. Follow [the exact manual steps](REPOSITORY_RENAME.md). The local origin remains unchanged until the rename succeeds.

Local Vercel metadata names project `dip-new-repo`. Inspecting that project through the connector returned HTTP 403 for the linked team. Live Git integration, project build settings, deployment hooks, branch protections and external webhook consumers are therefore unverified. No external integration was changed.

Public web-tool requests to `https://dip-new-repo.vercel.app`, its `/api/health/`, and `https://demo.maijiax.cn` could not retrieve the pages. This is inconclusive access evidence, not proof that the applications are down. README links are explicitly labelled as previously documented addresses; live functionality, exact database contents and production photo counts were not certified.

## Validation

| Check | Result |
| --- | --- |
| Documentation scope and archive comparison | Passed: all changed/new files are Markdown; all four archive bodies exactly match their originals after excluding the added historical notice. |
| Local documentation links | Passed: 63 relative link targets resolve in changed/new documents. |
| Python syntax | Passed: all 240 tracked Python files parsed with AST without writing bytecode. |
| Git diff whitespace check | Passed. Git reports only normal LF/CRLF conversion notices. |
| Remote default branch and HEAD | Passed: `main` matched the local baseline before creating the cleanup branch. |
| `.venv` dependency consistency (`python -m pip check`) | Passed: no broken requirements. No dependencies installed or changed. |
| Django `manage.py check` | Passed: no issues. Explicit local connection settings, a nonexistent temporary env-file path, debug mode and disabled LLM flags prevented use of private production configuration. This check does not prove database connectivity. |
| `node --test miniprogram/tests/privacy.test.cjs` | Passed: 4 tests, 0 failures; WeChat/network calls are mocked. |
| `manage.py test frontend.test_catalogue_i18n --settings=config.marketplace_test --noinput` | Failed: 129 tests, 21 error events (including subtests). Missing manifest entries for `frontend/css/site.css`, recommendation request fixtures without `session`, and a cascading unbound `html` variable were reported. No test database was created by this suite. |
| Full PostgreSQL suite, browser E2E, native/Windows builds and live-provider flows | Not run. This documentation-only audit did not create/reset databases, collect/replace existing assets, deploy or spend provider quota. |

The setup guide now documents test-profile static collection as a prerequisite. The failing localisation tests and application files are unchanged, so those errors are not caused by documentation edits; they remain separate follow-up work. No passing full-suite result is claimed.

## Separate findings retained for follow-up

- Root `.env.example` is tracked despite overlapping ignore patterns. Existing ignore configuration was retained; the setup guide copies the sample only when `.env` is absent and explicitly disables optional AI for keyless local work.
- `frontend/views_seller.py` still uses interpolated gettext strings such as `_(f"Product '{product.name}' was created successfully.")`; translation extraction quality warrants a separate localisation change.
- Test profiles inherit environment/database configuration. Their names alone do not guarantee isolation; the new guide makes the local-database requirement explicit.
- Historical phone/archive evidence files named in operational notes are not all present in this repository. Their dated claims are preserved as provenance, not independently reproduced results.
- The localisation run exposed stale recommendation fixtures (`SimpleNamespace` requests lack `session`) and a template-test static-manifest prerequisite. Investigate these in a separate test/implementation change; see the validation results above.
- Real payment, email, WeChat publication, fluent-language review and end-to-end browser acceptance need separate verification. No unrelated application bug was changed.

## Owner actions

Review the complete uncommitted diff, complete the GitHub rename and integration checks, and authorize any subsequent commit/push separately. Record fresh browser/staging/phone acceptance before treating historical delivery results as current. Application endpoints, internal package/database names and local compatibility paths should not be renamed cosmetically.

# Outstanding Tasks

Last reviewed: 6 September 2026.

## Recommended delivery order

2. Finish the seller dashboard and per-seller fulfilment workflow.
3. Add a complete browser end-to-end buyer-to-seller test.
4. Complete Simplified Chinese localisation.
5. Deploy and verify a staging build.
6. Complete account workflow and production polish.
7. Attempt Could-tier features only if the earlier items pass.

### P1 — Required product work

- [ ] Finish the seller dashboard browser experience:
  - [ ] Add product create and edit forms.
  - [ ] Add product image management.
  - [ ] Add variant, price and stock management.
  - [ ] Add seller order detail pages.
  - [ ] Let sellers update their fulfilment status, carrier and tracking number.
- [ ] Model fulfilment per seller rather than only at the whole-order level.
- [ ] Add one complete browser end-to-end test:
  - [ ] Buyer signs in or registers.
  - [ ] Buyer adds a product and completes checkout.
  - [ ] Buyer completes the mock WeChat Pay flow.
  - [ ] Seller signs in and sees the correct order lines.
  - [ ] Seller updates fulfilment and tracking.
  - [ ] Buyer sees the updated order state.
- [ ] Complete Simplified Chinese localisation:
  - [ ] Translate remaining templates and validation messages.
  - [ ] Translate static page copy.
  - [ ] Translate seeded catalogue, maker, FAQ and journal content.
  - [ ] Add appropriate Chinese address and phone validation.
  - [ ] Have a fluent speaker review the final translations.
- [ ] Complete the frontend account workflow:
  - [ ] Add a change-password form using the existing API behaviour.
  - [ ] Add password-reset token, confirmation and completion pages.

### P2 — Could-tier features

- [ ] Add in-app order and fulfilment notifications.
- [ ] Add seller analytics using existing product and order data.
- [ ] Add popularity- or content-based product recommendations that need no
      external AI provider.
- [ ] Add buyer-seller threaded messaging using ordinary HTTP polling.

## Can be started after a team decision

| Decision                     | Practical options                                                   | Why it blocks final implementation                                                               |
| ---------------------------- | ------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| Multi-vendor order structure | Seller sub-orders; per-seller fulfilment records                    | The current cart creates one order, while sellers need independently tracked work.               |
| Payment splitting            | Stripe Connect; demonstration-only settlement ledger                | The choice changes the data model, provider flow and what the demo promises.                     |
| Chat transport               | HTTP polling; Django Channels/WebSockets                            | WebSockets add Redis and deployment complexity. Polling is the recommended project-scale option. |
| Chinese search               | Existing `ILIKE`; `pg_trgm`; `zhparser`/`pg_jieba`; external search | Each option has different search quality and infrastructure requirements.                        |
| Recommendations              | Popularity/content-based; external AI provider                      | The approach determines whether credentials, usage limits and evaluation data are needed.        |
| Could-tier scope             | Include selected features; formally defer them                      | The Must-tier flow should be complete before optional work begins.                               |

Recommended defaults for the student demonstration are seller sub-orders or
per-seller fulfilment records, a manual settlement ledger, polling-based
messaging, the documented `ILIKE` search fallback, and popularity/content-based
recommendations.

## Blocked on accounts, credentials or external material

These cannot be completed independently from the current workspace.

| Task                                 | Required input or access                                                                                                                                                                                     |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Real Stripe WeChat Pay               | Eligible Stripe/merchant account, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` and an approved settlement design                                                                                             |
| Transactional email delivery         | Resend, SendGrid or SES account, API key and preferably a verified sending domain                                                                                                                            |
| Cloud image storage                  | S3, Cloudinary or equivalent account, bucket/configuration and credentials. Only needed once `imagery_siteimage` makes `pg_dump` unwieldy.                                                                   |
| Public staging/production deployment | A Vercel account and a Neon (or equivalent pooled) Postgres. Config is committed — `vercel.json`, `api/index.py` and the Deployment section of the README. Both free tiers, so no budget approval is needed. |
| Custom domain                        | Purchased/approved domain and DNS access                                                                                                                                                                     |
| Commissioned product photography     | Supplied and licensed studio assets. Openly licensed stand-ins are in place and legally usable, but they photograph other people's pieces, not ours.                                                         |
| Production legal/regulatory review   | Team/business decisions and qualified legal review                                                                                                                                                           |

The local mock payment provider, console notification sender and the generated SVG
fallbacks keep the application fully runnable while these integrations remain
unavailable.

## Blocked on official team or supervisor input

- [ ] Supply every member's full name and matriculation number.
- [ ] Identify the TA and complete the stakeholder register.
- [ ] Assign requirement, milestone, risk and RACI owners.
- [ ] Confirm the cost estimates, contingency and review cadence.
- [ ] Supply the PyShop baseline repository URL, licence and baseline feature list.
- [ ] Record the approved web-platform deviation date and rationale.
- [ ] Obtain the supervisor's approval/signature.
- [ ] Supply the editable charter source so the official document can be revised
      cleanly; only the PDF is currently present.

## Charter/report work that can be drafted now

- [ ] Add the Deviation from Original Project Brief section.
- [ ] Add Out of Scope and Assumptions & Constraints sections.
- [ ] Add MoSCoW priority and acceptance-criterion columns to the requirements.
- [ ] Repair the RACI structure so every activity has exactly one Accountable
      person; insert final owners when the team supplies them.
- [ ] Draft the stakeholder register and approval/sign-off block.
- [ ] Rebuild the risk register with likelihood, impact, owner, mitigation,
      contingency and status columns.
- [ ] Draft a numerical cost table, including approximately 15% contingency.
- [ ] Add owners, definitions of done, dependencies and slack to the milestones.
- [ ] Add a table of contents, version history, architecture diagram and ERD.
- [ ] Standardise payment terminology, rename "chatbot" to buyer-seller messaging,
      and consistently use British spelling for "fulfilment".

Drafts can be prepared without external services, but names, ownership, costs,
approval claims and signatures must not be invented.

## Definition of project-ready

The project is ready for its assessed demonstration when:

- [ ] All Must-tier acceptance criteria pass.
- [ ] The automated test suite and remote CI pass.
- [ ] The complete buyer-to-seller browser test passes.
- [ ] The English and Simplified Chinese primary flows have been reviewed.
- [ ] A staging deployment is healthy and a tested local fallback is available.
- [ ] No production secret is committed.
- [ ] The demo uses sandbox/mock payments and clearly states that no real money
      moves.

# Buyer and seller integration for team review

This work is based on `delfinee/dip-new-repo-test` main at
`83e1a9e2c9b5adee209e78bc1a4b8dd1a52a14d8`. Review the feature branch against main;
do not replace main with an exported folder or the older customer-service branch.

## Existing group work retained

- Bohan's buyer/seller messaging widget and backend are retained. The shopping
  assistant is a separate component, not a replacement for human messaging.
- Existing recommendations, account flows, product models, checkout, payments,
  reviews and per-seller fulfillment services are reused without changes to their
  implementation files. Seller operations call the existing fulfillment service.
- Every existing Simplified Chinese compiled translation is retained unchanged;
  the new buyer and Mini Program entry copy adds translations to the same catalogue.
- The original default website routing remains in `config.urls`. The optional
  `config.marketplace_*` entry points present the buyer website with seller Mini
  Program handoffs; they do not remove the group's seller dashboard from the
  default application.
- Existing handover/review documents and contributor commit history are retained.

## Added feature modules

- `concierge`: buyer product discovery, factual price/review comparisons and
  session-owned multi-turn filtering. The earlier customer demo remains guarded
  behind explicit demo configuration.
- `seller_agent` and `miniprogram`: linked seller identity, owner-scoped products
  and orders, proposed changes, explicit confirmation, expiry and retry handling.
- Seller image uploads reuse the existing product editor and database image store.
- Optional DeepSeek interpretation supports English/Chinese requests, follow-ups
  and seller advice. Model output cannot confirm a write, grant access, process
  payment or bypass the existing business rules. Exact quick actions work offline.
- Separate synthetic public demos and deployment/start scripts are included.
  No changes to the existing Vercel deployment configuration are required.

## Runtime configuration and review

No `.env`, real API key, WeChat AppSecret, SSH credential, database dump or local
runtime folder belongs in this branch. Set private credentials on the server.
External model calls are off by default; tests mock them. The public demo can opt
in using the settings documented in `deploy/PUBLIC-DEMO.txt`.

The existing shared demo URL is operated separately from GitHub; publishing this
branch does not restart its tunnel or deploy over another contributor's instance.
Native WeChat public release remains subject to the separate platform process.

Suggested verification:

```text
python manage.py test concierge sellerdesk seller_agent accounts products orders payments reviews recommendations messaging frontend imagery --settings=config.marketplace_test --noinput
node --test miniprogram/tests/privacy.test.cjs
python manage.py makemigrations --check --dry-run --settings=config.marketplace_test
```

Use a local test database for these commands. See `UNIFIED_DELIVERY.md` for startup
and `SELLER_WECHAT.md` for seller integration details. Merge through a reviewed PR;
do not force-push the shared main branch.

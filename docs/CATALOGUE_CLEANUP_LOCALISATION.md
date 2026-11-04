# Catalogue cleanup and localisation

Audit date: 4 November 2026 (Asia/Singapore). Branch: `fix/catalogue-cleanup-localisation`, created after fetching and fast-forward checking `origin/main`.

## Root causes and changes

- `localize_product()` accepted only seeded slugs. The actual tote is a separate seller-created product, absent from that map. Its PO entry also incorrectly said “Linen Cushion Cover”. `frontend/catalogue_overrides.py` now identifies the verified UUID, slug and maker, and translates only exact reviewed source copy. Edited seller copy and other products are preserved. The PO and compiled MO contain `窗帘布托特包`, short description, description, story, care and dispatch copy. English and database values are unchanged. Existing service consumers cover cards, detail, wishlist payloads, cart and recommendations; product API serializers and exact historical tote snapshots now use the same presentation translation.
- `ProductQuerySet.active()` previously tested only `is_active`. `products/publication.py` centralizes public visibility using exact product UUID/slug/maker triples and the dedicated maker identities. Frontend/API catalogue queries, collection/facet counts, recommendations, assistant search/cached cards and revision markers respect this boundary. Existing carts are revalidated at checkout. No migration or new column is needed.
- Public makers previously used only `is_active`. The exact tester maker and configured School Demo slug are now excluded. The cleanup command deactivates only the tester maker and removes only its owner's seller flag after an explicit owner confirmation. Active-user and active-maker checks strengthen seller API permission checks. Login, buyer access and historical rows remain intact.
- Shared-demo middleware and its unrestricted catalogue workspace are retained. School Demo's maker and user stay active. New products belonging to the configured `SELLER_SHARED_DEMO_SHOP` remain private even if an editor sets `is_active=True`. The existing demo regression now asserts this requirement while still testing stock edits, ownership, CSRF, buyer sessions and parcel workflows.

## Verified production records

Read-only public API calls were cross-checked against SELECT queries on Neon project `autumn-lake-53607230`, production branch `br-shiny-fog-b3nxikbw`. No production rows were changed. The configured local database contains only seed records and was not used as production evidence.

| Product ID | UUID | Slug | Maker ID / slug | Price | Order lines / reviews |
| --- | --- | --- | --- | --- | --- |
| 22 | `676e119f-ff2c-4e51-92df-3de52c05d2b8` | `bh-test-1` | 1 / `chen-meilin` | 221.93 | 0 / 0 |
| 23 | `81653267-3e98-40a0-b76a-11f905d8b537` | `mug` | 6 / `seller-c32d9f22cbea4c78` | 10.00 | 0 / 0 |
| 24 | `a194e3c5-e843-45f5-8637-ad4b5f5f9705` | `mug-2` | 6 / `seller-c32d9f22cbea4c78` | 10.00 | 0 / 0 |
| 25 | `52f7782d-7bc5-4e01-8666-442f66271f13` | `demo-sync-shared-catalogue-cup-86e9b80839` | 7 / `shared-school-demo` | 25.00 | 0 / 0 |

Both mugs have the description `test` and are the only products owned by Maker 6. Public image identifiers are `seller-photo-99e191ebb78448bfb46e935234025e55` (mug) and `seller-photo-6d80588c899b49fa8876f675ac5e597f` (mug 2). The complete database inventory contained 26 products: 21 seed products, these four test products and the tote. No further test-only products were identified.

- Tester: Maker **6**, UUID `24284c9f-1d4a-4d90-ab03-fb5eab3306d1`, slug `seller-c32d9f22cbea4c78`; owner User **8**, UUID `e50e9943-c877-4585-99aa-c0cbcaf1d670`. Approved seller application **1** explicitly links User 8 and Maker 6, with shop/discipline/location all “seller tester”. The user is active and a seller, with no staff/admin/superuser roles. Maker has zero order lines/fulfilments; user has zero buyer orders/authored reviews. This supports treating the seller role as dedicated testing. Preserve the user and application history.
- School Demo: Maker **7**, UUID `52ca46a7-a035-439e-8523-9b8dc04e4da0`; User **9**, UUID `9c64c95b-abeb-47c1-910a-31899dfa4e1f`. Both remain active; seller privileges remain enabled. Zero order lines/fulfilments/buyer orders/reviews at audit.
- Tote: Product **26**, UUID `bfa51b16-2aa1-4546-ae1a-5d84134f89c9`, slug `curtain-tote-bag`, Maker **1** (`chen-meilin`), price 48.00, **three historical order lines**, zero reviews. Never unpublish it. Chen Meilin has 14 order lines and 11 fulfilments overall and remains active.

## Controlled cleanup procedure

Use the reviewed code with the production environment supplied through your normal secure operator mechanism. Do not paste credentials into shell history. This command is not called by builds or migrations.

1. Run `python manage.py cleanup_test_catalogue --dry-run`. This reports exact IDs, ownership, original flags and relationship counts, without writes or row locks. Recheck the audit if anything changed.
2. Obtain approval for production data changes. Confirm User 8 is still the dedicated tester account. Review any additional maker products; the command refuses to apply if there are unreviewed products or a privileged owner.
3. Only after approval: `python manage.py cleanup_test_catalogue --apply --confirmed-owner-id 8 --backup /secure/operator-path/catalogue-before.json`.
4. The transaction sets four products' `is_active=False`, Maker 6's `is_active=False`, and User 8's `is_seller=False`. It does not delete anything, disable login, change application history, alter product text or deactivate School Demo. Identity drift aborts the transaction. Repeating is safe; choose a new backup filename because existing backups are never overwritten.
5. Rerun the dry run and verify customer catalogue/maker pages, original products, checkout and the shared workspace after the separately approved code deployment.

Rollback: retain the **first** backup (repeat-run backups contain already-disabled flags). In an approved database transaction, verify each saved UUID/slug/maker and owner relationship, then restore only the saved `is_active` product/maker flags and `is_seller` user flag, updating timestamps. Do not restore whole tables or overwrite intervening orders, stock or profile edits. The code-level visibility boundary intentionally remains even if flags are restored; undoing that boundary requires a separately reviewed code rollback. A failed transaction may leave a backup file, but rolls back database writes.

## Delivery and deployment

`vercel.json` disables Git-triggered deployments only for this fix branch, following [Vercel's branch configuration](https://vercel.com/docs/project-configuration/git-configuration). This allows a review PR without deploying. Other branch behaviour is unchanged. Do not merge or deploy without approval. A later approved release requires code review, the checks below, confirmation of target project/environment, then the normal deployment procedure. No catalogue schema migration or automatic cleanup is part of this change. Production cleanup is a separate approved operator action.

## Validation

Tests use the existing `config.marketplace_test` settings and an isolated PostgreSQL 17 instance on loopback port 55439. The ordinary local role cannot create test databases; the first attempt stopped before running tests. Missing declared dependencies were installed into the existing virtual environment. Static assets were collected locally. No test ran against production.

Initial targeted run: **184 tests passed** (products cleanup, shared demo, orders, seller onboarding service, frontend product listings, recommendations). Final results are recorded below after the expanded run.

The untouched `origin/main` baseline was extracted into an ignored directory and tested with the same static manifest: `frontend.test_catalogue_i18n` ran 129 tests with **7 failure events and 8 error events**, including subtests. Existing failures concern stale stock/order/error translation expectations; errors concern recommendation fixtures using plain `object()` as a user. These are independent of the tote and privacy changes. Query fixtures were updated for the new public visibility boundary; production visibility has separate database-backed tests.

Expanded final command:

```text
python manage.py test products.test_catalogue_cleanup seller_agent.test_shared_demo orders.tests accounts.test_seller_onboarding_service frontend.test_product_listings recommendations.tests frontend.test_catalogue_i18n concierge.test_shopping concierge.test_display --settings=config.marketplace_test --noinput
```

Result: **345 tests run, 11 failure events and 8 error events**, all in the two legacy localisation/display modules. All **187** tests in the targeted cleanup/shared-demo/orders/onboarding/listings/recommendations modules passed, including seven new cleanup regressions. The same 158 legacy/assistant tests on untouched `origin/main` reproduce exactly the same 11 failures and 8 errors. Standalone localisation is also unchanged: 129 tests, 7 failures / 8 errors on both baseline and this branch. No new failure remains.

Exact existing failing test methods (subtests account for repeated events):

- `concierge.test_display.ShoppingDisplayLanguageTests`: `test_chinese_result_translates_every_display_field_without_changing_records`, `test_custom_product_labels_also_follow_the_selected_language`, `test_reload_repairs_old_cached_messages_without_clearing_history`.
- `frontend.test_catalogue_i18n.CommerceAPIErrorLocalizationTests`: `test_exception_handler_preserves_reference_field_errors_and_status`.
- `frontend.test_catalogue_i18n.OrderDisplayLocalizationTests`: `test_real_order_templates_translate_display_and_preserve_links_prices_and_snapshots`, `test_status_payment_and_delivery_labels_switch_without_changing_codes`.
- `frontend.test_catalogue_i18n.ReviewRatingAndSearchLocalizationTests`: `test_search_page_and_api_accept_localised_presentation_objects` (only in the combined run, due to language-state dependence).
- `frontend.test_catalogue_i18n.ShopLabelLocalizationTests`: `test_availability_ids_and_labels`, `test_language_switching_keeps_display_only_changes`, `test_stock_label_and_unknown_statuses`.
- Erroring methods in `frontend.test_catalogue_i18n.RecommendationAndOrderCountLocalizationTests`: `test_existing_recommendation_template_renders_localised_cards_and_canonical_links`, `test_ranked_recommendations_switch_language_without_mutating_products`, `test_recommendation_tag_keeps_page_gates_and_empty_results`.

`makemigrations --check --dry-run`: no changes detected. `git diff --check`: passed. Compiled MO generated with polib 1.2.0 in the local virtual environment. Cleanup dry-run against the seeded local database passed with no matching production records and no changes. An earlier invocation against the isolated cluster's empty maintenance database failed with missing tables; application tests correctly create/migrate/destroy their own separate test database.

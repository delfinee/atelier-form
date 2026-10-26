> Historical branch review, archived 26 October 2026. Findings and test counts describe the original snapshot, not the current release. See [current status](../../OUTSTANDING_TASKS.md) and [documentation index](../README.md). Source paths below are relative to the repository root.

# Seller Frontend Integration Review

**Branch reviewed:** `feature/samuel-seller-frontend-continuation`  
**Target branch:** `main`  
**Branch tip reviewed:** `612190de57b854c8f1f71f9b425a16f4592f2df9` — `Harden seller frontend workflows`

## 1. Review context

This review checks the continuation of Min's seller frontend work, Samuel's seller fulfilment integration, and the seller regression coverage before merge.

The review is based on source inspection of the live GitHub repository.

**Important:** automated tests have not yet been independently executed by Delfine on this branch, and no GitHub Actions workflow run was found for the reviewed branch tip. Test files and test cases are present, but their current passing status still needs verification.

The branch was observed as:

- 6 commits ahead of `main`
- 1 commit behind `main`
- The commit it is behind is `39d26bf` (`chore: trigger Vercel deployment`), which contains no code diff

## 2. Scope reviewed

Areas reviewed:

- Seller analytics dashboard
- Seller product list
- Seller product creation and editing
- Product variants
- Product images
- Seller order list
- Seller order detail
- Per-seller fulfilment update flow
- Seller isolation in multi-seller orders
- Authentication and permissions
- URL integration
- Seller regression tests

Relevant files reviewed include:

- `backend/config/urls.py`
- `backend/orders/api.py`
- `backend/orders/serializers.py`
- `backend/orders/services.py`
- `backend/orders/models.py`
- `backend/orders/tests/test_seller_api.py`
- `backend/products/models.py`
- `frontend/forms.py`
- `frontend/forms_seller.py`
- `frontend/views.py`
- `frontend/views_seller.py`
- `frontend/tests.py`
- `frontend/tests_seller.py`
- `frontend/templates/frontend/seller/dashboard.html`
- `frontend/templates/frontend/seller/order_detail.html`
- `frontend/templates/frontend/seller/order_list.html`
- `frontend/templates/frontend/seller/product_form.html`
- `frontend/templates/frontend/seller/products.html`

## 3. Positive findings

The branch contains substantial seller frontend work and the latest hardening commit fixes several concrete integration issues.

### URL cleanup

Duplicate seller URL registration was removed.

This reduces the chance of conflicting route names and duplicate seller paths.

### Stock badge values corrected

The seller product page now checks the actual `Product.stock_status` values:

- `low-stock`
- `sold-out`

instead of the incorrect underscore forms.

### Variant SKU handling improved

Automatic SKU generation was removed.

The seller variant form now relies on the existing model rules where SKU is:

- required
- globally unique

Regression tests were added for missing and duplicate SKUs.

### Multi-seller isolation

The seller order list now has regression coverage confirming that, for a shared order, one seller only sees:

- their own items
- their own subtotal
- their own fulfilment information

and does not see another seller's order items.

### Seller order detail security

The seller order detail view scopes the order to the authenticated seller.

The browser-level tests cover:

- anonymous users
- buyers/non-sellers
- access to another seller's order
- shared-order seller isolation
- invalid fulfilment input
- CSRF protection
- missing legacy `SellerFulfillment` rows

### Reuse of existing fulfilment service

The browser form uses:

`orders.services.update_seller_fulfillment()`

instead of duplicating the fulfilment update logic.

This helps keep browser and API behaviour aligned.

## 4. Findings requiring attention

### High priority — non-dispatchable orders can still be fulfilled

The seller dashboard correctly defines **Awaiting dispatch** as an order that is:

- paid
- unfulfilled
- not cancelled

However, the seller order list/detail workflow currently does not enforce the same business rule.

The seller order list is built from all orders containing the seller's items, without filtering by successful payment or cancellation state.

The seller order detail page can also submit fulfilment updates for those orders.

`orders.services.update_seller_fulfillment()` currently validates seller ownership and fulfilment status values, but it does not check whether the order is actually eligible for dispatch.

This means an unpaid, failed, refunded, or cancelled order may still be opened and marked fulfilled through the seller browser flow.

#### Recommended action

Samuel and Yi Jun should confirm the intended business rule and decide where it should be enforced.

Prefer central enforcement if the same rule must apply to both:

- browser fulfilment updates
- seller fulfilment API updates

Regression tests should be added for:

- unpaid orders
- failed-payment orders
- refunded orders
- cancelled orders

**Status:** OPEN

---

### Medium priority — low-stock products without variants are missed

The seller dashboard low-stock query currently checks:

`product_variants__stock_quantity`

However, the product model supports products without variants.

For those products, `Product.stock_quantity` is the authoritative inventory value.

A non-variant product with low stock may therefore have `stock_status = low-stock` but still not appear in the seller dashboard low-stock alert.

#### Recommended action

Add regression coverage for a low-stock product with no variants and update the query so both inventory models are represented correctly.

**Status:** OPEN

---

### Medium priority — seller code remains in shared frontend files

The earlier seller frontend handover recommended keeping seller-specific work primarily in:

- `frontend/views_seller.py`
- seller templates

to reduce conflicts with Delfine's account/review work in `frontend/views.py`.

The current branch still contains major seller logic in:

- `frontend/views.py`
- `frontend/tests.py`

including seller analytics and seller order-detail code.

This is not automatically a functional defect, but it increases overlap with shared files and makes future account/review regression work harder to isolate.

#### Recommended action

Before further seller development, consider consolidating seller-specific views/tests into:

- `frontend/views_seller.py`
- `frontend/tests_seller.py`

where practical.

Avoid unrelated refactoring solely for file organisation if it creates additional merge risk.

**Status:** REVIEW

---

### Medium priority — `is_primary` image selection is not reflected by `primary_image()`

The seller image form exposes an `is_primary` checkbox.

However, `Product.primary_image()` currently returns the first related image based on normal image ordering rather than selecting the row marked `is_primary`.

The product list serializer follows a similar first-image approach.

This can create a mismatch between what the seller selects as **Primary** and which image is actually used as the main product image.

#### Recommended action

Either:

1. update primary-image selection to respect `is_primary`, with a clear rule for multiple checked images, or
2. remove/clarify the checkbox so it does not imply behaviour that is not currently implemented.

**Status:** OPEN

---

### Lower priority — product formset usability

The seller product form currently provides one extra variant row and one extra image row by default.

No dynamic formset JavaScript was identified during this review.

This may mean a seller creating a new product can initially add only one variant and one image, then must save and edit again to add more.

#### Recommended action

Confirm the intended UX manually before deciding whether additional dynamic formset controls are necessary.

**Status:** REVIEW

---

### Lower priority — translation/extraction consistency

Some seller-facing Python strings are plain strings or use interpolated translation calls such as:

`_(f"Product '{product.name}' was created successfully.")`

This style is harder for Django translation extraction than translating a fixed message with placeholders.

The dashboard's period labels are also plain Python strings.

#### Recommended action

Review seller-facing strings as part of the Chinese localisation pass rather than treating this as a seller functionality blocker.

**Status:** REVIEW

---

### Lower priority — product creation is not wrapped in one transaction

The product is saved before the variant and image formsets are saved.

If an unexpected database error occurs while saving a child formset, it is possible for the base product row to remain saved.

#### Recommended action

Consider wrapping product + variant + image writes in `transaction.atomic()` if the team wants all-or-nothing product creation/edit behaviour.

**Status:** REVIEW

## 5. Test coverage present in the branch

Static inspection found substantial seller regression coverage.

Approximate test-method counts found in source:

- Seller dashboard analytics tests: **16**
- Seller order-detail browser tests: **17**
- `frontend/tests_seller.py`: **12**

These numbers describe test methods present in the source.

They are **not proof that the current branch passes all tests**.

## 6. Test verification still required

Before merge, actual commands and results should be recorded.

Recommended minimum verification:

```bash
python manage.py check
python manage.py test frontend
python manage.py test orders
```

If the team has a known full-suite command that is practical to run, run that after the targeted seller tests.

Record the results here:

```text
Environment:
Date:

Command:
Result:
Tests run:
Failures:
Errors:

Command:
Result:
Tests run:
Failures:
Errors:
```

## 7. Suggested merge checklist

- [ ] Confirm expected behaviour for unpaid, failed, refunded and cancelled orders
- [ ] Prevent non-dispatchable orders from being fulfilled if required by the agreed business rule
- [ ] Add regression tests for the above
- [ ] Verify low-stock behaviour for non-variant products
- [ ] Decide whether the `is_primary` image field should affect primary-image selection
- [ ] Run `python manage.py check`
- [ ] Run seller/frontend regression tests
- [ ] Run orders regression tests
- [ ] Record exact test results
- [ ] Run account/review regression checks after integration
- [ ] Update README / outstanding-task documentation if seller frontend is considered complete

## 8. Ownership

| Area | Owner |
|---|---|
| Seller frontend | Min / Samuel |
| Seller fulfilment architecture | Samuel |
| Seller order and fulfilment API | Yi Jun |
| Account/review QA and integration review | Delfine |
| Messaging/chatbot | Bohan |

This review is intended to support integration and QA. It does not reassign seller implementation ownership to Delfine.

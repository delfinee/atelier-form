# HANDOVER — Min: Seller Dashboard Frontend Integration

## 0. Context & Handover Summary

This document is the working handover from **Yi Jun** to **Min** for connecting the **Seller Dashboard UI** to the **Seller Order & Fulfilment API**.

Yi Jun has completed, tested, and verified the API and serialization layer on branch:
`feature/yijun-seller-order-api`

* **Samuel's Backend:** Models (`SellerFulfillment`) & services (`update_seller_fulfillment`) are locked and working.
* **Yi Jun's API Layer:** HTTP endpoints, serializers, permissions, and 25 automated tests are locked and working (69/69 tests passing in `orders`).
* **Min's Scope:** Build the frontend pages and forms in `frontend/` so sellers can view their catalog, inspect incoming orders, and submit tracking numbers through the web interface.

---

## 1. File Boundaries (To Avoid Merge Conflicts)

To make sure Min, Delfine, and Yi Jun never overwrite each other's work:

| Team Member | Allowed / Primary Files | Do NOT Modify |
|---|---|---|
| **Min (Seller Frontend)** | `frontend/views_seller.py` (New)<br>`frontend/templates/frontend/seller/*` | `backend/orders/*`<br>`frontend/views.py` (Delfine working here)<br>`frontend/templates/frontend/account/*` |
| **Yi Jun (Order API)** | `backend/orders/api.py`<br>`backend/orders/serializers.py`<br>`backend/orders/tests/test_seller_api.py` | `backend/orders/models.py`<br>`backend/orders/services.py` |
| **Samuel (Data Architecture)** | `backend/orders/models.py`<br>`backend/orders/services.py` | *(Architecture locked)* |

> **Recommended Organization for Min:**  
> Create a separate `frontend/views_seller.py` and register its routes in `frontend/urls.py` (or route from `views.py`), rather than piling hundreds of lines into `frontend/views.py`. This keeps Delfine's account/review work completely safe from conflicts.

---

## 2. API Contract for Min's Frontend

All seller endpoints require authentication as a seller (`user.is_seller = True` and linked `maker_profile`).  
When browsing in a normal browser session, standard Django session cookies work automatically.

### Endpoint 1: List Seller Orders
* **URL:** `GET /api/seller/orders/`
* **Response format:**
  ```json
  {
    "items": [
      {
        "uuid": "06ff1255-65f9-4c3d-a6a4-4f06ce2ab8e2",
        "order_number": "AF-2026-000001",
        "status": "pending",
        "payment_status": "paid",
        "fulfillment_status": "unfulfilled",
        "customer_email": "buyer@example.com",
        "customer_phone": "+65 8000 0000",
        "placed_at": "2026-09-15T12:00:00Z",
        "seller_subtotal": "96.00",
        "carrier": "",
        "tracking_number": "",
        "items": [
          {
            "id": 1,
            "product_name": "Speckled Breakfast Bowl",
            "variant_name": "Standard",
            "maker_name": "Your Workshop",
            "unit_price": "48.00",
            "quantity": 2,
            "line_total": "96.00",
            "image": "..."
          }
        ],
        "fulfillment": {
          "uuid": "8693eb0d-b51b-4834-b481-92b4355d0fd5",
          "status": "unfulfilled",
          "carrier": "",
          "tracking_number": "",
          "shipped_at": null
        }
      }
    ],
    "page": 1,
    "limit": 20,
    "total": 1,
    "pages": 1
  }
  ```
* **Guarantees:**
  * Only orders that contain items from the logged-in seller are returned.
  * In multi-seller orders, lines from other sellers are already stripped out. `items` only contains products made by the logged-in seller.
  * `seller_subtotal` reflects only this seller's share of the order revenue.

---

### Endpoint 2: Retrieve Single Seller Order Detail
* **URL:** `GET /api/seller/orders/{order_uuid}/`
* **Response:** Single order object matching the schema above.
* **Security:** If an order does not belong to this seller, the endpoint returns **404 Not Found**.

---

### Endpoint 3: Update Fulfilment & Tracking (The Dispatch Form)
* **URL:** `PATCH /api/seller/orders/{order_uuid}/fulfilment/`
* **Headers:**
  * `Content-Type: application/json`
  * `X-CSRFToken: <csrf_token>` (for browser fetch calls)
* **Request Payload (all fields optional):**
  ```json
  {
    "status": "fulfilled",
    "carrier": "SF Express",
    "tracking_number": "SF1234567890"
  }
  ```
* **Allowed `status` values:**
  * `"unfulfilled"`
  * `"partial"`
  * `"fulfilled"`
* **Allowed `carrier` & `tracking_number`:**
  * Strings up to 80 characters.
* **Automatic System Side-effects:**
  * When `status` transitions to `"fulfilled"`, Samuel's backend automatically stamps `shipped_at = timezone.now()`.
  * The parent `Order.fulfillment_status` is automatically recalculated across all sellers on that order.
* **Success Response (HTTP 200):**
  * Returns the updated `SellerOrderSerializer` object with the new carrier, tracking number, and status.
* **Error Responses:**
  * `400 Bad Request` if `status` is invalid or fields exceed 80 chars.
  * `403 Forbidden` if caller is not an authenticated seller.
  * `404 Not Found` if order does not belong to the seller.

---

## 3. Recommended Frontend Integration Patterns for Min

### Option A: Server-rendered Django Form (Recommended for consistency)
In `frontend/views_seller.py`:
```python
@login_required
def seller_order_detail(request, uuid):
    if not request.user.is_seller or not hasattr(request.user, "maker_profile"):
        raise PermissionDenied("A linked seller profile is required.")
    
    order = get_object_or_404(
        Order.objects.filter(items__maker__owner=request.user).distinct(),
        uuid=uuid
    )
    maker = request.user.maker_profile
    fulfillment = get_object_or_404(order.seller_fulfillments, maker=maker)

    if request.method == "POST":
        carrier = request.POST.get("carrier", "").strip()
        tracking_number = request.POST.get("tracking_number", "").strip()
        status = request.POST.get("status", fulfillment.status)

        services.update_seller_fulfillment(
            fulfillment,
            acting_maker=maker,
            status=status,
            carrier=carrier,
            tracking_number=tracking_number,
        )
        messages.success(request, "Fulfilment details updated.")
        return redirect("seller_order_detail", uuid=uuid)

    seller_items = order.items.filter(maker=maker)
    return render(request, "frontend/seller/order_detail.html", {
        "order": order,
        "fulfillment": fulfillment,
        "seller_items": seller_items,
    })
```

### Option B: JavaScript Fetch on the Existing Dashboard
In `frontend/templates/frontend/seller/dashboard.html` or modal:
```javascript
async function updateFulfillment(orderUuid, status, carrier, trackingNumber) {
  const response = await fetch(`/api/seller/orders/${orderUuid}/fulfilment/`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
    body: JSON.stringify({ status, carrier, tracking_number: trackingNumber }),
  });
  if (response.ok) {
    location.reload();
  } else {
    const error = await response.json();
    alert("Update failed: " + (error.detail || "Validation error"));
  }
}
```

---

## 4. Test Verification Checklist for Min

Min can test locally right away using:
* **Server:** `python manage.py runserver`
* **Test Seller Account:** `seller@atelierform.test` / `demo-seller-2026`
* **Test Suite:** `python manage.py test orders` (verify all 69 pass before submitting PR)

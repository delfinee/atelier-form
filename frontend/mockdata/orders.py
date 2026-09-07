"""Mock account data -- orders, addresses and the signed-in customer.

Stands in for the `orders` and `accounts` apps until real models exist. Kept
deliberately small: enough to build and verify every account screen.
"""

from __future__ import annotations

from typing import TypedDict


class Customer(TypedDict):
    first_name: str
    last_name: str
    email: str
    phone: str
    joined: str


CUSTOMER: Customer = {
    "first_name": "Demo", "last_name": "User",
    "email": "paxedappteam@gmail.com", "phone": "+65 8123 4567",
    "joined": "March 2025",
}

ADDRESSES: list[dict] = [
    {"id": "addr-1", "label": "Home", "name": "Demo User", "line1": "18 Nanyang Crescent",
     "line2": "#07-14", "city": "Singapore", "postcode": "637553", "country": "Singapore",
     "phone": "+65 8123 4567", "default": True},
    {"id": "addr-2", "label": "Studio", "name": "Demo User", "line1": "50 Nanyang Avenue",
     "line2": "Block S2, B3b-08", "city": "Singapore", "postcode": "639798",
     "country": "Singapore", "phone": "+65 8123 4567", "default": False},
]

# status: placed | in-production | dispatched | delivered
ORDERS: list[dict] = [
    {
        "id": "AF-2026-1148", "date": "24 August 2026", "status": "dispatched",
        "status_label": "On its way", "total": 214.00, "subtotal": 214.00, "shipping": 0.00,
        "tracking": "SG7742019903CN", "carrier": "SF Express",
        "address": ADDRESSES[0], "delivery_method": "Standard delivery",
        "estimated": "Arriving 3–5 September",
        "timeline": [
            {"label": "Order placed", "date": "24 Aug", "done": True},
            {"label": "Made & packed", "date": "27 Aug", "done": True},
            {"label": "Dispatched", "date": "29 Aug", "done": True},
            {"label": "Delivered", "date": "Expected 3 Sep", "done": False},
        ],
        "items": [
            {"slug": "woven-cotton-throw", "name": "Woven Cotton Throw", "variant": "Indigo",
             "qty": 1, "price": 128.00},
            {"slug": "soy-wax-studio-candle", "name": "Soy Wax Studio Candle",
             "variant": "Cedar & Fig", "qty": 1, "price": 44.00},
            {"slug": "hand-loomed-tea-towel", "name": "Hand-loomed Tea Towel",
             "variant": "Natural", "qty": 1, "price": 26.00},
            {"slug": "ceramic-ring-dish", "name": "Ceramic Ring Dish", "variant": "Bone",
             "qty": 1, "price": 28.00},
        ],
    },
    {
        "id": "AF-2026-0973", "date": "2 July 2026", "status": "delivered",
        "status_label": "Delivered", "total": 168.00, "subtotal": 160.00, "shipping": 8.00,
        "tracking": "SG7741188420CN", "carrier": "SF Express",
        "address": ADDRESSES[0], "delivery_method": "Standard delivery",
        "estimated": "Delivered 9 July",
        "timeline": [
            {"label": "Order placed", "date": "2 Jul", "done": True},
            {"label": "Made & packed", "date": "4 Jul", "done": True},
            {"label": "Dispatched", "date": "5 Jul", "done": True},
            {"label": "Delivered", "date": "9 Jul", "done": True},
        ],
        "items": [
            {"slug": "hand-thrown-stoneware-mug", "name": "Hand-thrown Stoneware Mug",
             "variant": "Clay", "qty": 2, "price": 42.00},
            {"slug": "olive-wood-serving-board", "name": "Olive Wood Serving Board",
             "variant": None, "qty": 1, "price": 72.00},
        ],
    },
    {
        "id": "AF-2026-0612", "date": "18 April 2026", "status": "delivered",
        "status_label": "Delivered", "total": 96.00, "subtotal": 96.00, "shipping": 0.00,
        "tracking": "SG7739003311CN", "carrier": "SF Express",
        "address": ADDRESSES[1], "delivery_method": "Standard delivery",
        "estimated": "Delivered 24 April",
        "timeline": [
            {"label": "Order placed", "date": "18 Apr", "done": True},
            {"label": "Made & packed", "date": "20 Apr", "done": True},
            {"label": "Dispatched", "date": "21 Apr", "done": True},
            {"label": "Delivered", "date": "24 Apr", "done": True},
        ],
        "items": [
            {"slug": "studio-gift-set", "name": "Studio Gift Set", "variant": "Bone",
             "qty": 1, "price": 96.00},
        ],
    },
]

ORDERS_BY_ID: dict[str, dict] = {o["id"]: o for o in ORDERS}

"""Minimal, readable test fixtures for the SellerFulfillment test suite.

No third-party factory library is introduced -- the repository doesn't use
one, and these helpers are small enough not to need it. Each returns a real
saved model instance so tests read as plain Django ORM calls.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model

from orders.models import Cart, Order, OrderItem, OrderNumberSequence, OrderStatus, PaymentStatus
from products.models import Category, Maker, Product

User = get_user_model()

SHIPPING_ADDRESS = {
    "first_name": "Test", "last_name": "Buyer", "address_line_1": "1 Test Street",
    "address_line_2": "", "city": "Singapore", "postal_code": "123456",
    "country": "SG", "phone": "+65 8000 0000", "label": "Home",
}


def make_category(slug="test-category", name="Test Category"):
    return Category.objects.create(slug=slug, name=name)


def make_maker(slug, name, *, owner=None):
    return Maker.objects.create(slug=slug, name=name, owner=owner,
                                discipline="Ceramics", location="Singapore")


def make_seller_user(email, *, first_name="Seller"):
    return User.objects.create_user(email=email, password="test-pass-12345",
                                    first_name=first_name, last_name="Test", is_seller=True)


def make_buyer(email="buyer@example.test"):
    return User.objects.create_user(email=email, password="test-pass-12345",
                                    first_name="Buyer", last_name="Test")


def make_product(*, maker, category, slug, name="Test product", price="20.00", stock_quantity=50):
    return Product.objects.create(
        slug=slug, name=name, maker=maker, category=category,
        price=Decimal(price), stock_quantity=stock_quantity, is_active=True,
    )


def make_bare_order(*, currency="CNY", email="buyer@example.test",
                    status=OrderStatus.PENDING, payment_status=PaymentStatus.UNPAID):
    """An Order with no items and no SellerFulfillment rows -- for tests that
    exercise the model/service layer directly, without going through the
    heavier real checkout path in orders.services.create_order.

    Defaults to a freshly placed, unpaid order. Tests that exercise a
    successful dispatch pass status=CONFIRMED, payment_status=PAID -- the
    state a real order reaches once its payment succeeds."""
    return Order.objects.create(
        order_number=OrderNumberSequence.next_number(),
        status=status, payment_status=payment_status,
        customer_email=email, currency=currency,
    )


def make_order_item(*, order, product, maker=None, quantity=1):
    """An OrderItem created directly (bypassing checkout), for tests that only
    care about item membership, not stock/pricing/checkout mechanics.

    `maker=` overrides the snapshot maker; defaults to `product.maker`. For a
    historical line with no maker at all (Maker since deleted, SET_NULL --
    something today's real checkout cannot produce, see
    create_seller_fulfillments' docstring), build the OrderItem directly
    instead of through this helper.
    """
    resolved_maker = maker if maker is not None else product.maker
    return OrderItem.objects.create(
        order=order, product=product, maker=resolved_maker,
        product_slug=product.slug, product_name=product.name,
        maker_name=resolved_maker.name if resolved_maker else "",
        unit_price=product.price, quantity=quantity, line_total=product.price * quantity,
    )


def make_cart(user, *items):
    """items: (product, quantity) pairs."""
    from orders.models import CartItem
    cart = Cart.objects.create(user=user)
    for product, quantity in items:
        CartItem.objects.create(cart=cart, product=product, quantity=quantity)
    return cart

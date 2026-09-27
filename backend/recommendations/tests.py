from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User, WishlistItem
from orders.models import Order, OrderItem, PaymentStatus
from products.models import Category, Maker, Product, StockStatus

from .services import recommendations_for_user, similar_products


class RecommendationTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Ceramics", slug="ceramics")
        self.other_category = Category.objects.create(name="Textiles", slug="textiles")
        self.maker = Maker.objects.create(
            name="Maker One", slug="maker-one", discipline="Ceramics", location="Jingdezhen"
        )
        self.other_maker = Maker.objects.create(
            name="Maker Two", slug="maker-two", discipline="Textiles", location="Suzhou"
        )
        self.source = self.make_product(
            "Source Bowl", "source-bowl", self.category, self.maker,
            materials=["Stoneware"], price="80.00",
        )
        self.similar = self.make_product(
            "Similar Cup", "similar-cup", self.category, self.maker,
            materials=["Stoneware"], price="85.00",
        )
        self.other = self.make_product(
            "Linen Cloth", "linen-cloth", self.other_category, self.other_maker,
            materials=["Linen"], price="60.00", featured=True,
        )

    def make_product(self, name, slug, category, maker, *, materials, price, featured=False,
                     stock_status=StockStatus.IN_STOCK, active=True):
        return Product.objects.create(
            name=name,
            slug=slug,
            price=Decimal(price),
            category=category,
            maker=maker,
            materials=materials,
            stock_quantity=10,
            stock_status=stock_status,
            is_featured=featured,
            is_active=active,
        )

    def test_similar_category_and_content_rank_first(self):
        ranked = similar_products(self.source, limit=2)
        self.assertEqual(ranked[0].product, self.similar)
        self.assertIn("same category", ranked[0].reasons)

    def test_new_user_gets_cold_start_fallback(self):
        user = User.objects.create_user("new@example.com", "StrongPass123!")
        ranked = recommendations_for_user(user, limit=2)
        self.assertTrue(ranked)
        self.assertTrue(all(item.product.is_active for item in ranked))

    def test_wishlist_personalises_recommendations(self):
        user = User.objects.create_user("wish@example.com", "StrongPass123!")
        WishlistItem.objects.create(user=user, product=self.source)
        ranked = recommendations_for_user(user, limit=2)
        self.assertEqual(ranked[0].product, self.similar)
        self.assertIn("wishlist", ranked[0].reasons)

    def test_purchase_history_personalises_and_excludes_purchased_product(self):
        user = User.objects.create_user("buyer@example.com", "StrongPass123!")
        order = Order.objects.create(
            order_number="AF-2026-000001",
            user=user,
            payment_status=PaymentStatus.PAID,
            customer_email=user.email,
            subtotal=Decimal("80.00"),
            total=Decimal("80.00"),
        )
        OrderItem.objects.create(
            order=order,
            product=self.source,
            maker=self.maker,
            product_slug=self.source.slug,
            product_name=self.source.name,
            maker_name=self.maker.name,
            unit_price=self.source.price,
            quantity=1,
            line_total=self.source.price,
        )
        ranked = recommendations_for_user(user, limit=2)
        self.assertNotIn(self.source, [item.product for item in ranked])
        self.assertEqual(ranked[0].product, self.similar)
        self.assertIn("purchase history", ranked[0].reasons)

    def test_sold_out_and_inactive_products_are_excluded(self):
        sold_out = self.make_product(
            "Sold Out", "sold-out", self.category, self.maker,
            materials=["Stoneware"], price="82.00", stock_status=StockStatus.SOLD_OUT,
        )
        inactive = self.make_product(
            "Inactive", "inactive", self.category, self.maker,
            materials=["Stoneware"], price="82.00", active=False,
        )
        ranked = similar_products(self.source, limit=8)
        products = [item.product for item in ranked]
        self.assertNotIn(sold_out, products)
        self.assertNotIn(inactive, products)

    def test_api_works_with_limited_or_no_interaction_data(self):
        client = APIClient()
        response = client.get("/api/recommendations/?limit=2")
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(response.data["count"], 2)
        self.assertIn("results", response.data)

    def test_product_api_returns_content_recommendations(self):
        client = APIClient()
        response = client.get(f"/api/recommendations/?product={self.source.slug}&limit=2")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["slug"], self.similar.slug)

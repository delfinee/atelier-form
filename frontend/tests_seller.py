"""Tests for Min's seller product management and order list workflows."""

from decimal import Decimal
from django.conf import settings
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from orders.models import DeliveryMethod, Order, OrderItem, OrderStatus, PaymentStatus
from orders.services import create_seller_fulfillments
from products.models import Category, Maker, Product, ProductImage, ProductVariant, VariantGroup


@override_settings(
    STORAGES={
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class SellerProductManagementTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.category = Category.objects.create(name="Ceramics", slug="ceramics")
        self.category_textiles = Category.objects.create(name="Textiles", slug="textiles")

        # Seller A (Chen Meilin)
        self.seller_user = User.objects.create_user(
            email="seller-a@atelierform.test",
            password="test-password-123",
            first_name="Meilin",
            last_name="Chen",
            is_seller=True,
        )
        self.maker_a = Maker.objects.create(
            name="Chen Meilin",
            slug="chen-meilin",
            owner=self.seller_user,
            discipline="Ceramics",
            location="Jingdezhen",
        )

        # Seller B (Lu Wenjing)
        self.seller_b_user = User.objects.create_user(
            email="seller-b@atelierform.test",
            password="test-password-123",
            first_name="Wenjing",
            last_name="Lu",
            is_seller=True,
        )
        self.maker_b = Maker.objects.create(
            name="Lu Wenjing",
            slug="lu-wenjing",
            owner=self.seller_b_user,
            discipline="Textiles",
            location="Hangzhou",
        )

        # Buyer user (non-seller)
        self.buyer_user = User.objects.create_user(
            email="buyer@atelierform.test",
            password="test-password-123",
            first_name="Buyer",
            last_name="User",
            is_seller=False,
        )

        # Products
        self.product_a = Product.objects.create(
            maker=self.maker_a,
            category=self.category,
            name="Porcelain Tea Cup",
            slug="porcelain-tea-cup",
            price=Decimal("45.00"),
            stock_quantity=10,
            is_active=True,
        )
        self.product_b = Product.objects.create(
            maker=self.maker_b,
            category=self.category_textiles,
            name="Linen Scarf",
            slug="linen-scarf",
            price=Decimal("120.00"),
            stock_quantity=5,
            is_active=True,
        )

    def test_anonymous_redirected_to_login(self):
        resp = self.client.get(reverse("seller_product_list"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/account/login/", resp.url)

        resp = self.client.get(reverse("seller_product_create"))
        self.assertEqual(resp.status_code, 302)

        resp = self.client.get(reverse("seller_order_list"))
        self.assertEqual(resp.status_code, 302)

    def test_non_seller_forbidden(self):
        self.client.login(username="buyer@atelierform.test", password="test-password-123")
        resp = self.client.get(reverse("seller_product_list"))
        self.assertEqual(resp.status_code, 403)

        resp = self.client.get(reverse("seller_order_list"))
        self.assertEqual(resp.status_code, 403)

    def test_seller_sees_own_products_only(self):
        self.client.login(username="seller-a@atelierform.test", password="test-password-123")
        resp = self.client.get(reverse("seller_product_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Porcelain Tea Cup")
        self.assertNotContains(resp, "Linen Scarf")

    def test_seller_product_create_get(self):
        self.client.login(username="seller-a@atelierform.test", password="test-password-123")
        resp = self.client.get(reverse("seller_product_create"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Add New Product")

    def test_seller_product_create_post(self):
        self.client.login(username="seller-a@atelierform.test", password="test-password-123")
        post_data = {
            "name": "Celadon Glazed Bowl",
            "category": self.category.id,
            "price": "68.00",
            "short_description": "Hand-turned celadon bowl",
            "description": "Fired in wood kiln with authentic celadon glaze.",
            "stock_quantity": "15",
            "is_active": "on",
            # Variant formset management
            "product_variants-TOTAL_FORMS": "1",
            "product_variants-INITIAL_FORMS": "0",
            "product_variants-MIN_NUM_FORMS": "0",
            "product_variants-MAX_NUM_FORMS": "1000",
            "product_variants-0-group": VariantGroup.SIZE,
            "product_variants-0-label": "Medium",
            "product_variants-0-sku": "BOWL-CEL-MED",
            "product_variants-0-price_override": "75.00",
            "product_variants-0-stock_quantity": "8",
            "product_variants-0-is_active": "on",
            # Image formset management
            "product_images-TOTAL_FORMS": "1",
            "product_images-INITIAL_FORMS": "0",
            "product_images-MIN_NUM_FORMS": "0",
            "product_images-MAX_NUM_FORMS": "1000",
            "product_images-0-image": "product-celadon-bowl-1",
            "product_images-0-alt_text": "Celadon bowl studio view",
            "product_images-0-sort_order": "0",
            "product_images-0-is_primary": "on",
        }
        resp = self.client.post(reverse("seller_product_create"), post_data)
        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, reverse("seller_product_list"))

        created = Product.objects.get(name="Celadon Glazed Bowl")
        self.assertEqual(created.maker, self.maker_a)
        self.assertEqual(created.price, Decimal("68.00"))
        self.assertEqual(created.product_variants.count(), 1)
        self.assertEqual(created.product_variants.first().sku, "BOWL-CEL-MED")
        self.assertEqual(created.product_images.count(), 1)

    def test_seller_product_edit(self):
        self.client.login(username="seller-a@atelierform.test", password="test-password-123")
        edit_url = reverse("seller_product_edit", kwargs={"slug": self.product_a.slug})
        resp = self.client.get(edit_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Edit Product")

        post_data = {
            "name": "Porcelain Tea Cup Updated",
            "category": self.category.id,
            "price": "49.00",
            "short_description": "Updated description",
            "description": "Detailed notes",
            "stock_quantity": "12",
            "is_active": "on",
            "product_variants-TOTAL_FORMS": "0",
            "product_variants-INITIAL_FORMS": "0",
            "product_variants-MIN_NUM_FORMS": "0",
            "product_variants-MAX_NUM_FORMS": "1000",
            "product_images-TOTAL_FORMS": "0",
            "product_images-INITIAL_FORMS": "0",
            "product_images-MIN_NUM_FORMS": "0",
            "product_images-MAX_NUM_FORMS": "1000",
        }
        resp = self.client.post(edit_url, post_data)
        self.assertEqual(resp.status_code, 302)
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.name, "Porcelain Tea Cup Updated")
        self.assertEqual(self.product_a.price, Decimal("49.00"))

    def test_seller_cannot_edit_other_maker_product(self):
        self.client.login(username="seller-a@atelierform.test", password="test-password-123")
        other_edit_url = reverse("seller_product_edit", kwargs={"slug": self.product_b.slug})
        resp = self.client.get(other_edit_url)
        self.assertEqual(resp.status_code, 404)


@override_settings(
    STORAGES={
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class SellerOrderListTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.category = Category.objects.create(name="Ceramics", slug="ceramics")

        self.seller_user = User.objects.create_user(
            email="seller-list@atelierform.test",
            password="test-password-123",
            first_name="Meilin",
            last_name="Chen",
            is_seller=True,
        )
        self.maker = Maker.objects.create(
            name="Chen Meilin",
            slug="chen-meilin-order",
            owner=self.seller_user,
            discipline="Ceramics",
        )

        self.product = Product.objects.create(
            maker=self.maker,
            category=self.category,
            name="Studio Mug",
            slug="studio-mug",
            price=Decimal("50.00"),
            stock_quantity=20,
        )

        self.order = Order.objects.create(
            order_number="AF-2026-999001",
            status=OrderStatus.CONFIRMED,
            payment_status=PaymentStatus.PAID,
            subtotal=Decimal("100.00"),
            total=Decimal("108.00"),
            customer_email="buyer@test.test",
            shipping_address_snapshot={"first_name": "Alice", "city": "Shanghai"},
        )
        self.item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            maker=self.maker,
            product_name="Studio Mug",
            quantity=2,
            unit_price=Decimal("50.00"),
            line_total=Decimal("100.00"),
        )
        create_seller_fulfillments(self.order)

    def test_order_list_shows_seller_orders(self):
        self.client.login(username="seller-list@atelierform.test", password="test-password-123")
        resp = self.client.get(reverse("seller_order_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "AF-2026-999001")
        self.assertContains(resp, "Studio Mug")
        self.assertContains(resp, "¥100")
        self.assertContains(resp, "Unfulfilled")

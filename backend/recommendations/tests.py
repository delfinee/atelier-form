from decimal import Decimal

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User, WishlistItem
from orders.models import Cart, CartItem, Order, OrderItem, PaymentStatus
from products.models import (
    Category,
    Maker,
    Product,
    ProductVariant,
    StockStatus,
    VariantGroup,
)

from .services import (
    MAX_RECENT_VIEWS,
    RECENT_VIEWS_KEY,
    _product_similarity,
    recommendations_for_user,
    similar_products,
)


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
            "Source Bowl",
            "source-bowl",
            self.category,
            self.maker,
            materials=["Stoneware"],
            price="80.00",
            colours=["Bone", "Ash"],
        )
        self.similar = self.make_product(
            "Similar Cup",
            "similar-cup",
            self.category,
            self.maker,
            materials=["Stoneware"],
            price="85.00",
            colours=["Bone"],
        )
        self.other = self.make_product(
            "Linen Cloth",
            "linen-cloth",
            self.other_category,
            self.other_maker,
            materials=["Linen"],
            price="60.00",
            colours=["Indigo"],
            featured=True,
        )

    def make_product(
        self,
        name,
        slug,
        category,
        maker,
        *,
        materials,
        price,
        colours=(),
        finishes=(),
        sizes=(),
        featured=False,
        stock_status=StockStatus.IN_STOCK,
        active=True,
    ):
        product = Product.objects.create(
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
        for group, labels in (
            (VariantGroup.COLOUR, colours),
            (VariantGroup.FINISH, finishes),
            (VariantGroup.SIZE, sizes),
        ):
            for index, label in enumerate(labels):
                ProductVariant.objects.create(
                    product=product,
                    group=group,
                    label=label,
                    sku=f"{slug}-{group}-{index}",
                    stock_quantity=10,
                    is_active=True,
                )
        return product

    def test_similar_category_and_content_rank_first(self):
        ranked = similar_products(self.source, limit=2)
        self.assertEqual(ranked[0].product, self.similar)
        self.assertIn("same category", ranked[0].reasons)
        self.assertIn("shared colour: bone", ranked[0].reasons)

    def test_factor_priority_category_then_colour_then_price(self):
        category_only = self.make_product(
            "Category Only",
            "category-only",
            self.category,
            self.other_maker,
            materials=["Linen"],
            price="220.00",
            colours=["Indigo"],
        )
        colour_only = self.make_product(
            "Colour Only",
            "colour-only",
            self.other_category,
            self.other_maker,
            materials=["Linen"],
            price="220.00",
            colours=["Bone"],
        )
        price_only = self.make_product(
            "Price Only",
            "price-only",
            self.other_category,
            self.other_maker,
            materials=["Linen"],
            price="82.00",
            colours=["Indigo"],
        )

        category_score, _, category_factors = _product_similarity(self.source, category_only)
        colour_score, _, colour_factors = _product_similarity(self.source, colour_only)
        price_score, _, price_factors = _product_similarity(self.source, price_only)

        self.assertGreater(category_score, colour_score)
        self.assertGreater(colour_score, price_score)
        self.assertEqual(category_factors["category"], 14.0)
        self.assertEqual(colour_factors["colour"], 5.5)
        self.assertEqual(price_factors["price"], 4.0)

    def test_multiple_weaker_factors_can_combine_into_strong_match(self):
        category_only = self.make_product(
            "Category Match",
            "category-match",
            self.category,
            self.other_maker,
            materials=["Linen"],
            price="220.00",
            colours=["Indigo"],
        )
        combined = self.make_product(
            "Combined Match",
            "combined-match",
            self.other_category,
            self.maker,
            materials=["Stoneware"],
            price="82.00",
            colours=["Bone"],
        )

        category_score, _, _ = _product_similarity(self.source, category_only)
        combined_score, reasons, factors = _product_similarity(self.source, combined)

        self.assertGreater(combined_score, category_score)
        self.assertIn("multi-factor match", reasons)
        self.assertIn("colour", factors)
        self.assertIn("price", factors)
        self.assertIn("maker", factors)
        self.assertIn("materials", factors)

    def test_price_can_recommend_independently(self):
        price_only = self.make_product(
            "Price Peer",
            "price-peer",
            self.other_category,
            self.other_maker,
            materials=["Linen"],
            price="81.00",
            colours=["Indigo"],
        )
        score, reasons, factors = _product_similarity(self.source, price_only)

        self.assertGreater(score, 0)
        self.assertIn("very similar price", reasons)
        self.assertEqual(factors, {"price": 4.0})

    def test_finish_and_size_are_supported_as_lower_weight_factors(self):
        source = self.make_product(
            "Finished Source",
            "finished-source",
            self.category,
            self.maker,
            materials=["Stoneware"],
            price="100.00",
            colours=["Bone"],
            finishes=["Matte"],
            sizes=["Medium"],
        )
        candidate = self.make_product(
            "Finished Candidate",
            "finished-candidate",
            self.other_category,
            self.other_maker,
            materials=["Linen"],
            price="250.00",
            colours=["Indigo"],
            finishes=["Matte"],
            sizes=["Medium"],
        )

        score, reasons, factors = _product_similarity(source, candidate)

        self.assertGreater(score, 0)
        self.assertEqual(factors["finish"], 1.5)
        self.assertEqual(factors["size"], 0.75)
        self.assertIn("similar finish", reasons)
        self.assertIn("similar size option", reasons)

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
        factors = dict(ranked[0].factor_scores)
        self.assertGreater(factors["category"], factors["colour"])
        self.assertGreater(factors["colour"], factors["price"])

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
            "Sold Out",
            "sold-out",
            self.category,
            self.maker,
            materials=["Stoneware"],
            price="82.00",
            colours=["Bone"],
            stock_status=StockStatus.SOLD_OUT,
        )
        inactive = self.make_product(
            "Inactive",
            "inactive",
            self.category,
            self.maker,
            materials=["Stoneware"],
            price="82.00",
            colours=["Bone"],
            active=False,
        )
        ranked = similar_products(self.source, limit=20)
        products = [item.product for item in ranked]
        self.assertNotIn(sold_out, products)
        self.assertNotIn(inactive, products)

    def test_api_works_with_limited_or_no_interaction_data(self):
        client = APIClient()
        response = client.get("/api/recommendations/?limit=2")
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(response.data["count"], 2)
        self.assertIn("results", response.data)

    def test_product_api_returns_content_recommendations_and_factor_breakdown(self):
        client = APIClient()
        response = client.get(
            f"/api/recommendations/?product={self.source.slug}&limit=2"
        )
        self.assertEqual(response.status_code, 200)
        first = response.data["results"][0]
        self.assertEqual(first["slug"], self.similar.slug)
        self.assertIn("recommendation_factors", first)
        self.assertEqual(first["recommendation_factors"]["category"], 14.0)
        self.assertGreater(
            first["recommendation_factors"]["category"],
            first["recommendation_factors"]["colour"],
        )

    @override_settings(DEBUG=True)
    def test_guest_browsing_personalises_home_shop_and_api_without_login(self):
        response = self.client.get(f"/products/{self.source.slug}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session[RECENT_VIEWS_KEY], [self.source.pk])
        self.assertNotIn("_auth_user_id", self.client.session)

        response = self.client.get("/api/recommendations/?limit=2")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["slug"], self.similar.slug)
        self.assertIn("recently viewed", response.data["results"][0]["recommendation_reasons"])
        self.assertEqual(response["Cache-Control"], "private, no-store")
        for path in ("/", "/shop/", "/bag/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertContains(response, "data-recommendations")
                self.assertContains(response, "No sign-in needed.")
                self.assertContains(response, f'data-slug="{self.similar.slug}"')

    def test_guest_bag_personalises_without_browsing(self):
        session = self.client.session
        cart = Cart.objects.create(session_key=session.session_key)
        CartItem.objects.create(cart=cart, product=self.source, quantity=1)

        response = self.client.get("/api/recommendations/?limit=2")
        first = response.data["results"][0]
        self.assertEqual(first["slug"], self.similar.slug)
        self.assertIn("cart activity", first["recommendation_reasons"])
        self.assertNotIn(self.source.slug, [p["slug"] for p in response.data["results"]])

    @override_settings(DEBUG=True)
    def test_guest_recommendation_copy_is_translated(self):
        response = self.client.get("/shop/", HTTP_ACCEPT_LANGUAGE="zh-hans")
        self.assertContains(response, "为您精选热门作品，无需登录即可浏览推荐。")
        self.client.get(f"/products/{self.source.slug}/")
        response = self.client.get("/shop/", HTTP_ACCEPT_LANGUAGE="zh-hans")
        self.assertContains(response, "根据您本次浏览和加入购物袋的商品推荐，无需登录。")

    def test_guest_signals_do_not_leak_to_another_session(self):
        session = self.client.session
        session[RECENT_VIEWS_KEY] = [self.source.pk]
        session.save()
        cart = Cart.objects.create(session_key=session.session_key)
        CartItem.objects.create(cart=cart, product=self.source, quantity=1)
        response = APIClient().get("/api/recommendations/?limit=2")
        self.assertEqual(response.status_code, 200)
        for row in response.data["results"]:
            self.assertEqual(row["recommendation_reasons"], ["popular"])
            self.assertEqual(row["recommendation_score"], 0)

    def test_guest_ignores_inactive_bag_and_signed_in_users_bag(self):
        session = self.client.session
        inactive = Cart.objects.create(session_key=session.session_key, is_active=False)
        CartItem.objects.create(cart=inactive, product=self.source, quantity=1)
        user = User.objects.create_user("other-cart@example.com", "StrongPass123!")
        owned = Cart.objects.create(user=user, session_key=session.session_key)
        CartItem.objects.create(cart=owned, product=self.source, quantity=1)
        response = self.client.get("/api/recommendations/")
        self.assertTrue(all(row["recommendation_reasons"] == ["popular"] for row in response.data["results"]))

    @override_settings(DEBUG=True)
    def test_guest_recent_views_are_bounded_and_deduplicated(self):
        session = self.client.session
        session[RECENT_VIEWS_KEY] = list(range(1000, 1000 + MAX_RECENT_VIEWS))
        session.save()
        for _ in range(2):
            self.assertEqual(self.client.get(f"/products/{self.source.slug}/").status_code, 200)
        recent = self.client.session[RECENT_VIEWS_KEY]
        self.assertEqual(len(recent), MAX_RECENT_VIEWS)
        self.assertEqual(recent[-1], self.source.pk)
        self.assertEqual(recent.count(self.source.pk), 1)

    def test_guest_signals_never_recommend_unavailable_products(self):
        session = self.client.session
        session[RECENT_VIEWS_KEY] = [self.source.pk]
        session.save()
        self.similar.stock_status = StockStatus.SOLD_OUT
        self.similar.save()
        self.other.is_active = False
        self.other.save()
        response = self.client.get("/api/recommendations/")
        self.assertEqual(response.data["results"], [])

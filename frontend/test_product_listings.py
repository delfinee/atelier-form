"""PostgreSQL listing regressions with the production static manifest enabled."""

from tempfile import TemporaryDirectory

from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.templatetags.static import static
from django.test import TestCase, override_settings
from django.utils import translation

from imagery.models import SiteImage
from imagery.resolver import image_url, invalidate_index
from products.models import Category, Collection, Maker, Product, ProductImage, ProductVariant


@override_settings(DEBUG=False, SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=["testserver"])
class ProductListingTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        directory = TemporaryDirectory()
        cls.addClassCleanup(directory.cleanup)
        overrides = override_settings(
            STATIC_ROOT=directory.name,
            STORAGES={**settings.STORAGES, "staticfiles": {
                "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
            }},
        )
        overrides.enable()
        cls.addClassCleanup(overrides.disable)
        call_command("collectstatic", interactive=False, verbosity=0)

    @classmethod
    def setUpTestData(cls):
        cls.gifts = Category.objects.create(name="Gifts", slug="gifts")
        cls.ceramics = Category.objects.create(name="Ceramics", slug="ceramics")
        cls.earth = Collection.objects.create(name="Earth", slug="earth")
        cls.empty = Collection.objects.create(name="Empty", slug="empty")
        maker = Maker.objects.create(name="Test maker", slug="test-maker")
        cls.gift = Product.objects.create(
            name="Regression gift", slug="regression-gift", category=cls.gifts,
            maker=maker, price="30.00", materials=["Stoneware"], sort_weight=10,
        )
        # Exact image key from both production tracebacks; no SiteImage or SVG exists.
        ProductImage.objects.create(product=cls.gift, image="BH Image 1")
        ProductVariant.objects.create(
            product=cls.gift, label="Blue", sku="listing-blue", swatch="#0000ff",
        )
        cls.pot = Product.objects.create(
            name="Regression pot", slug="regression-pot", category=cls.ceramics,
            maker=maker, price="80.00", is_featured=True, stock_status="sold-out",
        )
        ProductImage.objects.create(product=cls.pot, image="product-studio-gift-set-1")
        cls.gift.collections.add(cls.earth)
        cls.pot.collections.add(cls.earth)
        Product.objects.create(name="Hidden", slug="hidden", category=cls.gifts,
                               maker=maker, price="10.00", is_active=False)

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        language = translation.get_language()
        self.addCleanup(translation.activate, language)

    def test_shop_and_gifts_render_in_both_languages(self):
        for language in ("en", "zh-hans"):
            for path in ("/shop/", "/collections/gifts/"):
                with self.subTest(language=language, path=path):
                    response = self.client.get(path, HTTP_ACCEPT_LANGUAGE=language)
                    self.assertEqual(response.headers["Content-Language"], language)
                    self.assertContains(response, "Regression gift")
                    self.assertContains(response, 'data-slug="regression-gift"')
                    self.assertContains(response, static("frontend/img/placeholders/product-placeholder.svg"))
                    self.assertContains(response, 'class="card__price"')
                    self.assertContains(response, 'background:#0000ff')
                    self.assertNotContains(response, 'data-slug="hidden"')

    def test_other_category_and_editorial_collection(self):
        for language in ("en", "zh-hans"):
            for path, expected in (("/collections/ceramics/", [self.pot]),
                                   ("/collections/earth/", [self.pot, self.gift])):
                with self.subTest(language=language, path=path):
                    response = self.client.get(path, HTTP_ACCEPT_LANGUAGE=language)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.context["products"], expected)

    def test_all_sort_orders_and_invalid_sort(self):
        orders = {"featured": [self.pot, self.gift], "newest": [self.gift, self.pot],
                  "price-asc": [self.gift, self.pot], "price-desc": [self.pot, self.gift],
                  "invalid": [self.pot, self.gift]}
        for path in ("/shop/", "/collections/earth/"):
            for sort, expected in orders.items():
                with self.subTest(path=path, sort=sort):
                    response = self.client.get(path, {"sort": sort})
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.context["products"], expected)

    def test_filters_and_sort_links_preserve_query(self):
        filters = {"category": "gifts", "material": "Stoneware", "colour": "Blue",
                   "price": "under-40", "availability": "in-stock"}
        for params in [{key: value} for key, value in filters.items()] + [filters]:
            with self.subTest(params=params):
                response = self.client.get("/shop/", params)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["products"], [self.gift])
                self.assertContains(response, "sort=price-asc")
        response = self.client.get("/shop/", {"category": ["gifts", "ceramics"]})
        self.assertContains(response, "category=gifts&amp;category=ceramics&amp;sort=price-asc")

    def test_empty_results(self):
        for language in ("en", "zh-hans"):
            for path in ("/shop/?category=missing", "/collections/empty/"):
                with self.subTest(language=language, path=path):
                    response = self.client.get(path, HTTP_ACCEPT_LANGUAGE=language)
                    self.assertContains(response, 'class="empty-state"')
                    self.assertEqual(response.context["products"], [])

    def test_product_with_no_images(self):
        self.gift.product_images.all().delete()
        response = self.client.get("/collections/gifts/")
        self.assertContains(response, static("frontend/img/placeholders/product-placeholder.svg"))

    def test_existing_placeholder_and_database_photo_are_preserved(self):
        name = "product-studio-gift-set-1"
        self.assertEqual(image_url(name), static(f"frontend/img/placeholders/{name}.svg"))
        photo = SiteImage.objects.create(name="regression-photo", data=b"image-bytes")
        invalidate_index()
        self.assertEqual(image_url(photo.name), f"/img/{photo.name}.jpg?v={photo.checksum[:12]}")
        self.assertEqual(image_url(""), "")

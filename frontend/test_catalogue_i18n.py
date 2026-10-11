"""Database-free checks for catalogue presentation translations."""

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.template import Context, Template
from django.test import SimpleTestCase
from django.utils import translation
from django.utils.translation import gettext

from orders.serializers import CartItemSerializer
from products.models import MATERIAL_ALIASES, MATERIAL_FAMILIES, Category, Collection, Product

from frontend import services
from frontend.catalogue_i18n import localize_collection, localize_colour_label, localize_product
from frontend.mockdata.collections import CATEGORIES, COLLECTIONS, EXTRA_COLLECTIONS
from frontend.mockdata.products import PRODUCTS, SWATCHES
from frontend.templatetags.frontend_extras import colour_label, stock_label


# Approved Chinese copy is fixed here, independent of the runtime translation source.
CATEGORY_EXPECTED = (
    ('ceramics', '陶器', '逐件拉坯、修整与烧制。', '为餐桌而作的炻器与瓷器，来自景德镇的一间工作室。泥料取自一小时车程外，釉料则由灰烬与铁调配而成。颜色与器口会有细微差异，那是手作留下的痕迹，而非瑕疵。'),
    ('textiles', '织物', '经编织、染色与水洗，直至柔软。', '亚麻与手织棉布，以云南种植的蓝靛染色，并经过处理，不会以僵硬的状态抵达。适合每日使用，也经得起频繁清洗。'),
    ('home', '家居', '为房间里安静的角落而作。', '蜡烛每批浇注四十支，木板取自回收的庭院梁木，黄铜则有意让它逐渐变深。这些小物件虽不大，却比尺寸所暗示的更能改变房间的气息。'),
    ('gifts', '礼品', '以本色纸与棉绳包裹。', '适合作为礼物寄送的作品，手工装盒，并附有可在结算时书写的卡片。这里的任何东西都不会以塑料密封。'),
)

EDITORIAL_EXPECTED = (
    ('earth', '大地系列', '灰烬、泥土、蓝靛与本色亚麻。', '九件作品取自同一份精简的材料清单，以匠人工作室一日车程内能够找到的材料上釉与染色。组合在一起，它们呈现出骨白、灰烬、泥土与草色组成的统一色调。'),
    ('quiet-mornings', '静谧清晨', '献给一天开始的第一个小时。', '杯子、手冲壶与一支蜡烛，属于清晨尚未向你提出任何要求的那段时间。我们挑选它们，让这些作品在一张小桌上自然相称。'),
    ('studio-essentials', '工作室日用', '我们自己每天使用的作品。', '工作室真正用于日常的物件：洗过一百次的围裙、反复切割使用的木板，以及每天都会用到的毛巾。'),
)

PRODUCT_EXPECTED = (
    ("hand-thrown-stoneware-mug", "Hand-thrown Stoneware Mug", "Stoneware · Chen Meilin", "手拉炻器马克杯", "炻器 · 陈梅琳"),
    ("speckled-breakfast-bowl", "Speckled Breakfast Bowl", "Stoneware · Chen Meilin", "斑点早餐碗", "炻器 · 陈梅琳"),
    ("ceramic-pour-over-dripper", "Ceramic Pour-Over Dripper", "Porcelain · Chen Meilin", "陶瓷手冲滤杯", "瓷器 · 陈梅琳"),
    ("ash-glazed-dinner-plate", "Ash-Glazed Dinner Plate", "Stoneware · Chen Meilin", "灰釉餐盘", "炻器 · 陈梅琳"),
    ("stoneware-serving-platter", "Stoneware Serving Platter", "Stoneware · Chen Meilin", "炻器餐盘", "炻器 · 陈梅琳"),
    ("matte-ceramic-vase", "Matte Ceramic Vase", "Stoneware · Chen Meilin", "哑光陶瓷花瓶", "炻器 · 陈梅琳"),
    ("tea-cup-set-of-two", "Tea Cup Set of Two", "Porcelain · Chen Meilin", "双人茶杯套装", "瓷器 · 陈梅琳"),
    ("linen-market-tote", "Linen Market Tote", "Washed linen · Ye Ruolan", "亚麻购物袋", "水洗亚麻 · 叶若兰"),
    ("woven-cotton-throw", "Woven Cotton Throw", "Handwoven cotton · Lu Wenjing", "手织棉盖毯", "手织棉 · 陆文静"),
    ("linen-cushion-cover", "Linen Cushion Cover", "Washed linen · Ye Ruolan", "亚麻靠垫套", "水洗亚麻 · 叶若兰"),
    ("stonewashed-table-runner", "Stonewashed Table Runner", "Washed linen · Ye Ruolan", "石洗亚麻桌旗", "水洗亚麻 · 叶若兰"),
    ("hand-loomed-tea-towel", "Hand-loomed Tea Towel", "Cotton & linen · Lu Wenjing", "手织茶巾", "棉与亚麻 · 陆文静"),
    ("quilted-linen-apron", "Quilted Linen Apron", "Washed linen · Ye Ruolan", "绗缝亚麻围裙", "水洗亚麻 · 叶若兰"),
    ("soy-wax-studio-candle", "Soy Wax Studio Candle", "Soy & rapeseed wax · Xu Anying", "大豆蜡工作室香薰蜡烛", "大豆蜡与菜籽蜡 · 徐安莹"),
    ("handmade-incense-holder", "Handmade Incense Holder", "Stoneware · Chen Meilin", "手作香座", "炻器 · 陈梅琳"),
    ("olive-wood-serving-board", "Olive Wood Serving Board", "Reclaimed timber · Zhao Hesheng", "橄榄木餐板", "再生木料 · 赵和生"),
    ("brass-oak-candle-snuffer", "Brass & Oak Candle Snuffer", "Brass & oak · Zhao Hesheng", "黄铜橡木烛剪", "黄铜与橡木 · 赵和生"),
    ("rattan-storage-basket", "Rattan Storage Basket", "Woven rattan · Lu Wenjing", "藤编收纳篮", "藤编 · 陆文静"),
    ("ceramic-ring-dish", "Ceramic Ring Dish", "Porcelain · Chen Meilin", "陶瓷首饰盘", "瓷器 · 陈梅琳"),
    ("studio-gift-set", "Studio Gift Set", "Three pieces, wrapped · Multiple makers", "工作室礼品套装", "三件作品，手工包裹 · 多位匠人"),
    ("beeswax-taper-pair", "Beeswax Taper Pair", "Pure beeswax · Xu Anying", "蜂蜡长烛一对", "纯蜂蜡 · 徐安莹"),
)

# Frozen before moving the English extras out of the seed command.
EXTRA_COLLECTIONS_BEFORE_MOVE = ({'slug': 'quiet-mornings',
  'name': 'Quiet Mornings',
  'tagline': 'For the first hour of the day.',
  'description': 'Cups, drippers and a candle for the part of the morning before anything '
                 'has been asked of you. Chosen so the pieces sit together on a small table.',
  'hero': 'collection-ceramics',
  'tile': 'category-ceramics',
  'featured': True,
  'members': ['hand-thrown-stoneware-mug',
              'ceramic-pour-over-dripper',
              'speckled-breakfast-bowl',
              'tea-cup-set-of-two',
              'soy-wax-studio-candle']},
 {'slug': 'studio-essentials',
  'name': 'Studio Essentials',
  'tagline': 'The pieces we use ourselves.',
  'description': 'What is actually in daily use in the studio: an apron that has been washed '
                 'a hundred times, boards that get cut on, towels that get used.',
  'hero': 'collection-home',
  'tile': 'category-home',
  'featured': False,
  'members': ['quilted-linen-apron',
              'olive-wood-serving-board',
              'hand-loomed-tea-towel',
              'linen-market-tote',
              'brass-oak-candle-snuffer']})

class CollectionLocalizationTests(SimpleTestCase):
    def make_category(self, seed):
        return Category(
            slug=seed["slug"], name=seed["title"], tagline=seed["tagline"],
            description=seed["description"], hero_image=seed["hero"],
            tile_image=seed["tile"], is_active=True, sort_order=7,
        )

    def make_editorial(self, seed):
        return Collection(
            slug=seed["slug"], name=seed.get("name", seed.get("title")),
            tagline=seed["tagline"], description=seed["description"],
            hero_image=seed["hero"], tile_image=seed["tile"],
            is_active=True, is_featured=seed["featured"], sort_order=7,
        )

    def editorial_seeds(self):
        return [item for item in COLLECTIONS if item["kind"] == "editorial"] + EXTRA_COLLECTIONS

    def test_english_categories_keep_canonical_seed_values(self):
        with translation.override("en"):
            for seed in CATEGORIES:
                with self.subTest(slug=seed["slug"]):
                    source = self.make_category(seed)
                    self.assertIs(localize_collection(source), source)
                    self.assertEqual(
                        (source.name, source.tagline, source.description),
                        (seed["title"], seed["tagline"], seed["description"]),
                    )

    def test_chinese_categories_match_approved_copy_without_mutation(self):
        with translation.override("zh-hans"):
            for seed, expected in zip(CATEGORIES, CATEGORY_EXPECTED, strict=True):
                with self.subTest(slug=seed["slug"]):
                    self.assertEqual(seed["slug"], expected[0])
                    source = self.make_category(seed)
                    localized = localize_collection(source)
                    self.assertIsNot(localized, source)
                    self.assertEqual(
                        (localized.name, localized.tagline, localized.description),
                        expected[1:],
                    )
                    self.assertEqual(
                        (source.name, source.tagline, source.description),
                        (seed["title"], seed["tagline"], seed["description"]),
                    )
                    self.assertEqual(
                        (localized.slug, localized.pk, localized.hero_image,
                         localized.tile_image, localized.is_active, localized.sort_order),
                        (source.slug, source.pk, source.hero_image,
                         source.tile_image, source.is_active, source.sort_order),
                    )

    def test_language_switching_uses_same_source_object(self):
        source = self.make_category(CATEGORIES[0])
        with translation.override("en"):
            self.assertEqual(localize_collection(source).name, "Ceramics")
        with translation.override("zh-hans"):
            self.assertEqual(localize_collection(source).name, CATEGORY_EXPECTED[0][1])
        with translation.override("en"):
            self.assertEqual(localize_collection(source).name, "Ceramics")
        self.assertEqual(source.name, "Ceramics")

    def test_home_category_uses_contextual_translation(self):
        source = self.make_category(next(item for item in CATEGORIES if item["slug"] == "home"))
        with translation.override("zh-hans"):
            self.assertEqual(localize_collection(source).name, CATEGORY_EXPECTED[2][1])
            expected_homepage = "\u9996\u9875"
            self.assertEqual(gettext("Home"), expected_homepage)

    def test_each_custom_field_remains_untouched_independently(self):
        seed = CATEGORIES[0]
        approved = CATEGORY_EXPECTED[0][1:]
        for custom_field in ("name", "tagline", "description"):
            with self.subTest(field=custom_field), translation.override("zh-hans"):
                source = self.make_category(seed)
                setattr(source, custom_field, "Custom English copy")
                localized = localize_collection(source)
                expected = dict(zip(("name", "tagline", "description"), approved))
                expected[custom_field] = "Custom English copy"
                self.assertEqual(
                    (localized.name, localized.tagline, localized.description),
                    tuple(expected[field] for field in ("name", "tagline", "description")),
                )
                self.assertEqual(getattr(source, custom_field), "Custom English copy")

    def test_extra_collections_match_pre_move_seed(self):
        self.assertEqual(EXTRA_COLLECTIONS, list(EXTRA_COLLECTIONS_BEFORE_MOVE))
        self.assertEqual(
            [tuple(row) for row in EXTRA_COLLECTIONS],
            [tuple(row) for row in EXTRA_COLLECTIONS_BEFORE_MOVE],
        )

    def test_english_editorials_keep_canonical_seed_values(self):
        with translation.override("en"):
            for seed in self.editorial_seeds():
                with self.subTest(slug=seed["slug"]):
                    source = self.make_editorial(seed)
                    english_name = seed["title"] if "title" in seed else seed["name"]
                    self.assertIs(localize_collection(source), source)
                    self.assertEqual(
                        (source.name, source.tagline, source.description),
                        (english_name, seed["tagline"], seed["description"]),
                    )

    def test_editorial_collection_translations_are_preserved(self):
        with translation.override("zh-hans"):
            for seed, expected in zip(self.editorial_seeds(), EDITORIAL_EXPECTED, strict=True):
                with self.subTest(slug=seed["slug"]):
                    self.assertEqual(seed["slug"], expected[0])
                    source = self.make_editorial(seed)
                    original_fields = (source.name, source.tagline, source.description)
                    localized = localize_collection(source)
                    self.assertIsNot(localized, source)
                    self.assertEqual(
                        (localized.name, localized.tagline, localized.description),
                        expected[1:],
                    )
                    self.assertEqual(
                        (source.name, source.tagline, source.description), original_fields,
                    )
                    self.assertEqual(
                        (localized.slug, localized.pk, localized.hero_image,
                         localized.tile_image, localized.is_active, localized.is_featured,
                         localized.sort_order),
                        (source.slug, source.pk, source.hero_image,
                         source.tile_image, source.is_active, source.is_featured,
                         source.sort_order),
                    )

    def test_editorial_language_switching_uses_same_source_objects(self):
        for seed, expected in zip(self.editorial_seeds(), EDITORIAL_EXPECTED, strict=True):
            with self.subTest(slug=seed["slug"]):
                source = self.make_editorial(seed)
                english = (source.name, source.tagline, source.description)
                with translation.override("en"):
                    self.assertIs(localize_collection(source), source)
                with translation.override("zh-hans"):
                    localized = localize_collection(source)
                    self.assertEqual(
                        (localized.name, localized.tagline, localized.description), expected[1:],
                    )
                with translation.override("en"):
                    localized = localize_collection(source)
                    self.assertEqual(
                        (localized.name, localized.tagline, localized.description), english,
                    )
                self.assertEqual((source.name, source.tagline, source.description), english)

    def test_each_custom_editorial_field_remains_untouched_independently(self):
        for seed, approved in zip(self.editorial_seeds(), EDITORIAL_EXPECTED, strict=True):
            for custom_field in ("name", "tagline", "description"):
                with self.subTest(slug=seed["slug"], field=custom_field):
                    source = self.make_editorial(seed)
                    setattr(source, custom_field, "Custom English copy")
                    original_fields = (source.name, source.tagline, source.description)
                    with translation.override("zh-hans"):
                        localized = localize_collection(source)
                    expected = dict(zip(("name", "tagline", "description"), approved[1:]))
                    expected[custom_field] = "Custom English copy"
                    self.assertEqual(
                        (localized.name, localized.tagline, localized.description),
                        tuple(expected[field] for field in ("name", "tagline", "description")),
                    )
                    self.assertEqual(
                        (source.name, source.tagline, source.description), original_fields,
                    )

    def test_non_chinese_language_returns_original(self):
        category = self.make_category(CATEGORIES[0])
        editorial = self.make_editorial(COLLECTIONS[-1])
        with translation.override("fr"):
            self.assertIs(localize_collection(category), category)
            self.assertIs(localize_collection(editorial), editorial)


class ProductLocalizationTests(SimpleTestCase):
    def make_product(self, expected=PRODUCT_EXPECTED[0], **overrides):
        slug, name, short_description, _, _ = expected
        values = {
            "id": 37,
            "slug": slug,
            "name": name,
            "short_description": short_description,
            "description": "Canonical long description",
            "story": "Canonical story",
            "price": Decimal("42.00"),
            "currency": "CNY",
            "category_id": 3,
            "maker_id": 4,
            "materials": ["Stoneware", "Ash glaze"],
            "dimensions": "8 cm × 9 cm",
            "stock_status": "in-stock",
            "stock_quantity": 12,
            "is_active": True,
            "is_featured": True,
            "is_new_arrival": True,
            "sort_weight": 9,
        }
        values.update(overrides)
        return Product(**values)

    def test_seeded_english_and_chinese_product_copy(self):
        self.assertEqual(len(PRODUCTS), 21)
        self.assertEqual(
            [(item["slug"], item["name"], item["short_description"]) for item in PRODUCTS],
            [expected[:3] for expected in PRODUCT_EXPECTED],
        )
        with translation.override("zh-hans"):
            for expected in PRODUCT_EXPECTED:
                with self.subTest(slug=expected[0]):
                    source = self.make_product(expected)
                    localized = localize_product(source)
                    self.assertIsNot(localized, source)
                    self.assertEqual((localized.name, localized.short_description), expected[3:])
                    self.assertEqual((source.name, source.short_description), expected[1:3])

    def test_product_language_switching(self):
        source = self.make_product()
        with translation.override("en"):
            self.assertIs(localize_product(source), source)
            self.assertEqual((source.name, source.short_description), PRODUCT_EXPECTED[0][1:3])
        with translation.override("zh-hans"):
            localized = localize_product(source)
            self.assertEqual((localized.name, localized.short_description), PRODUCT_EXPECTED[0][3:])
        with translation.override("en"):
            self.assertIs(localize_product(source), source)
            self.assertEqual((source.name, source.short_description), PRODUCT_EXPECTED[0][1:3])

    def test_custom_product_fields_are_guarded_independently(self):
        expected = PRODUCT_EXPECTED[0]
        cases = (
            ({"name": "Seller mug"}, ("Seller mug", expected[4])),
            ({"short_description": "Seller description"}, (expected[3], "Seller description")),
            ({"name": "Seller mug", "short_description": "Seller description"},
             ("Seller mug", "Seller description")),
        )
        with translation.override("zh-hans"):
            for overrides, localized_fields in cases:
                with self.subTest(overrides=overrides):
                    source = self.make_product(expected, **overrides)
                    original = (source.name, source.short_description)
                    localized = localize_product(source)
                    self.assertEqual((localized.name, localized.short_description), localized_fields)
                    self.assertEqual((source.name, source.short_description), original)

    def test_unknown_product_and_machine_fields_are_preserved(self):
        unknown = self.make_product(slug="seller-created-product")
        with translation.override("zh-hans"):
            self.assertIs(localize_product(unknown), unknown)

            source = self.make_product()
            machine_fields = (
                source.pk, source.uuid, source.slug, source.price, source.currency,
                source.category_id, source.maker_id, source.materials, source.dimensions,
                source.stock_status, source.stock_quantity, source.is_active,
                source.is_featured, source.is_new_arrival, source.sort_weight,
                source.description, source.story,
            )
            localized = localize_product(source)
            self.assertEqual(
                (localized.pk, localized.uuid, localized.slug, localized.price,
                 localized.currency, localized.category_id, localized.maker_id,
                 localized.materials, localized.dimensions, localized.stock_status,
                 localized.stock_quantity, localized.is_active, localized.is_featured,
                 localized.is_new_arrival, localized.sort_weight, localized.description,
                 localized.story),
                machine_fields,
            )

    def service_product(self):
        expected = PRODUCT_EXPECTED[0]
        images = SimpleNamespace(all=lambda: [SimpleNamespace(url="/media/mug.jpg")])
        return SimpleNamespace(
            pk=37, slug=expected[0], name=expected[1], short_description=expected[2],
            price=Decimal("42.00"), category=SimpleNamespace(slug="ceramics"),
            maker=SimpleNamespace(slug="chen-meilin"), product_images=images,
            stock_status="in-stock", is_featured=True, is_new_arrival=True,
        )

    def test_customer_facing_product_service_paths_localise_copies(self):
        expected_name, expected_short = PRODUCT_EXPECTED[0][3:]

        def assert_localized(result, source):
            product = result[0] if isinstance(result, list) else result
            self.assertEqual((product.name, product.short_description),
                             (expected_name, expected_short))
            self.assertEqual((source.name, source.short_description), PRODUCT_EXPECTED[0][1:3])

        with translation.override("zh-hans"):
            source = self.service_product()
            with patch.object(services, "_base_queryset", return_value=[source]) as base:
                assert_localized(services.all_products(), source)
                base.assert_called_once_with()

            source = self.service_product()
            queryset = MagicMock()
            queryset.filter.return_value.first.return_value = source
            with patch.object(services, "_base_queryset", return_value=queryset) as base:
                assert_localized(services.get_product(source.slug), source)
                queryset.filter.assert_called_once_with(slug=source.slug)
                base.assert_called_once_with()

            source = self.service_product()
            queryset = MagicMock()
            queryset.filter.return_value.__iter__.return_value = iter([source])
            with patch.object(services, "_base_queryset", return_value=queryset) as base:
                assert_localized(services.featured_products(), source)
                base.assert_called_once_with()

            source = self.service_product()
            queryset = MagicMock()
            queryset.filter.return_value.order_by.return_value.__getitem__.return_value = [source]
            with patch.object(services, "_base_queryset", return_value=queryset) as base:
                assert_localized(services.new_arrivals(), source)
                base.assert_called_once_with()

            source = self.service_product()
            queryset = MagicMock()
            queryset.filter.return_value.__iter__.return_value = iter([source])
            with patch.object(services, "_base_queryset", return_value=queryset) as base:
                assert_localized(services.products_by_maker("chen-meilin"), source)
                base.assert_called_once_with()

            source = self.service_product()
            queryset = MagicMock()
            queryset.exclude.return_value.annotate.return_value.order_by.return_value.__getitem__.return_value = [source]
            with patch.object(services, "_base_queryset", return_value=queryset) as base:
                assert_localized(services.related_products(source), source)
                base.assert_called_once_with()

            source = self.service_product()
            queryset = MagicMock()
            queryset.distinct.return_value.order_by.return_value = [source]
            with patch.object(services, "_base_queryset", return_value=queryset) as base:
                assert_localized(services.filter_products(), source)
                base.assert_called_once_with()

    def test_search_queries_raw_text_then_localises_product_results(self):
        source = self.service_product()
        queryset = MagicMock()
        queryset.search.return_value = [source]
        with (translation.override("zh-hans"),
              patch.object(services, "_base_queryset", return_value=queryset),
              patch.object(services.Collection.objects, "filter", return_value=[]),
              patch.object(services.Category.objects, "filter", return_value=[]),
              patch.object(services.Maker.objects, "filter", return_value=[]),
              patch.object(services.Article.objects, "published") as articles):
            articles.return_value.filter.return_value = []
            results = services.search("Stoneware")
        queryset.search.assert_called_once_with("Stoneware")
        self.assertEqual((results["products"][0].name,
                          results["products"][0].short_description), PRODUCT_EXPECTED[0][3:])
        self.assertEqual((source.name, source.short_description), PRODUCT_EXPECTED[0][1:3])

    def test_catalogue_payload_translates_only_display_text(self):
        source = self.service_product()
        with (translation.override("zh-hans"),
              patch.object(services, "_base_queryset", return_value=[source]) as base):
            payload = services.catalogue_payload()[source.slug]
        base.assert_called_once_with()
        self.assertEqual(payload, {
            "slug": source.slug,
            "name": PRODUCT_EXPECTED[0][3],
            "price": 42.0,
            "category": "ceramics",
            "label": PRODUCT_EXPECTED[0][4],
            "image": "/media/mug.jpg",
            "url": f"/products/{source.slug}/",
            "stock": "in-stock",
        })
        self.assertEqual((source.name, source.short_description), PRODUCT_EXPECTED[0][1:3])


class ShopLabelLocalizationTests(SimpleTestCase):
    SORT_EN = [
        ("featured", "Featured"),
        ("newest", "Newest"),
        ("price-asc", "Price: Low to High"),
        ("price-desc", "Price: High to Low"),
    ]
    SORT_ZH = [
        ("featured", "精选"),
        ("newest", "最新上架"),
        ("price-asc", "价格：从低到高"),
        ("price-desc", "价格：从高到低"),
    ]
    PRICE_EN = [
        ("under-40", "Under ¥40", 0, 40),
        ("40-70", "¥40 – ¥70", 40, 70),
        ("70-100", "¥70 – ¥100", 70, 100),
        ("over-100", "Over ¥100", 100, 10_000),
    ]
    PRICE_ZH = [
        ("under-40", "低于 ¥40"),
        ("40-70", "¥40 – ¥70"),
        ("70-100", "¥70 – ¥100"),
        ("over-100", "高于 ¥100"),
    ]
    AVAILABILITY_EN = [
        ("in-stock", "In stock"),
        ("low-stock", "Low stock"),
        ("made-to-order", "Made to order"),
    ]
    AVAILABILITY_ZH = [
        ("in-stock", "现货供应"),
        ("low-stock", "库存紧张"),
        ("made-to-order", "订制生产"),
    ]

    def price_options(self):
        return [(value, services._price_label(label))
                for value, label, _, _ in services.PRICE_BANDS]

    def availability_options(self):
        return [(value, services._availability_label(label))
                for value, label in services.AVAILABILITY_OPTIONS]

    def test_sort_ids_and_labels(self):
        self.assertEqual(services.SORT_OPTIONS, self.SORT_EN)
        self.assertEqual(set(services._SORT_FIELDS), {value for value, _ in self.SORT_EN})
        with translation.override("en"):
            self.assertEqual(services.localized_sort_options(), self.SORT_EN)
        with translation.override("zh-hans"):
            self.assertEqual(services.localized_sort_options(), self.SORT_ZH)

    def test_price_ids_bounds_and_labels(self):
        self.assertEqual(services.PRICE_BANDS, self.PRICE_EN)
        with translation.override("en"):
            self.assertEqual(self.price_options(), [(value, label) for value, label, _, _ in self.PRICE_EN])
        with translation.override("zh-hans"):
            self.assertEqual(self.price_options(), self.PRICE_ZH)

    def test_availability_ids_and_labels(self):
        self.assertEqual(services.AVAILABILITY_OPTIONS, self.AVAILABILITY_EN)
        with translation.override("en"):
            self.assertEqual(self.availability_options(), self.AVAILABILITY_EN)
        with translation.override("zh-hans"):
            self.assertEqual(self.availability_options(), self.AVAILABILITY_ZH)

    def test_stock_label_and_unknown_statuses(self):
        status_codes = ("in-stock", "low-stock", "made-to-order")
        with translation.override("en"):
            self.assertEqual([stock_label(code) for code in status_codes],
                             [label for _, label in self.AVAILABILITY_EN])
        with translation.override("zh-hans"):
            self.assertEqual([stock_label(code) for code in status_codes],
                             [label for _, label in self.AVAILABILITY_ZH])
            self.assertEqual(stock_label("sold-out"), "")
            self.assertEqual(stock_label("unknown"), "")

    def test_language_switching_keeps_display_only_changes(self):
        def displayed():
            return (services.localized_sort_options(), self.price_options(),
                    self.availability_options(), stock_label("in-stock"))

        with translation.override("en"):
            english = displayed()
        with translation.override("zh-hans"):
            chinese = displayed()
        with translation.override("en"):
            self.assertEqual(displayed(), english)
        self.assertEqual(english, (self.SORT_EN,
                                   [(value, label) for value, label, _, _ in self.PRICE_EN],
                                   self.AVAILABILITY_EN, "In stock"))
        self.assertEqual(chinese, (self.SORT_ZH, self.PRICE_ZH,
                                   self.AVAILABILITY_ZH, "现货供应"))
        self.assertEqual(services.SORT_OPTIONS, self.SORT_EN)
        self.assertEqual(services.PRICE_BANDS, self.PRICE_EN)
        self.assertEqual(services.AVAILABILITY_OPTIONS, self.AVAILABILITY_EN)


class ColourAndMaterialLocalizationTests(SimpleTestCase):
    COLOURS = {
        "Bone": "骨白", "Ash": "灰烬", "Clay": "泥土", "Olive": "橄榄绿",
        "Sand": "沙色", "Smoke": "烟灰", "Natural": "本色", "Indigo": "靛蓝",
        "Rust": "铁锈红", "Ink": "墨色", "Cedar & Fig": "雪松与无花果",
        "Wild Grass": "野草", "Smoked Cypress": "烟熏柏木",
    }
    MATERIALS = {
        "Stoneware": "炻器", "Porcelain": "瓷器", "Linen": "亚麻",
        "Cotton": "棉", "Wood": "木料", "Brass": "黄铜", "Rattan": "藤编",
        "Wax": "蜡",
    }
    SWATCHES_BEFORE = {
        "Bone": "#EFE7DA", "Ash": "#C6BFB2", "Clay": "#B4674B",
        "Olive": "#6F7757", "Ink": "#3A342D", "Sand": "#D9C9AF",
        "Indigo": "#4A5568", "Rust": "#A05A3C", "Natural": "#E2D7C3",
        "Smoke": "#8C8478",
    }
    ALIASES_BEFORE = {
        "Stoneware": ["stoneware"], "Porcelain": ["porcelain"],
        "Linen": ["linen", "flax"], "Cotton": ["cotton"],
        "Wood": ["wood", "oak", "hardwood", "timber"], "Brass": ["brass"],
        "Rattan": ["rattan"], "Wax": ["wax", "beeswax", "soy", "rapeseed"],
    }

    def test_all_colour_display_labels_and_language_switching(self):
        with translation.override("en"):
            self.assertEqual({key: localize_colour_label(key) for key in self.COLOURS},
                             {key: key for key in self.COLOURS})
        with translation.override("zh-hans"):
            self.assertEqual({key: localize_colour_label(key) for key in self.COLOURS},
                             self.COLOURS)
            self.assertEqual({key: colour_label(key) for key in self.COLOURS},
                             self.COLOURS)
        with translation.override("en"):
            self.assertEqual({key: localize_colour_label(key) for key in self.COLOURS},
                             {key: key for key in self.COLOURS})

    def test_all_material_labels_and_language_switching(self):
        with translation.override("en"):
            self.assertEqual({key: gettext(key) for key in self.MATERIALS},
                             {key: key for key in self.MATERIALS})
        with translation.override("zh-hans"):
            self.assertEqual({key: gettext(key) for key in self.MATERIALS},
                             self.MATERIALS)
        with translation.override("en"):
            self.assertEqual({key: gettext(key) for key in self.MATERIALS},
                             {key: key for key in self.MATERIALS})

    def test_unknown_or_custom_colour_stays_raw(self):
        with translation.override("zh-hans"):
            for label in ("Custom Blue", "Home", "45 cm", ""):
                with self.subTest(label=label):
                    self.assertEqual(localize_colour_label(label), label)

    def test_seed_identifiers_swatches_and_material_aliases_stay_english(self):
        self.assertEqual(SWATCHES, self.SWATCHES_BEFORE)
        self.assertEqual(MATERIAL_FAMILIES, list(self.MATERIALS))
        self.assertEqual(MATERIAL_ALIASES, self.ALIASES_BEFORE)
        variants = [variant for product in PRODUCTS for variant in product["variants"]]
        colours = [variant for variant in variants if variant["group"] == "colour"]
        sizes = [variant for variant in variants if variant["group"] == "size"]
        self.assertEqual({variant["label"] for variant in colours}, set(self.COLOURS))
        self.assertTrue(all(variant["id"] == "colour-" + variant["label"].lower()
                            for variant in colours))
        self.assertTrue(all(variant["swatch"] == SWATCHES.get(variant["label"], "#D9C9AF")
                            for variant in colours))
        self.assertEqual({variant["label"] for variant in sizes}, {"45 cm", "60 cm", "Medium", "Large"})
        self.assertTrue(all(variant["id"] == "size-" + variant["label"].lower().replace(" ", "-")
                            for variant in sizes))
        self.assertEqual([variant["label"] for variant in next(
            product for product in PRODUCTS if product["slug"] == "soy-wax-studio-candle"
        )["variants"]], ["Cedar & Fig", "Wild Grass", "Smoked Cypress"])

    def test_shop_facets_translate_labels_but_keep_filter_values(self):
        with (patch.object(services, "_base_queryset") as base,
              patch.object(services.Category.objects, "filter") as categories,
              patch.object(services.ProductVariant.objects, "filter") as variants):
            base.return_value.filter.return_value.count.return_value = 1
            base.return_value.order_by.return_value.values_list.return_value.first.return_value = 150
            categories.return_value.annotate.return_value.order_by.return_value = []
            variants.return_value.values.return_value.distinct.return_value.order_by.return_value = [
                {"label": "Bone", "swatch": "#EFE7DA"},
                {"label": "Custom Blue", "swatch": "#123456"},
            ]
            with translation.override("en"):
                english = services.shop_facets()
            with translation.override("zh-hans"):
                chinese = services.shop_facets()
        self.assertEqual([(item["value"], item["label"]) for item in english["materials"]],
                         [(value, value) for value in self.MATERIALS])
        self.assertEqual([(item["value"], item["label"]) for item in chinese["materials"]],
                         list(self.MATERIALS.items()))
        self.assertEqual(english["colours"], [
            {"value": "Bone", "label": "Bone", "swatch": "#EFE7DA"},
            {"value": "Custom Blue", "label": "Custom Blue", "swatch": "#123456"},
        ])
        self.assertEqual(chinese["colours"], [
            {"value": "Bone", "label": "骨白", "swatch": "#EFE7DA"},
            {"value": "Custom Blue", "label": "Custom Blue", "swatch": "#123456"},
        ])

    def test_product_template_separates_display_from_cart_identifier(self):
        source = (Path(__file__).parent / "templates/frontend/product/detail.html").read_text(encoding="utf-8")
        colour_section = source.split("{% if colours %}", 1)[1].split("{% if sizes %}", 1)[0]
        template = Template("{% load i18n frontend_extras %}{% if colours %}" + colour_section)
        variants = [SimpleNamespace(label="Bone", swatch="#EFE7DA", available=True),
                    SimpleNamespace(label="Olive", swatch="#6F7757", available=False)]
        with translation.override("zh-hans"):
            html = template.render(Context({"colours": variants}))
        self.assertIn("data-variant-value>骨白</span>", html)
        self.assertIn('data-variant="Bone"', html)
        self.assertIn('data-display-label="骨白"', html)
        self.assertIn('aria-label="骨白"', html)
        self.assertIn('data-variant="Olive"', html)
        self.assertIn('data-display-label="橄榄绿"', html)
        self.assertIn('aria-label="橄榄绿 — 已售罄"', html)
        size_section = source.split("{% if sizes %}", 1)[1].split("{% endwith %}", 1)[0]
        size_template = Template("{% load i18n frontend_extras %}{% if sizes %}" + size_section)
        size_html = size_template.render(Context({"sizes": [SimpleNamespace(label="45 cm", available=True)]}))
        self.assertIn('data-variant="45 cm"', size_html)
        self.assertIn('data-variant-value>45 cm</span>', size_html)
        self.assertNotIn("data-display-label", size_html)

    def test_product_card_swatch_title_uses_display_label(self):
        source = (Path(__file__).parent / "templates/frontend/partials/product_card.html").read_text(encoding="utf-8")
        swatches = source.split("{% with colours=", 1)[1].split("{% endwith %}", 1)[0]
        template = Template("{% load i18n frontend_extras %}{% with colours=" + swatches + "{% endwith %}")
        product = SimpleNamespace(variants=[SimpleNamespace(group="colour", label="Ash", swatch="#C6BFB2")])
        with translation.override("zh-hans"):
            html = template.render(Context({"product": product}))
        self.assertIn('title="灰烬"', html)
        self.assertIn('background:#C6BFB2', html)

    def test_cart_serializer_localises_only_colour_display(self):
        def display(group, label, language):
            item = SimpleNamespace(variant=SimpleNamespace(group=group, label=label))
            serializer = CartItemSerializer(context={"request": SimpleNamespace(LANGUAGE_CODE=language)})
            return serializer.get_variant_label(item), item.variant.label

        with translation.override("en"):
            self.assertEqual(display("colour", "Bone", "zh-hans"), ("骨白", "Bone"))
            self.assertEqual(display("colour", "Bone", "zh-cn"), ("骨白", "Bone"))
        with translation.override("zh-hans"):
            self.assertEqual(display("colour", "Bone", "en"), ("Bone", "Bone"))
            self.assertEqual(display("colour", "Home", "zh-hans"), ("Home", "Home"))
            self.assertEqual(display("size", "Bone", "zh-hans"), ("Bone", "Bone"))
            self.assertEqual(display("finish", "Ash", "zh-hans"), ("Ash", "Ash"))
        self.assertEqual(display("colour", "Bone", "zh-hans"), ("骨白", "Bone"))
        self.assertIn("variant_uuid", CartItemSerializer().fields)

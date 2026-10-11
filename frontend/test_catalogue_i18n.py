"""Database-free checks for catalogue collection presentation translations."""

from django.test import SimpleTestCase
from django.utils import translation
from django.utils.translation import gettext

from products.management.commands.seed import EXTRA_COLLECTIONS
from products.models import Category, Collection

from frontend.catalogue_i18n import localize_collection
from frontend.mockdata.collections import CATEGORIES, COLLECTIONS


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
        )

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

    def test_editorial_collection_translations_are_preserved(self):
        seeds = [item for item in COLLECTIONS if item["kind"] == "editorial"] + EXTRA_COLLECTIONS
        with translation.override("zh-hans"):
            for seed, expected in zip(seeds, EDITORIAL_EXPECTED, strict=True):
                with self.subTest(slug=seed["slug"]):
                    self.assertEqual(seed["slug"], expected[0])
                    source = self.make_editorial(seed)
                    localized = localize_collection(source)
                    self.assertIsNot(localized, source)
                    self.assertEqual(
                        (localized.name, localized.tagline, localized.description),
                        expected[1:],
                    )
                    self.assertEqual(source.name, seed.get("name", seed.get("title")))
                    self.assertEqual(localized.slug, source.slug)

    def test_non_chinese_language_returns_original(self):
        category = self.make_category(CATEGORIES[0])
        editorial = self.make_editorial(COLLECTIONS[-1])
        with translation.override("fr"):
            self.assertIs(localize_collection(category), category)
            self.assertIs(localize_collection(editorial), editorial)

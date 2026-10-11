"""Chinese presentation copy for seeded catalogue records."""

from __future__ import annotations

from copy import copy

from django.utils.translation import get_language, gettext, pgettext

from frontend.mockdata.collections import CATEGORIES, COLLECTIONS, EXTRA_COLLECTIONS
from frontend.mockdata.products import PRODUCTS, PRODUCTS_BY_SLUG


MAKER_TRANSLATIONS = {
    "chen-meilin": {
        "name": "陈梅琳",
        "discipline": "陶艺师",
        "location": "江西景德镇",
        "tagline": "薄到足以承托光线的瓷器。",
        "biography": [
            "梅琳曾在景德镇一位陶艺大师门下学习六年，之后在古窑区东侧开设了一间小工作室。她几乎只使用本地瓷石，泥料取自离工作室一小时车程的地方。",
            "她的器形安静而略带不完美，这是刻意为之。微微下沉的器口、露出泥土质感的素烧足部，都是她有意留下的痕迹，也正是每件作品各不相同的原因。",
        ],
        "process": [
            "每天早晨手工揉泥，静置一夜后才开始拉坯。",
            "每件作品都在转盘上完成，并在半干时修坯。",
            "釉料以灰烬、长石和氧化铁分批调配。",
            "以 1280°C 进行一次燃气烧制，窑炉缓慢冷却两天。",
        ],
    },
    "lu-wenjing": {
        "name": "陆文静",
        "discipline": "织工与天然染色师",
        "location": "云南大理",
        "tagline": "每一次清洗，靛蓝都更深一层。",
        "biography": [
            "文静向祖母学习染色。祖母曾在大理的家屋后经营一口靛蓝染缸。如今她自己种植蓝靛，并在收获季与邻近的三户人家合作。",
            "她使用父亲制作的木质地织机，以省内纺成的棉与麻织布。她工作室里的任何东西都不会以完全相同的方式染两次，她也不再为此道歉。",
        ],
        "process": [
            "靛蓝在陶缸中发酵，并在整个季节每周补养。",
            "布料浸染六至十四次，视所需深浅而定。",
            "在河水中清洗并于阴凉处晾干，使颜色保持均匀。",
            "在木质地织机上手工织造、整理与锁边。",
        ],
    },
    "zhao-hesheng": {
        "name": "赵和生",
        "discipline": "木匠",
        "location": "安徽徽州",
        "tagline": "顺着木纹工作，从不与它对抗。",
        "biography": [
            "和生花了十年修复徽州木屋，之后才转向制作更小的器物。他的大部分木材仍来自这些修复工程，是已经度过一段岁月的梁木与地板。",
            "他手工切削榫卯，所有作品都以生亚麻籽油完成。每件东西在握感恰到好处之前，都不会离开工作台。",
        ],
        "process": [
            "回收木材先加工，再静置一季让它稳定下来。",
            "每个榫接都手工切削与修整，不用木钉，也不用填料。",
            "表面经过五种不同粗细的磨料处理，呈现柔和光泽。",
            "使用食品级亚麻籽油完成表面处理，一周内重复涂刷三次。",
        ],
    },
    "xu-anying": {
        "name": "徐安莹",
        "discipline": "制烛师与调香师",
        "location": "江苏苏州",
        "tagline": "像栽种花园一样构筑香气。",
        "biography": [
            "安莹曾学习中国古典园林设计，之后接受调香训练。她以设计庭院的方式思考香气：首先遇见什么，之后又会发现什么。",
            "她在运河附近一间改造的底层工作室里手工浇注，每批四十支。每批蜡烛会静置固化两周，之后才点燃烛芯。",
        ],
        "process": [
            "精油混合后静置十天，让香气彼此融合。",
            "大豆蜡与菜籽蜡低温融化，温度不超过 65°C。",
            "每次一只容器，分批手工浇注，每批四十支。",
            "固化十四天后，从每批中抽样进行燃烧测试。",
        ],
    },
    "ye-ruolan": {
        "name": "叶若兰",
        "discipline": "纺织艺术家",
        "location": "浙江杭州",
        "tagline": "将亚麻洗到仿佛从未僵硬过。",
        "biography": [
            "若兰使用欧洲亚麻，在自己的工作室里以经过两年改良的石洗工艺完成整理。她说，理想状态是让新作品摸起来像已经陪伴你多年的旧物。",
            "她亲自裁剪和缝制所有作品，忙碌月份会有一名助手，并始终刻意保持系列精简。",
        ],
        "process": [
            "亚麻来自同一家纺厂，并以小批量裁片处理。",
            "缝合后，成品进行两次石洗。",
            "平铺晾干后只轻轻熨烫一次，保留自然的褶皱。",
            "逐条检查缝线，再折叠包裹。",
        ],
    },
}

_SEEDED_COLOUR_LABELS = frozenset(
    variant["label"] for product in PRODUCTS for variant in product["variants"]
    if variant["group"] == "colour"
)


def localize_colour_label(label: str) -> str:
    """Translate a recognised colour for display without changing its stored label."""
    return gettext(label) if label in _SEEDED_COLOUR_LABELS else label

FAQ_GROUP_TRANSLATIONS = {
    "orders": ("订单", "下单、修改与取消。"),
    "shipping": ("配送", "时效、费用与物流查询。"),
    "returns": ("退货", "改变主意与收到破损商品。"),
    "product-care": ("作品保养", "让作品长久保持良好状态。"),
    "handmade-variations": ("手作差异", "什么是正常差异，什么属于瑕疵。"),
    "gifting": ("礼赠", "留言、包装与礼品订单。"),
}

ARTICLE_TRANSLATIONS = {
    "why-no-two-glazes-match": ("为什么没有两种釉色完全相同", "手工灰釉记录着烧制它的过程。我们为什么不再追求完全一致？"),
    "an-indigo-vat-in-dali": ("大理的一口靛蓝染缸", "陆文静在家后院养着四口发酵染缸，每周照料，没有捷径。"),
    "how-to-care-for-handmade-ceramics": ("如何保养手作陶器", "真正缩短手作器物寿命的，多数是高温，而不是日常使用。"),
    "the-case-for-buying-less": ("少买一些的理由", "我们每月制作约四百件作品，这就是不打算制作四千件的原因。"),
    "a-table-set-for-nothing-in-particular": ("一张没有特别理由的餐桌", "在星期二也用上那些好盘子。"),
}


def _is_chinese() -> bool:
    return (get_language() or "").lower().startswith("zh")


def is_chinese() -> bool:
    return _is_chinese()


def localize_collection(collection):
    if not _is_chinese():
        return collection

    if collection.kind == "category":
        source = next((item for item in CATEGORIES if item["slug"] == collection.slug), None)
    elif collection.kind == "editorial":
        source = next(
            (item for item in COLLECTIONS
             if item["kind"] == "editorial" and item["slug"] == collection.slug),
            None,
        )
        if source is None:
            source = next(
                (item for item in EXTRA_COLLECTIONS if item["slug"] == collection.slug),
                None,
            )
    else:
        return collection
    if source is None:
        return collection

    localized = copy(collection)
    english_name = source["title"] if "title" in source else source["name"]
    for field, english in (("name", english_name), ("tagline", source["tagline"]),
                           ("description", source["description"])):
        current = getattr(collection, field)
        if current == english:
            value = (pgettext("category", "Home")
                     if field == "name" and collection.kind == "category"
                     and collection.slug == "home" else gettext(current))
            setattr(localized, field, value)
    return localized


def localize_maker(maker):
    if not _is_chinese() or maker.slug not in MAKER_TRANSLATIONS:
        return maker
    localized = copy(maker)
    for field, value in MAKER_TRANSLATIONS[maker.slug].items():
        setattr(localized, field, value)
    return localized


def localize_product(product):
    if not _is_chinese():
        return product
    source = PRODUCTS_BY_SLUG.get(product.slug)
    if source is None:
        return product
    localized = copy(product)
    fields = (
        ("name", "name"),
        ("short_description", "short_description"),
        ("description", "description"),
        ("story", "story"),
        ("care_instructions", "care"),
        ("shipping_information", "dispatch"),
    )
    for field, source_field in fields:
        current = getattr(product, field)
        if current == source[source_field]:
            setattr(localized, field, gettext(current))
    return localized


def localize_faq_group(group):
    if not is_chinese() or group.slug not in FAQ_GROUP_TRANSLATIONS:
        return group
    localized = copy(group)
    localized.title, localized.blurb = FAQ_GROUP_TRANSLATIONS[group.slug]
    return localized


def localize_article(article):
    if not is_chinese() or not article or article.slug not in ARTICLE_TRANSLATIONS:
        return article
    localized = copy(article)
    localized.title, localized.standfirst = ARTICLE_TRANSLATIONS[article.slug]
    return localized

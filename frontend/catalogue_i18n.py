"""Chinese presentation copy for seeded catalogue records."""

from copy import copy

from django.utils.translation import get_language

COLLECTION_TRANSLATIONS = {
    "ceramics": {"name": "陶器", "tagline": "逐件拉坯、修整与烧制。", "description": "为餐桌而作的炻器与瓷器，来自景德镇的一间工作室。"},
    "textiles": {"name": "织物", "tagline": "经编织、染色与水洗，直至柔软。", "description": "亚麻与手织棉布，以云南种植的蓝靛染色。"},
    "home": {"name": "家居", "tagline": "为房间里安静的角落而作。", "description": "蜡烛、木器与黄铜小物，为房间增添安静的质感。"},
    "gifts": {"name": "礼品", "tagline": "以本色纸与棉绳包裹。", "description": "适合作为礼物寄送的作品，全部手工装盒。"},
    "earth": {"name": "大地系列", "tagline": "灰烬、泥土、蓝靛与本色亚麻。", "description": "取自精简材料清单的九件作品，呈现统一的自然色调。"},
    "quiet-mornings": {"name": "静谧清晨", "tagline": "献给一天开始的第一个小时。", "description": "为清晨准备的杯子、手冲壶与蜡烛。"},
    "studio-essentials": {"name": "工作室日用", "tagline": "我们自己每天使用的作品。", "description": "工作室真正用于日常的围裙、木板与毛巾。"},
}

MAKER_TRANSLATIONS = {
    "chen-meilin": {"name": "陈梅琳", "discipline": "陶艺师", "location": "江西景德镇", "tagline": "薄到足以承托光线的瓷器。"},
    "lu-wenjing": {"name": "陆文静", "discipline": "织工与天然染色师", "location": "云南大理", "tagline": "每一次清洗，靛蓝都更深一层。"},
    "zhao-hesheng": {"name": "赵和生", "discipline": "木匠", "location": "安徽徽州", "tagline": "顺着木纹工作，从不与它对抗。"},
    "xu-anying": {"name": "徐安莹", "discipline": "制烛师与调香师", "location": "江苏苏州", "tagline": "像栽种花园一样构筑香气。"},
    "ye-ruolan": {"name": "叶若兰", "discipline": "纺织艺术家", "location": "浙江杭州", "tagline": "将亚麻洗到仿佛从未僵硬过。"},
}

PRODUCT_TRANSLATIONS = {
    "hand-thrown-stoneware-mug": ("手拉炻器马克杯", "炻器 · 陈梅琳"), "speckled-breakfast-bowl": ("斑点早餐碗", "炻器 · 陈梅琳"),
    "ceramic-pour-over-dripper": ("陶瓷手冲滤杯", "瓷器 · 陈梅琳"), "ash-glazed-dinner-plate": ("灰釉餐盘", "炻器 · 陈梅琳"),
    "stoneware-serving-platter": ("炻器餐盘", "炻器 · 陈梅琳"), "matte-ceramic-vase": ("哑光陶瓷花瓶", "炻器 · 陈梅琳"),
    "tea-cup-set-of-two": ("双人茶杯套装", "瓷器 · 陈梅琳"), "linen-market-tote": ("亚麻购物袋", "水洗亚麻 · 叶若兰"),
    "woven-cotton-throw": ("手织棉盖毯", "手织棉 · 陆文静"), "linen-cushion-cover": ("亚麻靠垫套", "水洗亚麻 · 叶若兰"),
    "stonewashed-table-runner": ("石洗亚麻桌旗", "水洗亚麻 · 叶若兰"), "hand-loomed-tea-towel": ("手织茶巾", "棉与亚麻 · 陆文静"),
    "quilted-linen-apron": ("绗缝亚麻围裙", "水洗亚麻 · 叶若兰"), "soy-wax-studio-candle": ("大豆蜡工作室香薰蜡烛", "大豆蜡与菜籽蜡 · 徐安莹"),
    "handmade-incense-holder": ("手作香座", "炻器 · 陈梅琳"), "olive-wood-serving-board": ("橄榄木餐板", "再生木料 · 赵和生"),
    "brass-oak-candle-snuffer": ("黄铜橡木烛剪", "黄铜与橡木 · 赵和生"), "rattan-storage-basket": ("藤编收纳篮", "藤编 · 陆文静"),
    "ceramic-ring-dish": ("陶瓷首饰盘", "瓷器 · 陈梅琳"), "studio-gift-set": ("工作室礼品套装", "三件作品，手工包裹 · 多位匠人"),
    "beeswax-taper-pair": ("蜂蜡长烛一对", "纯蜂蜡 · 徐安莹"),
}

COLOUR_TRANSLATIONS = {"Bone": "骨白", "Ash": "灰烬", "Clay": "泥土", "Olive": "橄榄绿", "Sand": "沙色", "Smoke": "烟灰", "Natural": "本色", "Indigo": "靛蓝", "Rust": "铁锈红", "Ink": "墨色", "Cedar & Fig": "雪松与无花果", "Wild Grass": "野草", "Smoked Cypress": "烟熏柏木"}
MATERIAL_TRANSLATIONS = {"Stoneware": "炻器", "Porcelain": "瓷器", "Linen": "亚麻", "Cotton": "棉", "Wood": "木料", "Brass": "黄铜", "Rattan": "藤编", "Wax": "蜡"}

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


def is_chinese():
    return (get_language() or "").lower().startswith("zh")


def _localize(obj, translations):
    if not is_chinese() or not obj or obj.slug not in translations:
        return obj
    localized = copy(obj)
    for field, value in translations[obj.slug].items():
        setattr(localized, field, value)
    return localized


def localize_collection(collection):
    return _localize(collection, COLLECTION_TRANSLATIONS)


def localize_maker(maker):
    return _localize(maker, MAKER_TRANSLATIONS)


def localize_product(product):
    if not is_chinese() or not product or product.slug not in PRODUCT_TRANSLATIONS:
        return product
    localized = copy(product)
    localized.name, localized.short_description = PRODUCT_TRANSLATIONS[product.slug]
    return localized


def localize_faq_group(group):
    if not is_chinese() or group.slug not in FAQ_GROUP_TRANSLATIONS:
        return group
    localized = copy(group)
    localized.title, localized.blurb = FAQ_GROUP_TRANSLATIONS[group.slug]
    return localized


def localize_article(article):
    if not is_chinese() or article.slug not in ARTICLE_TRANSLATIONS:
        return article
    localized = copy(article)
    localized.title, localized.standfirst = ARTICLE_TRANSLATIONS[article.slug]
    return localized

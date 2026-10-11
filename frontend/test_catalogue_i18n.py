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
from frontend.mockdata.products import CARE_BY_CATEGORY, PRODUCTS, SWATCHES
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

PRODUCT_DETAIL_EXPECTED = (
    ("hand-thrown-stoneware-mug", "A mug with a little weight to it, thrown to sit low in the hand. The glaze pools slightly where the wall meets the base, so the colour is never quite even across a set.", "Meilin threw the first of these for herself, then kept making them because visitors to the studio would not put them down. The handle is pulled by hand rather than cast, which is why the curve is a fraction different on every one.", "一只略有分量的马克杯，拉坯成低矮杯身，握在手中安稳贴合。釉料会在杯壁与杯底交接处略微积聚，因此同一套杯子的色泽也不会完全一致。", "梅琳最初为自己拉坯制作了这只杯子，后来到访工作室的人总是爱不释手，她便一直做了下去。杯把由手工拉制而非模具浇铸，因此每一只的弧度都会有细微差异。"),
    ("speckled-breakfast-bowl", "Wide enough for oats and deep enough for soup. The iron in the clay breaks through the glaze as fine dark flecks during firing.", "The speckle is not added. It is iron already present in the local clay, which surfaces only above 1250°C -- a firing Meilin holds for nine hours.", "宽度足以盛燕麦粥，深度也适合盛汤。烧制时，陶土中的铁质会透过釉面，形成细小的深色斑点。", "斑点并非额外添加，而是当地陶土中原有的铁质，在温度超过 1250°C 时才会显现；梅琳会将这一烧制温度保持九小时。"),
    ("ceramic-pour-over-dripper", "A single-piece dripper with three ribs turned into the cone, so water moves evenly through the bed rather than channelling down one side.", "Six prototypes went into the angle of the cone. Meilin brewed on every one of them for a fortnight before settling on this shape.", "一体成型的滤杯，锥形内壁设有三道导流凸棱，让水流均匀通过咖啡粉层，避免沿一侧集中流下。", "为了确定锥体角度，前后做了六个原型。梅琳连续两周用这六个原型逐一冲煮测试，最终才选定现在的形状。"),
    ("ash-glazed-dinner-plate", "A everyday plate with a low, generous rim. The ash glaze moves in the kiln, so the edge is usually a shade lighter than the well.", "The glaze is mixed from ash swept out of the studio's own kiln -- a practice old enough in Jingdezhen that nobody there thinks of it as unusual.", "一只适合日常使用的餐盘，盘沿低而宽。灰釉在窑中流动，因此边缘通常比盘心浅一个色调。", "釉料由工作室自家窑炉中清扫出的灰烬调制而成——这项做法在景德镇由来已久，当地人并不觉得稀奇。"),
    ("stoneware-serving-platter", "An oval platter for bread, roasted vegetables or a whole fish. Thrown, then pressed gently out of round while still soft.", "Made only in small runs, when the large kiln is fired. Meilin will not fire it half empty, so these appear a few times a year.", "椭圆形餐盘，适合盛放面包、烤蔬菜或整条鱼。先拉坯成型，再趁陶土尚软时轻轻压成略不规则的形状。", "只有在大型窑炉烧制时才会小批量制作。梅琳不会让窑炉半空着烧，因此这种餐盘一年只会出现几次。"),
    ("matte-ceramic-vase", "A tall, narrow-necked vase that holds a few stems upright without propping. Matte outside, glossed inside so it holds water.", "Meilin keeps one on the windowsill of the studio with whatever is in season. Most of the year that means a single branch.", "高挑的细颈花瓶，无需支撑便能让几枝花材直立。外壁为哑光质感，内壁施亮釉，可以盛水。", "梅琳在工作室窗台上放着一只，插上当季的花材。一年中的大部分时候，那意味着一根枝条。"),
    ("tea-cup-set-of-two", "Two handleless cups, thin at the lip and thicker at the base. Pale celadon that shifts towards green where the glaze gathers.", "Thrown in pairs and fired side by side, so the two cups in a set carry the same marks from the same corner of the kiln.", "两只无柄茶杯，杯口较薄，杯底较厚。淡青瓷釉在釉料积聚处会呈现更深的绿色。", "成对拉坯，并排烧制，因此一套中的两只杯子会留下来自窑炉同一角落的相同痕迹。"),
    ("linen-market-tote", "A flat-bottomed tote in heavyweight linen, with an inside pocket and handles long enough to carry over a shoulder.", "Ruolan made the first one because nothing she owned would hold a week of vegetables and still look like something she wanted to carry.", "采用厚实亚麻制成的平底托特包，设有内袋，提手长度足以肩背。", "若兰之所以做出第一只，是因为她手头没有一款包，既能装下一周采购的蔬菜，又好看得让她愿意随身携带。"),
    ("woven-cotton-throw", "Woven in two panels and joined by hand down the centre. Heavy enough for a bed, soft enough for a chair.", "Wenjing dips the yarn before it is ever woven, which is why the colour sits inside the cloth rather than on it, and deepens rather than fades.", "由两幅织片拼成，中间以手工缝合。厚实得可铺在床上，也柔软得适合搭在椅上。", "文静在织造之前就将纱线浸染，因此色彩深入织物内部而非停留在表面，并会随着使用加深而不是褪去。"),
    ("linen-cushion-cover", "A simple envelope cover with a buttoned back. Washed twice before it leaves the studio so it arrives already soft.", "The buttons are coconut shell, cut and drilled by a workshop two streets from Ruolan's own -- the last of its kind in the neighbourhood.", "简洁的信封式靠垫套，背面以纽扣开合。离开工作室前经过两次水洗，送到手中时已柔软舒适。", "纽扣由椰壳制成，在距离若兰工作室两条街的一家作坊切割并钻孔——那是附近最后一家这样的作坊。"),
    ("stonewashed-table-runner", "A long runner with a deep hand-turned hem. Creases readily, which is rather the point.", "Ruolan does not press these flat before packing. A runner that arrives perfectly smooth, she says, has been finished by a machine.", "一条长桌旗，饰有宽大的手工折边。它很容易留下褶皱，而这正是设计的本意。", "若兰在包装前不会把它们熨平。她说，一条到手时平整无痕的桌旗，是机器加工出来的。"),
    ("hand-loomed-tea-towel", "Loosely woven so it dries fast, with a hanging loop set into the corner. Gets better with washing.", "Woven on the narrow loom Wenjing keeps for offcuts, using yarn left over from the throws. No two runs are quite the same colour.", "织法疏松，干得快，角落设有挂环。越洗越好用。", "使用文静专门处理余料的窄幅织机织成，纱线来自盖毯制作剩余的材料。每一批的颜色都不完全相同。"),
    ("quilted-linen-apron", "A cross-back apron with a lightly quilted front panel and two deep pockets. Adjustable at the neck, ties at the waist.", "Designed with a baker in Hangzhou who wanted something that would take flour, heat and a hot pan handle without falling apart in a year.", "交叉背带式围裙，前片带轻薄绗缝，设有两个深口袋。颈带可调节，腰间系带固定。", "与杭州的一位烘焙师共同设计；她想要一件能经受面粉、高温和滚烫锅柄，又不会在一年内散架的围裙。"),
    ("soy-wax-studio-candle", "Cedar, dry earth and a little green fig. Poured into a stoneware vessel worth keeping once the wax is gone.", "Anying built this scent around the smell of her workshop after rain -- wet stone, cut wood, and the fig tree in the courtyard next door.", "雪松、干燥泥土与一丝青无花果的香气。蜡烛浇注在炻器容器中，蜡燃尽后仍值得继续使用。", "安莹以雨后工作室的气味为灵感调制这款香气——潮湿的石头、切开的木材，以及隔壁庭院里的无花果树。"),
    ("handmade-incense-holder", "A shallow dish with an off-centre hole, sized for standard incense sticks. Unglazed outside so it keeps a little grip on the table.", "Meilin makes these from the clay left at the end of a throwing session -- too little for a bowl, exactly enough for one of these.", "浅盘设有偏离中心的小孔，适配标准线香。外壁不施釉，与桌面接触时能增加一些摩擦力。", "梅琳用每次拉坯结束时剩下的陶土制作这些香座——做一只碗太少，做一个香座却刚刚好。"),
    ("olive-wood-serving-board", "A long board with a shaped handle and a lip cut into the underside so it lifts easily off a flat table.", "Cut from beams salvaged during the restoration of a Huizhou courtyard house. The grain, and occasionally an old nail hole, comes with the timber.", "一块带造型手柄的长餐板，底部切出一道托边，方便从平坦桌面上拿起。", "取材自修复一座徽州院落时回收的梁木。木纹，以及偶尔可见的旧钉孔，都是木材本身留下的痕迹。"),
    ("brass-oak-candle-snuffer", "An unlacquered brass bell on a turned oak handle. The brass will darken with handling, which is how it is meant to go.", "Hesheng turns the handles from oak offcuts and has the bells spun by a metalworker he has used for eleven years.", "旋制橡木手柄上装有一只未上漆的黄铜钟罩。黄铜会随着触摸逐渐变暗，这正是它应有的变化。", "和生用橡木余料车制手柄，钟罩则由一位与他合作了十一年的金工匠人旋压成型。"),
    ("rattan-storage-basket", "A deep round basket with soft rope handles, woven closely enough to hold its shape when empty.", "Woven by a group of five weavers in a village outside Dali, in the weeks between planting and harvest.", "深圆形篮筐配柔软绳把手，编织紧密，即使空着也能保持形状。", "由大理郊外一个村庄的五位编织匠人在播种与收获之间的农闲时节编成。"),
    ("ceramic-ring-dish", "A small pinched dish for rings, earrings or the change in your pocket. Pinched rather than thrown, so the rim is deliberately uneven.", "The first of these were made as thank-you gifts for the studio's earliest customers. Enough people asked to buy one that they became a product.", "一只用于放置戒指、耳环或口袋零钱的手捏小碟。采用手捏而非拉坯成型，因此碟沿特意保留不规则感。", "最初一批是为感谢工作室早期顾客而制作的礼物。后来有足够多的人询问能否购买，它们便成为了正式商品。"),
    ("studio-gift-set", "A mug, a small candle and a tea towel, wrapped in unbleached paper and tied with cotton string. A card can be written at checkout.", "The set we send most often, and the one the studio sends to its own suppliers at the end of every year.", "一只马克杯、一支小蜡烛和一条茶巾，以未漂白纸张包裹，并用棉绳系好。可在结账时填写卡片内容。", "这是我们最常寄出的礼盒，也是工作室每年年末寄给自家供应商的那一款。"),
    ("beeswax-taper-pair", "Two hand-dipped tapers in unbleached beeswax. They smell faintly of honey when lit and drip very little.", "Dipped forty times each, one layer at a time, over the course of an afternoon.", "两支以未漂白蜂蜡手工浸制的长烛。点燃时带有淡淡蜂蜜香，且极少滴蜡。", "每支都要分层浸制四十次，整个过程用去一个下午。"),
)

CARE_EXPECTED = (
    ("ceramics", "Dishwasher safe, though hand washing keeps the glaze bright. Avoid thermal shock -- let a hot piece cool before rinsing. Not for direct flame.", "可用洗碗机清洗，但手洗更能保持釉色明亮。避免骤冷骤热——热器皿应冷却后再冲洗。不可直接接触明火。"),
    ("textiles", "Machine wash cool on a gentle cycle with a mild detergent. Line dry in shade. Warm iron while slightly damp if you want a crisper finish.", "使用温和洗涤剂，以低温轻柔机洗。置于阴凉处晾干。如需更挺括的质感，可在织物尚微湿时用中温熨烫。"),
    ("home", "Wipe with a soft, barely damp cloth. Keep out of prolonged direct sun. Re-oil natural wood two or three times a year to keep it from drying out.", "用柔软、仅微微湿润的布擦拭。避免长时间阳光直射。天然木材每年重新上油两到三次，以免过度干燥。"),
    ("gifts", "Care varies by piece -- each item ships with its own short care card.", "护理方式因单品而异——每件商品发货时都会附带一张简短的专属护理卡。"),
)

DISPATCH_EXPECTED = (
    ("Ships in 2–4 working days", "2–4 个工作日内发货"),
    ("Made to order · ships in 3–4 weeks", "按订单制作 · 3–4 周内发货"),
    ("Made to order · ships in 2–3 weeks", "按订单制作 · 2–3 周内发货"),
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
        detail = next(item for item in PRODUCT_DETAIL_EXPECTED if item[0] == slug)
        values = {
            "id": 37,
            "slug": slug,
            "name": name,
            "short_description": short_description,
            "description": detail[1],
            "story": detail[2],
            "price": Decimal("42.00"),
            "currency": "CNY",
            "category_id": 3,
            "maker_id": 4,
            "materials": ["Stoneware", "Ash glaze"],
            "dimensions": "8 cm × 9 cm",
            "care_instructions": CARE_EXPECTED[0][1],
            "shipping_information": DISPATCH_EXPECTED[0][0],
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
            )
            localized = localize_product(source)
            self.assertEqual(
                (localized.pk, localized.uuid, localized.slug, localized.price,
                 localized.currency, localized.category_id, localized.maker_id,
                 localized.materials, localized.dimensions, localized.stock_status,
                 localized.stock_quantity, localized.is_active, localized.is_featured,
                 localized.is_new_arrival, localized.sort_weight),
                machine_fields,
            )

    def service_product(self):
        expected = PRODUCT_EXPECTED[0]
        images = SimpleNamespace(all=lambda: [SimpleNamespace(url="/media/mug.jpg")])
        return SimpleNamespace(
            pk=37, slug=expected[0], name=expected[1], short_description=expected[2],
            description=PRODUCT_DETAIL_EXPECTED[0][1], story=PRODUCT_DETAIL_EXPECTED[0][2],
            care_instructions=CARE_EXPECTED[0][1],
            shipping_information=DISPATCH_EXPECTED[0][0],
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

    def test_all_product_detail_content_in_english_and_chinese(self):
        self.assertEqual(
            [(item["slug"], item["description"], item["story"]) for item in PRODUCTS],
            [expected[:3] for expected in PRODUCT_DETAIL_EXPECTED],
        )
        for detail in PRODUCT_DETAIL_EXPECTED:
            product_expected = next(item for item in PRODUCT_EXPECTED if item[0] == detail[0])
            source = self.make_product(product_expected)
            with self.subTest(slug=detail[0], language="en"):
                with translation.override("en"):
                    self.assertIs(localize_product(source), source)
                    self.assertEqual((source.description, source.story), detail[1:3])
            with self.subTest(slug=detail[0], language="zh-hans"):
                with translation.override("zh-hans"):
                    localized = localize_product(source)
                self.assertEqual((localized.description, localized.story), detail[3:])
                self.assertEqual((source.description, source.story), detail[1:3])

    def test_all_care_and_dispatch_content(self):
        self.assertEqual(CARE_BY_CATEGORY,
                         {category: english for category, english, _ in CARE_EXPECTED})
        representatives = {
            "ceramics": "hand-thrown-stoneware-mug",
            "textiles": "linen-market-tote",
            "home": "soy-wax-studio-candle",
            "gifts": "ceramic-ring-dish",
        }
        with translation.override("zh-hans"):
            for category, english, chinese in CARE_EXPECTED:
                expected = next(item for item in PRODUCT_EXPECTED
                                if item[0] == representatives[category])
                source = self.make_product(expected, care_instructions=english)
                localized = localize_product(source)
                with self.subTest(category=category):
                    self.assertEqual(localized.care_instructions, chinese)
                    self.assertEqual(localized.care, chinese)
                    self.assertEqual(source.care_instructions, english)

            dispatch_products = (
                ("hand-thrown-stoneware-mug", DISPATCH_EXPECTED[0]),
                ("stoneware-serving-platter", DISPATCH_EXPECTED[1]),
                ("rattan-storage-basket", DISPATCH_EXPECTED[2]),
            )
            self.assertEqual({item["dispatch"] for item in PRODUCTS},
                             {english for english, _ in DISPATCH_EXPECTED})
            for slug, (english, chinese) in dispatch_products:
                expected = next(item for item in PRODUCT_EXPECTED if item[0] == slug)
                source = self.make_product(expected, shipping_information=english)
                localized = localize_product(source)
                with self.subTest(slug=slug):
                    self.assertEqual(localized.shipping_information, chinese)
                    self.assertEqual(localized.dispatch, chinese)
                    self.assertEqual(source.shipping_information, english)

    def test_product_detail_language_switching(self):
        source = self.make_product()
        english = (PRODUCT_DETAIL_EXPECTED[0][1], PRODUCT_DETAIL_EXPECTED[0][2],
                   CARE_EXPECTED[0][1], DISPATCH_EXPECTED[0][0])
        chinese = (PRODUCT_DETAIL_EXPECTED[0][3], PRODUCT_DETAIL_EXPECTED[0][4],
                   CARE_EXPECTED[0][2], DISPATCH_EXPECTED[0][1])
        with translation.override("en"):
            self.assertEqual((source.description, source.story, source.care,
                              source.dispatch), english)
            self.assertIs(localize_product(source), source)
        with translation.override("zh-hans"):
            localized = localize_product(source)
            self.assertEqual((localized.description, localized.story, localized.care,
                              localized.dispatch), chinese)
        with translation.override("en"):
            self.assertIs(localize_product(source), source)
            self.assertEqual((source.description, source.story, source.care,
                              source.dispatch), english)

    def test_custom_product_detail_fields_are_guarded_independently(self):
        chinese = (PRODUCT_DETAIL_EXPECTED[0][3], PRODUCT_DETAIL_EXPECTED[0][4],
                   CARE_EXPECTED[0][2], DISPATCH_EXPECTED[0][1])
        cases = (
            ({"description": "Seller description"},
             ("Seller description", chinese[1], chinese[2], chinese[3])),
            ({"story": "Seller story"},
             (chinese[0], "Seller story", chinese[2], chinese[3])),
            ({"care_instructions": "Seller care"},
             (chinese[0], chinese[1], "Seller care", chinese[3])),
            ({"shipping_information": "Seller dispatch"},
             (chinese[0], chinese[1], chinese[2], "Seller dispatch")),
            ({"description": "Seller description", "story": "Seller story",
              "care_instructions": "Seller care", "shipping_information": "Seller dispatch"},
             ("Seller description", "Seller story", "Seller care", "Seller dispatch")),
        )
        with translation.override("zh-hans"):
            for overrides, expected_fields in cases:
                with self.subTest(overrides=overrides):
                    source = self.make_product(**overrides)
                    original = (source.description, source.story, source.care_instructions,
                                source.shipping_information)
                    localized = localize_product(source)
                    self.assertEqual((localized.description, localized.story,
                                      localized.care_instructions,
                                      localized.shipping_information), expected_fields)
                    self.assertEqual((source.description, source.story,
                                      source.care_instructions,
                                      source.shipping_information), original)


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

"""Database-free checks for catalogue presentation translations."""

import ast
from datetime import datetime, timezone as datetime_timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID
from unittest.mock import MagicMock, patch

from django.template import Context, Template
from django.test import SimpleTestCase
from django.utils import translation
from django.utils.translation import gettext

from content.models import FAQ, Article, FAQGroup
from orders.serializers import CartItemSerializer
from products.models import (
    MATERIAL_ALIASES, MATERIAL_FAMILIES, Category, Collection, Maker, Product,
)

from frontend import services
from frontend.catalogue_i18n import (
    localize_article, localize_collection, localize_colour_label, localize_faq_group,
    localize_maker, localize_product,
)
from frontend.mockdata.collections import CATEGORIES, COLLECTIONS, EXTRA_COLLECTIONS
from frontend.mockdata.faqs import FAQ_GROUPS
from frontend.mockdata.journal import ARTICLES
from frontend.mockdata.makers import MAKERS
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

# Approved maker copy is fixed here, independent of the runtime translation source.
MAKER_EXPECTED = ({'slug': 'chen-meilin',
  'name': ('Chen Meilin', '陈梅琳'),
  'discipline': ('Ceramicist', '陶艺师'),
  'location': ('Jingdezhen, Jiangxi', '江西景德镇'),
  'tagline': ('Porcelain thrown thin enough to hold the light.', '薄到足以承托光线的瓷器。'),
  'biography': (('Meilin trained for six years under a Jingdezhen master before opening a small '
                 'studio on the eastern edge of the old kiln district. She works almost entirely '
                 'in local porcelain stone, quarried an hour from her door.',
                 '梅琳曾在景德镇一位陶艺大师门下学习六年，之后在古窑区东侧开设了一间小工作室。她几乎只使用本地瓷石，泥料取自离工作室一小时车程的地方。'),
                ('Her forms are quiet and slightly imperfect by design. A rim that dips a little, '
                 'a foot left unglazed so you can read the clay -- these are the marks she leaves '
                 'on purpose, and the reason no two pieces are alike.',
                 '她的器形安静而略带不完美，这是刻意为之。微微下沉的器口、露出泥土质感的素烧足部，都是她有意留下的痕迹，也正是每件作品各不相同的原因。')),
  'process': (('Clay is wedged by hand each morning and rested overnight before throwing.',
               '每天早晨手工揉泥，静置一夜后才开始拉坯。'),
              ('Every piece is turned on the wheel, then trimmed once leather-hard.',
               '每件作品都在转盘上完成，并在半干时修坯。'),
              ('Glazes are mixed in small batches from ash, feldspar and iron oxide.',
               '釉料以灰烬、长石和氧化铁分批调配。'),
              ('A single gas firing to 1280°C, with the kiln cooled slowly over two days.',
               '以 1280°C 进行一次燃气烧制，窑炉缓慢冷却两天。'))},
 {'slug': 'lu-wenjing',
  'name': ('Lu Wenjing', '陆文静'),
  'discipline': ('Weaver & natural dyer', '织工与天然染色师'),
  'location': ('Dali, Yunnan', '云南大理'),
  'tagline': ('Indigo that deepens with every wash.', '每一次清洗，靛蓝都更深一层。'),
  'biography': (('Wenjing learned to dye from her grandmother, who kept an indigo vat behind the '
                 'family house in Dali. She now grows her own indigo and works with three '
                 'neighbouring households during the harvest.',
                 '文静向祖母学习染色。祖母曾在大理的家屋后经营一口靛蓝染缸。如今她自己种植蓝靛，并在收获季与邻近的三户人家合作。'),
                ('She weaves on a floor loom her father built, in cotton and hemp spun within the '
                 'province. Nothing in her studio is dyed twice the same way, and she has stopped '
                 'apologising for it.',
                 '她使用父亲制作的木质地织机，以省内纺成的棉与麻织布。她工作室里的任何东西都不会以完全相同的方式染两次，她也不再为此道歉。')),
  'process': (('Indigo is fermented in clay vats and fed weekly through the season.',
               '靛蓝在陶缸中发酵，并在整个季节每周补养。'),
              ('Cloth is dipped between six and fourteen times, depending on the depth wanted.',
               '布料浸染六至十四次，视所需深浅而定。'),
              ('Washed in river water and dried in shade to keep the colour even.',
               '在河水中清洗并于阴凉处晾干，使颜色保持均匀。'),
              ('Woven, finished and hemmed by hand on a wooden floor loom.',
               '在木质地织机上手工织造、整理与锁边。'))},
 {'slug': 'zhao-hesheng',
  'name': ('Zhao Hesheng', '赵和生'),
  'discipline': ('Woodworker', '木匠'),
  'location': ('Huizhou, Anhui', '安徽徽州'),
  'tagline': ('Working with the grain, never against it.', '顺着木纹工作，从不与它对抗。'),
  'biography': (('Hesheng spent a decade restoring Huizhou timber houses before turning to smaller '
                 'objects. He still sources most of his wood from those restorations -- beams and '
                 'floorboards that have already lived a life.',
                 '和生花了十年修复徽州木屋，之后才转向制作更小的器物。他的大部分木材仍来自这些修复工程，是已经度过一段岁月的梁木与地板。'),
                ('He cuts joinery by hand and finishes everything in raw linseed oil. Nothing '
                 'leaves the bench until it feels right in the hand.',
                 '他手工切削榫卯，所有作品都以生亚麻籽油完成。每件东西在握感恰到好处之前，都不会离开工作台。')),
  'process': (('Reclaimed timber is milled, then rested for a season to settle.',
               '回收木材先加工，再静置一季让它稳定下来。'),
              ('Every joint is cut and pared by hand -- no dowels, no filler.',
               '每个榫接都手工切削与修整，不用木钉，也不用填料。'),
              ('Surfaces are worked through five grades of abrasive to a soft sheen.',
               '表面经过五种不同粗细的磨料处理，呈现柔和光泽。'),
              ('Finished in food-safe linseed oil, reapplied three times over a week.',
               '使用食品级亚麻籽油完成表面处理，一周内重复涂刷三次。'))},
 {'slug': 'xu-anying',
  'name': ('Xu Anying', '徐安莹'),
  'discipline': ('Candlemaker & perfumer', '制烛师与调香师'),
  'location': ('Suzhou, Jiangsu', '江苏苏州'),
  'tagline': ('Scent built the way a garden is planted.', '像栽种花园一样构筑香气。'),
  'biography': (('Anying studied classical Chinese garden design before training in perfumery. She '
                 'thinks about a scent the way she was taught to think about a courtyard: what you '
                 'meet first, and what you find later.',
                 '安莹曾学习中国古典园林设计，之后接受调香训练。她以设计庭院的方式思考香气：首先遇见什么，之后又会发现什么。'),
                ('She pours in batches of forty, by hand, in a converted ground-floor workshop '
                 'near the canal. Each batch is left to cure for two weeks before a wick is ever '
                 'lit.',
                 '她在运河附近一间改造的底层工作室里手工浇注，每批四十支。每批蜡烛会静置固化两周，之后才点燃烛芯。')),
  'process': (('Essential oils are blended and left to marry for ten days.', '精油混合后静置十天，让香气彼此融合。'),
              ('Soy and rapeseed wax is melted low, never above 65°C.', '大豆蜡与菜籽蜡低温融化，温度不超过 65°C。'),
              ('Poured by hand in batches of forty, one vessel at a time.', '每次一只容器，分批手工浇注，每批四十支。'),
              ('Cured for fourteen days, then burn-tested from every batch.',
               '固化十四天后，从每批中抽样进行燃烧测试。'))},
 {'slug': 'ye-ruolan',
  'name': ('Ye Ruolan', '叶若兰'),
  'discipline': ('Textile artist', '纺织艺术家'),
  'location': ('Hangzhou, Zhejiang', '浙江杭州'),
  'tagline': ('Linen washed until it forgets it was ever stiff.', '将亚麻洗到仿佛从未僵硬过。'),
  'biography': (('Ruolan works in European flax linen, finished in her own studio using a '
                 'stone-washing process she spent two years refining. The point, she says, is for '
                 'a new piece to feel like one you have owned for years.',
                 '若兰使用欧洲亚麻，在自己的工作室里以经过两年改良的石洗工艺完成整理。她说，理想状态是让新作品摸起来像已经陪伴你多年的旧物。'),
                ('She cuts and sews everything herself, with a single assistant during busy '
                 'months, and keeps her ranges deliberately small.',
                 '她亲自裁剪和缝制所有作品，忙碌月份会有一名助手，并始终刻意保持系列精简。')),
  'process': (('Flax linen is sourced from a single mill and cut in small lays.',
               '亚麻来自同一家纺厂，并以小批量裁片处理。'),
              ('Seams are sewn, then the finished piece is stone-washed twice.', '缝合后，成品进行两次石洗。'),
              ('Dried flat and pressed once, lightly, to keep the natural crumple.',
               '平铺晾干后只轻轻熨烫一次，保留自然的褶皱。'),
              ('Checked seam by seam before it is folded and wrapped.', '逐条检查缝线，再折叠包裹。'))})


# Approved FAQ copy is fixed here, independent of the runtime translation source.
FAQ_EXPECTED = (
    {
        "slug": "orders",
        "title": ("Orders", "订单"),
        "blurb": ("Placing, changing and cancelling.", "下单、修改与取消。"),
        "items": (
            (
                "Can I change or cancel my order?",
                "我可以修改或取消订单吗？",
                "Yes, within 12 hours of placing it, as long as it has not been packed. Email "
                "the studio with your order number and we will sort it out. After 12 hours a "
                "made-to-order piece may already be in production.",
                "可以。下单后 12 小时内，且订单尚未打包时，您可以修改或取消订单。请将订单编号发送至工作室邮箱，我们会为您处理。超过 12 小时后，按订单制作的商品可能已经开始生产。",
            ),
            (
                "I ordered several pieces. Will they arrive together?",
                "我订购了多件商品，它们会一起送达吗？",
                "Not always. In-stock items ship immediately and made-to-order pieces follow "
                "when they are ready. You are only charged delivery once.",
                "不一定。现货商品会立即发出，按订单制作的商品则会在完成后寄出。您只需支付一次配送费。",
            ),
            (
                "Do you take custom or commission requests?",
                "你们接受定制或委托制作吗？",
                "For some pieces, yes. Use the enquiry link on the product page and the maker "
                "will reply with what is possible and a quotation. Commissions typically take "
                "four to eight weeks.",
                "部分商品可以。请使用商品页面上的咨询链接，匠人会回复可行方案和报价。委托制作通常需要 4–8 周。",
            ),
            (
                "Can I order a piece that is sold out?",
                "我可以订购已售罄的商品吗？",
                "Sold-out pieces return when the maker next fires or weaves a batch. Add your "
                "email on the product page and you will hear when it does.",
                "已售罄的商品会在匠人下一次烧制或织造一批时重新上架。在商品页面留下您的电子邮箱，补货时我们会通知您。",
            ),
        ),
    },
    {
        "slug": "shipping",
        "title": ("Shipping", "配送"),
        "blurb": ("Timings, costs and tracking.", "时效、费用与物流查询。"),
        "items": (
            (
                "How long does delivery take?",
                "配送需要多长时间？",
                "In-stock orders are dispatched in 2–4 working days and arrive within a week "
                "domestically. Made-to-order pieces state their own lead time on the product page.",
                "现货订单会在 2–4 个工作日内发出，并在一周内送达国内地址。按订单制作的商品会在商品页面注明各自的交付周期。",
            ),
            (
                "How much does delivery cost?",
                "配送费是多少？",
                "Standard delivery is ¥8. It is complimentary on orders above ¥80. Express "
                "delivery is ¥18 and dispatches the next working day where stock allows.",
                "标准配送费为 ¥8。订单金额超过 ¥80 可免配送费。加急配送费为 ¥18，并会在库存允许的情况下于下一个工作日发出。",
            ),
            (
                "Do you ship internationally?",
                "可以寄送到海外吗？",
                "Yes, to most countries. Duties and import taxes are not included and are paid "
                "by the recipient on arrival.",
                "可以，我们可寄送至大多数国家。关税和进口税不包含在费用中，需由收件人在收货时支付。",
            ),
            (
                "How is fragile work packed?",
                "易碎作品如何包装？",
                "Ceramics are wrapped in recycled tissue and moulded pulp, inside a "
                "double-walled box. No plastic, no polystyrene.",
                "陶瓷会用再生薄纸和模塑纸浆包裹，再装入双层瓦楞纸箱。全程不使用塑料或聚苯乙烯泡沫。",
            ),
        ),
    },
    {
        "slug": "returns",
        "title": ("Returns", "退货"),
        "blurb": ("Changing your mind, and breakages.", "改变主意与收到破损商品。"),
        "items": (
            (
                "What is your returns window?",
                "退货期限是多久？",
                "Thirty days from delivery, for unused pieces in their original packaging. "
                "Tell us before you send anything back so we can issue a return reference.",
                "自收货之日起 30 天内，未使用且保留原包装的商品可以退货。寄回任何商品前请先联系我们，以便我们提供退货编号。",
            ),
            (
                "Something arrived broken.",
                "收到的商品破损了。",
                "Send a photograph within 48 hours of delivery and we will replace it or refund "
                "you in full. You do not need to return the damaged piece.",
                "请在收货后 48 小时内发送照片，我们会为您更换商品或全额退款。您无需寄回破损商品。",
            ),
            (
                "Can I return a made-to-order or commissioned piece?",
                "按订单制作或委托制作的商品可以退货吗？",
                "Only if it is faulty. These are made specifically for you, so we cannot resell "
                "them. The product page says clearly when this applies.",
                "只有商品存在瑕疵时才可以。这些商品是专门为您制作的，无法再次销售。适用此规则时，商品页面会明确说明。",
            ),
            (
                "Who pays return postage?",
                "退货邮费由谁承担？",
                "We do, if the piece is faulty or not what you ordered. For a change of mind, "
                "return postage is yours.",
                "如果商品有瑕疵或与您订购的不符，退货邮费由我们承担。如果只是改变主意，退货邮费由您承担。",
            ),
        ),
    },
    {
        "slug": "product-care",
        "title": ("Product Care", "作品保养"),
        "blurb": ("Keeping pieces well for years.", "让作品长久保持良好状态。"),
        "items": (
            (
                "Is your stoneware dishwasher safe?",
                "炻器可以用洗碗机清洗吗？",
                "Yes. It is fired to full vitrification. Hand washing keeps a matte glaze "
                "looking its best for longer, but the machine will not harm it.",
                "可以。炻器已经烧至完全玻化。手洗能让哑光釉面更长久地保持最佳状态，但洗碗机不会损坏它。",
            ),
            (
                "How should I wash linen?",
                "亚麻制品应该如何清洗？",
                "Cool machine wash on a gentle cycle, mild detergent, no fabric softener. Line "
                "dry in shade. It softens with every wash.",
                "使用温和洗涤剂，以低温轻柔模式机洗，不要使用衣物柔顺剂。置于阴凉处晾干。每洗一次，它都会更加柔软。",
            ),
            (
                "My candle is tunnelling.",
                "我的蜡烛出现了隧道现象。",
                "Let the first burn run until the melt pool reaches the edge -- usually two to "
                "three hours. Wax has a memory, and the first burn sets it.",
                "第一次燃烧时，请让融蜡池延伸到容器边缘，通常需要两到三个小时。蜡具有记忆效应，第一次燃烧会决定之后的燃烧方式。",
            ),
            (
                "The brass has darkened.",
                "黄铜变暗了。",
                "It is unlacquered, so that is expected and reversible. A little lemon juice and "
                "bicarbonate returns the shine if you want it back.",
                "黄铜没有上漆，因此变暗属于正常现象，也可以恢复。如果想让它重新亮起来，可使用少量柠檬汁和小苏打。",
            ),
        ),
    },
    {
        "slug": "handmade-variations",
        "title": ("Handmade Variations", "手作差异"),
        "blurb": ("What is a variation, and what is a fault.", "什么是正常差异，什么属于瑕疵。"),
        "items": (
            (
                "My piece does not look exactly like the photograph.",
                "我的商品看起来与照片不完全一样。",
                "It will not. Glaze colour, speckle, and dye depth vary between firings and dye "
                "baths. We photograph a typical piece rather than the best one in a batch.",
                "本来就不会完全一样。不同批次的烧制和染浴会造成釉色、斑点和染色深浅的差异。我们拍摄的是具有代表性的作品，而不是一批中最好的一件。",
            ),
            (
                "Are the dimensions exact?",
                "尺寸是完全准确的吗？",
                "Within about 5%. Every piece is thrown or cut by hand, and clay shrinks by "
                "roughly a tenth in the firing.",
                "误差约在 5% 以内。每件作品都由手工拉坯或裁切，陶土在烧制过程中还会收缩约十分之一。",
            ),
            (
                "There are fine lines in the glaze.",
                "釉面上有细纹。",
                "That is crazing, and on a vitrified body it is cosmetic. It does not affect "
                "strength or whether the piece holds water.",
                "这是开片。对于已经玻化的坯体，这只是外观上的变化，不会影响强度或盛水性能。",
            ),
            (
                "What actually counts as a fault?",
                "什么情况才算瑕疵？",
                "A chip, a crack through the body, a piece that does not sit flat, or a seam "
                "that has failed. Any of those, tell us and we will replace it.",
                "崩口、贯穿坯体的裂纹、无法平稳放置，或接缝开裂，都属于瑕疵。遇到任何一种情况，请告诉我们，我们会为您更换。",
            ),
        ),
    },
    {
        "slug": "gifting",
        "title": ("Gifting", "礼赠"),
        "blurb": ("Notes, wrapping and gift orders.", "留言、包装与礼品订单。"),
        "items": (
            (
                "Can you include a handwritten note?",
                "可以附上手写留言吗？",
                "Yes. Add your message at checkout and it is written onto a card by hand, "
                "unsigned by us, and tucked into the parcel.",
                "可以。结账时填写留言，我们会将其手写在卡片上，不署工作室名，并放入包裹中。",
            ),
            (
                "Will the recipient see the price?",
                "收件人会看到价格吗？",
                "No. Parcels never contain an invoice. Pricing is emailed to you only.",
                "不会。包裹中绝不会放入发票。价格信息只会通过电子邮件发送给您。",
            ),
            (
                "Is gift wrapping extra?",
                "礼品包装需要额外收费吗？",
                "No. Everything is wrapped in unbleached paper and cotton string as standard. "
                "There is nothing extra to add.",
                "不需要。所有商品都会按标准使用未漂白纸张和棉绳包装，无需另行添加。",
            ),
            (
                "Do you sell gift cards?",
                "你们销售礼品卡吗？",
                "Yes, in ¥50, ¥100 and ¥200. They are emailed to the recipient on a date you "
                "choose and do not expire.",
                "有 ¥50、¥100 和 ¥200 三种面额。礼品卡会在您选择的日期通过电子邮件发送给收件人，且不会过期。",
            ),
        ),
    },
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


class MakerLocalizationTests(SimpleTestCase):
    @staticmethod
    def display_fields(expected, language_index):
        return (
            expected["name"][language_index],
            expected["discipline"][language_index],
            expected["location"][language_index],
            expected["tagline"][language_index],
            [value[language_index] for value in expected["biography"]],
            [value[language_index] for value in expected["process"]],
        )

    def make_maker(self, expected=MAKER_EXPECTED[0], **overrides):
        seed = next(item for item in MAKERS if item["slug"] == expected["slug"])
        english = self.display_fields(expected, 0)
        values = {
            "id": 23,
            "slug": expected["slug"],
            "name": english[0],
            "discipline": english[1],
            "location": english[2],
            "since": seed["since"],
            "tagline": english[3],
            "short_bio": english[4][0],
            "biography": list(english[4]),
            "process": list(english[5]),
            "portrait": seed["portrait"],
            "studio_images": list(seed["images"]),
            "is_featured": True,
            "is_active": True,
        }
        values.update(overrides)
        return Maker(**values)

    @staticmethod
    def maker_fields(maker):
        return (
            maker.name, maker.discipline, maker.location, maker.tagline,
            maker.biography, maker.process,
        )

    def test_all_seeded_maker_copy_in_english_and_chinese(self):
        self.assertEqual(len(MAKERS), 5)
        for seed, expected in zip(MAKERS, MAKER_EXPECTED, strict=True):
            with self.subTest(slug=expected["slug"]):
                english = self.display_fields(expected, 0)
                chinese = self.display_fields(expected, 1)
                self.assertEqual(seed["slug"], expected["slug"])
                self.assertEqual(
                    (seed["name"], seed["discipline"], seed["location"],
                     seed["tagline"], seed["biography"], seed["process"]),
                    english,
                )
                source = self.make_maker(expected)
                original_biography = list(source.biography)
                original_process = list(source.process)
                with translation.override("en"):
                    self.assertIs(localize_maker(source), source)
                with translation.override("zh-hans"):
                    localized = localize_maker(source)
                self.assertIsNot(localized, source)
                self.assertEqual(self.maker_fields(localized), chinese)
                self.assertEqual(localized.short_bio, chinese[4][0])
                self.assertEqual(self.maker_fields(source), english)
                self.assertEqual(source.short_bio, english[4][0])
                self.assertEqual(source.biography, original_biography)
                self.assertEqual(source.process, original_process)
                self.assertIsNot(localized.biography, source.biography)
                self.assertIsNot(localized.process, source.process)

    def test_maker_language_switching_uses_the_same_source_object(self):
        expected = MAKER_EXPECTED[0]
        source = self.make_maker(expected)
        with translation.override("en"):
            self.assertIs(localize_maker(source), source)
            self.assertEqual(self.maker_fields(source), self.display_fields(expected, 0))
        with translation.override("zh-hans"):
            self.assertEqual(
                self.maker_fields(localize_maker(source)), self.display_fields(expected, 1),
            )
        with translation.override("en"):
            self.assertIs(localize_maker(source), source)
            self.assertEqual(self.maker_fields(source), self.display_fields(expected, 0))

    def test_custom_scalar_fields_are_guarded_independently(self):
        expected = MAKER_EXPECTED[0]
        chinese = self.display_fields(expected, 1)
        scalar_fields = ("name", "discipline", "location", "tagline")
        with translation.override("zh-hans"):
            for custom_field in scalar_fields:
                with self.subTest(field=custom_field):
                    source = self.make_maker(expected, **{custom_field: "Seller copy"})
                    localized = localize_maker(source)
                    wanted = dict(zip(scalar_fields, chinese[:4]))
                    wanted[custom_field] = "Seller copy"
                    self.assertEqual(
                        tuple(getattr(localized, field) for field in scalar_fields),
                        tuple(wanted[field] for field in scalar_fields),
                    )
                    self.assertEqual(getattr(source, custom_field), "Seller copy")

    def test_custom_biography_and_process_use_all_or_nothing_guards(self):
        expected = MAKER_EXPECTED[0]
        english = self.display_fields(expected, 0)
        chinese = self.display_fields(expected, 1)
        cases = (
            ("biography", ["Seller biography", english[4][1]]),
            ("process", ["Seller process", *english[5][1:]]),
        )
        with translation.override("zh-hans"):
            for custom_field, custom_list in cases:
                with self.subTest(field=custom_field):
                    source = self.make_maker(expected, **{custom_field: custom_list})
                    original_biography = list(source.biography)
                    original_process = list(source.process)
                    localized = localize_maker(source)
                    if custom_field == "biography":
                        self.assertEqual(localized.biography, custom_list)
                        self.assertEqual(localized.process, chinese[5])
                    else:
                        self.assertEqual(localized.biography, chinese[4])
                        self.assertEqual(localized.process, custom_list)
                    self.assertEqual(source.biography, original_biography)
                    self.assertEqual(source.process, original_process)

    def test_short_bio_is_translated_only_when_it_matches_the_canonical_first_paragraph(self):
        expected = MAKER_EXPECTED[0]
        with translation.override("zh-hans"):
            canonical = self.make_maker(expected)
            self.assertEqual(localize_maker(canonical).short_bio,
                             expected["biography"][0][1])
            for value in ("", "Seller summary"):
                with self.subTest(value=value):
                    source = self.make_maker(expected, short_bio=value)
                    localized = localize_maker(source)
                    self.assertEqual(localized.short_bio, value)
                    self.assertEqual(source.short_bio, value)

    def test_unknown_maker_and_functional_fields_are_preserved(self):
        expected = MAKER_EXPECTED[0]
        unknown = self.make_maker(expected, slug="seller-created-maker")
        with translation.override("zh-hans"):
            self.assertIs(localize_maker(unknown), unknown)

            source = self.make_maker(expected)
            functional = (
                source.pk, source.uuid, source.slug, source.owner_id, source.since,
                source.portrait, source.studio_images, source.images,
                source.is_featured, source.is_active,
            )
            localized = localize_maker(source)
            self.assertEqual(
                (localized.pk, localized.uuid, localized.slug, localized.owner_id,
                 localized.since, localized.portrait, localized.studio_images,
                 localized.images, localized.is_featured, localized.is_active),
                functional,
            )

    def test_customer_facing_maker_services_localise_after_raw_queries(self):
        expected = MAKER_EXPECTED[0]
        chinese = self.display_fields(expected, 1)

        def assert_localized(result, source):
            maker = result[0] if isinstance(result, list) else result
            self.assertEqual(self.maker_fields(maker), chinese)
            self.assertEqual(self.maker_fields(source), self.display_fields(expected, 0))

        with translation.override("zh-hans"):
            source = self.make_maker(expected)
            with patch.object(services.Maker.objects, "filter", return_value=[source]) as query:
                assert_localized(services.all_makers(), source)
            query.assert_called_once_with(is_active=True)

            source = self.make_maker(expected)
            queryset = MagicMock()
            queryset.first.return_value = source
            with patch.object(services.Maker.objects, "filter", return_value=queryset) as query:
                assert_localized(services.get_maker(source.slug), source)
            query.assert_called_once_with(slug=source.slug, is_active=True)

            source = self.make_maker(expected)
            product_queryset = MagicMock()
            product_queryset.search.return_value = []
            with (patch.object(services, "_base_queryset", return_value=product_queryset),
                  patch.object(services.Collection.objects, "filter", return_value=[]),
                  patch.object(services.Category.objects, "filter", return_value=[]),
                  patch.object(services.Maker.objects, "filter", return_value=[source]) as query,
                  patch.object(services.Article.objects, "published") as articles):
                articles.return_value.filter.return_value = []
                results = services.search("Chen")
            assert_localized(results["makers"], source)
            product_queryset.search.assert_called_once_with("Chen")
            query.assert_called_once_with(
                services.Q(name__icontains="Chen")
                | services.Q(discipline__icontains="Chen")
                | services.Q(location__icontains="Chen")
                | services.Q(tagline__icontains="Chen"),
                is_active=True,
            )


class FAQLocalizationTests(SimpleTestCase):
    @staticmethod
    def make_group(expected=FAQ_EXPECTED[0], *, group_overrides=None):
        group_values = {
            "id": 31,
            "slug": expected["slug"],
            "title": expected["title"][0],
            "blurb": expected["blurb"][0],
            "sort_order": 2,
            "is_active": True,
        }
        group_values.update(group_overrides or {})
        group = FAQGroup(**group_values)
        items = [
            FAQ(
                id=100 + index, group=group, question=item[0], answer=item[2],
                sort_order=index, is_active=True,
            )
            for index, item in enumerate(expected["items"])
        ]
        group._prefetched_objects_cache = {"faqs": items}
        return group, items

    @staticmethod
    def item_copy(items):
        return [(item.question, item.answer, item.sort_order, item.is_active) for item in items]

    def test_all_seeded_faq_copy_in_english_and_chinese(self):
        self.assertEqual(len(FAQ_GROUPS), 6)
        self.assertEqual(sum(len(group["items"]) for group in FAQ_GROUPS), 24)
        for seed, expected in zip(FAQ_GROUPS, FAQ_EXPECTED, strict=True):
            with self.subTest(slug=expected["slug"]):
                self.assertEqual(
                    (seed["slug"], seed["title"], seed["blurb"]),
                    (expected["slug"], expected["title"][0], expected["blurb"][0]),
                )
                self.assertEqual(
                    [(item["q"], item["a"]) for item in seed["items"]],
                    [(item[0], item[2]) for item in expected["items"]],
                )
                source, source_items = self.make_group(expected)
                original_items = self.item_copy(source_items)
                with translation.override("en"):
                    self.assertIs(localize_faq_group(source), source)
                with translation.override("zh-hans"):
                    localized = localize_faq_group(source)
                self.assertEqual((localized.title, localized.blurb),
                                 (expected["title"][1], expected["blurb"][1]))
                self.assertEqual(
                    [(item.q, item.a) for item in localized.items],
                    [(item[1], item[3]) for item in expected["items"]],
                )
                self.assertEqual((source.title, source.blurb),
                                 (expected["title"][0], expected["blurb"][0]))
                self.assertEqual(self.item_copy(source_items), original_items)
                self.assertEqual(
                    (localized.slug, localized.pk, localized.sort_order, localized.is_active),
                    (source.slug, source.pk, source.sort_order, source.is_active),
                )

    def test_faq_language_switching_uses_the_same_source_objects(self):
        expected = FAQ_EXPECTED[0]
        source, source_items = self.make_group(expected)
        english_items = [(item[0], item[2]) for item in expected["items"]]
        chinese_items = [(item[1], item[3]) for item in expected["items"]]
        with translation.override("en"):
            self.assertIs(localize_faq_group(source), source)
            self.assertEqual([(item.q, item.a) for item in source_items], english_items)
        with translation.override("zh-hans"):
            localized = localize_faq_group(source)
            self.assertEqual([(item.q, item.a) for item in localized.items], chinese_items)
        with translation.override("en"):
            self.assertIs(localize_faq_group(source), source)
            self.assertEqual([(item.q, item.a) for item in source_items], english_items)
        self.assertEqual([(item.q, item.a) for item in source_items], english_items)

    def test_custom_group_title_and_blurb_are_guarded_independently(self):
        expected = FAQ_EXPECTED[0]
        cases = (
            ({"title": "Seller title"}, ("Seller title", expected["blurb"][1])),
            ({"blurb": "Seller blurb"}, (expected["title"][1], "Seller blurb")),
            ({"title": "Seller title", "blurb": "Seller blurb"},
             ("Seller title", "Seller blurb")),
        )
        with translation.override("zh-hans"):
            for overrides, wanted in cases:
                with self.subTest(overrides=overrides):
                    source, _ = self.make_group(expected, group_overrides=overrides)
                    localized = localize_faq_group(source)
                    self.assertEqual((localized.title, localized.blurb), wanted)
                    self.assertEqual(
                        (source.title, source.blurb),
                        (overrides.get("title", expected["title"][0]),
                         overrides.get("blurb", expected["blurb"][0])),
                    )

    def test_custom_questions_and_answers_are_guarded_independently(self):
        expected = FAQ_EXPECTED[0]
        cases = (
            ({"question": "Seller question"},
             ("Seller question", expected["items"][0][3])),
            ({"answer": "Seller answer"},
             (expected["items"][0][1], "Seller answer")),
            ({"question": "Seller question", "answer": "Seller answer"},
             ("Seller question", "Seller answer")),
        )
        with translation.override("zh-hans"):
            for overrides, wanted in cases:
                with self.subTest(overrides=overrides):
                    source, items = self.make_group(expected)
                    for field, value in overrides.items():
                        setattr(items[0], field, value)
                    original = self.item_copy(items)
                    localized = localize_faq_group(source)
                    self.assertEqual((localized.items[0].q, localized.items[0].a), wanted)
                    self.assertEqual(self.item_copy(items), original)

    def test_inserted_removed_reordered_and_unknown_faqs_are_not_mismatched(self):
        expected = FAQ_EXPECTED[0]
        with translation.override("zh-hans"):
            inserted, items = self.make_group(expected)
            items.append(FAQ(id=999, group=inserted, question="Inserted question",
                             answer="Inserted answer", sort_order=4, is_active=True))
            inserted_localized = localize_faq_group(inserted)
            self.assertEqual([(item.q, item.a) for item in inserted_localized.items],
                             [(item.q, item.a) for item in items])

            removed, items = self.make_group(expected)
            removed._prefetched_objects_cache["faqs"] = items[:-1]
            removed_localized = localize_faq_group(removed)
            self.assertEqual([(item.q, item.a) for item in removed_localized.items],
                             [(item.q, item.a) for item in items[:-1]])

            reordered, items = self.make_group(expected)
            reordered_items = list(reversed(items))
            reordered._prefetched_objects_cache["faqs"] = reordered_items
            reordered_localized = localize_faq_group(reordered)
            self.assertEqual([(item.q, item.a) for item in reordered_localized.items],
                             [(item.q, item.a) for item in reordered_items])

            unknown, _ = self.make_group(
                expected, group_overrides={"slug": "seller-faq-group"},
            )
            self.assertIs(localize_faq_group(unknown), unknown)

    def test_active_filtering_and_order_use_prefetched_items_without_database_queries(self):
        expected = FAQ_EXPECTED[0]
        source, items = self.make_group(expected)
        inactive = FAQ(id=998, group=source, question="Inactive question",
                       answer="Inactive answer", sort_order=2, is_active=False)
        source._prefetched_objects_cache["faqs"] = [items[0], inactive, *items[1:]]
        with translation.override("zh-hans"):
            localized = localize_faq_group(source)
        self.assertEqual([item.pk for item in localized.items], [item.pk for item in items])
        self.assertEqual(
            [(item.q, item.a) for item in localized.items],
            [(item[1], item[3]) for item in expected["items"]],
        )
        self.assertNotIn(inactive, localized.items)

    def test_faq_and_contact_template_contracts_accept_the_presentation_wrapper(self):
        expected = FAQ_EXPECTED[0]
        source, _ = self.make_group(expected)
        with translation.override("zh-hans"):
            localized = localize_faq_group(source)

        faq_source = (Path(__file__).parent / "templates/frontend/pages/faq.html").read_text(
            encoding="utf-8",
        )
        contact_source = (
            Path(__file__).parent / "templates/frontend/pages/contact.html"
        ).read_text(encoding="utf-8")
        self.assertIn("{% for item in group.items %}", faq_source)
        self.assertIn("{{ item.q }}", faq_source)
        self.assertIn("{{ item.a }}", faq_source)
        self.assertIn("group.items|length", contact_source)

        faq_template = Template(
            "{% for group in faq_groups %}{{ group.title }}|{{ group.blurb }}|"
            "{% for item in group.items %}{{ item.q }}|{{ item.a }}|{% endfor %}{% endfor %}",
        )
        contact_template = Template(
            "{% for group in faq_groups %}{{ group.title }}:{{ group.items|length }}{% endfor %}",
        )
        faq_html = faq_template.render(Context({"faq_groups": [localized]}))
        contact_html = contact_template.render(Context({"faq_groups": [localized]}))
        self.assertIn(expected["title"][1], faq_html)
        self.assertIn(expected["items"][0][1], faq_html)
        self.assertIn(expected["items"][0][3], faq_html)
        self.assertEqual(contact_html, f'{expected["title"][1]}:4')


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


ARTICLE_EXPECTED = (
    {
        "slug": "why-no-two-glazes-match",
        "title": ("Why no two glazes match", "为什么没有两种釉色完全相同"),
        "standfirst": (
            "A wood-ash glaze is a record of the firing that made it. Here is why we stopped trying to make them identical.",
            "手工灰釉记录着烧制它的过程。我们为什么不再追求完全一致？",
        ),
        "category": ("Craft", "工艺"),
        "read_time": ("6 min", "6 分钟"),
        "author": ("Chen Meilin", "陈梅琳"),
        "date": ("12 August 2026", "2026年8月12日"),
        "image": "journal-why-no-two-glazes-match",
        "featured": True,
        "body": (
            ("paragraph", "Ask a factory to make five hundred mugs the same colour and it will. Ask a kiln to do it and you will get something more interesting and less obedient.", "让工厂把五百只马克杯做成同一种颜色，它可以做到。让窑炉这样做，你得到的会是更有意思、也更不听话的东西。"),
            ("heading", "What the kiln decides", "窑炉的决定"),
            ("paragraph", "Ash glaze is mixed from what is swept out of the kiln after a firing -- wood ash, feldspar, a little iron oxide, water. The proportions are consistent. What is not consistent is where a piece sits in the kiln, how the flame moves around it, and how fast that corner cools over the two days afterwards.", "灰釉由每次烧制后从窑炉中清扫出的材料调配而成——木灰、长石、少量氧化铁和水。配比始终一致。无法保持一致的是器物在窑中的位置、火焰绕过它的方式，以及之后两天里那个角落冷却的速度。"),
            ("paragraph", "A mug on the top shelf near the flue will come out a shade greener than the same mug, from the same batch of glaze, on the bottom shelf. Neither is the correct one.", "靠近烟道的上层窑架上，一只马克杯出窑时会比下层窑架上那只使用同批釉料的同款杯子更偏绿一些。两者都不是唯一正确的样子。"),
            ("quote", "We fire to a range, not a number. The kiln finishes the piece, and it does not take instruction.", "我们烧制的是一个范围，而不是一个数字。器物由窑炉完成，它不听从指令。"),
            ("heading", "Living with variation", "与差异共处"),
            ("paragraph", "This has a practical consequence for anyone buying a set. If you order four bowls, you will get four bowls that clearly belong together and are clearly not identical. Over a few years of use they diverge further -- the ones you reach for most develop a slightly different surface.", "这会给购买成套器物的人带来一个实际结果。如果你订购四只碗，收到的四只显然属于一套，也显然并不完全相同。使用几年后，它们之间的差异还会加深——你最常拿取的那些，表面会逐渐呈现稍有不同的状态。"),
            ("paragraph", "We used to photograph the most even piece of a batch. We now photograph a middling one, because it is closer to what arrives.", "过去，我们会拍摄一批中最均匀的那一件。现在，我们拍摄处于中间状态的一件，因为它更接近你实际收到的样子。"),
        ),
    },
    {
        "slug": "an-indigo-vat-in-dali",
        "title": ("An indigo vat in Dali", "大理的一口靛蓝染缸"),
        "standfirst": (
            "Lu Wenjing keeps four fermenting vats behind her house. Feeding them is a weekly job that has no shortcut.",
            "陆文静在家后院养着四口发酵染缸，每周照料，没有捷径。",
        ),
        "category": ("Makers", "匠人"),
        "read_time": ("8 min", "8 分钟"),
        "author": ("Atelier Form", "Atelier Form"),
        "date": ("29 July 2026", "2026年7月29日"),
        "image": "journal-an-indigo-vat-in-dali",
        "featured": True,
        "body": (
            ("paragraph", "The vats are clay, sunk to the rim in the ground behind the house, and they are alive in a fairly literal sense. Indigo does not dissolve in water. It has to be reduced by bacteria first, and those bacteria need feeding, warmth and time.", "这些染缸由陶土制成，埋在屋后的地里，缸口与地面齐平；从相当直观的意义上说，它们是活的。靛蓝不溶于水，必须先由细菌还原，而这些细菌需要养料、温度和时间。"),
            ("heading", "A weekly rhythm", "每周的节奏"),
            ("paragraph", "Every Monday Wenjing adds wheat bran and lime, stirs each vat and checks the surface for the coppery film that says the vat is working. A healthy vat smells sweet. An unhappy one smells of nothing at all, which is worse.", "每逢星期一，文静都会加入麦麸和石灰，搅动每口染缸，并查看表面是否出现说明染缸运作正常的铜色薄膜。健康的染缸带着甜香；状态不佳的染缸则什么气味也没有，而这更糟。"),
            ("paragraph", "Cloth goes in yellow-green and turns blue in the air, in front of you, over about twenty seconds. Six dips gives a pale sky. Fourteen gives the near-black indigo on our heaviest throws.", "布料入缸时呈黄绿色，在你眼前接触空气后变成蓝色，整个过程约二十秒。浸染六次会得到浅淡的天蓝色；十四次则会得到我们最厚重盖毯上近乎黑色的靛蓝。"),
            ("heading", "Why it fades the way it does", "为什么会这样褪色"),
            ("paragraph", "Indigo sits on the outside of the fibre rather than inside it. That is why indigo cloth wears at the folds and the edges first, and why a piece you use every week will look different from one kept in a cupboard. It is also why it will never look worse -- only more specific to you.", "靛蓝附着在纤维外部，而非进入纤维内部。因此靛蓝织物会先在折叠处和边缘磨损，每周使用的织物也会与一直收在柜中的那件呈现不同面貌。也正因如此，它永远不会变得更糟——只会越来越带有属于你的痕迹。"),
        ),
    },
    {
        "slug": "how-to-care-for-handmade-ceramics",
        "title": ("How to care for handmade ceramics", "如何保养手作陶器"),
        "standfirst": (
            "Most of what shortens the life of a handmade piece is heat, not use.",
            "真正缩短手作器物寿命的，多数是高温，而不是日常使用。",
        ),
        "category": ("Care", "保养"),
        "read_time": ("4 min", "4 分钟"),
        "author": ("Atelier Form", "Atelier Form"),
        "date": ("14 July 2026", "2026年7月14日"),
        "image": "journal-how-to-care-for-handmade-ceramics",
        "featured": False,
        "body": (
            ("paragraph", "Our stoneware is fired high enough to be fully vitrified, which means it is dishwasher safe and will not absorb water or odours. You can put it in the machine without thinking about it.", "我们的炻器以足够高的温度烧至完全玻化，这意味着它可以放入洗碗机，也不会吸收水分或气味。放进机器清洗时，无需多虑。"),
            ("paragraph", "The thing that will actually damage a piece is thermal shock -- a hot bowl into cold water, or a cold plate into a hot oven. Glaze and clay expand at slightly different rates, and a sharp change can craze the surface or, occasionally, crack the piece outright. Let things cool first.", "真正会损坏器物的是热震——把热碗放入冷水，或把冷盘放进热烤箱。釉料与陶土的膨胀速度略有不同，温度骤变可能使釉面产生开片，偶尔甚至会让器物彻底开裂。先让它们冷却。"),
            ("paragraph", "Unglazed feet will pick up marks from the table over time. That is normal and, in our view, an improvement. If it bothers you, a light rub with a damp cloth and a little bicarbonate lifts most of it.", "未施釉的圈足会随时间从桌面沾上痕迹。这很正常，在我们看来反而更好看。如果你介意，用湿布蘸少量小苏打轻轻擦拭，就能去除大部分痕迹。"),
            ("paragraph", "Fine crazing -- a web of hairline lines in the glaze -- is not a crack and does not affect whether a piece holds water. In a vitrified body it is cosmetic.", "细密的开片——釉面上如网状分布的发丝纹——并不是裂缝，也不影响器物盛水。对于已经玻化的坯体，它只是外观上的变化。"),
        ),
    },
    {
        "slug": "the-case-for-buying-less",
        "title": ("The case for buying less", "少买一些的理由"),
        "standfirst": (
            "We make about four hundred pieces a month. Here is why we have no plans to make four thousand.",
            "我们每月制作约四百件作品，这就是不打算制作四千件的原因。",
        ),
        "category": ("Studio", "工作室"),
        "read_time": ("7 min", "7 分钟"),
        "author": ("Atelier Form", "Atelier Form"),
        "date": ("30 June 2026", "2026年6月30日"),
        "image": "journal-the-case-for-buying-less",
        "featured": True,
        "body": (
            ("paragraph", "Every year we are asked why we do not scale. The honest answer is that the thing people like about the work is a direct consequence of how little of it there is.", "每年都有人问我们为什么不扩大规模。坦率地说，人们喜欢这些作品，正是因为它们数量有限。"),
            ("paragraph", "A studio making four hundred pieces a month can afford to lose a firing. It can let a maker spend a season on a shape that may not sell. It can turn down the wholesale order that would have paid for a second kiln but required the glaze to be standardised first.", "一家每月制作四百件作品的工作室，经得起一次烧制失败。它可以让匠人用一整个季节琢磨一种未必卖得出去的器形；也可以拒绝一笔本可支付第二座窑炉费用、却要求先把釉色标准化的批发订单。"),
            ("paragraph", "None of that survives contact with volume. The pieces would still be competent. They would stop being specific.", "一旦产量扩大，这些都无法维持。器物依然会做得合格，却不再具有鲜明的个性。"),
            ("paragraph", "This has a cost, and we would rather be plain about it: some things sell out and do not come back for months, and made-to-order items really do take three weeks. We think that is the better trade.", "这会带来代价，我们愿意坦白说明：有些作品售罄后要几个月才会回来，按订单制作的商品也确实需要三周。我们认为，这样的取舍更好。"),
        ),
    },
    {
        "slug": "a-table-set-for-nothing-in-particular",
        "title": ("A table set for nothing in particular", "一张没有特别理由的餐桌"),
        "standfirst": (
            "Notes on using the good plates on a Tuesday.",
            "在星期二也用上那些好盘子。",
        ),
        "category": ("Interiors", "室内"),
        "read_time": ("5 min", "5 分钟"),
        "author": ("Atelier Form", "Atelier Form"),
        "date": ("6 June 2026", "2026年6月6日"),
        "image": "journal-a-table-set-for-nothing-in-particular",
        "featured": False,
        "body": (
            ("paragraph", "There is a particular cupboard, in a lot of houses, where the good things live. They come out twice a year and spend the rest of their life being protected from the very thing they were made for.", "许多家里都有一个专门的柜子，里面放着那些好东西。它们一年只拿出来两次，其余时间都被保护着，远离它们原本被制作出来要服务的用途。"),
            ("paragraph", "Handmade pieces are, counter-intuitively, better suited to daily use than to occasional display. They are not delicate. High-fired stoneware is tougher than most factory porcelain, and washed linen is at its best after fifty washes rather than five.", "有些反直觉的是，手工作品比起偶尔陈列，其实更适合日常使用。它们并不娇贵。高温烧制的炻器比大多数工厂瓷器更坚实，水洗亚麻也要洗过五十次，而不是五次，才会呈现最好的状态。"),
            ("paragraph", "The argument for using them is not really about the objects. It is that a weeknight dinner eaten off something someone made by hand is a different kind of evening, at no additional cost, on a day that had nothing else to recommend it.", "使用它们的理由，其实不只关乎物件本身。在一个原本平淡无奇的工作日里，用某个人亲手制作的器皿吃一顿晚餐，不需增加任何花费，却会让那个夜晚变得不同。"),
            ("paragraph", "Our suggestion is unglamorous: take the good plates out of the high cupboard and put them where the everyday ones are. Within a month you will stop noticing, which is the point.", "我们的建议并不华丽：把好盘子从高处的柜子里拿出来，放到日常餐具的位置。一个月内，你就不会再特意注意它们，而这正是意义所在。"),
        ),
    },
)


class ArticleLocalizationTests(SimpleTestCase):
    @staticmethod
    def make_article(expected=ARTICLE_EXPECTED[0], **overrides):
        values = {
            "id": 71,
            "uuid": UUID("11111111-2222-3333-4444-555555555555"),
            "slug": expected["slug"],
            "title": expected["title"][0],
            "standfirst": expected["standfirst"][0],
            "category": expected["category"][0],
            "author": expected["author"][0],
            "cover_image": expected["image"],
            "read_time": expected["read_time"][0],
            "body": [{"type": kind, "text": english}
                     for kind, english, _ in expected["body"]],
            "is_featured": expected["featured"],
            "is_published": True,
            "published_at": datetime.strptime(
                expected["date"][0], "%d %B %Y",
            ).replace(tzinfo=datetime_timezone.utc),
        }
        values.update(overrides)
        return Article(**values)

    @staticmethod
    def scalar_fields(article):
        return (
            article.title, article.standfirst, article.category,
            article.read_time, article.author,
        )

    def test_all_canonical_english_seed_content_is_unchanged(self):
        self.assertEqual(len(ARTICLES), 5)
        for seed, expected in zip(ARTICLES, ARTICLE_EXPECTED, strict=True):
            with self.subTest(slug=expected["slug"]):
                self.assertEqual(
                    (seed["slug"], seed["title"], seed["standfirst"],
                     seed["category"], seed["read_time"], seed["author"],
                     seed["date"], seed["image"], seed["featured"]),
                    (expected["slug"], expected["title"][0],
                     expected["standfirst"][0], expected["category"][0],
                     expected["read_time"][0], expected["author"][0],
                     expected["date"][0], expected["image"], expected["featured"]),
                )
                self.assertEqual(
                    [(block["type"], block["text"]) for block in seed["body"]],
                    [(kind, english) for kind, english, _ in expected["body"]],
                )

    def test_all_five_articles_and_every_body_block_translate(self):
        for expected in ARTICLE_EXPECTED:
            with self.subTest(slug=expected["slug"]):
                source = self.make_article(expected)
                original_body = [dict(block) for block in source.body]
                original_dict_ids = [id(block) for block in source.body]
                with translation.override("zh-hans"):
                    localized = localize_article(source)
                self.assertEqual(
                    self.scalar_fields(localized),
                    (expected["title"][1], expected["standfirst"][1],
                     expected["category"][1], expected["read_time"][1],
                     expected["author"][1]),
                )
                self.assertEqual(
                    [(block["type"], block["text"]) for block in localized.body],
                    [(kind, chinese) for kind, _, chinese in expected["body"]],
                )
                self.assertEqual(source.body, original_body)
                self.assertEqual([id(block) for block in source.body], original_dict_ids)
                self.assertIsNot(localized.body, source.body)
                self.assertTrue(all(
                    localized_block is not source_block
                    for localized_block, source_block in zip(
                        localized.body, source.body, strict=True,
                    )
                ))

    def test_language_switching_preserves_all_ten_approved_title_strings(self):
        for expected in ARTICLE_EXPECTED:
            source = self.make_article(expected)
            with self.subTest(slug=expected["slug"]):
                with translation.override("en"):
                    self.assertIs(localize_article(source), source)
                    self.assertEqual(
                        (source.title, source.standfirst),
                        (expected["title"][0], expected["standfirst"][0]),
                    )
                with translation.override("zh-hans"):
                    localized = localize_article(source)
                    self.assertEqual(
                        (localized.title, localized.standfirst),
                        (expected["title"][1], expected["standfirst"][1]),
                    )
                with translation.override("en"):
                    self.assertIs(localize_article(source), source)
                    self.assertEqual(
                        (source.title, source.standfirst),
                        (expected["title"][0], expected["standfirst"][0]),
                    )

    def test_custom_scalar_fields_are_guarded_independently(self):
        expected = ARTICLE_EXPECTED[0]
        field_names = ("title", "standfirst", "category", "read_time", "author")
        chinese = (
            expected["title"][1], expected["standfirst"][1],
            expected["category"][1], expected["read_time"][1],
            expected["author"][1],
        )
        with translation.override("zh-hans"):
            for field in field_names:
                with self.subTest(field=field):
                    source = self.make_article(expected, **{field: "Editor copy"})
                    localized = localize_article(source)
                    wanted = dict(zip(field_names, chinese, strict=True))
                    wanted[field] = "Editor copy"
                    self.assertEqual(
                        self.scalar_fields(localized),
                        tuple(wanted[name] for name in field_names),
                    )
                    self.assertEqual(getattr(source, field), "Editor copy")

    def test_custom_body_text_is_preserved_independently_without_mutation(self):
        expected = ARTICLE_EXPECTED[0]
        source = self.make_article(expected)
        source.body[2]["text"] = "Editor-written kiln paragraph."
        original_body = [dict(block) for block in source.body]
        with translation.override("zh-hans"):
            localized = localize_article(source)
        self.assertEqual(localized.body[2]["text"], "Editor-written kiln paragraph.")
        self.assertEqual(localized.body[0]["text"], expected["body"][0][2])
        self.assertEqual(localized.body[-1]["text"], expected["body"][-1][2])
        self.assertEqual(source.body, original_body)
        self.assertIsNot(localized.body, source.body)
        self.assertTrue(all(
            localized_block is not source_block
            for localized_block, source_block in zip(
                localized.body, source.body, strict=True,
            )
        ))

    def test_changed_body_structures_are_preserved_as_a_whole(self):
        expected = ARTICLE_EXPECTED[0]
        cases = {}
        inserted = self.make_article(expected).body
        inserted.insert(1, {"type": "paragraph", "text": "Inserted block"})
        cases["inserted"] = inserted
        cases["missing"] = self.make_article(expected).body[:-1]
        reordered = self.make_article(expected).body
        reordered[0], reordered[1] = reordered[1], reordered[0]
        cases["reordered"] = reordered
        modified_type = self.make_article(expected).body
        modified_type[0] = {**modified_type[0], "type": "quote"}
        cases["modified-type"] = modified_type

        with translation.override("zh-hans"):
            for label, body in cases.items():
                with self.subTest(case=label):
                    source = self.make_article(expected, body=body)
                    localized = localize_article(source)
                    self.assertIs(localized.body, source.body)
                    self.assertEqual(localized.body, body)

    def test_none_unknown_slug_and_non_chinese_languages_return_original(self):
        source = self.make_article(slug="editor-created-article")
        with translation.override("zh-hans"):
            self.assertIsNone(localize_article(None))
            self.assertIs(localize_article(source), source)
        canonical = self.make_article()
        with translation.override("fr"):
            self.assertIs(localize_article(canonical), canonical)

    def test_presentation_metadata_and_template_contracts_are_preserved(self):
        expected = ARTICLE_EXPECTED[0]
        source = self.make_article(expected)
        with translation.override("zh-hans"):
            localized = localize_article(source)
        self.assertEqual(localized.excerpt, expected["standfirst"][1])
        self.assertEqual(localized.date, expected["date"][1])
        self.assertEqual(
            (localized.pk, localized.uuid, localized.slug, localized.image,
             localized.cover_image, localized.featured, localized.is_featured,
             localized.is_published, localized.published_at),
            (source.pk, source.uuid, source.slug, source.image,
             source.cover_image, source.featured, source.is_featured,
             source.is_published, source.published_at),
        )
        self.assertEqual(str(localized), expected["title"][1])

        index_source = (
            Path(__file__).parent / "templates/frontend/journal/index.html"
        ).read_text(encoding="utf-8")
        detail_source = (
            Path(__file__).parent / "templates/frontend/journal/detail.html"
        ).read_text(encoding="utf-8")
        for field in ("category", "read_time", "title", "standfirst"):
            self.assertIn(f"article.{field}", index_source)
            self.assertIn(f"article.{field}", detail_source)
        for field in ("author", "date", "body"):
            self.assertIn(f"article.{field}", detail_source)

        template = Template(
            "{{ article.category }}|{{ article.read_time }}|{{ article.author }}|"
            "{{ article.date }}|{{ article.title }}|{{ article.standfirst }}|"
            "{% for block in article.body %}{{ block.type }}:{{ block.text }}|{% endfor %}",
        )
        rendered = template.render(Context({"article": localized}))
        self.assertIn(expected["title"][1], rendered)
        self.assertIn(expected["standfirst"][1], rendered)
        self.assertIn(expected["date"][1], rendered)
        self.assertIn(f"heading:{expected['body'][1][2]}", rendered)
        self.assertIn(f"quote:{expected['body'][4][2]}", rendered)

    def test_article_services_keep_queries_and_localise_display_results(self):
        lead = self.make_article(ARTICLE_EXPECTED[0])
        related = self.make_article(ARTICLE_EXPECTED[1], id=72)
        manager = MagicMock()
        with translation.override("zh-hans"), patch.object(
            services.Article, "objects", manager,
        ):
            manager.published.return_value = [lead]
            all_result = services.all_articles()
            self.assertEqual(all_result[0].title, ARTICLE_EXPECTED[0]["title"][1])
            manager.published.assert_called_once_with()

            manager.reset_mock()
            published = MagicMock()
            published.filter.return_value.first.return_value = lead
            manager.published.return_value = published
            detail_result = services.get_article(lead.slug)
            self.assertEqual(detail_result.title, ARTICLE_EXPECTED[0]["title"][1])
            published.filter.assert_called_once_with(slug=lead.slug)
            published.filter.return_value.first.assert_called_once_with()

            manager.reset_mock()
            published = MagicMock()
            published.exclude.return_value.__getitem__.return_value = [related]
            manager.published.return_value = published
            related_result = services.related_articles(lead)
            self.assertEqual(related_result[0].title, ARTICLE_EXPECTED[1]["title"][1])
            published.exclude.assert_called_once_with(pk=lead.pk)
            published.exclude.return_value.__getitem__.assert_called_once_with(
                slice(None, 2, None),
            )

        self.assertEqual(lead.title, ARTICLE_EXPECTED[0]["title"][0])
        self.assertEqual(related.title, ARTICLE_EXPECTED[1]["title"][0])

    def test_every_body_text_is_a_literal_gettext_noop_argument(self):
        source = (
            Path(__file__).parent / "mockdata/journal.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        static_messages = {
            node.args[0].value
            for node in ast.walk(tree)
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "gettext_noop"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            )
        }
        body_messages = {
            english
            for article in ARTICLE_EXPECTED
            for _, english, _ in article["body"]
        }
        self.assertEqual(body_messages - static_messages, set())

    def test_same_type_body_reordering_preserves_the_complete_body(self):
        expected = ARTICLE_EXPECTED[0]
        source = self.make_article(expected)
        source.body[2], source.body[3] = source.body[3], source.body[2]
        original_body = [dict(block) for block in source.body]
        original_dict_ids = [id(block) for block in source.body]

        with translation.override("zh-hans"):
            localized = localize_article(source)

        self.assertIs(localized.body, source.body)
        self.assertEqual(localized.body, original_body)
        self.assertEqual(source.body, original_body)
        self.assertEqual([id(block) for block in source.body], original_dict_ids)
        self.assertTrue(all(
            block["text"] in {english for _, english, _ in expected["body"]}
            for block in localized.body
        ))

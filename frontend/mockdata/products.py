"""Product catalogue.

Mock data only. The shape mirrors the `products` app models described in the
project charter (listing, materials, stock status, variants, seller/maker link)
so that swapping this module for a queryset is a view-layer change, not a
template rewrite.
"""

from __future__ import annotations

import re

from typing import Any, Literal, TypedDict

from django.utils.translation import gettext_noop

StockStatus = Literal["in-stock", "low-stock", "made-to-order"]


class Variant(TypedDict):
    id: str
    label: str
    group: str          # "colour" | "size"
    swatch: str | None  # hex value, colour variants only
    available: bool


class Product(TypedDict):
    id: str
    slug: str
    name: str
    short_description: str
    description: str
    story: str
    price: float
    category: str
    collection: str | None
    materials: list[str]
    dimensions: str
    care: str
    images: list[str]
    variants: list[Variant]
    maker: str          # maker slug
    featured: bool
    new_arrival: bool
    stock_status: StockStatus
    dispatch: str
    added: int          # relative recency, higher is newer -- drives "Newest" sort


# Colour swatches drawn from the site palette so product chips never introduce
# a colour the rest of the design system does not already use.
SWATCHES = {
    gettext_noop("Bone"): "#EFE7DA", gettext_noop("Ash"): "#C6BFB2",
    gettext_noop("Clay"): "#B4674B", gettext_noop("Olive"): "#6F7757",
    gettext_noop("Ink"): "#3A342D", gettext_noop("Sand"): "#D9C9AF",
    gettext_noop("Indigo"): "#4A5568", gettext_noop("Rust"): "#A05A3C",
    gettext_noop("Natural"): "#E2D7C3", gettext_noop("Smoke"): "#8C8478",
}

CARE_BY_CATEGORY = {
    "ceramics": gettext_noop("Dishwasher safe, though hand washing keeps the glaze bright. "
                "Avoid thermal shock -- let a hot piece cool before rinsing. Not for direct flame."),
    "textiles": gettext_noop("Machine wash cool on a gentle cycle with a mild detergent. Line dry in "
                "shade. Warm iron while slightly damp if you want a crisper finish."),
    "home": gettext_noop("Wipe with a soft, barely damp cloth. Keep out of prolonged direct sun. "
            "Re-oil natural wood two or three times a year to keep it from drying out."),
    "gifts": gettext_noop("Care varies by piece -- each item ships with its own short care card."),
}


def _variants(colours: list[str] = (), sizes: list[str] = (), sold_out: list[str] = ()) -> list[Variant]:
    out: list[Variant] = []
    for c in colours:
        out.append({"id": f"colour-{c.lower()}", "label": c, "group": "colour",
                    "swatch": SWATCHES.get(c, "#D9C9AF"), "available": c not in sold_out})
    for s in sizes:
        out.append({"id": f"size-{s.lower().replace(' ', '-')}", "label": s, "group": "size",
                    "swatch": None, "available": s not in sold_out})
    return out


def _p(**kw: Any) -> Product:
    """Build a product, filling in everything that can be derived from the slug."""
    slug = kw["slug"]
    kw.setdefault("id", slug)
    kw.setdefault("images", [f"product-{slug}-1", f"product-{slug}-2", f"product-{slug}-3"])
    kw.setdefault("care", CARE_BY_CATEGORY[kw["category"]])
    kw.setdefault("collection", kw["category"])
    kw.setdefault("variants", [])
    kw.setdefault("featured", False)
    kw.setdefault("new_arrival", False)
    kw.setdefault("stock_status", "in-stock")
    kw.setdefault("dispatch", gettext_noop("Ships in 2–4 working days"))
    return kw  # type: ignore[return-value]


PRODUCTS: list[Product] = [
    # -- Ceramics ---------------------------------------------------------
    _p(slug="hand-thrown-stoneware-mug", name=gettext_noop("Hand-thrown Stoneware Mug"),
       short_description=gettext_noop("Stoneware · Chen Meilin"), price=42, category="ceramics",
       collection="earth", maker="chen-meilin", featured=True, new_arrival=True, added=21,
       materials=["Jingdezhen stoneware", "Ash glaze", "Unglazed foot"],
       dimensions="Ø 8.5 cm × 9 cm · 280 ml",
       description=gettext_noop("A mug with a little weight to it, thrown to sit low in the hand. "
                   "The glaze pools slightly where the wall meets the base, so the colour "
                   "is never quite even across a set."),
       story=gettext_noop("Meilin threw the first of these for herself, then kept making them because "
             "visitors to the studio would not put them down. The handle is pulled by hand "
             "rather than cast, which is why the curve is a fraction different on every one."),
       variants=_variants(colours=["Bone", "Ash", "Clay", "Olive"])),

    _p(slug="speckled-breakfast-bowl", name=gettext_noop("Speckled Breakfast Bowl"),
       short_description=gettext_noop("Stoneware · Chen Meilin"), price=38, category="ceramics",
       collection="earth", maker="chen-meilin", featured=True, new_arrival=True, added=20,
       materials=["Speckled stoneware", "Matte glaze"],
       dimensions="Ø 15 cm × 7 cm · 500 ml",
       description=gettext_noop("Wide enough for oats and deep enough for soup. The iron in the clay "
                   "breaks through the glaze as fine dark flecks during firing."),
       story=gettext_noop("The speckle is not added. It is iron already present in the local clay, "
             "which surfaces only above 1250°C -- a firing Meilin holds for nine hours."),
       variants=_variants(colours=["Bone", "Ash", "Olive"], sold_out=["Olive"])),

    _p(slug="ceramic-pour-over-dripper", name=gettext_noop("Ceramic Pour-Over Dripper"),
       short_description=gettext_noop("Porcelain · Chen Meilin"), price=68, category="ceramics",
       collection="earth", maker="chen-meilin", featured=True, new_arrival=True, added=19,
       materials=["Porcelain", "Clear glaze"], dimensions="Ø 11.5 cm × 8 cm · 1–2 cups",
       description=gettext_noop("A single-piece dripper with three ribs turned into the cone, so water "
                   "moves evenly through the bed rather than channelling down one side."),
       story=gettext_noop("Six prototypes went into the angle of the cone. Meilin brewed on every one of "
             "them for a fortnight before settling on this shape."),
       stock_status="low-stock"),

    _p(slug="ash-glazed-dinner-plate", name=gettext_noop("Ash-Glazed Dinner Plate"),
       short_description=gettext_noop("Stoneware · Chen Meilin"), price=46, category="ceramics",
       collection="earth", maker="chen-meilin", added=14,
       materials=["Stoneware", "Wood-ash glaze"], dimensions="Ø 26 cm × 2.5 cm",
       description=gettext_noop("A everyday plate with a low, generous rim. The ash glaze moves in the "
                   "kiln, so the edge is usually a shade lighter than the well."),
       story=gettext_noop("The glaze is mixed from ash swept out of the studio's own kiln -- a practice "
             "old enough in Jingdezhen that nobody there thinks of it as unusual."),
       variants=_variants(colours=["Bone", "Sand", "Ash"])),

    _p(slug="stoneware-serving-platter", name=gettext_noop("Stoneware Serving Platter"),
       short_description=gettext_noop("Stoneware · Chen Meilin"), price=88, category="ceramics",
       maker="chen-meilin", added=8, stock_status="made-to-order",
       dispatch=gettext_noop("Made to order · ships in 3–4 weeks"),
       materials=["Stoneware", "Satin glaze"], dimensions="34 cm × 22 cm × 3 cm",
       description=gettext_noop("An oval platter for bread, roasted vegetables or a whole fish. Thrown, "
                   "then pressed gently out of round while still soft."),
       story=gettext_noop("Made only in small runs, when the large kiln is fired. Meilin will not fire it "
             "half empty, so these appear a few times a year.")),

    _p(slug="matte-ceramic-vase", name=gettext_noop("Matte Ceramic Vase"),
       short_description=gettext_noop("Stoneware · Chen Meilin"), price=74, category="ceramics",
       collection="earth", maker="chen-meilin", featured=True, added=17,
       materials=["Stoneware", "Matte glaze"], dimensions="Ø 12 cm × 24 cm",
       description=gettext_noop("A tall, narrow-necked vase that holds a few stems upright without "
                   "propping. Matte outside, glossed inside so it holds water."),
       story=gettext_noop("Meilin keeps one on the windowsill of the studio with whatever is in season. "
             "Most of the year that means a single branch."),
       variants=_variants(colours=["Bone", "Smoke", "Clay"])),

    _p(slug="tea-cup-set-of-two", name=gettext_noop("Tea Cup Set of Two"),
       short_description=gettext_noop("Porcelain · Chen Meilin"), price=64, category="ceramics",
       maker="chen-meilin", added=11,
       materials=["Porcelain", "Celadon glaze"], dimensions="Ø 7 cm × 5 cm · 120 ml each",
       description=gettext_noop("Two handleless cups, thin at the lip and thicker at the base. Pale "
                   "celadon that shifts towards green where the glaze gathers."),
       story=gettext_noop("Thrown in pairs and fired side by side, so the two cups in a set carry the "
             "same marks from the same corner of the kiln.")),

    # -- Textiles ---------------------------------------------------------
    _p(slug="linen-market-tote", name=gettext_noop("Linen Market Tote"),
       short_description=gettext_noop("Washed linen · Ye Ruolan"), price=58, category="textiles",
       maker="ye-ruolan", featured=True, new_arrival=True, added=18,
       materials=["European flax linen", "Cotton webbing handles"],
       dimensions="42 cm × 38 cm · 12 cm base",
       description=gettext_noop("A flat-bottomed tote in heavyweight linen, with an inside pocket and "
                   "handles long enough to carry over a shoulder."),
       story=gettext_noop("Ruolan made the first one because nothing she owned would hold a week of "
             "vegetables and still look like something she wanted to carry."),
       variants=_variants(colours=["Natural", "Indigo", "Olive"])),

    _p(slug="woven-cotton-throw", name=gettext_noop("Woven Cotton Throw"),
       short_description=gettext_noop("Handwoven cotton · Lu Wenjing"), price=128, category="textiles",
       collection="earth", maker="lu-wenjing", featured=True, new_arrival=True, added=22,
       materials=["Handwoven cotton", "Natural indigo dye", "Hand-knotted fringe"],
       dimensions="130 cm × 180 cm",
       description=gettext_noop("Woven in two panels and joined by hand down the centre. Heavy enough "
                   "for a bed, soft enough for a chair."),
       story=gettext_noop("Wenjing dips the yarn before it is ever woven, which is why the colour sits "
             "inside the cloth rather than on it, and deepens rather than fades."),
       variants=_variants(colours=["Indigo", "Natural", "Smoke"]),
       stock_status="low-stock"),

    _p(slug="linen-cushion-cover", name=gettext_noop("Linen Cushion Cover"),
       short_description=gettext_noop("Washed linen · Ye Ruolan"), price=54, category="textiles",
       maker="ye-ruolan", new_arrival=True, added=16,
       materials=["Stone-washed flax linen", "Coconut buttons"],
       dimensions="Available 45 cm or 60 cm square",
       description=gettext_noop("A simple envelope cover with a buttoned back. Washed twice before it "
                   "leaves the studio so it arrives already soft."),
       story=gettext_noop("The buttons are coconut shell, cut and drilled by a workshop two streets from "
             "Ruolan's own -- the last of its kind in the neighbourhood."),
       variants=_variants(colours=["Bone", "Sand", "Olive", "Rust"], sizes=["45 cm", "60 cm"])),

    _p(slug="stonewashed-table-runner", name=gettext_noop("Stonewashed Table Runner"),
       short_description=gettext_noop("Washed linen · Ye Ruolan"), price=62, category="textiles",
       maker="ye-ruolan", added=9,
       materials=["Stone-washed flax linen", "Hand-hemmed edges"],
       dimensions="45 cm × 200 cm",
       description=gettext_noop("A long runner with a deep hand-turned hem. Creases readily, which is "
                   "rather the point."),
       story=gettext_noop("Ruolan does not press these flat before packing. A runner that arrives "
             "perfectly smooth, she says, has been finished by a machine."),
       variants=_variants(colours=["Natural", "Ash", "Olive"])),

    _p(slug="hand-loomed-tea-towel", name=gettext_noop("Hand-loomed Tea Towel"),
       short_description=gettext_noop("Cotton & linen · Lu Wenjing"), price=26, category="textiles",
       maker="lu-wenjing", added=6,
       materials=["Handwoven cotton-linen", "Natural dye"], dimensions="50 cm × 70 cm",
       description=gettext_noop("Loosely woven so it dries fast, with a hanging loop set into the corner. "
                   "Gets better with washing."),
       story=gettext_noop("Woven on the narrow loom Wenjing keeps for offcuts, using yarn left over from "
             "the throws. No two runs are quite the same colour."),
       variants=_variants(colours=["Indigo", "Natural", "Rust"])),

    _p(slug="quilted-linen-apron", name=gettext_noop("Quilted Linen Apron"),
       short_description=gettext_noop("Washed linen · Ye Ruolan"), price=78, category="textiles",
       maker="ye-ruolan", added=12,
       materials=["Flax linen", "Cotton wadding", "Brass hardware"],
       dimensions="One size · adjustable neck strap · 85 cm long",
       description=gettext_noop("A cross-back apron with a lightly quilted front panel and two deep "
                   "pockets. Adjustable at the neck, ties at the waist."),
       story=gettext_noop("Designed with a baker in Hangzhou who wanted something that would take flour, "
             "heat and a hot pan handle without falling apart in a year."),
       variants=_variants(colours=["Ink", "Natural", "Olive"])),

    # -- Home -------------------------------------------------------------
    _p(slug="soy-wax-studio-candle", name=gettext_noop("Soy Wax Studio Candle"),
       short_description=gettext_noop("Soy & rapeseed wax · Xu Anying"), price=44, category="home",
       collection="earth", maker="xu-anying", featured=True, new_arrival=True, added=23,
       materials=["Soy and rapeseed wax", "Cotton wick", "Refillable stoneware vessel"],
       dimensions="Ø 8 cm × 9 cm · 220 g · approx. 45 hours",
       description=gettext_noop("Cedar, dry earth and a little green fig. Poured into a stoneware vessel "
                   "worth keeping once the wax is gone."),
       story=gettext_noop("Anying built this scent around the smell of her workshop after rain -- wet "
             "stone, cut wood, and the fig tree in the courtyard next door."),
       variants=_variants(colours=[gettext_noop("Cedar & Fig"),
                                  gettext_noop("Wild Grass"),
                                  gettext_noop("Smoked Cypress")])),

    _p(slug="handmade-incense-holder", name=gettext_noop("Handmade Incense Holder"),
       short_description=gettext_noop("Stoneware · Chen Meilin"), price=32, category="home",
       maker="chen-meilin", added=13,
       materials=["Stoneware", "Unglazed exterior"], dimensions="Ø 9 cm × 2 cm",
       description=gettext_noop("A shallow dish with an off-centre hole, sized for standard incense "
                   "sticks. Unglazed outside so it keeps a little grip on the table."),
       story=gettext_noop("Meilin makes these from the clay left at the end of a throwing session -- too "
             "little for a bowl, exactly enough for one of these."),
       variants=_variants(colours=["Bone", "Smoke", "Clay"])),

    _p(slug="olive-wood-serving-board", name=gettext_noop("Olive Wood Serving Board"),
       short_description=gettext_noop("Reclaimed timber · Zhao Hesheng"), price=72, category="home",
       collection="earth", maker="zhao-hesheng", featured=True, added=15,
       materials=["Reclaimed hardwood", "Linseed oil finish"],
       dimensions="38 cm × 18 cm × 2 cm · varies slightly",
       description=gettext_noop("A long board with a shaped handle and a lip cut into the underside so "
                   "it lifts easily off a flat table."),
       story=gettext_noop("Cut from beams salvaged during the restoration of a Huizhou courtyard house. "
             "The grain, and occasionally an old nail hole, comes with the timber."),
       stock_status="low-stock"),

    _p(slug="brass-oak-candle-snuffer", name=gettext_noop("Brass & Oak Candle Snuffer"),
       short_description=gettext_noop("Brass & oak · Zhao Hesheng"), price=36, category="home",
       maker="zhao-hesheng", added=7,
       materials=["Unlacquered brass", "Oak handle"], dimensions="24 cm long",
       description=gettext_noop("An unlacquered brass bell on a turned oak handle. The brass will darken "
                   "with handling, which is how it is meant to go."),
       story=gettext_noop("Hesheng turns the handles from oak offcuts and has the bells spun by a "
             "metalworker he has used for eleven years.")),

    _p(slug="rattan-storage-basket", name=gettext_noop("Rattan Storage Basket"),
       short_description=gettext_noop("Woven rattan · Lu Wenjing"), price=84, category="home",
       maker="lu-wenjing", added=10, stock_status="made-to-order",
       dispatch=gettext_noop("Made to order · ships in 2–3 weeks"),
       materials=["Rattan", "Cotton rope handles"], dimensions="Ø 36 cm × 32 cm",
       description=gettext_noop("A deep round basket with soft rope handles, woven closely enough to "
                   "hold its shape when empty."),
       story=gettext_noop("Woven by a group of five weavers in a village outside Dali, in the weeks "
             "between planting and harvest."),
       variants=_variants(sizes=["Medium", "Large"])),

    # -- Gifts ------------------------------------------------------------
    _p(slug="ceramic-ring-dish", name=gettext_noop("Ceramic Ring Dish"),
       short_description=gettext_noop("Porcelain · Chen Meilin"), price=28, category="gifts",
       maker="chen-meilin", added=5,
       materials=["Porcelain", "Gold-free celadon glaze"], dimensions="Ø 9 cm × 1.5 cm",
       description=gettext_noop("A small pinched dish for rings, earrings or the change in your pocket. "
                   "Pinched rather than thrown, so the rim is deliberately uneven."),
       story=gettext_noop("The first of these were made as thank-you gifts for the studio's earliest "
             "customers. Enough people asked to buy one that they became a product."),
       variants=_variants(colours=["Bone", "Sand", "Olive"])),

    _p(slug="studio-gift-set", name=gettext_noop("Studio Gift Set"),
       short_description=gettext_noop("Three pieces, wrapped · Multiple makers"), price=96, category="gifts",
       maker="xu-anying", featured=True, added=4,
       materials=["Stoneware mug", "Soy wax candle", "Hand-loomed tea towel"],
       dimensions="Boxed 26 cm × 20 cm × 11 cm",
       description=gettext_noop("A mug, a small candle and a tea towel, wrapped in unbleached paper and "
                   "tied with cotton string. A card can be written at checkout."),
       story=gettext_noop("The set we send most often, and the one the studio sends to its own suppliers "
             "at the end of every year."),
       variants=_variants(colours=["Bone", "Olive"])),

    _p(slug="beeswax-taper-pair", name=gettext_noop("Beeswax Taper Pair"),
       short_description=gettext_noop("Pure beeswax · Xu Anying"), price=24, category="gifts",
       maker="xu-anying", added=3,
       materials=["Pure beeswax", "Cotton wick"], dimensions="2 cm × 25 cm · approx. 8 hours each",
       description=gettext_noop("Two hand-dipped tapers in unbleached beeswax. They smell faintly of "
                   "honey when lit and drip very little."),
       story=gettext_noop("Dipped forty times each, one layer at a time, over the course of an afternoon."),
       stock_status="low-stock"),
]

PRODUCTS_BY_SLUG: dict[str, Product] = {p["slug"]: p for p in PRODUCTS}

# Facets are derived from the catalogue rather than hard-coded, so a new product
# with a new material automatically appears in the shop filters.
# The raw materials list runs to ~40 strings, which is unusable as a filter, so
# the shop facets on a curated set of material families instead.
MATERIAL_FAMILIES = ["Stoneware", "Porcelain", "Linen", "Cotton", "Wood", "Brass",
                     "Rattan", "Wax"]


def material_families(product: Product) -> list[str]:
    """Material families a product belongs to, used for shop filtering."""
    blob = " ".join(product["materials"]).lower()
    # "wood-ash glaze" is a glaze, not a timber -- drop it before matching.
    blob = blob.replace("wood-ash", "ash")
    aliases = {
        "Stoneware": ["stoneware"], "Porcelain": ["porcelain"],
        "Linen": ["linen", "flax"], "Cotton": ["cotton"],
        "Wood": ["wood", "oak", "hardwood", "timber"], "Brass": ["brass"],
        "Rattan": ["rattan"], "Wax": ["wax", "beeswax", "soy", "rapeseed"],
    }
    return [f for f in MATERIAL_FAMILIES
            if any(re.search(rf"\b{a}", blob) for a in aliases[f])]


ALL_MATERIALS = MATERIAL_FAMILIES
ALL_COLOURS = sorted({v["label"] for p in PRODUCTS for v in p["variants"] if v["group"] == "colour"})
PRICE_MAX = max(p["price"] for p in PRODUCTS)

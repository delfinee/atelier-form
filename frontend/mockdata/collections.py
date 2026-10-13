"""Collections -- both the four browsing categories and the editorial groupings."""

from __future__ import annotations

from typing import TypedDict

from django.utils.translation import gettext_noop


class Collection(TypedDict):
    slug: str
    title: str
    kind: str            # "category" | "editorial"
    tagline: str
    description: str
    hero: str
    tile: str
    featured: bool


COLLECTIONS: list[Collection] = [
    {
        "slug": "ceramics", "title": gettext_noop("Ceramics"), "kind": "category",
        "tagline": gettext_noop("Thrown, trimmed and fired one at a time."),
        "description": gettext_noop(
            "Stoneware and porcelain for the table, made in a Jingdezhen studio "
                       "where the clay is quarried an hour away and the glazes are mixed from "
                       "ash and iron. Expect small variations in colour and rim -- they are "
                       "the record of a hand, not a fault."
        ),
        "hero": "collection-ceramics", "tile": "category-ceramics", "featured": True,
    },
    {
        "slug": "textiles", "title": gettext_noop("Textiles"), "kind": "category",
        "tagline": gettext_noop("Woven, dyed and washed until they soften."),
        "description": gettext_noop(
            "Linen and handwoven cotton, dyed with indigo grown in Yunnan and "
                       "finished so that nothing arrives stiff. These are pieces meant to be "
                       "used daily and washed often."
        ),
        "hero": "collection-textiles", "tile": "category-textiles", "featured": True,
    },
    {
        "slug": "home", "title": "Home", "kind": "category",
        "tagline": gettext_noop("Objects for the quieter corners of a room."),
        "description": gettext_noop(
            "Candles poured in batches of forty, boards cut from reclaimed "
                       "courtyard beams, brass that is meant to darken. Small things that "
                       "change the feeling of a room more than their size suggests."
        ),
        "hero": "collection-home", "tile": "category-home", "featured": True,
    },
    {
        "slug": "gifts", "title": gettext_noop("Gifts"), "kind": "category",
        "tagline": gettext_noop("Wrapped in unbleached paper and cotton string."),
        "description": gettext_noop(
            "Pieces that travel well as a gift, boxed by hand with a card you can "
                       "write at checkout. Nothing here is sealed in plastic."
        ),
        "hero": "collection-gifts", "tile": "category-gifts", "featured": True,
    },
    {
        "slug": "earth", "title": gettext_noop("The Earth Collection"), "kind": "editorial",
        "tagline": gettext_noop("Ash, clay, indigo and unbleached linen."),
        "description": gettext_noop(
            "Nine pieces built from the same short list of materials, glazed and "
            "dyed with what our makers can source within a day's drive of their own "
            "studios. Put together, they sit in a single tonal range -- bone, ash, "
            "clay and a green that comes from grass rather than a pigment jar."
        ),
        "hero": "collection-earth", "tile": "collection-earth", "featured": True,
    },
]

COLLECTIONS_BY_SLUG: dict[str, Collection] = {c["slug"]: c for c in COLLECTIONS}
CATEGORIES = [c for c in COLLECTIONS if c["kind"] == "category"]

# Editorial groupings beyond the four browsing categories.
EXTRA_COLLECTIONS = [
    {"slug": "quiet-mornings", "name": gettext_noop("Quiet Mornings"),
     "tagline": gettext_noop("For the first hour of the day."),
     "description": gettext_noop(
         "Cups, drippers and a candle for the part of the morning before anything "
         "has been asked of you. Chosen so the pieces sit together on a small table."
     ),
     "hero": "collection-ceramics", "tile": "category-ceramics", "featured": True,
     "members": ["hand-thrown-stoneware-mug", "ceramic-pour-over-dripper",
                 "speckled-breakfast-bowl", "tea-cup-set-of-two", "soy-wax-studio-candle"]},
    {"slug": "studio-essentials", "name": gettext_noop("Studio Essentials"),
     "tagline": gettext_noop("The pieces we use ourselves."),
     "description": gettext_noop(
         "What is actually in daily use in the studio: an apron that has been "
         "washed a hundred times, boards that get cut on, towels that get used."
     ),
     "hero": "collection-home", "tile": "category-home", "featured": False,
     "members": ["quilted-linen-apron", "olive-wood-serving-board", "hand-loomed-tea-towel",
                 "linen-market-tote", "brass-oak-candle-snuffer"]},
]

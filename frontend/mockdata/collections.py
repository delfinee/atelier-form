"""Collections -- both the four browsing categories and the editorial groupings."""

from __future__ import annotations

from typing import TypedDict


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
        "slug": "ceramics", "title": "Ceramics", "kind": "category",
        "tagline": "Thrown, trimmed and fired one at a time.",
        "description": "Stoneware and porcelain for the table, made in a Jingdezhen studio "
                       "where the clay is quarried an hour away and the glazes are mixed from "
                       "ash and iron. Expect small variations in colour and rim -- they are "
                       "the record of a hand, not a fault.",
        "hero": "collection-ceramics", "tile": "category-ceramics", "featured": True,
    },
    {
        "slug": "textiles", "title": "Textiles", "kind": "category",
        "tagline": "Woven, dyed and washed until they soften.",
        "description": "Linen and handwoven cotton, dyed with indigo grown in Yunnan and "
                       "finished so that nothing arrives stiff. These are pieces meant to be "
                       "used daily and washed often.",
        "hero": "collection-textiles", "tile": "category-textiles", "featured": True,
    },
    {
        "slug": "home", "title": "Home", "kind": "category",
        "tagline": "Objects for the quieter corners of a room.",
        "description": "Candles poured in batches of forty, boards cut from reclaimed "
                       "courtyard beams, brass that is meant to darken. Small things that "
                       "change the feeling of a room more than their size suggests.",
        "hero": "collection-home", "tile": "category-home", "featured": True,
    },
    {
        "slug": "gifts", "title": "Gifts", "kind": "category",
        "tagline": "Wrapped in unbleached paper and cotton string.",
        "description": "Pieces that travel well as a gift, boxed by hand with a card you can "
                       "write at checkout. Nothing here is sealed in plastic.",
        "hero": "collection-gifts", "tile": "category-gifts", "featured": True,
    },
    {
        "slug": "earth", "title": "The Earth Collection", "kind": "editorial",
        "tagline": "Ash, clay, indigo and unbleached linen.",
        "description": "Nine pieces built from the same short list of materials, glazed and "
                       "dyed with what our makers can source within a day's drive of their own "
                       "studios. Put together, they sit in a single tonal range -- bone, ash, "
                       "clay and a green that comes from grass rather than a pigment jar.",
        "hero": "collection-earth", "tile": "collection-earth", "featured": True,
    },
]

COLLECTIONS_BY_SLUG: dict[str, Collection] = {c["slug"]: c for c in COLLECTIONS}
CATEGORIES = [c for c in COLLECTIONS if c["kind"] == "category"]

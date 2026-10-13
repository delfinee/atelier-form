"""Maker profiles.

Mock data only. When the `accounts` app gains a real Seller/ArtisanProfile model
this module is replaced by a queryset -- the shape below is deliberately close to
what those models will expose, so templates will not need to change.
"""

from __future__ import annotations

from typing import TypedDict

from django.utils.translation import gettext_noop


class Maker(TypedDict):
    slug: str
    name: str
    discipline: str
    location: str
    since: str
    portrait: str
    tagline: str
    biography: list[str]
    process: list[str]
    images: list[str]


MAKERS: list[Maker] = [
    {
        "slug": "chen-meilin",
        "name": gettext_noop("Chen Meilin"),
        "discipline": gettext_noop("Ceramicist"),
        "location": gettext_noop("Jingdezhen, Jiangxi"),
        "since": "2014",
        "portrait": "maker-chen-meilin",
        "tagline": gettext_noop("Porcelain thrown thin enough to hold the light."),
        "biography": [
            gettext_noop("Meilin trained for six years under a Jingdezhen master before opening a "
            "small studio on the eastern edge of the old kiln district. She works "
            "almost entirely in local porcelain stone, quarried an hour from her door."),
            gettext_noop("Her forms are quiet and slightly imperfect by design. A rim that dips a "
            "little, a foot left unglazed so you can read the clay -- these are the "
            "marks she leaves on purpose, and the reason no two pieces are alike."),
        ],
        "process": [
            gettext_noop("Clay is wedged by hand each morning and rested overnight before throwing."),
            gettext_noop("Every piece is turned on the wheel, then trimmed once leather-hard."),
            gettext_noop("Glazes are mixed in small batches from ash, feldspar and iron oxide."),
            gettext_noop("A single gas firing to 1280°C, with the kiln cooled slowly over two days."),
        ],
        "images": ["maker-chen-meilin-process-1", "maker-chen-meilin-process-2"],
    },
    {
        "slug": "lu-wenjing",
        "name": gettext_noop("Lu Wenjing"),
        "discipline": gettext_noop("Weaver & natural dyer"),
        "location": gettext_noop("Dali, Yunnan"),
        "since": "2011",
        "portrait": "maker-lu-wenjing",
        "tagline": gettext_noop("Indigo that deepens with every wash."),
        "biography": [
            gettext_noop("Wenjing learned to dye from her grandmother, who kept an indigo vat "
            "behind the family house in Dali. She now grows her own indigo and "
            "works with three neighbouring households during the harvest."),
            gettext_noop("She weaves on a floor loom her father built, in cotton and hemp spun "
            "within the province. Nothing in her studio is dyed twice the same way, "
            "and she has stopped apologising for it."),
        ],
        "process": [
            gettext_noop("Indigo is fermented in clay vats and fed weekly through the season."),
            gettext_noop("Cloth is dipped between six and fourteen times, depending on the depth wanted."),
            gettext_noop("Washed in river water and dried in shade to keep the colour even."),
            gettext_noop("Woven, finished and hemmed by hand on a wooden floor loom."),
        ],
        "images": ["maker-lu-wenjing-process-1", "maker-lu-wenjing-process-2"],
    },
    {
        "slug": "zhao-hesheng",
        "name": gettext_noop("Zhao Hesheng"),
        "discipline": gettext_noop("Woodworker"),
        "location": gettext_noop("Huizhou, Anhui"),
        "since": "2009",
        "portrait": "maker-zhao-hesheng",
        "tagline": gettext_noop("Working with the grain, never against it."),
        "biography": [
            gettext_noop("Hesheng spent a decade restoring Huizhou timber houses before turning "
            "to smaller objects. He still sources most of his wood from those "
            "restorations -- beams and floorboards that have already lived a life."),
            gettext_noop("He cuts joinery by hand and finishes everything in raw linseed oil. "
            "Nothing leaves the bench until it feels right in the hand."),
        ],
        "process": [
            gettext_noop("Reclaimed timber is milled, then rested for a season to settle."),
            gettext_noop("Every joint is cut and pared by hand -- no dowels, no filler."),
            gettext_noop("Surfaces are worked through five grades of abrasive to a soft sheen."),
            gettext_noop("Finished in food-safe linseed oil, reapplied three times over a week."),
        ],
        "images": ["maker-zhao-hesheng-process-1", "maker-zhao-hesheng-process-2"],
    },
    {
        "slug": "xu-anying",
        "name": gettext_noop("Xu Anying"),
        "discipline": gettext_noop("Candlemaker & perfumer"),
        "location": gettext_noop("Suzhou, Jiangsu"),
        "since": "2017",
        "portrait": "maker-xu-anying",
        "tagline": gettext_noop("Scent built the way a garden is planted."),
        "biography": [
            gettext_noop("Anying studied classical Chinese garden design before training in "
            "perfumery. She thinks about a scent the way she was taught to think "
            "about a courtyard: what you meet first, and what you find later."),
            gettext_noop("She pours in batches of forty, by hand, in a converted ground-floor "
            "workshop near the canal. Each batch is left to cure for two weeks "
            "before a wick is ever lit."),
        ],
        "process": [
            gettext_noop("Essential oils are blended and left to marry for ten days."),
            gettext_noop("Soy and rapeseed wax is melted low, never above 65°C."),
            gettext_noop("Poured by hand in batches of forty, one vessel at a time."),
            gettext_noop("Cured for fourteen days, then burn-tested from every batch."),
        ],
        "images": ["maker-xu-anying-process-1", "maker-xu-anying-process-2"],
    },
    {
        "slug": "ye-ruolan",
        "name": gettext_noop("Ye Ruolan"),
        "discipline": gettext_noop("Textile artist"),
        "location": gettext_noop("Hangzhou, Zhejiang"),
        "since": "2016",
        "portrait": "maker-ye-ruolan",
        "tagline": gettext_noop("Linen washed until it forgets it was ever stiff."),
        "biography": [
            gettext_noop("Ruolan works in European flax linen, finished in her own studio using "
            "a stone-washing process she spent two years refining. The point, she "
            "says, is for a new piece to feel like one you have owned for years."),
            gettext_noop("She cuts and sews everything herself, with a single assistant during "
            "busy months, and keeps her ranges deliberately small."),
        ],
        "process": [
            gettext_noop("Flax linen is sourced from a single mill and cut in small lays."),
            gettext_noop("Seams are sewn, then the finished piece is stone-washed twice."),
            gettext_noop("Dried flat and pressed once, lightly, to keep the natural crumple."),
            gettext_noop("Checked seam by seam before it is folded and wrapped."),
        ],
        "images": ["maker-ye-ruolan-process-1", "maker-ye-ruolan-process-2"],
    },
]

MAKERS_BY_SLUG: dict[str, Maker] = {m["slug"]: m for m in MAKERS}

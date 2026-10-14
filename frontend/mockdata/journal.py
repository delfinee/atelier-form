"""Journal articles."""

from __future__ import annotations

from typing import TypedDict

from django.utils.translation import gettext_noop


class Article(TypedDict):
    slug: str
    title: str
    standfirst: str
    category: str
    date: str
    read_time: str
    author: str
    image: str
    featured: bool
    body: list[dict]     # {"type": "paragraph" | "heading" | "quote", "text": str}


def _t(*paras: str) -> list[dict]:
    return [{"type": "paragraph", "text": p} for p in paras]


ARTICLES: list[Article] = [
    {
        "slug": "why-no-two-glazes-match",
        "title": gettext_noop("Why no two glazes match"),
        "standfirst": gettext_noop(
            "A wood-ash glaze is a record of the firing that made it. Here is why "
            "we stopped trying to make them identical."
        ),
        "category": gettext_noop("Craft"), "date": "12 August 2026",
        "read_time": gettext_noop("6 min"),
        "author": gettext_noop("Chen Meilin"),
        "image": "journal-why-no-two-glazes-match", "featured": True,
        "body": [
            {"type": "paragraph", "text": gettext_noop(
             "Ask a factory to make five hundred mugs the same colour and it will. Ask a "
             "kiln to do it and you will get something more interesting and less obedient.")},
            {"type": "heading", "text": gettext_noop("What the kiln decides")},
            {"type": "paragraph", "text": gettext_noop(
             "Ash glaze is mixed from what is swept out of the kiln after a firing -- wood "
             "ash, feldspar, a little iron oxide, water. The proportions are consistent. "
             "What is not consistent is where a piece sits in the kiln, how the flame moves "
             "around it, and how fast that corner cools over the two days afterwards.")},
            {"type": "paragraph", "text": gettext_noop(
             "A mug on the top shelf near the flue will come out a shade greener than the "
             "same mug, from the same batch of glaze, on the bottom shelf. Neither is the "
             "correct one.")},
            {"type": "quote", "text": gettext_noop(
             "We fire to a range, not a number. The kiln finishes the piece, and it does not "
             "take instruction.")},
            {"type": "heading", "text": gettext_noop("Living with variation")},
            {"type": "paragraph", "text": gettext_noop(
             "This has a practical consequence for anyone buying a set. If you order four "
             "bowls, you will get four bowls that clearly belong together and are clearly not "
             "identical. Over a few years of use they diverge further -- the ones you reach "
             "for most develop a slightly different surface.")},
            {"type": "paragraph", "text": gettext_noop(
             "We used to photograph the most even piece of a batch. We now photograph a "
             "middling one, because it is closer to what arrives.")},
        ],
    },
    {
        "slug": "an-indigo-vat-in-dali",
        "title": gettext_noop("An indigo vat in Dali"),
        "standfirst": gettext_noop(
            "Lu Wenjing keeps four fermenting vats behind her house. Feeding them "
            "is a weekly job that has no shortcut."
        ),
        "category": gettext_noop("Makers"), "date": "29 July 2026",
        "read_time": gettext_noop("8 min"),
        "author": gettext_noop("Atelier Form"),
        "image": "journal-an-indigo-vat-in-dali", "featured": True,
        "body": [
            {"type": "paragraph", "text": gettext_noop(
             "The vats are clay, sunk to the rim in the ground behind the house, and they are "
             "alive in a fairly literal sense. Indigo does not dissolve in water. It has to be "
             "reduced by bacteria first, and those bacteria need feeding, warmth and time.")},
            {"type": "heading", "text": gettext_noop("A weekly rhythm")},
            {"type": "paragraph", "text": gettext_noop(
             "Every Monday Wenjing adds wheat bran and lime, stirs each vat and checks the "
             "surface for the coppery film that says the vat is working. A healthy vat smells "
             "sweet. An unhappy one smells of nothing at all, which is worse.")},
            {"type": "paragraph", "text": gettext_noop(
             "Cloth goes in yellow-green and turns blue in the air, in front of you, over about "
             "twenty seconds. Six dips gives a pale sky. Fourteen gives the near-black indigo "
             "on our heaviest throws.")},
            {"type": "heading", "text": gettext_noop("Why it fades the way it does")},
            {"type": "paragraph", "text": gettext_noop(
             "Indigo sits on the outside of the fibre rather than inside it. That is why "
             "indigo cloth wears at the folds and the edges first, and why a piece you use "
             "every week will look different from one kept in a cupboard. It is also why it "
             "will never look worse -- only more specific to you.")},
        ],
    },
    {
        "slug": "how-to-care-for-handmade-ceramics",
        "title": gettext_noop("How to care for handmade ceramics"),
        "standfirst": gettext_noop(
            "Most of what shortens the life of a handmade piece is heat, not use."
        ),
        "category": gettext_noop("Care"), "date": "14 July 2026",
        "read_time": gettext_noop("4 min"),
        "author": gettext_noop("Atelier Form"),
        "image": "journal-how-to-care-for-handmade-ceramics",
        "featured": False,
        "body": _t(
            gettext_noop(
                "Our stoneware is fired high enough to be fully vitrified, which means it is "
                "dishwasher safe and will not absorb water or odours. You can put it in the "
                "machine without thinking about it."
            ),
            gettext_noop(
                "The thing that will actually damage a piece is thermal shock -- a hot bowl "
                "into cold water, or a cold plate into a hot oven. Glaze and clay expand at "
                "slightly different rates, and a sharp change can craze the surface or, "
                "occasionally, crack the piece outright. Let things cool first."
            ),
            gettext_noop(
                "Unglazed feet will pick up marks from the table over time. That is normal "
                "and, in our view, an improvement. If it bothers you, a light rub with a "
                "damp cloth and a little bicarbonate lifts most of it."
            ),
            gettext_noop(
                "Fine crazing -- a web of hairline lines in the glaze -- is not a crack and "
                "does not affect whether a piece holds water. In a vitrified body it is "
                "cosmetic."
            ),
        ),
    },
    {
        "slug": "the-case-for-buying-less",
        "title": gettext_noop("The case for buying less"),
        "standfirst": gettext_noop(
            "We make about four hundred pieces a month. Here is why we have no "
            "plans to make four thousand."
        ),
        "category": gettext_noop("Studio"), "date": "30 June 2026",
        "read_time": gettext_noop("7 min"),
        "author": gettext_noop("Atelier Form"),
        "image": "journal-the-case-for-buying-less", "featured": True,
        "body": _t(
            gettext_noop(
                "Every year we are asked why we do not scale. The honest answer is that the "
                "thing people like about the work is a direct consequence of how little of "
                "it there is."
            ),
            gettext_noop(
                "A studio making four hundred pieces a month can afford to lose a firing. It "
                "can let a maker spend a season on a shape that may not sell. It can turn down "
                "the wholesale order that would have paid for a second kiln but required the "
                "glaze to be standardised first."
            ),
            gettext_noop(
                "None of that survives contact with volume. The pieces would still be "
                "competent. They would stop being specific."
            ),
            gettext_noop(
                "This has a cost, and we would rather be plain about it: some things sell out "
                "and do not come back for months, and made-to-order items really do take three "
                "weeks. We think that is the better trade."
            ),
        ),
    },
    {
        "slug": "a-table-set-for-nothing-in-particular",
        "title": gettext_noop("A table set for nothing in particular"),
        "standfirst": gettext_noop("Notes on using the good plates on a Tuesday."),
        "category": gettext_noop("Interiors"), "date": "6 June 2026",
        "read_time": gettext_noop("5 min"),
        "author": gettext_noop("Atelier Form"),
        "image": "journal-a-table-set-for-nothing-in-particular",
        "featured": False,
        "body": _t(
            gettext_noop(
                "There is a particular cupboard, in a lot of houses, where the good things "
                "live. They come out twice a year and spend the rest of their life being "
                "protected from the very thing they were made for."
            ),
            gettext_noop(
                "Handmade pieces are, counter-intuitively, better suited to daily use than to "
                "occasional display. They are not delicate. High-fired stoneware is tougher "
                "than most factory porcelain, and washed linen is at its best after fifty "
                "washes rather than five."
            ),
            gettext_noop(
                "The argument for using them is not really about the objects. It is that a "
                "weeknight dinner eaten off something someone made by hand is a different "
                "kind of evening, at no additional cost, on a day that had nothing else to "
                "recommend it."
            ),
            gettext_noop(
                "Our suggestion is unglamorous: take the good plates out of the high cupboard "
                "and put them where the everyday ones are. Within a month you will stop "
                "noticing, which is the point."
            ),
        ),
    },
]

ARTICLES_BY_SLUG: dict[str, Article] = {a["slug"]: a for a in ARTICLES}

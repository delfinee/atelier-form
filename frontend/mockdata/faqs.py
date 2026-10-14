"""FAQ content, grouped into the categories used by the /faq page."""

from __future__ import annotations

from typing import TypedDict

from django.utils.translation import gettext_noop


class FaqGroup(TypedDict):
    slug: str
    title: str
    blurb: str
    items: list[dict]    # {"q": str, "a": str}


FAQ_GROUPS: list[FaqGroup] = [
    {"slug": "orders", "title": gettext_noop("Orders"), "blurb": gettext_noop("Placing, changing and cancelling."),
     "items": [
        {"q": gettext_noop("Can I change or cancel my order?"),
         "a": gettext_noop("Yes, within 12 hours of placing it, as long as it has not been packed. Email "
              "the studio with your order number and we will sort it out. After 12 hours a "
              "made-to-order piece may already be in production.")},
        {"q": gettext_noop("I ordered several pieces. Will they arrive together?"),
         "a": gettext_noop("Not always. In-stock items ship immediately and made-to-order pieces follow "
              "when they are ready. You are only charged delivery once.")},
        {"q": gettext_noop("Do you take custom or commission requests?"),
         "a": gettext_noop("For some pieces, yes. Use the enquiry link on the product page and the maker "
              "will reply with what is possible and a quotation. Commissions typically take "
              "four to eight weeks.")},
        {"q": gettext_noop("Can I order a piece that is sold out?"),
         "a": gettext_noop("Sold-out pieces return when the maker next fires or weaves a batch. Add your "
              "email on the product page and you will hear when it does.")},
     ]},
    {"slug": "shipping", "title": gettext_noop("Shipping"), "blurb": gettext_noop("Timings, costs and tracking."),
     "items": [
        {"q": gettext_noop("How long does delivery take?"),
         "a": gettext_noop("In-stock orders are dispatched in 2–4 working days and arrive within a week "
              "domestically. Made-to-order pieces state their own lead time on the product page.")},
        {"q": gettext_noop("How much does delivery cost?"),
         "a": gettext_noop("Standard delivery is ¥8. It is complimentary on orders above ¥80. Express "
              "delivery is ¥18 and dispatches the next working day where stock allows.")},
        {"q": gettext_noop("Do you ship internationally?"),
         "a": gettext_noop("Yes, to most countries. Duties and import taxes are not included and are paid "
              "by the recipient on arrival.")},
        {"q": gettext_noop("How is fragile work packed?"),
         "a": gettext_noop("Ceramics are wrapped in recycled tissue and moulded pulp, inside a "
              "double-walled box. No plastic, no polystyrene.")},
     ]},
    {"slug": "returns", "title": gettext_noop("Returns"), "blurb": gettext_noop("Changing your mind, and breakages."),
     "items": [
        {"q": gettext_noop("What is your returns window?"),
         "a": gettext_noop("Thirty days from delivery, for unused pieces in their original packaging. "
              "Tell us before you send anything back so we can issue a return reference.")},
        {"q": gettext_noop("Something arrived broken."),
         "a": gettext_noop("Send a photograph within 48 hours of delivery and we will replace it or refund "
              "you in full. You do not need to return the damaged piece.")},
        {"q": gettext_noop("Can I return a made-to-order or commissioned piece?"),
         "a": gettext_noop("Only if it is faulty. These are made specifically for you, so we cannot resell "
              "them. The product page says clearly when this applies.")},
        {"q": gettext_noop("Who pays return postage?"),
         "a": gettext_noop("We do, if the piece is faulty or not what you ordered. For a change of mind, "
              "return postage is yours.")},
     ]},
    {"slug": "product-care", "title": gettext_noop("Product Care"), "blurb": gettext_noop("Keeping pieces well for years."),
     "items": [
        {"q": gettext_noop("Is your stoneware dishwasher safe?"),
         "a": gettext_noop("Yes. It is fired to full vitrification. Hand washing keeps a matte glaze "
              "looking its best for longer, but the machine will not harm it.")},
        {"q": gettext_noop("How should I wash linen?"),
         "a": gettext_noop("Cool machine wash on a gentle cycle, mild detergent, no fabric softener. Line "
              "dry in shade. It softens with every wash.")},
        {"q": gettext_noop("My candle is tunnelling."),
         "a": gettext_noop("Let the first burn run until the melt pool reaches the edge -- usually two to "
              "three hours. Wax has a memory, and the first burn sets it.")},
        {"q": gettext_noop("The brass has darkened."),
         "a": gettext_noop("It is unlacquered, so that is expected and reversible. A little lemon juice and "
              "bicarbonate returns the shine if you want it back.")},
     ]},
    {"slug": "handmade-variations", "title": gettext_noop("Handmade Variations"),
     "blurb": gettext_noop("What is a variation, and what is a fault."),
     "items": [
        {"q": gettext_noop("My piece does not look exactly like the photograph."),
         "a": gettext_noop("It will not. Glaze colour, speckle, and dye depth vary between firings and dye "
              "baths. We photograph a typical piece rather than the best one in a batch.")},
        {"q": gettext_noop("Are the dimensions exact?"),
         "a": gettext_noop("Within about 5%. Every piece is thrown or cut by hand, and clay shrinks by "
              "roughly a tenth in the firing.")},
        {"q": gettext_noop("There are fine lines in the glaze."),
         "a": gettext_noop("That is crazing, and on a vitrified body it is cosmetic. It does not affect "
              "strength or whether the piece holds water.")},
        {"q": gettext_noop("What actually counts as a fault?"),
         "a": gettext_noop("A chip, a crack through the body, a piece that does not sit flat, or a seam "
              "that has failed. Any of those, tell us and we will replace it.")},
     ]},
    {"slug": "gifting", "title": gettext_noop("Gifting"), "blurb": gettext_noop("Notes, wrapping and gift orders."),
     "items": [
        {"q": gettext_noop("Can you include a handwritten note?"),
         "a": gettext_noop("Yes. Add your message at checkout and it is written onto a card by hand, "
              "unsigned by us, and tucked into the parcel.")},
        {"q": gettext_noop("Will the recipient see the price?"),
         "a": gettext_noop("No. Parcels never contain an invoice. Pricing is emailed to you only.")},
        {"q": gettext_noop("Is gift wrapping extra?"),
         "a": gettext_noop("No. Everything is wrapped in unbleached paper and cotton string as standard. "
              "There is nothing extra to add.")},
        {"q": gettext_noop("Do you sell gift cards?"),
         "a": gettext_noop("Yes, in ¥50, ¥100 and ¥200. They are emailed to the recipient on a date you "
              "choose and do not expire.")},
     ]},
]

FAQ_GROUPS_BY_SLUG: dict[str, FaqGroup] = {group["slug"]: group for group in FAQ_GROUPS}

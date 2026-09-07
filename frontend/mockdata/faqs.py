"""FAQ content, grouped into the categories used by the /faq page."""

from __future__ import annotations

from typing import TypedDict


class FaqGroup(TypedDict):
    slug: str
    title: str
    blurb: str
    items: list[dict]    # {"q": str, "a": str}


FAQ_GROUPS: list[FaqGroup] = [
    {"slug": "orders", "title": "Orders", "blurb": "Placing, changing and cancelling.",
     "items": [
        {"q": "Can I change or cancel my order?",
         "a": "Yes, within 12 hours of placing it, as long as it has not been packed. Email "
              "the studio with your order number and we will sort it out. After 12 hours a "
              "made-to-order piece may already be in production."},
        {"q": "I ordered several pieces. Will they arrive together?",
         "a": "Not always. In-stock items ship immediately and made-to-order pieces follow "
              "when they are ready. You are only charged delivery once."},
        {"q": "Do you take custom or commission requests?",
         "a": "For some pieces, yes. Use the enquiry link on the product page and the maker "
              "will reply with what is possible and a quotation. Commissions typically take "
              "four to eight weeks."},
        {"q": "Can I order a piece that is sold out?",
         "a": "Sold-out pieces return when the maker next fires or weaves a batch. Add your "
              "email on the product page and you will hear when it does."},
     ]},
    {"slug": "shipping", "title": "Shipping", "blurb": "Timings, costs and tracking.",
     "items": [
        {"q": "How long does delivery take?",
         "a": "In-stock orders are dispatched in 2–4 working days and arrive within a week "
              "domestically. Made-to-order pieces state their own lead time on the product page."},
        {"q": "How much does delivery cost?",
         "a": "Standard delivery is ¥8. It is complimentary on orders above ¥80. Express "
              "delivery is ¥18 and dispatches the next working day where stock allows."},
        {"q": "Do you ship internationally?",
         "a": "Yes, to most countries. Duties and import taxes are not included and are paid "
              "by the recipient on arrival."},
        {"q": "How is fragile work packed?",
         "a": "Ceramics are wrapped in recycled tissue and moulded pulp, inside a "
              "double-walled box. No plastic, no polystyrene."},
     ]},
    {"slug": "returns", "title": "Returns", "blurb": "Changing your mind, and breakages.",
     "items": [
        {"q": "What is your returns window?",
         "a": "Thirty days from delivery, for unused pieces in their original packaging. "
              "Tell us before you send anything back so we can issue a return reference."},
        {"q": "Something arrived broken.",
         "a": "Send a photograph within 48 hours of delivery and we will replace it or refund "
              "you in full. You do not need to return the damaged piece."},
        {"q": "Can I return a made-to-order or commissioned piece?",
         "a": "Only if it is faulty. These are made specifically for you, so we cannot resell "
              "them. The product page says clearly when this applies."},
        {"q": "Who pays return postage?",
         "a": "We do, if the piece is faulty or not what you ordered. For a change of mind, "
              "return postage is yours."},
     ]},
    {"slug": "product-care", "title": "Product Care", "blurb": "Keeping pieces well for years.",
     "items": [
        {"q": "Is your stoneware dishwasher safe?",
         "a": "Yes. It is fired to full vitrification. Hand washing keeps a matte glaze "
              "looking its best for longer, but the machine will not harm it."},
        {"q": "How should I wash linen?",
         "a": "Cool machine wash on a gentle cycle, mild detergent, no fabric softener. Line "
              "dry in shade. It softens with every wash."},
        {"q": "My candle is tunnelling.",
         "a": "Let the first burn run until the melt pool reaches the edge -- usually two to "
              "three hours. Wax has a memory, and the first burn sets it."},
        {"q": "The brass has darkened.",
         "a": "It is unlacquered, so that is expected and reversible. A little lemon juice and "
              "bicarbonate returns the shine if you want it back."},
     ]},
    {"slug": "handmade-variations", "title": "Handmade Variations",
     "blurb": "What is a variation, and what is a fault.",
     "items": [
        {"q": "My piece does not look exactly like the photograph.",
         "a": "It will not. Glaze colour, speckle, and dye depth vary between firings and dye "
              "baths. We photograph a typical piece rather than the best one in a batch."},
        {"q": "Are the dimensions exact?",
         "a": "Within about 5%. Every piece is thrown or cut by hand, and clay shrinks by "
              "roughly a tenth in the firing."},
        {"q": "There are fine lines in the glaze.",
         "a": "That is crazing, and on a vitrified body it is cosmetic. It does not affect "
              "strength or whether the piece holds water."},
        {"q": "What actually counts as a fault?",
         "a": "A chip, a crack through the body, a piece that does not sit flat, or a seam "
              "that has failed. Any of those, tell us and we will replace it."},
     ]},
    {"slug": "gifting", "title": "Gifting", "blurb": "Notes, wrapping and gift orders.",
     "items": [
        {"q": "Can you include a handwritten note?",
         "a": "Yes. Add your message at checkout and it is written onto a card by hand, "
              "unsigned by us, and tucked into the parcel."},
        {"q": "Will the recipient see the price?",
         "a": "No. Parcels never contain an invoice. Pricing is emailed to you only."},
        {"q": "Is gift wrapping extra?",
         "a": "No. Everything is wrapped in unbleached paper and cotton string as standard. "
              "There is nothing extra to add."},
        {"q": "Do you sell gift cards?",
         "a": "Yes, in ¥50, ¥100 and ¥200. They are emailed to the recipient on a date you "
              "choose and do not expire."},
     ]},
]

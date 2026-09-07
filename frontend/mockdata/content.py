"""Site configuration and long-form editorial copy.

Anything a merchandiser would eventually edit in a CMS lives here rather than
being hard-coded into a template.
"""

from __future__ import annotations

# Lazy: this module is imported once at startup, but each string must be
# translated per request, in whichever language the visitor chose.
from django.utils.translation import gettext_lazy as _, pgettext_lazy

SITE = {
    "brand": "Atelier Form",
    "tagline": _("Handmade for everyday moments."),
    "description": _("Small-batch ceramics, textiles and homeware, made by hand by a "
                   "short list of makers we know by name."),
    "email": "studio@atelierform.example",
    "phone": "+86 21 5000 0000",
    "address": _("Unit 4, Lane 210 Taikang Road, Huangpu, Shanghai"),
    "hours": _("Studio visits by appointment · Tuesday to Saturday, 10am–6pm"),
    "currency_symbol": "$",          # single point of change for RMB later
    "free_shipping_threshold": 80,
    "shipping_standard": 8,
    "shipping_express": 18,
    "announcement": _("Complimentary delivery on orders above ¥80"),
    "instagram": "https://instagram.com",
    "pinterest": "https://pinterest.com",
}

PRIMARY_NAV = [
    {"label": _("Shop"), "url_name": "shop"},
    {"label": _("Collections"), "url_name": "collections"},
    {"label": _("Our Story"), "url_name": "our_story"},
    {"label": _("Journal"), "url_name": "journal"},
]

FOOTER_NAV = [
    {"title": _("Shop"), "links": [
        {"label": _("New Arrivals"), "href": "/shop/?sort=newest"},
        {"label": _("Ceramics"), "href": "/collections/ceramics/"},
        {"label": _("Textiles"), "href": "/collections/textiles/"},
        # "Home" here is the homeware category, not the homepage, and Chinese
        # renders the two differently -- so it needs its own context.
        {"label": pgettext_lazy("category", "Home"), "href": "/collections/home/"},
        {"label": _("Gifts"), "href": "/collections/gifts/"},
    ]},
    {"title": _("About"), "links": [
        {"label": _("Our Story"), "href": "/our-story/"},
        {"label": _("Makers"), "href": "/makers/"},
        {"label": _("Materials"), "href": "/our-story/#materials"},
        {"label": _("Journal"), "href": "/journal/"},
    ]},
    {"title": _("Help"), "links": [
        {"label": _("Shipping"), "href": "/shipping-returns/#shipping"},
        {"label": _("Returns"), "href": "/shipping-returns/#returns"},
        {"label": _("Care Guide"), "href": "/care/"},
        {"label": _("Contact"), "href": "/contact/"},
        {"label": _("FAQ"), "href": "/faq/"},
        {"label": _("Image Credits"), "href": "/credits/"},
    ]},
]

PROCESS_STEPS = [
    {"number": "01", "title": _("Designed"),
     "text": _("Each piece begins with an idea, a sketch or -- more often -- a material that "
             "turned up and suggested something. Nothing goes into production until the maker "
             "has lived with a sample for a season."),
     "image": "process-designed"},
    {"number": "02", "title": _("Crafted"),
     "text": _("Made individually, on a wheel, a loom or a bench. A mug takes about forty "
             "minutes to throw and trim; a throw takes the better part of three days on the "
             "loom. There is no version of this that is faster."),
     "image": "process-crafted"},
    {"number": "03", "title": _("Finished"),
     "text": _("Checked by hand, wrapped in unbleached paper, and packed with a card naming the "
             "person who made it. Anything that does not pass goes back to the studio shelf, "
             "not into a box."),
     "image": "process-finished"},
]

STORY_PAGE = {
    "eyebrow": _("Our story"),
    "title": _("Made by hand, meant to be kept."),
    "standfirst": _("Atelier Form began in 2019 with one kiln, one loom and a stubborn "
                  "conviction that the objects people use every day deserve more attention "
                  "than they usually get."),
    "sections": [
        {"id": "beginning", "heading": _("How it started"),
         "paragraphs": [
             _("We started by buying a single firing from a ceramicist in Jingdezhen who was "
             "about to close her studio because wholesale prices had fallen below what the "
             "clay cost her. That firing sold out in nine days. She is still with us, and "
             "she now works with two apprentices."),
             _("That set the shape of everything since. We do not commission from factories or "
             "buy from agents. We work with five makers, we know what each of them can "
             "produce in a month, and we build the range around that rather than the other "
             "way round."),
         ], "image": "story-materials", "layout": "text-left"},
        {"id": "materials", "heading": _("The materials we use"),
         "paragraphs": [
             _("Stoneware and porcelain from clay quarried within an hour of the studio that "
             "throws it. Flax linen from a single European mill. Cotton spun in Yunnan and "
             "dyed with indigo grown in the same valley. Timber reclaimed from Huizhou houses "
             "under restoration."),
             _("The list is short on purpose. A short list means we can actually answer the "
             "question of where something came from, and it means the range holds together "
             "tonally without anyone having to art-direct it."),
         ], "image": "story-hands", "layout": "text-right"},
        {"id": "small-batch", "heading": _("Why small batches"),
         "paragraphs": [
             _("We make roughly four hundred pieces a month across every category. That number "
             "has not changed much in three years, and we are not trying to change it."),
             _("Volume would mean standardising the glazes, mechanising the finishing, and "
             "moving to a schedule the makers do not set. The pieces would survive that. The "
             "reason people like them would not."),
             _("The trade-off is real and we would rather state it plainly: things sell out, "
             "restocks take weeks, and made-to-order means made to order."),
         ], "image": "story-interior", "layout": "text-left"},
    ],
    "stats": [
        {"value": "5", "label": _("makers, all known by name")},
        {"value": "400", "label": _("pieces made each month")},
        {"value": "2019", "label": _("the year of the first firing")},
        {"value": "0", "label": _("pieces made in a factory")},
    ],
}

SHIPPING_PAGE = {
    "title": _("Shipping & Returns"),
    "standfirst": _("Everything is packed by hand in the studio. Here is exactly what that "
                  "means for timings, costs and sending something back."),
    "sections": [
        {"id": "shipping", "heading": _("Shipping"), "body": [
            _("In-stock orders are dispatched within 2–4 working days. Made-to-order pieces "
            "carry their own lead time, stated clearly on the product page before you buy."),
            _("Standard delivery is ¥8 and takes 3–6 working days domestically. It is "
            "complimentary on orders above ¥80. Express delivery is ¥18 and dispatches the "
            "next working day where stock allows."),
            _("International delivery is available to most countries at cost, calculated at "
            "checkout. Duties and import taxes are not included and are payable by the "
            "recipient on arrival."),
            _("If an order contains both in-stock and made-to-order pieces, we ship them "
            "separately as they are ready and charge delivery only once."),
        ]},
        {"id": "packaging", "heading": _("Packaging"), "body": [
            _("Ceramics travel wrapped in recycled tissue inside moulded pulp, in a "
            "double-walled box. We do not use plastic film, bubble wrap or polystyrene "
            "anywhere in the studio."),
            _("Textiles are folded, wrapped in unbleached paper and tied with cotton string. "
            "The wrapping is the gift wrapping -- there is no upgrade to buy."),
        ]},
        {"id": "returns", "heading": _("Returns"), "body": [
            _("You have thirty days from delivery to return an unused piece in its original "
            "packaging. Email the studio first and we will send you a return reference."),
            _("Refunds are issued to the original payment method within five working days of "
            "the parcel reaching us. Return postage is ours if the piece is faulty or not "
            "what you ordered, and yours for a change of mind."),
            _("Made-to-order and commissioned pieces can only be returned if faulty, since they "
            "were made specifically for you. This is stated on the product page."),
        ]},
        {"id": "damage", "heading": _("If something arrives broken"), "body": [
            _("Send a photograph within 48 hours and we will replace the piece or refund you in "
            "full, whichever you prefer. You do not need to send the damaged piece back."),
            _("This happens on roughly one order in two hundred. We would rather you told us "
            "than lived with it."),
        ]},
    ],
}

CARE_PAGE = {
    "title": _("Care Guide"),
    "standfirst": _("Handmade pieces are more robust than most people expect. Nearly all of "
                  "what shortens their life is heat, sunlight or impatience."),
    "sections": [
        {"id": "ceramics", "heading": _("Ceramics"),
         "intro": _("High-fired stoneware and porcelain, fully vitrified."),
         "points": [
             _("Dishwasher safe. Hand washing keeps a matte glaze looking newer for longer, "
             "but the machine will not damage the piece."),
             _("Avoid thermal shock. Let a hot piece cool before rinsing, and never move a "
             "cold piece straight into a hot oven."),
             _("Not suitable for direct flame or the microwave if the piece has any metallic "
             "detail. None of ours currently do."),
             _("Unglazed feet may mark the table over time. A damp cloth with a little "
             "bicarbonate lifts most marks."),
             _("Fine crazing in the glaze is cosmetic on a vitrified body and does not affect "
             "strength or water-tightness."),
         ]},
        {"id": "textiles", "heading": _("Textiles"),
         "intro": _("Washed linen and handwoven, naturally dyed cotton."),
         "points": [
             _("Cool machine wash, gentle cycle, mild detergent. No fabric softener -- it coats "
             "the fibre and stops linen softening naturally."),
             _("Line dry in shade. Direct sun will lift natural indigo faster than anything "
             "else you can do to it."),
             _("Wash naturally dyed pieces separately for the first two or three washes."),
             _("Warm iron while slightly damp if you want a crisper finish. Most pieces are "
             "designed to be left alone."),
             _("Linen strengthens when wet, so it handles washing better than it looks like it "
             "should. It genuinely improves for the first fifty washes."),
         ]},
        {"id": "candles", "heading": _("Candles"),
         "intro": _("Soy and rapeseed wax, cotton wick."),
         "points": [
             _("Let the first burn run two to three hours, until the melt pool reaches the "
             "edge. Wax has a memory and the first burn sets the pattern."),
             _("Trim the wick to about 5 mm before every burn. This is the single thing that "
             "most affects how cleanly a candle burns."),
             _("Never burn for more than four hours at a time, and never leave one unattended."),
             _("Stop burning when about 10 mm of wax remains, then wash the vessel in warm "
             "water and keep it."),
         ]},
        {"id": "wood-brass", "heading": _("Wood & brass"),
         "intro": _("Reclaimed hardwood, oak and unlacquered brass."),
         "points": [
             _("Hand wash wood in warm water and dry immediately. Never put a board in the "
             "dishwasher or leave it soaking."),
             _("Re-oil with food-safe linseed or mineral oil two or three times a year, or "
             "whenever the surface looks dry."),
             _("Unlacquered brass darkens with handling. That is the intended finish."),
             _("If you want the shine back, lemon juice and bicarbonate will do it in a minute. "
             "It will darken again, which is fine."),
         ]},
    ],
}

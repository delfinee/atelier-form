"""Reviewed display copy for the verified non-seeded tote; no database writes."""
from django.utils.translation import gettext_noop

TOTE_UUID = 'bfa51b16-2aa1-4546-ae1a-5d84134f89c9'
TOTE_SLUG = 'curtain-tote-bag'
TOTE_COPY = {
    'name': gettext_noop('Curtain Tote Bag'),
    'short_description': gettext_noop('Curtain Tote Bag by Chen Meilin'),
    'description': gettext_noop('Using recycled materials from extra curtains to make a tote bag, customisation is allowed and please chat with me to tell me your ideas, thank you.'),
    'story': gettext_noop('Making customised tote bag for 7 years ,using curtain material which my mom has passed down to me as she no longer can do the work.'),
    'care_instructions': gettext_noop('Washing Machine Proof'),
    'shipping_information': gettext_noop('2-3 days'),
}


def approved_copy(product):
    if (str(getattr(product, 'uuid', '')) == TOTE_UUID and product.slug == TOTE_SLUG
            and product.maker.slug == 'chen-meilin'):
        return TOTE_COPY
    return {}

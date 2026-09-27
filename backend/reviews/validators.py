"""Text rules shared by storefront forms and review API fields."""

import unicodedata

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def validate_review_text(value, *, multiline=False):
    # Validate raw input: strip() would otherwise hide some controls.
    allowed = "\t\r\n" if multiline else ""
    if any(unicodedata.category(char) in {"Cc", "Cs"} and char not in allowed
           for char in value):
        raise ValidationError(
            _("Remove invalid control characters from this field."), code="invalid_characters",
        )

"""Validation and accessible widgets for storefront review submission."""

import unicodedata

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class ReviewTextField(forms.CharField):
    def __init__(self, *args, multiline=False, **kwargs):
        self.multiline = multiline
        super().__init__(*args, strip=False, **kwargs)

    def to_python(self, value):
        value = super().to_python(value)
        # Check before trimming: strip() would otherwise hide some controls.
        allowed = "\t\r\n" if self.multiline else ""
        if any(unicodedata.category(char) in {"Cc", "Cs"} and char not in allowed
               for char in value):
            raise ValidationError(
                _("Remove invalid control characters from this field."), code="invalid_characters",
            )
        return value.strip()


class ReviewForm(forms.Form):
    rating = forms.TypedChoiceField(
        coerce=int,
        choices=[("", _("Choose")), ("5", _("5 — Excellent")), ("4", _("4 — Good")),
                 ("3", _("3 — Fair")), ("2", _("2 — Poor")), ("1", _("1 — Very poor"))],
        error_messages={"required": _("Choose a rating from 1 to 5."),
                        "invalid_choice": _("Choose a rating from 1 to 5.")},
        widget=forms.Select(attrs={"id": "review-rating", "class": "select"}),
    )
    title = ReviewTextField(
        required=False, max_length=160,
        widget=forms.TextInput(attrs={"id": "review-title", "class": "input"}),
    )
    body = ReviewTextField(
        required=False, multiline=True,
        widget=forms.Textarea(attrs={"id": "review-body", "class": "textarea", "rows": 4}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.is_bound:
            rating = self.fields["rating"]
            submitted = self["rating"].value()
            if submitted and not rating.valid_value(submitted):
                # Preserve a forged/invalid selection without making it valid.
                rating.widget.choices = [*rating.choices, (submitted, submitted)]
            for name in self.errors:
                widget = self.fields[name].widget
                widget.attrs.update({"aria-invalid": "true",
                                     "aria-describedby": f"{widget.attrs['id']}-errors"})

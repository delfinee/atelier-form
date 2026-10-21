"""Forms for buyer return requests and seller return decisions.

Validation of the business rules lives in orders.returns; these forms only
check input shape, and the views turn a rule rejected there into a form error.
"""

from decimal import Decimal

from django import forms
from django.core.validators import MaxValueValidator
from django.utils.translation import gettext_lazy as _

from orders.models import ReturnReason

from .forms_seller import clean_photo_upload


class ReturnRequestForm(forms.Form):
    reason = forms.ChoiceField(label=_("What is wrong?"), choices=ReturnReason.choices,
                               widget=forms.RadioSelect)
    quantity = forms.IntegerField(label=_("How many?"), min_value=1)
    details = forms.CharField(label=_("Tell the maker more"), required=False, max_length=2000,
                              widget=forms.Textarea(attrs={"class": "input", "rows": 4}))
    photo = forms.ImageField(label=_("Photograph"), required=False,
                             help_text=_("Required if the piece arrived damaged. JPEG, PNG or WebP, up to 5 MB."),
                             widget=forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}))

    def __init__(self, *args, max_quantity: int = 1, **kwargs):
        super().__init__(*args, **kwargs)
        # max_value set after construction does not add a validator by itself.
        self.fields["quantity"].validators.append(MaxValueValidator(max_quantity))
        self.fields["quantity"].initial = 1
        self.fields["quantity"].widget.attrs.update({"class": "input", "min": 1, "max": max_quantity})
        self.photo_data = None

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if photo:
            self.photo_data = clean_photo_upload(photo)
        return photo


class ReturnDecisionForm(forms.Form):
    action = forms.ChoiceField(choices=[("approve", _("Approve — buyer sends it back")),
                                        ("refund", _("Refund")),
                                        ("replace", _("Send a replacement")),
                                        ("reject", _("Reject"))],
                               widget=forms.RadioSelect)
    seller_note = forms.CharField(label=_("Note to the buyer"), required=False, max_length=2000,
                                  widget=forms.Textarea(attrs={"class": "input", "rows": 3}))
    refund_amount = forms.DecimalField(label=_("Refund amount"), required=False,
                                       min_value=Decimal("0.01"), max_digits=10, decimal_places=2,
                                       widget=forms.NumberInput(attrs={"class": "input", "step": "0.01"}))

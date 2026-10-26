"""Seller onboarding forms: the public application, and the reviewer's rejection reason.

Only the applicant's own shop details are application fields. Status, reviewer
fields, the linked Maker and the owning user are never form fields: the view
sets the user, and accounts.seller_onboarding is the only code that decides.
"""
from django import forms
from django.utils.translation import gettext_lazy as _

from accounts.models import SellerApplication
from accounts.seller_onboarding import REVIEW_NOTE_MAX_LENGTH


class SellerApplicationForm(forms.ModelForm):
    class Meta:
        model = SellerApplication
        fields = ["shop_name", "discipline", "location", "description"]
        labels = {
            "shop_name": _("Shop name"),
            "discipline": _("What you make"),
            "location": _("Where you work"),
            "description": _("About your work"),
        }
        widgets = {
            "shop_name": forms.TextInput(attrs={"class": "input", "autocomplete": "organization"}),
            "discipline": forms.TextInput(attrs={"class": "input",
                                                 "placeholder": _("e.g. Ceramics, weaving")}),
            "location": forms.TextInput(attrs={"class": "input", "placeholder": _("e.g. Jingdezhen")}),
            "description": forms.Textarea(attrs={"class": "textarea", "rows": 5}),
        }


class SellerRejectionForm(forms.Form):
    """An administrator's reason for rejecting an application.

    The applicant sees this text on their application page. The length limit
    is the service's own; reject_application validates the reason again.
    """
    reason = forms.CharField(
        label=_("Reason for the applicant"),
        max_length=REVIEW_NOTE_MAX_LENGTH,
        error_messages={"required": _("Please give a reason for the rejection.")},
        widget=forms.Textarea(attrs={"class": "textarea", "rows": 4}),
    )

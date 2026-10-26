"""The public seller application form.

Only the applicant's own shop details are fields. Status, reviewer fields,
the linked Maker and the owning user are never form fields: the view sets the
user, and accounts.seller_onboarding is the only code that decides.
"""
from django import forms
from django.utils.translation import gettext_lazy as _

from accounts.models import SellerApplication


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

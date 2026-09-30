"""Forms for seller product and catalogue management."""

from decimal import Decimal
from django import forms
from django.forms import inlineformset_factory
from django.utils.text import slugify

from products.models import Product, ProductImage, ProductVariant, VariantGroup


class SellerProductForm(forms.ModelForm):
    """Product creation and editing form for sellers."""

    class Meta:
        model = Product
        fields = [
            "name",
            "category",
            "price",
            "short_description",
            "description",
            "story",
            "dimensions",
            "care_instructions",
            "shipping_information",
            "stock_quantity",
            "is_made_to_order",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input", "placeholder": "e.g. Handcrafted Ceramic Mug"}),
            "category": forms.Select(attrs={"class": "select"}),
            "price": forms.NumberInput(attrs={"class": "input", "step": "0.01", "min": "0"}),
            "short_description": forms.TextInput(attrs={"class": "input", "placeholder": "One-line summary for shop cards"}),
            "description": forms.Textarea(attrs={"class": "input", "rows": 4, "placeholder": "Full product description"}),
            "story": forms.Textarea(attrs={"class": "input", "rows": 3, "placeholder": "Artisan craft story and inspiration"}),
            "dimensions": forms.TextInput(attrs={"class": "input", "placeholder": "e.g. 12cm × 8cm, 350ml"}),
            "care_instructions": forms.TextInput(attrs={"class": "input", "placeholder": "e.g. Dishwasher and microwave safe"}),
            "shipping_information": forms.TextInput(attrs={"class": "input", "placeholder": "e.g. Ships within 2-3 business days"}),
            "stock_quantity": forms.NumberInput(attrs={"class": "input", "min": "0"}),
            "is_made_to_order": forms.CheckboxInput(attrs={"class": "checkbox"}),
            "is_active": forms.CheckboxInput(attrs={"class": "checkbox"}),
        }

    def clean_price(self):
        price = self.cleaned_data.get("price")
        if price is not None and price < Decimal("0.00"):
            raise forms.ValidationError("Price cannot be negative.")
        return price

    def clean_stock_quantity(self):
        stock = self.cleaned_data.get("stock_quantity")
        if stock is not None and stock < 0:
            raise forms.ValidationError("Stock quantity cannot be negative.")
        return stock


class SellerProductVariantForm(forms.ModelForm):
    """Variant row in inline formset."""

    class Meta:
        model = ProductVariant
        fields = ["group", "label", "sku", "price_override", "stock_quantity", "is_active"]
        widgets = {
            "group": forms.Select(attrs={"class": "select"}),
            "label": forms.TextInput(attrs={"class": "input", "placeholder": "e.g. Oatmeal / Small"}),
            "sku": forms.TextInput(attrs={"class": "input", "placeholder": "Unique SKU code"}),
            "price_override": forms.NumberInput(attrs={"class": "input", "step": "0.01", "min": "0", "placeholder": "Leave empty to use base price"}),
            "stock_quantity": forms.NumberInput(attrs={"class": "input", "min": "0"}),
            "is_active": forms.CheckboxInput(attrs={"class": "checkbox"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        label = cleaned_data.get("label")
        sku = cleaned_data.get("sku")
        # If label is given but SKU is missing, generate a clean default SKU
        if label and not sku:
            cleaned_data["sku"] = f"SKU-{slugify(label).upper()}"
        return cleaned_data


SellerVariantFormSet = inlineformset_factory(
    Product,
    ProductVariant,
    form=SellerProductVariantForm,
    fields=["group", "label", "sku", "price_override", "stock_quantity", "is_active"],
    extra=1,
    can_delete=True,
)


class SellerProductImageForm(forms.ModelForm):
    """Product image row in inline formset."""

    class Meta:
        model = ProductImage
        fields = ["image", "alt_text", "sort_order", "is_primary"]
        widgets = {
            "image": forms.TextInput(attrs={"class": "input", "placeholder": "e.g. product-speckled-breakfast-bowl-1"}),
            "alt_text": forms.TextInput(attrs={"class": "input", "placeholder": "Descriptive image caption"}),
            "sort_order": forms.NumberInput(attrs={"class": "input", "min": "0"}),
            "is_primary": forms.CheckboxInput(attrs={"class": "checkbox"}),
        }


SellerImageFormSet = inlineformset_factory(
    Product,
    ProductImage,
    form=SellerProductImageForm,
    fields=["image", "alt_text", "sort_order", "is_primary"],
    extra=1,
    can_delete=True,
)

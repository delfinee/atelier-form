"""Forms for seller product and catalogue management."""

from decimal import Decimal
from io import BytesIO
from uuid import uuid4
from django import forms
from django.db import transaction
from django.forms import inlineformset_factory
from PIL import Image, ImageOps
from django.utils.translation import gettext as _
from frontend.catalogue_i18n import localize_collection

from products.models import Product, ProductImage, ProductVariant, VariantGroup


class LocalizedSellerForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        labels = {'name':'Name', 'category':'Category', 'price':'Price',
            'short_description':'Short description', 'description':'Description', 'story':'Story',
            'dimensions':'Dimensions', 'care_instructions':'Care instructions',
            'shipping_information':'Shipping information', 'stock_quantity':'Stock quantity',
            'is_made_to_order':'Made to order', 'is_active':'Is active', 'group':'Option group',
            'label':'Option name', 'sku':'SKU', 'price_override':'Option price',
            'alt_text':'Image description', 'sort_order':'Sort order', 'DELETE':'Delete'}
        for name, field in self.fields.items():
            field.label = _(labels.get(name, str(field.label or name)))
            if field.help_text:
                field.help_text = _(str(field.help_text))
            if field.widget.attrs.get('placeholder'):
                field.widget.attrs['placeholder'] = _(field.widget.attrs['placeholder'])
        if 'group' in self.fields:
            self.fields['group'].choices = [(key, _(str(label))) for key, label in self.fields['group'].choices]
        if 'category' in self.fields:
            self.fields['category'].label_from_instance = lambda item: localize_collection(item).name


class SellerProductForm(LocalizedSellerForm):
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
            raise forms.ValidationError(_("Price cannot be negative."))
        return price

    def clean_stock_quantity(self):
        stock = self.cleaned_data.get("stock_quantity")
        if stock is not None and stock < 0:
            raise forms.ValidationError(_("Stock quantity cannot be negative."))
        return stock


class SellerProductVariantForm(LocalizedSellerForm):
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



SellerVariantFormSet = inlineformset_factory(
    Product,
    ProductVariant,
    form=SellerProductVariantForm,
    fields=["group", "label", "sku", "price_override", "stock_quantity", "is_active"],
    extra=1,
    can_delete=True,
)


class SellerProductImageForm(LocalizedSellerForm):
    """Product image row in inline formset."""

    image = forms.CharField(required=False, label="Existing image reference (optional)")
    upload = forms.ImageField(required=False, label="Upload photo",
        help_text="JPEG, PNG or WebP, up to 5 MB and 20 megapixels.",
        widget=forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}))

    def clean_upload(self):
        upload = self.cleaned_data.get("upload")
        if not upload:
            return None
        if upload.size > 5 * 1024 * 1024:
            raise forms.ValidationError(_("Choose an image smaller than 5 MB."))
        try:
            upload.seek(0)
            with Image.open(upload) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"} or source.width * source.height > 20_000_000:
                    raise ValueError()
                photo = ImageOps.exif_transpose(source)
                photo.thumbnail((2048, 2048))
                rgba = photo.convert("RGBA")
                clean = Image.new("RGB", rgba.size, "white")
                clean.paste(rgba, mask=rgba.getchannel("A"))
                encoded = BytesIO()
                clean.save(encoded, format="JPEG", quality=88)
                self.photo_data = (encoded.getvalue(), clean.width, clean.height)
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            raise forms.ValidationError(_("Choose a valid JPEG, PNG or WebP under 20 megapixels.")) from exc
        return upload

    def clean(self):
        data = super().clean()
        if data.get("upload"):
            data["image"] = "seller-photo-" + uuid4().hex
        elif not data.get("image") and not data.get("DELETE"):
            self.add_error("upload", "Upload a photo or enter an existing image reference.")
        return data

    @transaction.atomic
    def save(self, commit=True):
        instance = super().save(commit=False)
        if commit:
            if self.cleaned_data.get("upload"):
                from imagery.models import SiteImage
                payload, width, height = self.photo_data
                SiteImage.objects.create(name=instance.image, data=payload, width=width,
                    height=height, content_type="image/jpeg", alt_text=instance.alt_text,
                    provider="seller-upload")
            instance.save()
        return instance

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

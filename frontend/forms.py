"""Validation for storefront account registration."""

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from accounts.models import User


class RegistrationForm(forms.Form):
    first_name = forms.CharField(max_length=User._meta.get_field("first_name").max_length)
    last_name = forms.CharField(max_length=User._meta.get_field("last_name").max_length)
    email = forms.EmailField(max_length=User._meta.get_field("email").max_length)
    password = forms.CharField(strip=False, widget=forms.PasswordInput)
    accepts_marketing = forms.BooleanField(required=False)

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email=email).exists():
            raise ValidationError("An account with this email already exists.", code="duplicate")
        return email

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        if password:
            candidate = User(**{
                field: cleaned.get(field, "")
                for field in ("first_name", "last_name", "email")
            })
            try:
                validate_password(password, user=candidate)
            except ValidationError as exc:
                self.add_error("password", exc)
        return cleaned

    def save(self):
        if not self.is_valid():
            raise ValueError("Cannot save an invalid registration form.")
        return User.objects.create_user(**self.cleaned_data)

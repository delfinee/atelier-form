"""Customer accounts, saved addresses and the wishlist.

Email is the login identifier -- there is no separate username, because the
frontend never asks for one.
"""

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.db.models import Q
from django.utils import timezone

from config.mixins import TimeStampedModel, UUIDModel


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)          # hashes with Argon2; never stored raw
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("is_admin", True)
        if extra.get("is_staff") is not True or extra.get("is_superuser") is not True:
            raise ValueError("A superuser must have is_staff and is_superuser set.")
        return self._create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin, UUIDModel, TimeStampedModel):
    email = models.EmailField(unique=True, db_index=True)
    first_name = models.CharField(max_length=80, blank=True)
    last_name = models.CharField(max_length=80, blank=True)
    phone = models.CharField(max_length=32, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False, help_text="Can sign in to the Django admin.")
    is_admin = models.BooleanField(default=False, help_text="Can use the protected /api/admin endpoints.")
    is_seller = models.BooleanField(default=False, help_text="Owns and manages an artisan frontend.")

    accepts_marketing = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        ordering = ["-date_joined"]

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        self.email = self.email.lower().strip()
        super().save(*args, **kwargs)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip() or self.email

    def get_full_name(self) -> str:
        return self.full_name

    def get_short_name(self) -> str:
        return self.first_name or self.email


class Address(UUIDModel, TimeStampedModel):
    """A saved delivery address. Orders snapshot these rather than referencing
    them, so editing an address never rewrites delivery history."""

    user = models.ForeignKey(User, related_name="addresses", on_delete=models.CASCADE)
    label = models.CharField(max_length=60, help_text="Home, studio, parents'…")

    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    address_line_1 = models.CharField(max_length=200)
    address_line_2 = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100)
    state_region = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=80, default="China")
    phone = models.CharField(max_length=32, blank=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_default", "label"]
        verbose_name_plural = "addresses"
        indexes = [models.Index(fields=["user", "is_default"])]
        constraints = [
            models.UniqueConstraint(
                fields=["user"], condition=models.Q(is_default=True),
                name="one_default_address_per_user",
            )
        ]

    def __str__(self):
        return f"{self.label} — {self.full_name}"

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    # -- template compatibility (the frontend was built against dicts) ----
    @property
    def name(self) -> str:
        return self.full_name

    @property
    def line1(self) -> str:
        return self.address_line_1

    @property
    def line2(self) -> str:
        return self.address_line_2

    @property
    def postcode(self) -> str:
        return self.postal_code

    def snapshot(self) -> dict:
        """Frozen copy stored on an order."""
        return {
            "label": self.label,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "address_line_1": self.address_line_1,
            "address_line_2": self.address_line_2,
            "city": self.city,
            "state_region": self.state_region,
            "postal_code": self.postal_code,
            "country": self.country,
            "phone": self.phone,
        }

    def save(self, *args, **kwargs):
        # A user's first address becomes their default automatically.
        if not self.pk and not Address.objects.filter(user=self.user).exists():
            self.is_default = True
        if self.is_default:
            Address.objects.filter(user=self.user, is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class WishlistItem(TimeStampedModel):
    user = models.ForeignKey(User, related_name="wishlist_items", on_delete=models.CASCADE)
    product = models.ForeignKey("products.Product", related_name="wishlisted_by", on_delete=models.CASCADE)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "product"], name="unique_wishlist_entry")
        ]
        indexes = [models.Index(fields=["user", "-created_at"])]

    def __str__(self):
        return f"{self.user.email} ♥ {self.product.name}"


class SellerApplication(UUIDModel, TimeStampedModel):
    """One moderated request per user to become a seller.

    Creating an application grants nothing. Its status, reviewer fields and
    `maker` are written only by the server-side approval service; the database
    checks below reject any combination that service could never produce.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    user = models.OneToOneField(User, related_name="seller_application", on_delete=models.CASCADE)
    shop_name = models.CharField(max_length=160)    # becomes Maker.name
    discipline = models.CharField(max_length=120)   # Maker.discipline is required
    location = models.CharField(max_length=120)     # Maker.location is required
    description = models.TextField(max_length=2000, blank=True)  # becomes Maker.short_bio
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING,
                              db_index=True)
    # SET_NULL keeps a decision on record if the reviewer's account is later deleted.
    reviewed_by = models.ForeignKey(User, related_name="+", null=True, blank=True,
                                    on_delete=models.SET_NULL)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(max_length=1000, blank=True)
    # PROTECT: a shop created by an approval cannot be deleted out from under it.
    maker = models.OneToOneField("products.Maker", related_name="seller_application",
                                 null=True, blank=True, on_delete=models.PROTECT)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                name="seller_application_status_valid",
                condition=Q(status__in=["pending", "approved", "rejected"]),
            ),
            models.CheckConstraint(
                name="seller_application_review_state_consistent",
                condition=(
                    Q(status="pending", reviewed_at__isnull=True, reviewed_by__isnull=True,
                      maker__isnull=True)
                    | Q(status="approved", reviewed_at__isnull=False, maker__isnull=False)
                    | Q(status="rejected", reviewed_at__isnull=False, maker__isnull=True)
                ),
            ),
            models.CheckConstraint(
                name="seller_application_required_text",
                condition=~Q(shop_name="") & ~Q(discipline="") & ~Q(location=""),
            ),
        ]

    def __str__(self):
        return f"{self.shop_name} ({self.get_status_display()}) — {self.user.email}"

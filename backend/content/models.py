"""Editorial and inbound-message content: journal, FAQs, newsletter, contact."""

from django.db import models
from django.db.models.functions import Now
from django.utils import timezone
from django.utils.text import slugify

from config.mixins import TimeStampedModel, UUIDModel


class ArticleQuerySet(models.QuerySet):
    def published(self):
        # `Now()` is evaluated by the database on every execution. A Python
        # `timezone.now()` here would be frozen at import time, hiding anything
        # published after the process started.
        return self.filter(is_published=True, published_at__lte=Now())


class Article(UUIDModel, TimeStampedModel):
    """A journal piece.

    `body` is a list of typed blocks -- {"type": "paragraph|heading|quote",
    "text": "..."} -- so the template renders structure rather than raw HTML,
    which keeps stored content out of reach of script injection.
    """

    slug = models.SlugField(max_length=180, unique=True, db_index=True)
    title = models.CharField(max_length=200)
    standfirst = models.TextField(blank=True, help_text="Short intro shown under the title.")
    category = models.CharField(max_length=60, blank=True)
    author = models.CharField(max_length=120, blank=True)
    cover_image = models.CharField(max_length=200, blank=True)
    read_time = models.CharField(max_length=20, blank=True)
    body = models.JSONField(default=list, blank=True)

    is_featured = models.BooleanField(default=False)
    is_published = models.BooleanField(default=True)
    published_at = models.DateTimeField(default=timezone.now, db_index=True)

    objects = ArticleQuerySet.as_manager()

    class Meta:
        ordering = ["-published_at"]
        indexes = [models.Index(fields=["is_published", "-published_at"])]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:180]
        super().save(*args, **kwargs)

    # -- frontend template compatibility ---------------------------------
    @property
    def excerpt(self) -> str:
        return self.standfirst

    @property
    def image(self) -> str:
        return self.cover_image

    @property
    def date(self) -> str:
        return self.published_at.strftime("%-d %B %Y")

    @property
    def featured(self) -> bool:
        return self.is_featured


class FAQGroup(TimeStampedModel):
    slug = models.SlugField(max_length=80, unique=True)
    title = models.CharField(max_length=120)
    blurb = models.CharField(max_length=240, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "title"]
        verbose_name = "FAQ group"

    def __str__(self):
        return self.title

    @property
    def items(self):
        return self.faqs.filter(is_active=True)


class FAQ(TimeStampedModel):
    group = models.ForeignKey(FAQGroup, related_name="faqs", on_delete=models.CASCADE)
    question = models.CharField(max_length=300)
    answer = models.TextField()
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "FAQ"
        verbose_name_plural = "FAQs"
        indexes = [models.Index(fields=["group", "sort_order"])]

    def __str__(self):
        return self.question

    # The template renders {{ item.q }} / {{ item.a }}.
    @property
    def q(self) -> str:
        return self.question

    @property
    def a(self) -> str:
        return self.answer


class NewsletterSubscriber(UUIDModel, TimeStampedModel):
    email = models.EmailField(unique=True, db_index=True)
    is_active = models.BooleanField(default=True)
    subscribed_at = models.DateTimeField(default=timezone.now)
    unsubscribed_at = models.DateTimeField(null=True, blank=True)
    source = models.CharField(max_length=60, blank=True, default="frontend")

    class Meta:
        ordering = ["-subscribed_at"]

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        self.email = self.email.lower().strip()
        super().save(*args, **kwargs)

    def resubscribe(self):
        self.is_active = True
        self.unsubscribed_at = None
        self.subscribed_at = timezone.now()
        self.save(update_fields=["is_active", "unsubscribed_at", "subscribed_at", "updated_at"])


class ContactStatus(models.TextChoices):
    NEW = "new", "New"
    IN_PROGRESS = "in_progress", "In progress"
    RESOLVED = "resolved", "Resolved"


class ContactMessage(UUIDModel, TimeStampedModel):
    name = models.CharField(max_length=120)
    email = models.EmailField()
    subject = models.CharField(max_length=200, blank=True)
    order_number = models.CharField(max_length=32, blank=True)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=ContactStatus.choices,
                              default=ContactStatus.NEW, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} — {self.subject or 'no subject'}"

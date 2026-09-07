"""Expire abandoned sandbox reservations and return their stock."""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from payments.models import Payment, PaymentProviderChoices, PaymentState
from payments.services import MockPaymentProvider


class Command(BaseCommand):
    help = "Cancel expired mock payments and restore reserved inventory exactly once."

    def add_arguments(self, parser):
        parser.add_argument("--minutes", type=int, default=settings.PAYMENT_RESERVATION_MINUTES)

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(minutes=max(1, options["minutes"]))
        payments = Payment.objects.filter(
            provider=PaymentProviderChoices.MOCK,
            state__in=[PaymentState.CREATED, PaymentState.REQUIRES_ACTION],
            created_at__lt=cutoff,
        )
        provider = MockPaymentProvider()
        expired = 0
        for payment in payments.iterator():
            result = provider.confirm(
                payment, succeed=False,
                failure_reason="Payment reservation expired before completion.",
            )
            if result.inventory_released_at:
                expired += 1
        self.stdout.write(self.style.SUCCESS(f"Expired {expired} payment reservation(s)."))

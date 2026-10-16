"""Populate an empty local catalogue without resetting existing project data."""
from django.conf import settings
from django.core.management import call_command, BaseCommand, CommandError
from products.models import Product


class Command(BaseCommand):
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('Local catalogue preparation is unavailable in production.')
        if Product.objects.exists():
            self.stdout.write('Existing catalogue retained.')
        else:
            call_command('seed', public_only=True)

"""Populate only the dedicated, explicitly synthetic group-test deployment."""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command, BaseCommand, CommandError
from products.models import Product
from reviews.models import Review


class Command(BaseCommand):
    def handle(self, *args, **options):
        if not getattr(settings, 'MARKETPLACE_PUBLIC_DEMO', False) or settings.DATABASES['default']['NAME'] != 'atelier_marketplace_demo':
            raise CommandError('This seed command requires the dedicated marketplace demo database.')
        if Product.objects.exists():
            self.stdout.write('Existing demo catalogue retained; no stock or orders reset.')
            return
        call_command('seed', public_only=True)
        user = get_user_model().objects.create_user(email='sample-reviewer@marketplace-demo.invalid',
            password=None, first_name='Sample reviewer', is_active=False)
        for slug, rating in [('hand-thrown-stoneware-mug',5),('tea-cup-set-of-two',4),('speckled-breakfast-bowl',5)]:
            product = Product.objects.filter(slug=slug).first()
            if product:
                Review.objects.create(product=product,user=user,rating=rating,title='Synthetic demonstration review',
                    body='Sample data for group acceptance testing, not a real customer purchase.')
        self.stdout.write('Created public sample catalogue and labelled sample reviews; no usable accounts.')

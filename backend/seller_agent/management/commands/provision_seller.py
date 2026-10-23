"""Operator-only creation of a new verified seller; never upgrades existing users."""
from pathlib import Path
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import transaction
from products.models import Maker


class Command(BaseCommand):
    help = 'Provision a new seller after operator verification. Existing accounts are never changed.'

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True)
        parser.add_argument('--shop', required=True)
        parser.add_argument('--password-file', type=Path, required=True)
        parser.add_argument('--review-fixtures', action='store_true', help='Create labelled synthetic review records in this new shop only.')

    @transaction.atomic
    def handle(self, *args, **options):
        email = options['email'].strip().lower()
        shop = options['shop'].strip()
        try:
            validate_email(email)
            password = options['password_file'].read_text(encoding='utf-8').strip()
            validate_password(password)
        except (ValidationError, OSError) as exc:
            raise CommandError('Use a valid email and a readable private password file with a strong password.') from exc
        if len(password) < 16 or password == 'demo-seller-2026':
            raise CommandError('Use a unique password of at least 16 characters.')
        if not 2 <= len(shop) <= 160:
            raise CommandError('Shop name must contain 2 to 160 characters.')
        if get_user_model().objects.filter(email__iexact=email).exists():
            raise CommandError('Account already exists. No password or privileges were changed.')
        user = get_user_model().objects.create_user(email=email, password=password, is_seller=True)
        maker = Maker.objects.create(owner=user, name=shop, slug='seller-' + uuid4().hex[:16])
        if options['review_fixtures']:
            from products.models import Category, Product
            from orders.models import Order, OrderItem, SellerFulfillment, OrderStatus, PaymentStatus
            category, _ = Category.objects.get_or_create(slug='ceramics', defaults={'name': 'Ceramics'})
            suffix = uuid4().hex[:12]
            product = Product.objects.create(maker=maker, category=category, name='REVIEW TEST - sample mug',
                slug='review-test-' + suffix, description='Synthetic review fixture. No real sale or delivery.',
                price='20.00', stock_quantity=7, is_active=False)
            order = Order.objects.create(order_number='REVIEW-TEST-' + suffix,
                status=OrderStatus.CONFIRMED, payment_status=PaymentStatus.PAID,
                customer_email='review-buyer@example.invalid', currency=product.currency,
                shipping_address_snapshot={'first_name':'REVIEW', 'last_name':'TEST',
                    'address_line_1':'TEST ONLY - DO NOT SHIP', 'city':'Test', 'country':'SG'})
            OrderItem.objects.create(order=order, product=product, maker=maker, product_slug=product.slug,
                product_name=product.name, maker_name=maker.name, unit_price=product.price,
                quantity=1, line_total=product.price)
            SellerFulfillment.objects.create(order=order, maker=maker)
            order.recalculate()
            self.stdout.write('New review shop created with labelled synthetic product and order. No real payment or courier call occurred.')
        else:
            self.stdout.write('New seller and shop created. No sample orders, payments or products were created.')

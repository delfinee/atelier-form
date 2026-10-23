"""Add clearly labelled, disposable acceptance records without resetting a shop."""
import json
from uuid import uuid4
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from products.models import Category, Maker, Product
from orders.models import Order, OrderItem, SellerFulfillment, OrderStatus, PaymentStatus


class Command(BaseCommand):
    help = 'Add demo-only seller, product and a simulated paid test order; never reset existing data.'

    def add_arguments(self, parser):
        parser.add_argument('--email', default='seller@atelierform.test')
        parser.add_argument('--new-run', action='store_true', help='Add another labelled product and order for a new test.')

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('Acceptance fixtures are restricted to local development settings.')
        email = options['email']
        if not email.endswith('@atelierform.test'):
            raise CommandError('Use a disposable @atelierform.test demo account.')
        user, created = get_user_model().objects.get_or_create(email=email,
            defaults={'is_seller': True, 'first_name': 'Demo', 'last_name': 'Seller'})
        if created:
            user.set_password('demo-seller-2026')
            user.save()
        if not user.is_seller or not user.is_active:
            raise CommandError('Existing account is not an active seller. No privileges were changed.')
        maker = Maker.objects.filter(owner=user).first()
        if maker is None:
            maker = Maker.objects.create(owner=user, slug='acceptance-shop-' + uuid4().hex[:10],
                name='Acceptance Demo Shop', discipline='Demo crafts', location='Singapore')
        if not maker.is_active:
            raise CommandError('Existing shop is inactive. No privileges were changed.')
        category, _ = Category.objects.get_or_create(slug='ceramics', defaults={'name': 'Ceramics'})
        suffix = uuid4().hex[:8] if options['new_run'] else str(maker.pk)
        slug = 'acceptance-test-mug-' + suffix
        product, _ = Product.objects.get_or_create(slug=slug, maker=maker, defaults={
            'name': 'Acceptance test mug ' + suffix, 'category': category,
            'description': 'Disposable seller acceptance record. No real sale or delivery.',
            'price': '20.00', 'stock_quantity': 7, 'is_active': False})
        order, order_created = Order.objects.get_or_create(order_number='DEMO-SELLER-' + suffix, defaults={
            'status': OrderStatus.CONFIRMED, 'payment_status': PaymentStatus.PAID,
            'customer_email': 'acceptance-buyer@atelierform.test', 'currency': product.currency,
            'shipping_address_snapshot': {'first_name': 'Demo', 'last_name': 'Buyer',
                'address_line_1': 'TEST ONLY - DO NOT SHIP', 'city': 'Singapore', 'country': 'SG'}})
        if order_created:
            OrderItem.objects.create(order=order, product=product, maker=maker, product_slug=product.slug,
                product_name=product.name, maker_name=maker.name, unit_price=product.price,
                quantity=1, line_total=product.price)
            SellerFulfillment.objects.create(order=order, maker=maker)
            order.recalculate()
        self.stdout.write(json.dumps({'email': email, 'account_created': created,
            'product': product.slug, 'order': str(order.uuid), 'order_number': order.order_number,
            'simulated_payment': True, 'existing_records_reset': False}))

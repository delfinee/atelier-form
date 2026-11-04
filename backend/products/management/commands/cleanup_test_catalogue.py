"""Explicit, transactional unpublishing; never called by migrations or builds."""
import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from products.models import Maker, Product
from products.publication import TEST_MAKER, TEST_PRODUCTS


class Command(BaseCommand):
    help = 'Audit exact confirmed test records (dry-run by default). Never deletes rows.'

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument('--apply', action='store_true')
        mode.add_argument('--dry-run', action='store_true')
        parser.add_argument('--confirmed-owner-id', type=int)
        parser.add_argument('--backup', help='New JSON file for original flags; required with --apply')

    @transaction.atomic
    def handle(self, *args, **options):
        products = []
        for uuid, slug, maker_slug in TEST_PRODUCTS:
            queryset = Product.objects.select_for_update() if options['apply'] else Product.objects.all()
            product = queryset.filter(uuid=uuid).first()
            if product is None:
                self.stdout.write(f'Not present: {uuid} / {slug}')
                continue
            if product.slug != slug or product.maker.slug != maker_slug:
                raise CommandError(f'Identity changed for {uuid}; review required.')
            products.append(product)
        makers = Maker.objects.select_for_update() if options['apply'] else Maker.objects.all()
        maker = makers.filter(uuid=TEST_MAKER[0]).first()
        owner = None
        if maker:
            if maker.slug != TEST_MAKER[1]:
                raise CommandError('Test maker identity changed; review required.')
            if maker.owner_id:
                users = get_user_model().objects
                if options['apply']:
                    users = users.select_for_update()
                owner = users.get(pk=maker.owner_id)
        report = {
            'products': [dict(id=p.pk, uuid=str(p.uuid), slug=p.slug,
                              maker_id=p.maker_id, maker_slug=p.maker.slug,
                              is_active=p.is_active, orders=p.order_items.count(),
                              reviews=p.reviews.count()) for p in products],
            'maker': None if not maker else dict(id=maker.pk, uuid=str(maker.uuid),
                slug=maker.slug, owner_id=maker.owner_id, is_active=maker.is_active,
                products=list(maker.products.values('id', 'slug', 'is_active')),
                orders=maker.order_items.count(), fulfillments=maker.seller_fulfillments.count()),
            'owner': None if not owner else dict(id=owner.pk, uuid=str(owner.uuid),
                is_seller=owner.is_seller, is_active=owner.is_active,
                is_staff=owner.is_staff, is_admin=owner.is_admin, is_superuser=owner.is_superuser,
                buyer_orders=owner.orders.count(), reviews=owner.reviews.count()),
        }
        self.stdout.write(json.dumps(report, indent=2))
        if not options['apply']:
            self.stdout.write('DRY RUN: no rows changed. Verify owner is dedicated to testing before applying.')
            return
        if not options['backup']:
            raise CommandError('--backup is required; no rows changed.')
        if maker:
            if not owner or options['confirmed_owner_id'] != owner.pk:
                raise CommandError('Confirm the audited dedicated test owner with --confirmed-owner-id.')
            if owner.is_staff or owner.is_admin or owner.is_superuser:
                raise CommandError('Privileged owner: manual review required.')
            if maker.products.exclude(pk__in=[p.pk for p in products]).exists():
                raise CommandError('Additional seller products require review; no rows changed.')
        # Exclusive create prevents overwriting an earlier rollback record.
        with Path(options['backup']).open('x', encoding='utf-8') as output:
            json.dump(report, output, indent=2)
        for product in products:
            product.is_active = False
            product.save(update_fields=['is_active', 'updated_at'])
        if maker:
            maker.is_active = False
            maker.save(update_fields=['is_active', 'updated_at'])
            owner.is_seller = False
            owner.save(update_fields=['is_seller', 'updated_at'])
        self.stdout.write('Applied. School Demo identity, accounts and historical rows retained.')

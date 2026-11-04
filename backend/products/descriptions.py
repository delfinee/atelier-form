"""Persistent bilingual descriptions, shared by storefronts and seller channels."""
from copy import copy
import hashlib

from django.core.cache import cache
from django.db import DatabaseError, transaction
from django.utils.translation import gettext, override

from frontend.mockdata.products import PRODUCTS_BY_SLUG
from .models import Product, ProductTextTranslation
from .names import _language, warm_product_names

FIELDS = ('description', 'short_description')


def warm_product_descriptions(products, language=None):
    from concierge.display import _needs_translation, _translate

    language = _language(language)
    chinese = language == 'zh-hans'
    products = [copy(p) for p in products]
    pending = []
    for product in products:
        values = dict(getattr(product, '_display_description_cache', {}))
        preset = PRODUCTS_BY_SLUG.get(getattr(product, 'slug', ''))
        for field in FIELDS:
            if not hasattr(product, field):
                continue
            source = getattr(product, field) or ''
            key = (field, source, language)
            if key in values:
                continue
            with override(language):
                value = gettext(source) if source and preset and preset[field] == source else source
            if not _needs_translation(value, chinese) or getattr(getattr(product, '_state', None), 'adding', True):
                values[key] = value
            else:
                pending.append((product, field, source))
        product._display_description_cache = values
    if not pending:
        return products
    try:
        saved = {(r.product_id, r.field): r for r in ProductTextTranslation.objects.filter(
            product_id__in=[p.pk for p, _, _ in pending], field__in=FIELDS)}
    except DatabaseError:
        return products
    missing = {}
    for product, field, source in pending:
        row = saved.get((product.pk, field))
        value = getattr(row, 'chinese' if chinese else 'english', '') if row and row.source_text == source else ''
        if value and not _needs_translation(value, chinese):
            product._display_description_cache[(field, source, language)] = value
            continue
        digest = hashlib.sha256((language + '\0' + source).encode()).hexdigest()
        cache_key = 'product-description:v1:' + digest
        missing[source] = (cache_key, cache.get(cache_key))
    translated, batch, chars = {}, [], 0
    for source, (_, cached) in missing.items():
        if cached is not None:
            continue
        if batch and (chars + len(source) > 6000 or len(batch) >= 8):
            translated.update(_translate(batch, language, max_chars=20000, max_tokens=6000))
            batch, chars = [], 0
        batch.append(source)
        chars += len(source)
    if batch:
        translated.update(_translate(batch, language, max_chars=20000, max_tokens=6000))
    for product, field, source in pending:
        key = (field, source, language)
        if key in product._display_description_cache:
            continue
        cache_key, cached = missing[source]
        value = cached if cached is not None else translated.get(source, '')
        if not isinstance(value, str) or not value or _needs_translation(value, chinese):
            if cached is None:
                cache.set(cache_key, '', 60)
            product._display_description_cache[key] = source
            continue
        with transaction.atomic():
            current = Product.objects.select_for_update().only(field).filter(pk=product.pk).first()
            if current and getattr(current, field) == source:
                previous = ProductTextTranslation.objects.filter(product_id=product.pk, field=field, source_text=source).first()
                defaults = {'source_text': source,
                    'english': (previous.english if previous else '') if _needs_translation(source, False) else source,
                    'chinese': (previous.chinese if previous else '') if _needs_translation(source, True) else source}
                defaults['chinese' if chinese else 'english'] = value
                ProductTextTranslation.objects.update_or_create(product_id=product.pk, field=field, defaults=defaults)
        cache.set(cache_key, value, 604800)
        product._display_description_cache[key] = value
    return products


def localized_product_descriptions(product, language=None):
    language = _language(language)
    prepared = warm_product_descriptions([product], language)[0]
    values = getattr(prepared, '_display_description_cache', {})
    return {field: values.get((field, getattr(product, field, '') or '', language), getattr(product, field, '') or '')
            for field in FIELDS if hasattr(product, field)}


def warm_product_content(products, language=None):
    return warm_product_descriptions(warm_product_names(products, language), language)

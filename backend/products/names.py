"""Shared, persistent display names for seller and buyer surfaces."""
import hashlib
from copy import copy

from django.core.cache import cache
from django.db import DatabaseError, transaction
from django.utils.translation import get_language, gettext, override

from frontend.mockdata.products import PRODUCTS_BY_SLUG
from .models import Product, ProductNameTranslation


def _language(language=None):
    return 'zh-hans' if (language or get_language() or 'en').startswith('zh') else 'en'


def warm_product_names(products, language=None):
    """Translate missing names together, and reuse the same names on every channel."""
    from concierge.display import _needs_translation, _translate

    language = _language(language)
    chinese = language == 'zh-hans'
    products = [copy(product) if hasattr(product, 'name') else product for product in products]
    pending = []
    for product in products:
        if not hasattr(product, 'name') or not hasattr(product, 'slug'):
            continue
        source = product.name
        key = (source, language)
        names = dict(getattr(product, '_display_name_cache', {}))
        if key in names:
            continue
        preset = PRODUCTS_BY_SLUG.get(product.slug)
        with override(language):
            value = gettext(source) if preset and preset['name'] == source else source
        if not _needs_translation(value, chinese) or getattr(getattr(product, '_state', None), 'adding', True):
            names[key] = value
        else:
            pending.append(product)
        product._display_name_cache = names
    if not pending:
        return products
    try:
        saved = {row.product_id: row for row in ProductNameTranslation.objects.filter(
            product_id__in=[p.pk for p in pending])}
    except DatabaseError:
        return products
    missing = {}
    for product in pending:
        row = saved.get(product.pk)
        value = getattr(row, 'chinese' if chinese else 'english', '') if row and row.source_name == product.name else ''
        if value and not _needs_translation(value, chinese):
            product._display_name_cache[(product.name, language)] = value
            continue
        digest = hashlib.sha256((language + '\0' + product.name).encode()).hexdigest()
        cache_key = 'public-review-translation:v1:' + digest
        cached = cache.get(cache_key)
        missing[product.name] = (cache_key, cached)
    texts = [name for name, (_, cached) in missing.items() if cached is None][:32]
    translated = _translate(texts, language) if texts else {}
    for product in pending:
        key = (product.name, language)
        if key in product._display_name_cache:
            continue
        cache_key, cached = missing[product.name]
        value = cached if cached is not None else translated.get(product.name, '')
        if not isinstance(value, str) or not value or len(value) > 160 or _needs_translation(value, chinese):
            if cached is None:
                cache.set(cache_key, '', 60)
            product._display_name_cache[key] = product.name
            continue
        source = product.name
        # A concurrent rename must never acquire translations of the old name.
        with transaction.atomic():
            current = Product.objects.select_for_update().only('name').filter(pk=product.pk).first()
            if current and current.name == source:
                previous = ProductNameTranslation.objects.filter(product_id=product.pk, source_name=source).first()
                defaults = {'source_name': source,
                    'english': (previous.english if previous else '') if _needs_translation(source, False) else source,
                    'chinese': (previous.chinese if previous else '') if _needs_translation(source, True) else source}
                defaults['chinese' if chinese else 'english'] = value
                ProductNameTranslation.objects.update_or_create(product_id=product.pk, defaults=defaults)
        cache.set(cache_key, value, 604800)
        product._display_name_cache[key] = value
    return products


def localized_product_name(product, language=None):
    language = _language(language)
    prepared = warm_product_names([product], language)[0]
    return getattr(prepared, '_display_name_cache', {}).get((product.name, language), product.name)

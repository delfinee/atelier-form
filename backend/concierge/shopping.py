"""Buyer discovery over the existing catalogue. This module never writes commerce data.

The earlier customer assistant remains the optional model adapter; filtering,
prices, variants, review facts and links are always calculated here from Django.
"""
import re
from decimal import Decimal
from types import SimpleNamespace
from django.conf import settings
from django.db.models import Avg, Count, Q
from django.urls import reverse
from imagery.resolver import image_url
from products.models import Product
from . import assistant

TYPES = {
    'mug': ('mug', 'mugs', 'cup', 'cups', '杯'),
    'bowl': ('bowl', 'bowls', '碗'),
    'plate': ('plate', 'plates', 'dish', 'dishes', '盘', '碟'),
    'vase': ('vase', 'vases', '花瓶'),
    'candle': ('candle', 'candles', '蜡烛'),
    'linen': ('napkin', 'napkins', 'towel', 'towels', '餐巾', '毛巾'),
}
MATERIALS = {
    'ceramic': ('ceramic', 'ceramics', 'porcelain', 'stoneware', '陶瓷', '瓷', '陶'),
    'wood': ('wood', 'wooden', 'oak', '木'),
    'cotton': ('cotton', '棉'),
    'linen': ('linen', 'flax', '亚麻'),
    'brass': ('brass', '黄铜'),
}
COLOURS = {
    'blue': ('blue', 'indigo', 'sky', '蓝', '天青', '靛'), 'white': ('white', 'bone', '白'), 'black': ('black', '黑'),
    'green': ('green', '绿'), 'red': ('red', '红'), 'pink': ('pink', '粉'),
    'yellow': ('yellow', '黄'), 'brown': ('brown', '棕'),
}
STOP = set('i me my a an the want need find show some something please only ones one with without and or of for to in on within under below budget than less at most cheapest cheaper best good reviews reviewed rated rating compare difference differences between these them more two handmade hand made options available stock all products items pieces reset start over new search'.split())


def contains(text, word):
    return bool(re.search(r'\b' + re.escape(word) + r'\b', text)) if word.isascii() else word in text


def keys_in(text, mapping):
    return [key for key, words in mapping.items() if any(contains(text, w) for w in words)]


def plan(text, previous):
    lower = text.casefold()
    reset = any(s in lower for s in ('start over', 'reset', 'new search', '重新', '重来', '清空'))
    result = {} if reset else dict(previous or {})
    types = keys_in(lower, TYPES)
    materials = keys_in(lower, MATERIALS)
    colours = keys_in(lower, COLOURS)
    if types:
        # Naming a new item starts its own search, while colour/budget-only replies refine.
        if types != result.get('types') or re.search(r'^(?:find\b|i (?:want|need)\b|找|帮我找)', lower):
            result = {}
        result['types'] = types
        result.pop('keywords', None)
    if materials:
        result['materials'] = materials
    if colours:
        result['colours'] = colours
    result['language'] = 'zh' if re.search(r'[\u4e00-\u9fff]', text) else result.get('language', 'en')
    budget = re.search(r'(?:under|below|less than|at most|budget(?:\s+of)?|within|不超过|预算|低于)\s*(?:is\s*)?(?:CNY|SGD|USD|RMB|S\$|\$|¥|￥)?\s*(\d+(?:\.\d{1,2})?)', text, re.I)
    budget = budget or re.search(r'(\d+(?:\.\d{1,2})?)\s*(?:元|块)?\s*(?:以下|以内)', text)
    if budget:
        result['max_price'] = str(Decimal(budget[1]))
    if any(s in lower for s in ('no budget', 'any price', '不限价格', '不限预算')):
        result.pop('max_price', None)
    currency = re.search(r'\b(CNY|SGD|USD|RMB)\b', text, re.I)
    if currency:
        result['currency'] = 'CNY' if currency[1].upper() == 'RMB' else currency[1].upper()
    elif '￥' in text or '¥' in text or (budget and result['language'] == 'zh'):
        result['currency'] = 'CNY'
    elif budget and not result.get('currency'):
        result['currency'] = settings.CURRENCY
    if any(s in lower for s in ('cheapest', 'cheaper', 'lowest price', '最便宜', '便宜点', '价格最低')):
        result['sort'] = 'price'
    if any(s in lower for s in ('best reviewed', 'best rated', 'highest rated', '评价最好', '评分最高')):
        result['sort'] = 'rating'
        result['min_rating'] = 1
    elif any(s in lower for s in ('good reviews', 'well reviewed', 'highly rated', '好评', '评价好')):
        result['min_rating'] = 4
    if any(s in lower for s in ('any reviews', 'no review filter', '不限评价')):
        result.pop('min_rating', None)
    if any(s in lower for s in ('in stock', 'available now', '有货', '现货')):
        result['in_stock'] = True
    if not (types or materials or colours or budget or previous or reset or result.get('sort') or result.get('min_rating')):
        words = [w for w in re.findall(r'[a-z]{3,}|[\u4e00-\u9fff]{2,}', lower) if w not in STOP]
        if words:
            result['keywords'] = words[:6]
    result['more'] = any(s in lower for s in ('two more', 'show more', 'next', '再来', '更多', '另外'))
    result['compare'] = any(s in lower for s in ('compare', 'difference', '比较', '区别'))
    return result


def catalogue():
    return Product.objects.filter(is_active=True, maker__is_active=True, category__is_active=True).select_related(
        'maker', 'category').prefetch_related('product_variants', 'product_images').annotate(
        review_count=Count('reviews', filter=Q(reviews__is_published=True)),
        review_average=Avg('reviews__rating', filter=Q(reviews__is_published=True))).order_by('name', 'pk')


def card(product, filters):
    variants = list(product.product_variants.all())
    active = [v for v in variants if v.is_active]
    colour_keys = filters.get('colours', [])
    matching = [v for v in active if all(any(contains(v.label.casefold(), w) for w in COLOURS[c]) for c in colour_keys)]
    name_colour = all(any(contains(product.name.casefold(), w) for w in COLOURS[c]) for c in colour_keys)
    if colour_keys and not matching and not name_colour:
        return None
    options = matching if colour_keys and matching else active
    available = [v for v in options if product.is_made_to_order or v.stock_quantity > 0]
    # A product with options is never priced from an unrelated/unavailable parent row.
    chosen = available or options
    if variants and not chosen:
        return None
    price = min((v.unit_price for v in chosen), default=product.price)
    in_stock = bool(available) if variants else product.is_made_to_order or product.stock_quantity > 0
    if filters.get('in_stock') and not in_stock:
        return None
    if filters.get('currency') and product.currency != filters['currency']:
        return None
    if filters.get('max_price') and price > Decimal(filters['max_price']):
        return None
    count = product.review_count
    average = product.review_average
    if filters.get('min_rating') and (not count or average < filters['min_rating']):
        return None
    return {'slug': product.slug, 'name': product.name, 'price': str(price), 'currency': product.currency,
        'price_label': 'from' if len({v.unit_price for v in chosen}) > 1 else 'item',
        'available': in_stock, 'made_to_order': product.is_made_to_order,
        'quantity': None if product.is_made_to_order else sum(v.stock_quantity for v in options) if variants else product.stock_quantity,
        'rating': round(float(average), 2) if count else None, 'review_count': count,
        'maker': product.maker.name, 'materials': product.materials,
        'url': reverse('product_detail', kwargs={'slug': product.slug}),
        'image': image_url(product.primary_image()),
        'options': [{'id': str(v.uuid), 'label': v.label, 'price': str(v.unit_price), 'available': v.available} for v in options]}


def discover(text, previous=None, history=()):
    filters = plan(text, previous)
    zh = filters.get('language') == 'zh'
    if re.search(r'(?:set|update|delete|refund|ship)\s+(?:stock|price|order|product)|修改库存|修改价格|退款|发货', text, re.I):
        return {'reply': '卖家操作请使用卖家微信小程序。这里仅查询商品，不会修改库存或付款。' if zh else
                'Use the seller Mini Program for shop operations. This assistant only reads the catalogue; it cannot change stock or payments.',
                'products': [], 'context': previous or {}, 'engine': 'guided'}
    rows = []
    products = list(catalogue()[:1000])
    for p in products:
        blob = ' '.join([p.name, p.short_description, p.description, p.category.name, p.category.slug, *p.materials]).casefold()
        if not all(any(contains(blob, w) for w in TYPES[k]) for k in filters.get('types', [])):
            continue
        if not all(any(contains(blob, w) for w in MATERIALS[k]) for k in filters.get('materials', [])):
            continue
        if not all(contains(blob, w) for w in filters.get('keywords', [])):
            continue
        item = card(p, filters)
        if item:
            rows.append(item)
    engine = 'guided'
    if (getattr(settings, 'BUYER_AI_USE_LLM', False) and settings.DEEPSEEK_API_KEY
            and filters.get('keywords') and not rows):
        # Reuse the existing bounded assistant, then validate its IDs again against public rows.
        public_catalog = [{'product': p.slug, 'name': p.name, 'price': str(p.price), 'variants': []} for p in products[:100]]
        turns = [SimpleNamespace(text=t['text'], response=t['response']) for t in history[-6:]]
        suggestions = assistant.suggest(text, public_catalog, turns)
        selected = {line['product'] for line in suggestions.get('lines', [])}
        rows = [c for p in products if p.slug in selected and (c := card(p, filters))]
        engine = suggestions.get('engine', 'guided')
    if filters.get('compare') and previous and previous.get('shown'):
        rows = [row for row in rows if row['slug'] in previous['shown']]
    if filters.get('sort') == 'price':
        rows.sort(key=lambda p: (p['currency'], Decimal(p['price']), p['name']))
    elif filters.get('sort') == 'rating':
        rows.sort(key=lambda p: (-(p['rating'] or 0), -p['review_count'], p['name']))
    offset = previous.get('next_offset', 0) if filters.get('more') and previous else 0
    size = 2 if filters.get('more') else 4
    shown = rows[offset:offset + size]
    filters.update(shown=[p['slug'] for p in shown], next_offset=offset + len(shown))
    filters.pop('more', None)
    filters.pop('compare', None)
    if not rows:
        reply = ('没有同时满足这些条件的在售商品。可以放宽预算、颜色或评价条件；没有评价的商品不会被当作好评商品。' if zh else
                 'No active products match all these filters. Try relaxing the budget, colour or review filter. Products without reviews are not treated as well reviewed.')
    elif not shown:
        reply = '符合条件的商品已经展示完了。' if zh else 'You have seen all products matching these filters.'
    else:
        reply = ('以下价格、库存和评价均来自当前商品记录，点击商品可查看详情。' if zh else
                 'These prices, availability and review counts come from the current catalogue. Open a product for its full details.')
    basis = '按所选规格的商品单价比较，不含运费；不同币种分组展示，不进行汇率换算。' if zh else 'Item prices for the matching options, before delivery. Currencies are grouped separately; no exchange conversion.'
    return {'reply': reply, 'products': shown, 'total': len(rows), 'has_more': offset + len(shown) < len(rows),
            'context': filters, 'engine': engine, 'comparison_basis': basis}

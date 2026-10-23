"""Buyer discovery over the existing catalogue. This module never writes commerce data.

The buyer model interprets requests and writes conversational guidance; filtering,
prices, variants, review facts and links are always calculated here from Django.
"""
import re
from decimal import Decimal
from django.conf import settings
from django.db.models import Avg, Count, Q
from django.urls import reverse
from imagery.resolver import image_url
from products.models import Product
from . import buyer_ai

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


def model_facts(products):
    facts = []
    for product in products[:100]:
        item = card(product, {})
        if item:
            facts.append({'id': product.slug, 'name': product.name, 'category': product.category.name,
                'description': (product.short_description or product.description or '')[:400],
                'materials': product.materials, 'price': item['price'], 'currency': item['currency'],
                'available': item['available'], 'made_to_order': item['made_to_order'],
                'rating': item['rating'], 'review_count': item['review_count'],
                'options': [{'label': v['label'], 'price': v['price'], 'available': v['available']}
                            for v in item['options'][:20]]})
    return facts


def comparison_text(rows, details, zh):
    """All item-specific comparison claims are rendered from actual records."""
    lines = []
    for item in rows:
        facts = []
        if 'price' in details:
            facts.append(item['currency'] + ' ' + item['price'])
        if 'reviews' in details:
            facts.append((f"{item['rating']}/5 · {item['review_count']} " + ('条评价' if zh else 'published reviews'))
                         if item['review_count'] else ('暂无已发布评价' if zh else 'no published reviews'))
        if 'materials' in details:
            facts.append(' / '.join(item['materials']) or ('未提供材质' if zh else 'materials not specified'))
        if 'availability' in details:
            facts.append(('按单制作' if zh else 'made to order') if item['made_to_order'] else
                         ('有货' if zh else 'available') if item['available'] else ('缺货' if zh else 'unavailable'))
        if 'options' in details:
            facts.append(' / '.join(v['label'] for v in item['options']) or ('标准款' if zh else 'standard option'))
        lines.append(item['name'] + ': ' + '; '.join(facts))
    return '\n'.join(lines)


def discover(text, previous=None, history=()):
    filters = plan(text, previous)
    zh = filters.get('language') == 'zh'
    if re.search(r'(?:set|update|delete|refund|ship)\s+(?:stock|price|order|product)|修改库存|修改价格|退款|发货', text, re.I):
        return {'reply': '卖家操作请使用卖家微信小程序。这里仅查询商品，不会修改库存或付款。' if zh else
                'Use the seller Mini Program for shop operations. This assistant only reads the catalogue; it cannot change stock or payments.',
                'products': [], 'context': previous or {}, 'engine': 'guided'}
    products = list(catalogue()[:1000])
    model, problem = buyer_ai.interpret(text, previous, model_facts(products) if buyer_ai.enabled() else [],
        history, {'types': list(TYPES), 'materials': list(MATERIALS), 'colours': list(COLOURS)})
    engine, ai_reply, details = 'guided', '', []
    if model:
        engine, ai_reply, details = 'deepseek', model['reply'], model['details']
        if model['intent'] == 'unsupported':
            return {'reply': '我可以帮你挑选和比较商品，请在网站自行确认订单与付款；卖家操作请使用卖家小程序。' if zh else
                    'I can help you choose and compare products. Confirm checkout and payment yourself on the website; use the seller Mini Program for shop changes.',
                    'products': [], 'context': previous or {}, 'engine': engine}
        if model['intent'] in ('advice', 'clarify'):
            return {'reply': ai_reply or ('你想找什么商品？可以告诉我用途和预算。' if zh else
                    'What would you like to find? Tell me the occasion and your budget.'),
                    'products': [], 'context': previous or {}, 'engine': engine}
        filters = {**model['filters'], 'language': filters['language'], 'more': model['more'],
                   'compare': model['intent'] == 'compare'}
        if model['selection']:
            filters['selection'] = model['selection']
        if model['more'] and previous:
            filters = {**previous, 'more': True, 'compare': False, 'language': filters['language']}
        # A seller may edit stock/price while the provider is responding. Re-read
        # public rows so displayed facts and filters use the latest stored values.
        products = list(catalogue()[:1000])
    rows = []
    for p in products:
        blob = ' '.join([p.name, p.short_description, p.description, p.category.name, p.category.slug, *p.materials]).casefold()
        if not all(any(contains(blob, w) for w in TYPES[k]) for k in filters.get('types', [])):
            continue
        if not all(any(contains(blob, w) for w in MATERIALS[k]) for k in filters.get('materials', [])):
            continue
        if not all(contains(blob, w) for w in filters.get('keywords', [])):
            continue
        if filters.get('selection') and p.slug not in filters['selection']:
            continue
        item = card(p, filters)
        if item:
            rows.append(item)
    comparing = filters.get('compare')
    if comparing and not filters.get('selection') and previous and previous.get('shown'):
        rows = [row for row in rows if row['slug'] in previous['shown']]
    if filters.get('sort') == 'price':
        rows.sort(key=lambda p: (p['currency'], Decimal(p['price']), p['name']))
    elif filters.get('sort') == 'rating':
        rows.sort(key=lambda p: (-(p['rating'] or 0), -p['review_count'], p['name']))
    elif filters.get('selection'):
        positions = {slug: index for index, slug in enumerate(filters['selection'])}
        rows.sort(key=lambda p: positions[p['slug']])
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
        reply = ai_reply or ('以下价格、库存和评价均来自当前商品记录，点击商品可查看详情。' if zh else
                 'These prices, availability and review counts come from the current catalogue. Open a product for its full details.')
        if comparing:
            reply += '\n\n' + comparison_text(shown, details or ['price', 'reviews', 'materials'], zh)
    basis = '按所选规格的商品单价比较，不含运费；不同币种分组展示，不进行汇率换算。' if zh else 'Item prices for the matching options, before delivery. Currencies are grouped separately; no exchange conversion.'
    notice = ''
    if problem:
        notice = ('今日 AI 演示额度已用完，暂时使用目录匹配。' if problem == 'quota' else 'AI 暂时不可用，已切换为目录匹配。') if zh else (
            "Today's AI allowance is used up; using catalogue matching." if problem == 'quota' else 'AI is temporarily unavailable; using catalogue matching.')
    return {'reply': reply, 'products': shown, 'total': len(rows), 'has_more': offset + len(shown) < len(rows),
            'context': filters, 'engine': engine, 'comparison_basis': basis, 'notice': notice}

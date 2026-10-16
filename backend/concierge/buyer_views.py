"""Session-owned buyer chat. No seller identity or checkout authority is granted."""
import hashlib
import json
from uuid import UUID
from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST
from .shopping import discover


class DemoBoundaries:
    """The anonymous group demo cannot create accounts or link a real WeChat."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(('/api/auth/', '/api/admin/', '/account/register/', '/account/reset/',
            '/account/forgot-password/', '/api/seller-agent/', '/seller/ai/link/')):
            return reply({'detail':'Account and WeChat connection changes are not available in this synthetic website demo.'}, 403)
        response = self.get_response(request)
        response['X-Robots-Tag'] = 'noindex, nofollow'
        return response


class DemoLanguage:
    """Share an English group link, while retaining an explicit Chinese switch."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        language = request.GET.get('lang')
        explicit = language in ('en', 'zh-hans')
        if not explicit:
            language = request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME, 'en')
        request.COOKIES = {**request.COOKIES, settings.LANGUAGE_COOKIE_NAME: language}
        response = self.get_response(request)
        if explicit:
            response.set_cookie(settings.LANGUAGE_COOKIE_NAME, language, samesite='Lax', secure=request.is_secure())
        return response


def reply(data, status=200):
    response = JsonResponse(data, status=status)
    response['Cache-Control'] = 'private, no-store'
    response['X-Robots-Tag'] = 'noindex, nofollow'
    return response


@require_POST
@csrf_protect
def message(request):
    if not getattr(settings, 'BUYER_ASSISTANT_ENABLED', True):
        return reply({'detail': 'Shopping assistant is unavailable.'}, 404)
    if len(request.body) > 10000:
        return reply({'detail': 'Message is too large.'}, 400)
    try:
        body = json.loads(request.body)
        text = body['text'].strip()
        request_id = str(UUID(body['request_id']))
        if not isinstance(text, str) or not 1 <= len(text) <= 2000:
            raise ValueError()
    except (ValueError, TypeError, KeyError, AttributeError):
        return reply({'detail': 'Send a message of 1–2000 characters and a request UUID.'}, 400)
    state = request.session.get('buyer_assistant', {'history': [], 'context': {}, 'responses': {}})
    if request_id in state['responses']:
        return reply(state['responses'][request_id])
    address = request.META.get('REMOTE_ADDR', '')
    if getattr(settings, 'TRUST_PROXY_CLIENT_IP', False):
        address = request.META.get('HTTP_X_FORWARDED_FOR', address).split(',')[-1].strip()
    bucket = 'buyer-chat:' + hashlib.sha256(address.encode()).hexdigest()
    cache.add(bucket, 0, 60)
    try:
        count = cache.incr(bucket)
    except ValueError:
        cache.set(bucket, 1, 60)
        count = 1
    if count > 30:
        return reply({'detail': 'Please wait a minute before sending more messages.'}, 429)
    result = discover(text, state['context'], state['history'])
    state['context'] = result.pop('context')
    state['history'] = (state['history'] + [{'text': text, 'response': result}])[-6:]
    state['responses'][request_id] = result
    state['responses'] = dict(list(state['responses'].items())[-12:])
    request.session['buyer_assistant'] = state
    return reply(result)


@require_GET
def history(request):
    state = request.session.get('buyer_assistant', {})
    return reply({'messages': state.get('history', [])})


@require_POST
@csrf_protect
def reset(request):
    request.session.pop('buyer_assistant', None)
    return reply({'reset': True})


@require_GET
@ensure_csrf_cookie
def seller_mini_program(request):
    return render(request, 'seller_agent/mini_entry.html')

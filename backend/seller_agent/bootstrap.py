"""Temporary, single-use provider setup; removed after deployment acceptance."""
import hashlib
import json
import re
import secrets
import time
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import ProviderSecret
from .provider import encrypt_key

TOKEN_HASH = "13fe383a0da696c1cce7672ad9a23ea0f58e8ae2f45599fcc016deb005611744"
EXPIRES = 1793542424

@csrf_exempt
def configure(request):
    token = request.headers.get('Authorization', '').removeprefix('Bearer ')
    if (request.method != 'POST' or request.get_host() != 'dip-new-repo.vercel.app'
            or time.time() > EXPIRES or not secrets.compare_digest(
                hashlib.sha256(token.encode()).hexdigest(), TOKEN_HASH)):
        return HttpResponse(status=404)
    try:
        data = json.loads(request.body)
        key = data['api_key']
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,200}', key):
            return JsonResponse({'detail':'Invalid provider key.'}, status=400)
    except (ValueError, KeyError, TypeError):
        return JsonResponse({'detail':'Invalid provider configuration.'}, status=400)
    with transaction.atomic():
        item, created = ProviderSecret.objects.get_or_create(provider='deepseek',
            defaults={'encrypted_key':encrypt_key(key)})
    return JsonResponse({'configured': True, 'created': created}, status=201 if created else 200)

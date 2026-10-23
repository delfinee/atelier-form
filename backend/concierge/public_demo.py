"""Anonymous sessions with isolated seller identities for the public sandbox."""
from copy import copy
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import transaction
from django.http import HttpResponse
from products.models import Maker, Product

SESSION_ACTOR_KEY = "public_demo_actor"
VISITOR_PREFIX = "public-visitor-"


@transaction.atomic
def create_visitor():
    # This source row also serializes guest creation so the cap is enforceable.
    source = Maker.objects.select_for_update().get(owner__email=settings.PUBLIC_DEMO_SEED_EMAIL)
    User = get_user_model()
    if User.objects.filter(email__startswith=VISITOR_PREFIX).count() >= settings.PUBLIC_DEMO_MAX_VISITORS:
        return None
    identity = uuid4().hex
    user = User.objects.create_user(email=f"{VISITOR_PREFIX}{identity}@demo.invalid", password=None,
                                    first_name="Demo", is_seller=True)
    maker = Maker.objects.create(name="Team demo studio", slug=f"visitor-{identity}", owner=user,
                                 discipline=source.discipline, location="Demo")
    for original in Product.objects.filter(maker=source, is_active=True).prefetch_related("product_variants"):
        product = copy(original)
        product.pk = None
        product._state = copy(original._state)
        product._state.adding = True
        product.uuid = uuid4()
        product.slug = f"demo-{identity[:12]}-{original.slug}"[:180]
        product.maker = maker
        product.save(force_insert=True)
        for original_variant in original.product_variants.all():
            variant = copy(original_variant)
            variant.pk = None
            variant._state = copy(original_variant._state)
            variant._state.adding = True
            variant.uuid = uuid4()
            variant.sku = f"DEMO-{uuid4().hex}"
            variant.product = product
            variant.save(force_insert=True)
    return user


class PublicDemoVisitorMiddleware:
    """Only the dedicated public URL configuration installs this middleware.

    It never calls login() and never creates an admin or usable password. The
    server-side session selects a guest seller; clients cannot choose its ID.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not settings.PUBLIC_CONCIERGE_DEMO:
            return self.get_response(request)
        User = get_user_model()
        user = User.objects.filter(pk=request.session.get(SESSION_ACTOR_KEY),
            email__startswith=VISITOR_PREFIX, is_active=True, is_seller=True,
            is_staff=False, is_superuser=False).first()
        if user is None and request.method == "GET" and request.path in ("/seller/assistant/", "/seller/workbench/"):
            user = create_visitor()
            if user is None:
                return HttpResponse("This demo has reached its visitor limit. Please contact the demo owner.", status=503)
            request.session.cycle_key()
            request.session[SESSION_ACTOR_KEY] = user.pk
            request.session.set_expiry(86400)
        request.user = user if user is not None else AnonymousUser()
        response = self.get_response(request)
        response["Cache-Control"] = "private, no-store"
        response["Referrer-Policy"] = "no-referrer"
        return response

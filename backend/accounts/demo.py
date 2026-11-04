"""The explicitly public coursework seller account, never a real credential."""
from django.contrib.auth import get_user_model
from django.db import transaction

from products.models import Maker


DEMO_SELLER = {
    'email': 'seller@atelierform.test', 'password': 'demo-seller-2026',
    'first_name': 'chen', 'last_name': 'mei lin',
}
DEMO_SELLER_NAME = 'chen mei lin'
DEMO_SELLER_SHOP = 'chen-meilin'


def is_seller_app(request):
    # Presentation hint from the existing Windows client, not authentication.
    return 'AtelierSeller/' in request.META.get('HTTP_USER_AGENT', '')


def is_demo_seller(user):
    return bool(user.is_authenticated and user.email == DEMO_SELLER['email']
                and user.is_active and user.is_seller
                and not (user.is_staff or user.is_admin or user.is_superuser)
                and Maker.objects.filter(owner=user, slug=DEMO_SELLER_SHOP, is_active=True).exists())


def login_details(request):
    from seller_agent.shared_demo import enabled_for
    if not is_seller_app(request) or not enabled_for(request):
        return None
    user = get_user_model().objects.filter(email=DEMO_SELLER['email']).first()
    if user is None or not is_demo_seller(user) or not user.check_password(DEMO_SELLER['password']):
        return None
    return {**DEMO_SELLER, 'name': DEMO_SELLER_NAME}


@transaction.atomic
def sync_demo_seller_name():
    """Rename only the existing seeded seller and their shop; do not reset data or access."""
    user = get_user_model().objects.select_for_update().filter(email=DEMO_SELLER['email']).first()
    if user is None or not is_demo_seller(user):
        return False
    if (user.first_name, user.last_name) != (DEMO_SELLER['first_name'], DEMO_SELLER['last_name']):
        user.first_name = DEMO_SELLER['first_name']
        user.last_name = DEMO_SELLER['last_name']
        user.save(update_fields=['first_name', 'last_name', 'updated_at'])
    Maker.objects.filter(owner=user, slug=DEMO_SELLER_SHOP).exclude(name=DEMO_SELLER_NAME).update(name=DEMO_SELLER_NAME)
    return True

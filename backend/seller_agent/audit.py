"""Use the real session actor for writes in the shared school workspace."""
from django.contrib.auth import get_user_model
from django.db import transaction
from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext as _

from .models import SellerOperation


def operation_actor(user, *, lock=False):
    actor = getattr(user, '_seller_operation_user', user)
    users = get_user_model().objects.select_for_update() if lock else get_user_model().objects
    actor = users.filter(pk=actor.pk, is_active=True, is_seller=True).first()
    if actor is None:
        raise PermissionDenied(_('An active, verified seller account is required for this operation.'))
    return actor


@transaction.atomic
def record_operation(user, action, *, channel='web', product=None, order=None, change=None):
    actor = operation_actor(user, lock=True)
    return SellerOperation.objects.create(
        actor=actor, actor_name=actor.full_name, action=action, channel=channel,
        product=product, product_slug=product.slug if product else '',
        order=order, order_number=order.order_number if order else '', change=change,
    )


def operation_data(operation):
    if operation is None:
        return None
    return {'actor_name': operation.actor_name, 'action': operation.action,
            'at': operation.created_at.isoformat()}


def latest_operations(*, product_ids=None, order_ids=None):
    field, ids = ('product_id', product_ids) if product_ids is not None else ('order_id', order_ids)
    if not ids:
        return {}
    rows = SellerOperation.objects.filter(**{field + '__in': ids}).order_by(
        field, '-created_at', '-pk').distinct(field)
    return {getattr(row, field): operation_data(row) for row in rows}


def latest_operation(*, product=None, order=None):
    if product is not None and getattr(product, 'pk', None):
        row = SellerOperation.objects.filter(product_id=product.pk).first()
    elif order is not None and getattr(order, 'pk', None):
        row = SellerOperation.objects.filter(order_id=order.pk).first()
    else:
        row = None
    return operation_data(row)

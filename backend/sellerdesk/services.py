from datetime import timedelta
import secrets
from django.db import transaction
from django.utils import timezone
from concierge import services as commerce
from concierge.models import Conversation, OrderDraft
from .auth import digest
from .models import CustomerSession


def stage(draft):
    if not draft.order_id:
        return "expired" if draft.expires_at <= timezone.now() else "review"
    order = draft.order
    if order.status == "cancelled" or order.payment_status in ("failed", "refunded"):
        return "attention"
    if order.status in ("shipped", "delivered"):
        return "shipped"
    if order.payment_status != "paid":
        return "payment"
    if draft.packed_at:
        return "dispatch"
    return "packing"


def draft_data(draft):
    data = commerce.draft_data(draft)
    customer_actions = {a.action for a in draft.customer_actions.all()}
    for event in data["events"]:
        event["initiator"] = "customer" if event["action"] in customer_actions else "seller"
    return {**data, "stage": stage(draft),
            "conversation_id": str(draft.conversation.uuid),
            "customer_label": draft.conversation.customer_label,
            "created_at": draft.created_at.isoformat()}


def drafts(conversation):
    return conversation.drafts.select_related("order", "conversation").prefetch_related("events", "customer_actions").order_by("-id")


def conversation_data(conversation):
    messages = []
    for message in conversation.messages.all():
        messages.extend([
            {"id": f"c{message.id}", "role": "customer", "text": message.text,
             "at": message.created_at.isoformat()},
            {"id": f"a{message.id}", "role": "assistant", "text": message.response.get("reply", ""),
             "lines": message.response.get("lines", []), "engine": message.response.get("engine", ""),
             "at": message.created_at.isoformat()},
        ])
    messages.extend({"id": f"s{r.id}", "role": "seller", "text": r.text, "at": r.created_at.isoformat()}
                    for r in conversation.seller_replies.all())
    messages.sort(key=lambda m: m["at"])
    return {"id": str(conversation.uuid), "label": conversation.customer_label, "messages": messages,
            "drafts": [draft_data(d) for d in drafts(conversation)]}


@transaction.atomic
def invite(actor, label):
    commerce.require_demo()
    conversation = Conversation.objects.create(maker=actor.maker_profile, created_by=actor,
                                               customer_label=label)
    token = secrets.token_urlsafe(32)
    access = CustomerSession.objects.create(conversation=conversation, token_hash=digest(token),
                                            expires_at=timezone.now() + timedelta(hours=24))
    return {"conversation_id": str(conversation.uuid),
            "preview_url": "/customer/preview/#token=" + token,
            "expires_at": access.expires_at.isoformat()}


def seller_drafts(actor):
    return OrderDraft.objects.filter(conversation__maker__owner=actor).select_related(
        "order", "conversation").prefetch_related("events", "customer_actions").order_by("-id")

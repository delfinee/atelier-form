from django.db import transaction
from rest_framework.exceptions import ValidationError
from products.models import Category
from . import services, planner
from .models import Message

ONBOARDING = ("Use your website account to complete seller onboarding and shop verification. "
    "Linking WeChat never grants seller rights. I can help collect a listing draft now. "
    "Start with 'new listing', then provide name, category, description, price and quantity. "
    "Images, variants and publication are completed in the authenticated product editor.")
REQUIRED = ["name", "category", "description", "price", "quantity"]


def get_catalog(user):
    return services.products(user) if services.has_shop(user) else []


@transaction.atomic
def respond(user, conversation_id, request_id, text, channel, plan):
    conversation = services.conversation_for(user, conversation_id, lock=True)
    old = conversation.messages.filter(request_id=request_id).first()
    if old:
        return old.response
    intent = plan["intent"]
    result = {"intent":intent, "engine":plan.get("engine","guided")}
    if plan.get("notice"):
        result["notice"] = plan["notice"]
    if intent in ("products", "low_stock"):
        result["products"] = services.products(user, low_stock=intent=="low_stock")
        result["reply"] = "These are your shop's current product records." if result["products"] else "No matching products in your shop."
    elif intent == "orders":
        records = services.orders(user)
        if plan.get("pending"):
            records = [o for o in records if o["can_ship"]]
        result.update(reply="These orders contain only your shop's items and fulfillment details.", orders=records)
    elif intent == "onboarding":
        result["reply"] = ONBOARDING
    elif intent == "listing":
        if plan.get("expected_field") and plan["expected_field"] != conversation.context.get("awaiting"):
            raise ValidationError("This draft changed in another channel. Refresh it before continuing.")
        previous = {} if plan.get("reset") else conversation.context.get("listing", {})
        values = {**previous, **{k:v for k,v in plan.get("values", {}).items() if k in REQUIRED}}
        missing = [key for key in REQUIRED if not str(values.get(key, "")).strip()]
        conversation.context = {"listing":values, "awaiting":missing[0] if missing else None}
        conversation.save(update_fields=["context", "updated_at"])
        result.update(listing=values, missing=missing,
            categories=[{"slug":c.slug,"name":c.name} for c in Category.objects.filter(is_active=True)])
        if missing:
            result["reply"] = "Draft in progress. Please provide " + missing[0] + ". Still needed: " + ", ".join(missing) + "."
        elif not services.has_shop(user):
            result["reply"] = "Your draft details are saved. Complete website seller verification before creating the product. No seller rights were granted."
        else:
            change = services.prepare_change(user, conversation.uuid, request_id, "listing", "", values)
            result.update(reply="Review this unpublished product draft. It will only be saved after you confirm.", change=services.change_data(change))
    elif intent in ("stock", "price", "fulfillment"):
        target = plan.get("target", "")
        if intent != "fulfillment":
            matches = [p for p in get_catalog(user) if p["slug"].casefold()==target.casefold() or p["name"].casefold()==target.casefold()]
            if len(matches) != 1:
                raise ValidationError("Choose one of your exact product names or slugs. Use 'my products' to see them.")
            target = matches[0]["slug"]
        change = services.prepare_change(user, conversation.uuid, request_id, intent, target, plan.get("values", {}))
        result.update(reply="Review the before and after values. Nothing changes until you explicitly confirm.", change=services.change_data(change))
    else:
        result["reply"] = ("I can show 'my products', 'low stock' or 'my orders', help with 'new listing', "
            "or prepare 'set stock EXACT PRODUCT NAME to 5'. Select a variant in the product card when needed. "
            "I do not process payments, refunds or ownership changes.")
        if plan.get("engine") == "deepseek" and plan.get("reply"):
            result["reply"] = "AI suggestion · no changes made\n" + plan["reply"]
    Message.objects.create(conversation=conversation, request_id=request_id, text=text, channel=channel, response=result)
    return result

import re
from django.conf import settings

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
DEMO_GUIDE = ("This is a coursework demo with sample products and orders. "
    "No registration or shop verification is needed. Try 'my products', preview and confirm a stock change, "
    "create an unpublished sample with 'new listing', then inspect 'my orders' and record a simulated shipment. "
    "Changes are saved to the demo database. Payments and shipping are simulated.")


def get_catalog(user):
    return services.products(user) if services.has_shop(user) else []


@transaction.atomic
def respond(user, conversation_id, request_id, text, channel, plan):
    conversation = services.conversation_for(user, conversation_id, lock=True)
    old = conversation.messages.filter(request_id=request_id).first()
    if old:
        return old.response
    chinese = bool(re.search(r"[\u3400-\u9fff]", text))
    def say(english, translated):
        return translated if chinese else english
    intent = plan["intent"]
    result = {"intent":intent, "engine":plan.get("engine","guided")}
    if plan.get("notice"):
        result["notice"] = plan["notice"]
    if intent in ("products", "low_stock"):
        result["products"] = services.products(user, low_stock=intent=="low_stock")
        result["reply"] = say("These are your shop's current product records.", "这是你店铺当前的商品和库存记录。") if result["products"] else say("No matching products in your shop.", "你店铺中暂无符合条件的商品。")
    elif intent == "orders":
        records = services.orders(user)
        if plan.get("pending"):
            records = [o for o in records if o["can_ship"]]
        result.update(reply=say("These orders contain only your shop's items and fulfillment details.", "这是你店铺的订单商品和履约信息。"), orders=records)
    elif intent == "onboarding":
        result["reply"] = DEMO_GUIDE if getattr(settings, "SELLER_PUBLIC_DEMO", False) else ONBOARDING
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
            labels = {"name": "商品名称", "category": "分类", "description": "商品描述", "price": "价格", "quantity": "库存数量"}
            result["reply"] = say(
                "Draft in progress. Please provide " + missing[0] + ". Still needed: " + ", ".join(missing) + ".",
                "正在整理商品草稿，请提供" + labels[missing[0]] + "。还需要：" + "、".join(labels[key] for key in missing) + "。",
            )
        elif not services.has_shop(user):
            result["reply"] = "Your draft details are saved. Complete website seller verification before creating the product. No seller rights were granted."
        else:
            change = services.prepare_change(user, conversation.uuid, request_id, "listing", "", values)
            result.update(reply=say("Review this unpublished product draft. It will only be saved after you confirm.", "请检查商品草稿。你确认后才会保存，商品仍为未发布状态。"), change=services.change_data(change))
    elif intent in ("stock", "price", "fulfillment"):
        target = plan.get("target", "")
        if intent != "fulfillment":
            matches = [p for p in get_catalog(user) if p["slug"].casefold()==target.casefold() or p["name"].casefold()==target.casefold()]
            if len(matches) != 1:
                raise ValidationError("Choose one of your exact product names or slugs. Use 'my products' to see them.")
            target = matches[0]["slug"]
        change = services.prepare_change(user, conversation.uuid, request_id, intent, target, plan.get("values", {}))
        result.update(reply=say("Review the before and after values. Nothing changes until you explicitly confirm.", "请检查修改前后的内容。只有你确认后，才会更新店铺数据。"), change=services.change_data(change))
    else:
        result["reply"] = ("I can show 'my products', 'low stock' or 'my orders', help with 'new listing', "
            "or prepare 'set stock EXACT PRODUCT NAME to 5'. Select a variant in the product card when needed. "
            "I do not process payments, refunds or ownership changes.")
        if plan.get("engine") == "deepseek" and plan.get("reply"):
            result["reply"] = say("AI suggestion · no changes made\n", "AI 建议 · 尚未修改数据\n") + plan["reply"]
    Message.objects.create(conversation=conversation, request_id=request_id, text=text, channel=channel, response=result)
    return result

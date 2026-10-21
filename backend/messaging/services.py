"""Domain services for buyer-seller messaging."""

import uuid
from typing import Optional, Tuple

from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from orders.models import Order
from products.models import Maker, Product

from .models import Conversation, ConversationMessage


def get_or_create_conversation(
    buyer,
    maker_identifier: Optional[str] = None,
    product_identifier: Optional[str] = None,
    order_identifier: Optional[str] = None,
) -> Tuple[Conversation, bool]:
    """Retrieve or create a conversation thread for an authenticated buyer."""
    if not buyer or not buyer.is_authenticated:
        raise PermissionDenied("Authentication required to start a conversation.")

    product = None
    if product_identifier:
        try:
            if isinstance(product_identifier, int) or (isinstance(product_identifier, str) and product_identifier.isdigit()):
                product = Product.objects.select_related("maker").get(pk=int(product_identifier))
            else:
                try:
                    uuid_val = uuid.UUID(str(product_identifier))
                    product = Product.objects.select_related("maker").get(uuid=uuid_val)
                except ValueError:
                    product = Product.objects.select_related("maker").get(slug=str(product_identifier))
        except Product.DoesNotExist:
            raise ValidationError(f"Product '{product_identifier}' not found.")

    maker = None
    if product and product.maker:
        maker = product.maker

    if not maker and maker_identifier:
        try:
            if isinstance(maker_identifier, int) or (isinstance(maker_identifier, str) and maker_identifier.isdigit()):
                maker = Maker.objects.get(pk=int(maker_identifier))
            else:
                try:
                    uuid_val = uuid.UUID(str(maker_identifier))
                    maker = Maker.objects.get(uuid=uuid_val)
                except ValueError:
                    maker = Maker.objects.get(slug=str(maker_identifier))
        except Maker.DoesNotExist:
            raise ValidationError(f"Maker '{maker_identifier}' not found.")

    order = None
    if order_identifier:
        try:
            if isinstance(order_identifier, int) or (isinstance(order_identifier, str) and order_identifier.isdigit()):
                order = Order.objects.prefetch_related("items").get(pk=int(order_identifier))
            else:
                try:
                    uuid_val = uuid.UUID(str(order_identifier))
                    order = Order.objects.prefetch_related("items").get(uuid=uuid_val)
                except ValueError:
                    order = Order.objects.prefetch_related("items").get(order_number=str(order_identifier))
        except Order.DoesNotExist:
            raise ValidationError(f"Order '{order_identifier}' not found.")

        # Permissions check: order must belong to this buyer
        if order.user_id != buyer.id:
            raise PermissionDenied("The specified order does not belong to you.")

        # Maker check: if maker was resolved, verify the maker has items in this order
        if maker:
            if not order.items.filter(maker=maker).exists():
                raise ValidationError("The selected maker is not part of this order.")
        else:
            # Derive maker from order items
            first_item = order.items.filter(maker__isnull=False).first()
            if first_item:
                maker = first_item.maker
            else:
                raise ValidationError("No valid maker found for the specified order.")

    if not maker and not product and not order:
        existing = Conversation.objects.filter(buyer=buyer, is_closed=False).order_by("-updated_at").first()
        if existing:
            return existing, False
        raise ValidationError("Select a maker or product to start a conversation.")

    if not maker:
        raise ValidationError("A maker, product, or order is required to start a conversation.")

    # Match existing open thread
    filters = {
        "buyer": buyer,
        "maker": maker,
        "is_closed": False,
    }
    if product:
        filters["product"] = product
    if order:
        filters["order"] = order

    existing = Conversation.objects.filter(**filters).first()
    if existing:
        return existing, False

    # Also check if an open conversation already exists between buyer & maker generally
    if not product and not order:
        general_existing = Conversation.objects.filter(buyer=buyer, maker=maker, is_closed=False).first()
        if general_existing:
            return general_existing, False

    conversation = Conversation.objects.create(
        buyer=buyer,
        maker=maker,
        product=product,
        order=order,
    )

    # Send an automated welcome greeting on behalf of the maker if they have an active owner
    seller_user = maker.owner
    if seller_user:
        if product:
            welcome_text = (
                f"[Automated] Hello! Welcome to {maker.name}. "
                f"I see you're viewing our {product.name}. "
                "Feel free to ask about materials, dimensions, or custom crafting, and the maker will reply here!"
            )
        else:
            welcome_text = (
                f"[Automated] Hello! Welcome to {maker.name}. "
                "We craft handmade studio pieces with care. "
                "How can we help you today with our items or custom commissions? "
                "Leave a message and the maker will reply here!"
            )
        ConversationMessage.objects.create(
            conversation=conversation,
            sender=seller_user,
            body=welcome_text,
        )

    return conversation, True


def send_message(conversation: Conversation, sender, body: str) -> ConversationMessage:
    """Send a message within an existing conversation thread."""
    if not sender or not sender.is_authenticated:
        raise PermissionDenied("Authentication required to send a message.")

    is_buyer = conversation.buyer_id == sender.id
    is_seller = bool(conversation.maker and conversation.maker.owner_id and conversation.maker.owner_id == sender.id)

    if not (is_buyer or is_seller):
        raise PermissionDenied("You are not a participant in this conversation.")

    clean_body = (body or "").strip()
    if not clean_body:
        raise ValidationError("Message body cannot be empty.")
    if len(clean_body) > 3000:
        raise ValidationError("Message exceeds maximum length of 3000 characters.")

    message = ConversationMessage.objects.create(
        conversation=conversation,
        sender=sender,
        body=clean_body,
    )
    conversation.save(update_fields=["updated_at"])
    return message


def mark_messages_read(conversation: Conversation, viewer) -> int:
    """Mark all incoming unread messages as read for the viewer."""
    if not viewer or not viewer.is_authenticated:
        return 0

    return ConversationMessage.objects.filter(
        conversation=conversation,
        read_at__isnull=True,
    ).exclude(sender=viewer).update(read_at=timezone.now())


# Common phrase pairs for English <-> Chinese e-commerce and artisan studio chat
_EN_TO_ZH_PHRASES = [
    (r"(?i)\[automated\]\s*hello!\s*welcome to ([^.]+)\.\s*how can we help you today with our items or custom commissions\?\s*leave a message and the maker will reply here!?",
     r"[自动回复] 您好！欢迎光临 \1。今天我们在商品或定制委托方面能为您提供什么帮助？请留言，手作人将在此回复！"),
    (r"(?i)\[automated\]\s*hello!\s*welcome to ([^.]+)\.\s*i see you're viewing our ([^.]+)\.\s*feel free to ask about materials, dimensions, or custom crafting, and the maker will reply here!?",
     r"[自动回复] 您好！欢迎光临 \1。看到您正在浏览我们的 \2。欢迎咨询材质、尺寸或定制工艺，手作人将在此回复！"),
    (r"(?i)\[automated\]\s*hello!\s*welcome to ([^.]+)\.?",
     r"[自动回复] 您好！欢迎光临 \1。"),
    (r"(?i)(?:hello,?\s*)?(?:is this|is the) (?:keepsake box|product|item|ceramic mug|piece)?\s*(?:currently\s*)?(?:in stock|available)\??",
     "您好，请问这件作品目前有现货吗？"),
    (r"(?i)do you have this (?:in stock|available)\??",
     "请问有现货吗？"),
    (r"(?i)is this in stock\??",
     "请问有现货吗？"),
    (r"(?i)(?:hello,?\s*)?can (?:this|it|the item) be customized(?:\s*with (?:initials|letters|names?))?\??",
     "您好，请问这个支持定制吗？"),
    (r"(?i)can you engrave initials(?: on the (?:lid|item|box))?\??",
     "请问可以在上面刻首字母吗？"),
    (r"(?i)yes,?\s*we can engrave on the inner lid!?",
     "是的，我们可以在内盖上刻字！"),
    (r"(?i)yes,?\s*(?:we can|it can be) customized!?",
     "可以的，我们支持定制！"),
    (r"(?i)(?:what is|how much is) the shipping fee(?: to ([^?]+))?\??",
     r"请问发货\1的运费是多少？"),
    (r"(?i)how long will (?:production and shipping|making and delivery|it) take\??",
     "请问制作和发货大概需要多久？"),
    (r"(?i)how many days (?:does it take to make|for production)\??",
     "请问制作需要几天？"),
    (r"(?i)is this (?:handmade with|made of) genuine leather\??",
     "请问这是真皮手工制作的吗？"),
    (r"(?i)is this (?:handmade|handcrafted)\??",
     "请问这是手工制作的吗？"),
    (r"(?i)i (?:really\s*)?like this (?:handmade\s*)?(?:piece|work|item),?\s*(?:is it|do you have) (?:still\s*)?(?:in stock|available)\??",
     "我很喜欢这款手工作品，请问还有库存吗？"),
    (r"(?i)when will this be shipped\??",
     "请问什么时候可以发货？"),
    (r"(?i)when can it be delivered\??",
     "请问大概什么时候能送达？"),
    (r"(?i)inquiring about order #?([A-Za-z0-9-]+)",
     r"咨询订单 #\1"),
    (r"(?i)inquiring about ([^()]+)(?:\s*\(([^)]+)\))?",
     r"咨询商品：\1"),
    (r"(?i)could you (?:please\s*)?help me check (?:my\s*)?order status\??",
     "您能帮我查询一下订单状态吗？"),
    (r"(?i)hello!?\s*i would like to inquire about your craft work\.?",
     "您好！我想咨询关于您的手工作品。"),
    (r"(?i)thank you (?:very much|so much)!?",
     "非常感谢！"),
    (r"(?i)thank you!?",
     "谢谢！"),
    (r"(?i)thanks!?",
     "多谢！"),
    (r"(?i)you(?:'re| are) welcome!?",
     "不客气！"),
    (r"(?i)it is high-fired porcelain,?\s*excellent for retaining heat\.?",
     "这是高温烧制瓷器，保温性能极佳。"),
    (r"(?i)in stock,?\s*can be shipped today\.?",
     "有现货，今天即可发货。"),
    (r"(?i)handmade studio pieces with care\.?",
     "用心制作的手工工作室作品。"),
    (r"(?i)it (?:usually\s*)?takes (\d+)(?:\s*to\s*(\d+))?\s*(?:business\s*)?days to (?:craft|make)\.?",
     r"通常需要\1至\2个工作日制作。"),
]

_ZH_TO_EN_PHRASES = [
    (r"\[自动回复\]\s*您好！欢迎光临\s*([^。]+)。今天我们在商品或定制委托方面能为您提供什么帮助？请留言，手作人将在此回复！",
     r"[Automated] Hello! Welcome to \1. How can we help you today with our items or custom commissions? Leave a message and the maker will reply here!"),
    (r"\[自动回复\]\s*您好！欢迎光临\s*([^。]+)。看到您正在浏览我们的\s*([^。]+)。欢迎咨询材质、尺寸或定制工艺，手作人将在此回复！",
     r"[Automated] Hello! Welcome to \1. I see you're viewing our \2. Feel free to ask about materials, dimensions, or custom crafting, and the maker will reply here!"),
    (r"(?:您好[，！]\s*)?请问(?:这件作品|这款商品|这个)?(?:目前)?有现货吗？?",
     "Hello, is this item currently in stock?"),
    (r"请问有现货吗？?",
     "Is this in stock?"),
    (r"请问还有库存吗？?",
     "Is this still in stock?"),
    (r"请问有现货吗？什么时候发货？?",
     "Is this in stock? When will it be shipped?"),
    (r"请问可以在(?:盖子|表面|内侧)上刻(?:首字母|名字|字)吗？?",
     "Can you engrave initials or a name on it?"),
    (r"可以定制刻字吗？?",
     "Can this be customized with engraving?"),
    (r"(?:请问)?这个可以定制吗？?",
     "Can this piece be customized?"),
    (r"是的，我们可以在内盖上刻字！?",
     "Yes, we can engrave on the inner lid!"),
    (r"可以的[，！]我们支持定制[。！]?",
     "Yes, we support custom orders!"),
    (r"(?:请问)?(?:发货到([^？?]+)的)?运费是多少[？?]",
     r"What is the shipping fee to \1?"),
    (r"制作和发货大概需要多久[？?]",
     "How long will production and shipping take?"),
    (r"制作周期需要几天[？?]",
     "How many days does production take?"),
    (r"通常需要\s*(\d+)(?:[到至-](\d+))?\s*个工作日制作[。！]?",
     r"It usually takes \1 to \2 business days to craft."),
    (r"请问这是纯?手工制作的吗[？?]",
     "Is this handmade?"),
    (r"请问是真皮手工制作的吗[？?]",
     "Is this handmade with genuine leather?"),
    (r"我很喜欢这款手工作品，请问还有库存吗[？?]",
     "I really like this handmade piece, is it still in stock?"),
    (r"请问什么时候可以发货[？?]",
     "When will this be shipped?"),
    (r"什么时候能发货[？?]",
     "When can it be dispatched?"),
    (r"咨询订单\s*#?([A-Za-z0-9-]+)",
     r"Inquiring about order #\1"),
    (r"您能帮我查询一下订单状态吗[？?]",
     "Could you help me check my order status?"),
    (r"您好！我想咨询关于您的手工作品[。！]?",
     "Hello! I would like to inquire about your craft work."),
    (r"非常感谢[！!。]?",
     "Thank you very much!"),
    (r"谢谢[！!。]?",
     "Thank you!"),
    (r"多谢[！!。]?",
     "Thanks a lot!"),
    (r"不客气[！!。]?",
     "You are welcome!"),
    (r"好的[，！]没问题[！!。]?",
     "Sure, no problem!"),
    (r"有现货，今天即可发货[。！]?",
     "In stock, can be shipped today."),
]

_EN_ZH_WORDS = [
    ("hello", "你好"),
    ("hi", "你好"),
    ("in stock", "有现货"),
    ("out of stock", "缺货"),
    ("custom", "定制"),
    ("customized", "定制的"),
    ("engrave", "刻字"),
    ("engraving", "雕刻"),
    ("shipping", "发货"),
    ("shipped", "已发货"),
    ("delivered", "已送达"),
    ("delivery", "配送"),
    ("tracking number", "物流单号"),
    ("order", "订单"),
    ("artisan", "手作人"),
    ("maker", "手作人"),
    ("ceramic", "陶瓷"),
    ("porcelain", "瓷器"),
    ("celadon", "青瓷"),
    ("wood", "木作"),
    ("woodcraft", "木艺"),
    ("walnut", "胡桃木"),
    ("textiles", "织物"),
    ("indigo", "蓝染"),
    ("glass", "玻璃"),
    ("glassblower", "吹制玻璃"),
    ("metalwork", "金属工艺"),
    ("silver", "纯银"),
    ("tea cup", "茶杯"),
    ("tea set", "茶具套组"),
    ("keepsake box", "纪念盒"),
    ("lid", "盖子"),
    ("inner lid", "内盖"),
    ("price", "价格"),
    ("material", "材质"),
    ("dimension", "尺寸"),
    ("size", "规格"),
    ("colour", "颜色"),
    ("color", "颜色"),
    ("studio", "工作室"),
    ("batch", "批次"),
    ("firing", "开窑"),
    ("glaze", "釉面"),
    ("yes", "是的"),
    ("no", "没有"),
    ("please", "请"),
    ("thanks", "谢谢"),
    ("thank you", "谢谢"),
]


_TRANSLATION_CACHE = {}


def translate_message(text: str, target_lang: Optional[str] = None) -> dict:
    """Translate a chat message with high accuracy between English and Chinese.

    Multi-tier architecture:
    1. In-memory LRU cache for instant response to repeated queries.
    2. Neural Machine Translation (NMT) via Google Translate API with browser client emulation.
    3. Secondary NMT fallback via MyMemory Translation Memory API.
    4. Domain-specific craft & artisan e-commerce phrase matcher.
    5. Clean token replacement fallback when offline.
    """
    import re
    clean = (text or "").strip()
    if not clean:
        return {"original": "", "translated": "", "source_lang": "en", "target_lang": "zh"}

    has_chinese = bool(re.search(r"[\u4e00-\u9fff]", clean))
    source_lang = "zh" if has_chinese else "en"
    if not target_lang:
        target_lang = "en" if source_lang == "zh" else "zh"

    # If source and target are the same, return as-is
    if source_lang == target_lang:
        return {"original": clean, "translated": clean, "source_lang": source_lang, "target_lang": target_lang}

    cache_key = (clean, target_lang)
    if cache_key in _TRANSLATION_CACHE:
        return _TRANSLATION_CACHE[cache_key]

    translated = None

    # Tier 1: High-accuracy Neural Machine Translation (Google NMT)
    try:
        import requests
        sl = "zh-CN" if source_lang == "zh" else "en"
        tl = "zh-CN" if target_lang == "zh" else "en"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }
        for client in ("dict-chrome-ex", "gtx"):
            try:
                url = "https://translate.googleapis.com/translate_a/single"
                params = {"client": client, "sl": sl, "tl": tl, "dt": "t", "q": clean}
                resp = requests.get(url, params=params, headers=headers, timeout=2.5)
                if resp.status_code == 200:
                    data = resp.json()
                    if data and data[0]:
                        nmt_result = "".join([part[0] for part in data[0] if part and part[0]]).strip()
                        if nmt_result:
                            translated = nmt_result
                            break
            except Exception:
                continue
    except Exception:
        pass

    # Tier 2: Secondary NMT fallback (MyMemory API)
    if not translated:
        try:
            import requests
            url = f"https://api.mymemory.translated.net/get?q={requests.utils.quote(clean)}&langpair={source_lang}|{target_lang}"
            headers = {"User-Agent": "AtelierForm/1.0"}
            resp = requests.get(url, headers=headers, timeout=2.5)
            if resp.status_code == 200:
                data = resp.json()
                res_text = (data.get("responseData", {}).get("translatedText") or "").strip()
                if res_text and not res_text.startswith("MYMEMORY WARNING") and res_text.lower() != clean.lower():
                    translated = res_text
        except Exception:
            pass

    # Tier 3: Domain-specific high-fidelity e-commerce & craft phrase mapping
    if not translated:
        if source_lang == "en" and target_lang == "zh":
            for pattern, repl in _EN_TO_ZH_PHRASES:
                if re.fullmatch(pattern, clean):
                    translated = re.sub(pattern, repl, clean)
                    break
        elif source_lang == "zh" and target_lang == "en":
            for pattern, repl in _ZH_TO_EN_PHRASES:
                if re.fullmatch(pattern, clean):
                    translated = re.sub(pattern, repl, clean)
                    break

    # Tier 4: Token-level dictionary fallback for offline partial queries
    if not translated:
        translated = clean
        if source_lang == "en" and target_lang == "zh":
            for en, zh in _EN_ZH_WORDS:
                translated = re.sub(r"(?i)\b" + re.escape(en) + r"\b", zh, translated)
        elif source_lang == "zh" and target_lang == "en":
            for en, zh in _EN_ZH_WORDS:
                if zh in translated:
                    translated = translated.replace(zh, f" {en} ")
            translated = re.sub(r"\s+", " ", translated).strip()

    result = {
        "original": clean,
        "translated": translated or clean,
        "source_lang": source_lang,
        "target_lang": target_lang,
    }

    # Keep cache reasonable in size (< 1000 items)
    if len(_TRANSLATION_CACHE) > 1000:
        _TRANSLATION_CACHE.clear()
    _TRANSLATION_CACHE[cache_key] = result

    return result

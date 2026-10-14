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

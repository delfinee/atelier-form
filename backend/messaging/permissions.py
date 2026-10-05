"""Permission classes for messaging."""

from rest_framework import permissions


class IsConversationParticipant(permissions.BasePermission):
    """Allows access only to the buyer or the seller owning the maker profile."""

    message = "You do not have access to this conversation."

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        # If object is ConversationMessage, get its conversation
        conversation = getattr(obj, "conversation", obj)

        if conversation.buyer_id == user.id:
            return True

        maker = conversation.maker
        if maker and maker.owner_id and maker.owner_id == user.id:
            return True

        return False

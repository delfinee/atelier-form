"""Shared DRF permissions."""

from rest_framework import permissions


class IsAdminUserRole(permissions.BasePermission):
    """Requires the application's own `is_admin` flag, not just Django staff."""

    message = "Administrator access is required."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (user.is_admin or user.is_superuser))


class IsOwner(permissions.BasePermission):
    """Object-level ownership. The queryset is already scoped to the user;
    this is the second line of defence against an IDOR."""

    message = "You do not have access to this resource."

    def has_object_permission(self, request, view, obj):
        owner = getattr(obj, "user", None)
        return owner is not None and owner == request.user


class IsSeller(permissions.BasePermission):
    """Requires a seller account linked to exactly one Maker profile."""

    message = "A linked seller profile is required."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_seller
                    and hasattr(user, "maker_profile"))

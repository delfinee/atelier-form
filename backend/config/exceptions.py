"""One error shape for the whole API: {"detail": "..."} plus optional field errors.

DRF's default handler already returns `detail` for APIException subclasses but
returns a bare field-error dict for validation errors. This normalises both, and
turns an unhandled exception into a 500 that carries a reference id instead of a
stack trace.
"""

import logging
import uuid

from django.core.exceptions import PermissionDenied, ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


class InsufficientStock(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Not enough stock available."
    default_code = "insufficient_stock"


class EmptyCart(exceptions.APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Your bag is empty."
    default_code = "empty_cart"


def api_exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        exc = exceptions.ValidationError(detail=getattr(exc, "message_dict", exc.messages))
    elif isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, PermissionDenied):
        exc = exceptions.PermissionDenied()

    response = drf_exception_handler(exc, context)

    if response is None:
        # Unhandled: log with a reference the user can quote, return nothing else.
        reference = uuid.uuid4().hex[:12]
        logger.exception("Unhandled API error [ref=%s]", reference)
        return Response(
            {"detail": "An unexpected error occurred.", "reference": reference},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    data = response.data
    if isinstance(data, dict) and "detail" not in data:
        # Field-level validation errors: keep them, add a human-readable summary.
        response.data = {"detail": "Validation failed.", "errors": data}
    elif isinstance(data, list):
        response.data = {"detail": "Validation failed.", "errors": {"non_field_errors": data}}

    return response

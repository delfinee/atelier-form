"""Payment endpoints.

There is no endpoint that lets a client declare a payment successful. The only
route to `paid` is the provider webhook, which the provider signs.
"""

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import get_payment_provider


class PaymentWebhookView(APIView):
    """Provider callback.

    CSRF does not apply (no cookie auth); authenticity comes from the
    provider's signature, verified inside `handle_webhook`.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        summary="Payment provider webhook",
        description=("Development: POST {\"session_id\": \"...\", \"status\": \"succeeded\"} "
                     "to settle a mock payment. A real provider signs this request and the "
                     "signature is verified before the order is touched."),
        request=None, responses={200: None, 400: None},
    )
    def post(self, request):
        payment = get_payment_provider().handle_webhook(request.body, dict(request.headers))
        if payment is None:
            return Response({"detail": "Webhook could not be verified."},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Processed.", "state": payment.state,
                         "order": payment.order.order_number})

"""Stripe Checkout request contract; no requests reach Stripe."""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from orders.models import Order, OrderStatus, PaymentStatus
from payments.models import Payment, PaymentProviderChoices, PaymentState
from payments.services import StripeWeChatProvider


@override_settings(STRIPE_SECRET_KEY="test-placeholder", SITE_URL="https://shop.example.test")
class StripeCheckoutSessionTests(SimpleTestCase):
    def setUp(self):
        self.order = Order(
            order_number="AF-STRIPE-TEST",
            customer_email="buyer@example.test",
            total=Decimal("123.45"),
            currency="CNY",
        )
        self.stripe_session = SimpleNamespace(
            id="cs_test_rehearsal",
            url="https://checkout.stripe.com/c/pay/" + "x" * 250,
        )
        self.payment = Payment(order=self.order)
        self.create_payment = self.enterContext(
            patch("payments.services.Payment.objects.create", return_value=self.payment)
        )
        self.save_payment = self.enterContext(patch.object(self.payment, "save"))

    @patch("payments.services.stripe.checkout.Session.create")
    def test_wechat_only_request_and_pending_payment_are_preserved(self, create):
        create.return_value = self.stripe_session

        session = StripeWeChatProvider().create_session(self.order)

        payment = self.payment
        create.assert_called_once_with(
            allowed_payment_method_types=["wechat_pay"],
            payment_method_options={"wechat_pay": {"client": "web"}},
            line_items=[{
                "price_data": {
                    "currency": "cny",
                    "product_data": {"name": "Order AF-STRIPE-TEST"},
                    "unit_amount": 12345,
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=f"https://shop.example.test/checkout/confirmation/{self.order.uuid}/",
            cancel_url="https://shop.example.test/checkout/",
            metadata={
                "order_number": self.order.order_number,
                "payment_uuid": str(payment.uuid),
            },
        )
        self.create_payment.assert_called_once_with(
            order=self.order,
            provider=PaymentProviderChoices.STRIPE_WECHAT,
            state=PaymentState.CREATED,
            amount=Decimal("123.45"),
            currency="CNY",
        )
        self.save_payment.assert_called_once_with(
            update_fields=["provider_session_id", "checkout_url", "updated_at"],
        )
        self.assertEqual(payment.provider_session_id, self.stripe_session.id)
        self.assertEqual(payment.checkout_url, self.stripe_session.url)
        self.assertIs(session.payment, payment)
        self.assertEqual(session.session_id, self.stripe_session.id)
        self.assertEqual(session.checkout_url, self.stripe_session.url)
        self.assertTrue(session.requires_action)
        self.assertEqual(self.order.payment_status, PaymentStatus.UNPAID)
        self.assertEqual(self.order.status, OrderStatus.PENDING)

    @patch("payments.services.stripe.checkout.Session.create")
    def test_explicit_return_url_preserves_wechat_only_checkout(self, create):
        create.return_value = self.stripe_session

        StripeWeChatProvider().create_session(
            self.order, return_url="https://shop.example.test/return/",
        )

        params = create.call_args.kwargs
        self.assertEqual(params["success_url"], "https://shop.example.test/return/")
        self.assertEqual(params["allowed_payment_method_types"], ["wechat_pay"])
        self.assertNotIn("payment_method_types", params)
        self.assertEqual(params["payment_method_options"], {"wechat_pay": {"client": "web"}})

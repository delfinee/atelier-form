"""Category Y: admin registration smoke check. Deliberately minimal -- no
admin UI/rendering coverage, just confirming the model is registered."""
from django.contrib import admin
from django.test import TestCase

from orders.models import SellerFulfillment


class SellerFulfillmentAdminRegistrationTests(TestCase):
    def test_registered_with_the_default_admin_site(self):
        self.assertIn(SellerFulfillment, admin.site._registry)

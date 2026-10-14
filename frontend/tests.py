"""Browser account registration, login, profile and password tests."""

import json
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest import skipUnless
from unittest.mock import PropertyMock, patch
from urllib.parse import urlencode, urlsplit

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import HASH_SESSION_KEY, SESSION_KEY, get_user_model
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.tokens import default_token_generator
from django.contrib.messages import get_messages
from django.contrib.sessions.models import Session
from django.core import mail
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone as django_timezone
from django.utils.html import escape
from rest_framework.test import APIClient

from accounts.models import WishlistItem
from orders.models import (
    FulfillmentStatus, Order, OrderItem, OrderNumberSequence, OrderStatus,
    PaymentStatus, SellerFulfillment,
)
from frontend.templatetags.frontend_extras import money as money_filter
from products.models import Category, Maker, Product, ProductVariant
from reviews.models import Review

from .forms import ProfileForm, RegistrationForm


@override_settings(
    LANGUAGE_CODE="en", SECURE_SSL_REDIRECT=False,
    STORAGES={
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class AccountRegistrationTests(TestCase):
    def data(self, **overrides):
        return {
            "first_name": "Alex", "last_name": "Potter", "email": "alex@example.com",
            "password": "Ceramic-violet-83!", **overrides,
        }

    def assert_invalid(self, data, field, code):
        count = get_user_model().objects.count()
        response = self.client.post(reverse("register"), data)
        self.assertEqual(response.status_code, 200)
        form = response.context["registration_form"]
        self.assertIn(code, [error.code for error in form.errors.as_data()[field]])
        self.assertContains(response, response.context["errors"][field])
        error_id = {
            "first_name": "au-first-errors", "last_name": "au-last-errors",
            "email": "au-remail-errors", "password": "au-rpass-errors",
        }[field]
        self.assertContains(response, f'aria-describedby="{error_id}"')
        self.assertContains(response, f'id="{error_id}" role="alert"')
        self.assertEqual(get_user_model().objects.count(), count)
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertNotContains(response, self.data()["password"])
        return response

    def test_valid_registration_normalizes_details_and_signs_in(self):
        response = self.client.post(reverse("register"), self.data(
            first_name="  Alex  ", last_name="  Potter  ", email="  ALEX@EXAMPLE.COM  ",
            accepts_marketing="on",
        ), follow=True)
        self.assertRedirects(response, reverse("account_overview"))
        user = get_user_model().objects.get(email="alex@example.com")
        self.assertEqual((user.first_name, user.last_name), ("Alex", "Potter"))
        self.assertTrue(user.accepts_marketing)
        self.assertTrue(user.check_password(self.data()["password"]))
        self.assertNotEqual(user.password, self.data()["password"])
        self.assertEqual(self.client.session[SESSION_KEY], str(user.pk))
        self.assertContains(response, "Your account is ready.", count=1)
        self.assertNotContains(self.client.get(reverse("account_overview")), "Your account is ready.")
        self.assertNotContains(self.client.get(reverse("account_profile")), "Your account is ready.")

    def test_names_required_when_omitted_empty_or_whitespace(self):
        for field in ("first_name", "last_name"):
            for value in (None, "", "   "):
                with self.subTest(field=field, value=value):
                    data = self.data(**{field: value})
                    if value is None:
                        data.pop(field)
                    self.assert_invalid(data, field, "required")

    def test_name_length_limits_and_boundaries(self):
        for field in ("first_name", "last_name"):
            with self.subTest(field=field):
                self.assert_invalid(self.data(**{field: "A" * 81}), field, "max_length")
                form = RegistrationForm(self.data(**{field: " " + "A" * 80 + " "}))
                self.assertTrue(form.is_valid(), form.errors)
                self.assertEqual(len(getattr(form.save(), field)), 80)
                get_user_model().objects.all().delete()

    def test_email_required_and_validated_by_django(self):
        for email, code in (("", "required"), ("not-an-email", "invalid"),
                            ("alex@example..com", "invalid"),
                            ("a" * 243 + "@example.com", "max_length")):
            with self.subTest(email=email):
                self.assert_invalid(self.data(email=email), "email", code)

    def test_duplicate_email_is_case_and_whitespace_insensitive(self):
        get_user_model().objects.create_user(email="alex@example.com", password="Existing-94!")
        response = self.assert_invalid(self.data(email=" ALEX@EXAMPLE.COM "), "email", "duplicate")
        self.assertContains(response, "An account with this email already exists.")

    def test_required_password_and_all_configured_validators(self):
        for password, code in (
            ("", "required"), ("Ab9!", "password_too_short"),
            ("password", "password_too_common"), ("839261740582", "password_entirely_numeric"),
            ("alex@example.com", "password_too_similar"),
            ("Alexanderson", "password_too_similar"), ("Potterington", "password_too_similar"),
        ):
            with self.subTest(code=code, password=password):
                self.assert_invalid(self.data(
                    password=password, first_name="Alexanderson", last_name="Potterington",
                ), "password", code)

    def test_password_whitespace_is_preserved(self):
        password = " K9!zQ2 "  # Eight characters; trimming would change it and make it too short.
        response = self.client.post(reverse("register"), self.data(password=password))
        self.assertRedirects(response, reverse("account_overview"))
        user = get_user_model().objects.get()
        self.assertTrue(user.check_password(password))
        self.assertFalse(user.check_password(password.strip()))

    def test_invalid_form_preserves_nonsecret_fields(self):
        response = self.assert_invalid(self.data(first_name="  Alex  ", password="short"),
                                       "password", "password_too_short")
        self.assertContains(response, 'value="Alex"')
        self.assertContains(response, 'value="Potter"')
        self.assertContains(response, 'value="alex@example.com"')
        self.assertNotContains(response, 'value="short"')

    def test_registration_fields_keep_single_password_and_length_limits(self):
        response = self.client.get(reverse("register"))
        self.assertContains(response, 'type="password"', count=1)
        self.assertContains(response, 'maxlength="80"', count=2)
        self.assertContains(response, 'maxlength="254"')
        self.assertContains(response, 'autocomplete="new-password"')

    def test_registration_csrf_is_enforced(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse("register"), self.data()).status_code, 403)
        self.assertFalse(get_user_model().objects.exists())
        page = client.get(reverse("register"))
        response = client.post(reverse("register"), {
            **self.data(), "csrfmiddlewaretoken": str(page.context["csrf_token"]),
        })
        self.assertRedirects(response, reverse("account_overview"))


@override_settings(
    LANGUAGE_CODE="en", SECURE_SSL_REDIRECT=False,
    STORAGES={
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class AccountLoginLogoutTests(TestCase):
    password = "Original-studio-57!"

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="login@example.com", password=cls.password, first_name="Alex",
        )

    def login_data(self, **overrides):
        return {"email": self.user.email, "password": self.password, **overrides}

    def test_success_signs_in_and_shows_message_once(self):
        response = self.client.post(reverse("login"), self.login_data(email=" LOGIN@EXAMPLE.COM "), follow=True)
        self.assertRedirects(response, reverse("account_overview"))
        self.assertEqual(self.client.session[SESSION_KEY], str(self.user.pk))
        self.assertContains(response, "Welcome back, Alex.", count=1)
        self.assertNotContains(self.client.get(reverse("account_overview")), "Welcome back, Alex.")

    def test_wrong_unknown_and_inactive_accounts_have_same_error(self):
        get_user_model().objects.create_user(email="inactive@example.com", password=self.password, is_active=False)
        for data in (self.login_data(password="Wrong-88!"), self.login_data(email="unknown@example.com"),
                     self.login_data(email="inactive@example.com")):
            with self.subTest(email=data["email"]):
                response = self.client.post(reverse("login"), data)
                self.assertContains(response, "Invalid email or password.")
                self.assertNotIn(SESSION_KEY, self.client.session)

    def test_valid_short_and_whitespace_passwords_are_accepted(self):
        for password in ("old", " K9!zQ2 "):
            with self.subTest(password=password):
                self.user.set_password(password)
                self.user.save()
                client = Client()
                response = client.post(reverse("login"), self.login_data(password=password))
                self.assertRedirects(response, reverse("account_overview"))
                self.assertEqual(client.session[SESSION_KEY], str(self.user.pk))

    def test_safe_internal_next_is_followed(self):
        for destination in ("/account/orders/", "/account/orders/?page=2", "http://testserver/account/orders/"):
            with self.subTest(destination=destination):
                response = Client().post(reverse("login") + "?" + urlencode({"next": destination}), self.login_data())
                self.assertRedirects(response, destination, fetch_redirect_response=False)

    def test_unsafe_or_malformed_next_falls_back_to_account(self):
        for destination in (
            "https://example.invalid/phish", "//example.invalid/phish", "///example.invalid/phish",
            "/\\example.invalid/phish", "javascript:alert(1)", "http:///example.invalid",
            "https://testserver@example.invalid/", "http://[broken", "not-a-route", "", "   ",
        ):
            with self.subTest(destination=destination):
                response = Client().post(reverse("login") + "?" + urlencode({"next": destination}), self.login_data())
                self.assertRedirects(response, reverse("account_overview"))

    def test_https_next_cannot_downgrade_to_http(self):
        for destination, expected in (("http://testserver/account/orders/", reverse("account_overview")),
                                      ("https://testserver/account/orders/", "https://testserver/account/orders/")):
            with self.subTest(destination=destination):
                response = Client().post(reverse("login") + "?" + urlencode({"next": destination}),
                                         self.login_data(), secure=True)
                self.assertRedirects(response, expected, fetch_redirect_response=False)

    def test_authenticated_auth_pages_still_redirect_to_account(self):
        self.client.force_login(self.user)
        for name in ("login", "register"):
            self.assertRedirects(self.client.get(reverse(name)), reverse("account_overview"))

    def test_overview_displays_queued_error_messages(self):
        def queue_error(request, text):
            messages.error(request, "Account test error.")

        with patch("frontend.views.messages.success", side_effect=queue_error):
            response = self.client.post(reverse("login"), self.login_data(), follow=True)
        self.assertContains(response, 'role="alert">Account test error.</p>', count=1)
        self.assertNotContains(self.client.get(reverse("account_overview")), "Account test error.")

    def test_login_copy_does_not_promise_indefinite_sessions(self):
        response = self.client.get(reverse("login"))
        self.assertNotContains(response, "Sessions last until you sign out.")
        self.assertContains(response, "For your privacy, sign out on shared devices.")

    def test_login_csrf_is_enforced(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse("login"), self.login_data()).status_code, 403)
        self.assertNotIn(SESSION_KEY, client.session)
        page = client.get(reverse("login"))
        response = client.post(reverse("login"), {
            **self.login_data(), "csrfmiddlewaretoken": str(page.context["csrf_token"]),
        })
        self.assertRedirects(response, reverse("account_overview"))

    def test_logout_rejects_get_and_head_without_clearing_session(self):
        self.client.force_login(self.user)
        for method in (self.client.get, self.client.head):
            response = method(reverse("logout"))
            self.assertEqual(response.status_code, 405)
            self.assertEqual(response.headers["Allow"], "POST")
            self.assertEqual(self.client.session[SESSION_KEY], str(self.user.pk))
        self.assertEqual(Client().get(reverse("logout")).status_code, 405)

    def test_logout_requires_csrf_and_post_clears_session(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(reverse("logout")).status_code, 403)
        self.assertEqual(client.session[SESSION_KEY], str(self.user.pk))
        page = client.get(reverse("account_overview"))
        response = client.post(reverse("logout"), {"csrfmiddlewaretoken": str(page.context["csrf_token"])})
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        self.assertNotIn(SESSION_KEY, client.session)


    def test_logout_feedback_is_consumed_on_home_before_next_login(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("logout"), follow=True)
        self.assertRedirects(response, reverse("home"))
        self.assertContains(response, 'role="status">You have been signed out.</p>', count=1)
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertNotContains(self.client.get(reverse("home")), "You have been signed out.")
        response = self.client.post(reverse("login"), self.login_data(), follow=True)
        self.assertContains(response, "Welcome back, Alex.", count=1)
        self.assertNotContains(response, "You have been signed out.")
        self.assertNotContains(self.client.get(reverse("account_profile")), "You have been signed out.")

    def test_login_feedback_is_consumed_on_shop_before_profile(self):
        response = self.client.post(
            reverse("login") + "?" + urlencode({"next": reverse("shop")}),
            self.login_data(), follow=True,
        )
        self.assertRedirects(response, reverse("shop"))
        self.assertContains(response, 'role="status">Welcome back, Alex.</p>', count=1)
        self.assertNotContains(self.client.get(reverse("shop")), "Welcome back, Alex.")
        self.assertNotContains(self.client.get(reverse("account_profile")), "Welcome back, Alex.")

    def test_storefront_info_and_error_messages_keep_accessible_semantics(self):
        def queue_messages(request, text):
            messages.info(request, "Storefront information.")
            messages.error(request, "Storefront error <example>.")

        for name in ("home", "shop"):
            with self.subTest(page=name):
                client = Client()
                with patch("frontend.views.messages.success", side_effect=queue_messages):
                    response = client.post(
                        reverse("login") + "?" + urlencode({"next": reverse(name)}),
                        self.login_data(), follow=True,
                    )
                self.assertRedirects(response, reverse(name))
                self.assertContains(response, 'role="status">Storefront information.</p>', count=1)
                self.assertContains(response, 'role="alert">Storefront error &lt;example&gt;.</p>', count=1)
                later = client.get(reverse("account_profile"))
                self.assertNotContains(later, "Storefront information.")
                self.assertNotContains(later, "Storefront error")


@skipUnless(shutil.which("node"), "Node.js is needed to execute browser validation regression checks.")
class AccountClientValidationTests(SimpleTestCase):
    def test_account_validation_uses_exact_password_and_only_checks_new_password_strength(self):
        # Execute the production validator; minimal DOM doubles record its visible errors.
        script_path = Path(__file__).parent / "static" / "frontend" / "js" / "site.js"
        script = r'''
const fs = require("fs"), vm = require("vm"), assert = require("node:assert/strict");
const source = fs.readFileSync(SCRIPT_PATH, "utf8");
const start = source.indexOf("  function validateForm(form)");
const end = source.indexOf("\n  function initForms()", start);
assert.ok(start >= 0 && end > start);
const context = {
  $$: (_selector, form) => form.inputs,
  fieldError: (input, message) => { input.error = message; },
  text: (_key, fallback) => fallback,
  interpolate: (template, values) => template.replace(/\{(\w+)\}/g, (placeholder, key) =>
    Object.prototype.hasOwnProperty.call(values, key) ? String(values[key]) : placeholder),
};
vm.createContext(context);
vm.runInContext(source.split("\n").find(line => line.includes("const EMAIL =")) +
                "\n" + source.slice(start, end), context);
for (const [label, type, autocomplete, value, maxLength, expected] of [
  ["short existing password", "password", "current-password", "old", -1, true],
  ["spaces in existing password", "password", "current-password", "   ", -1, true],
  ["empty login password", "password", "current-password", "", -1, false],
  ["short new password", "password", "new-password", "short", -1, false],
  ["new password with outer spaces", "password", "new-password", " K9!zQ2 ", -1, true],
  ["empty first name", "text", "given-name", "", 80, false],
  ["whitespace last name", "text", "family-name", "   ", 80, false],
  ["trimmed name at limit", "text", "given-name", " " + "A".repeat(80) + " ", 80, true],
  ["overlong name", "text", "family-name", "A".repeat(81), 80, false],
  ["malformed email", "email", "email", "not-an-email", 254, false],
  ["normal email", "email", "email", "user@example.com", 254, true],
]) {
  const input = { type, autocomplete, value, maxLength, focus() { this.focused = true; } };
  assert.equal(context.validateForm({ inputs: [input] }), expected, label);
  assert.equal(input.value, value, label + " must not mutate input");
  assert.equal(Boolean(input.error), !expected, label + " error feedback");
  assert.equal(Boolean(input.focused), !expected, label + " focus");
}
'''.replace("SCRIPT_PATH", json.dumps(str(script_path)))
        result = subprocess.run([shutil.which("node"), "-"], input=script, text=True,
                                capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


@override_settings(
    LANGUAGE_CODE="en", SECURE_SSL_REDIRECT=False,
    # Rendering account pages should not require a collectstatic build.
    STORAGES={
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class AccountPasswordChangeTests(TestCase):
    old_password = "Original-studio-57!"
    new_password = "Updated-pottery-92!"

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="profile@example.com", password=cls.old_password,
            first_name="Alex", last_name="Potter", phone="12345678",
            accepts_marketing=True,
        )

    def setUp(self):
        self.profile_url = reverse("account_profile")
        self.password_url = reverse("account_change_password")
        self.client.force_login(self.user)

    def password_data(self, **overrides):
        return {
            "old_password": self.old_password,
            "new_password1": self.new_password,
            "new_password2": self.new_password,
            **overrides,
        }

    def assert_password_unchanged(self):
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.old_password))

    def assert_field_error(self, response, field, code, error_id):
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "frontend/account/profile.html")
        form = response.context["password_form"]
        self.assertIn(code, [error.code for error in form.errors.as_data()[field]])
        for error in form.errors[field]:
            self.assertContains(response, error)
        self.assertContains(response, f'aria-describedby="{error_id}"')
        self.assert_password_unchanged()

    def test_profile_get_has_separate_password_form(self):
        response = self.client.get(self.profile_url)
        form = response.context["password_form"]
        self.assertIsInstance(form, PasswordChangeForm)
        self.assertFalse(form.is_bound)
        self.assertContains(response, f'action="{self.profile_url}" novalidate')
        self.assertContains(
            response, f'<form class="panel" method="post" action="{self.password_url}">',
        )
        for name, label in (
            ("old_password", "Current password"),
            ("new_password1", "New password"),
            ("new_password2", "Confirm new password"),
        ):
            self.assertContains(response, f'name="{name}" type="password" required')
            self.assertContains(response, label)

    def test_success_changes_password_and_preserves_session_and_profile(self):
        session = self.client.session
        session["profile_test_marker"] = "keep me"
        session.save()
        response = self.client.post(self.password_url, self.password_data(), follow=True)
        self.assertRedirects(response, self.profile_url)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.new_password))
        self.assertFalse(self.user.check_password(self.old_password))
        self.assertEqual(self.client.session[SESSION_KEY], str(self.user.pk))
        self.assertEqual(self.client.session[HASH_SESSION_KEY], self.user.get_session_auth_hash())
        self.assertEqual(self.client.session["profile_test_marker"], "keep me")
        self.assertTrue(response.context["user"].is_authenticated)
        self.assertFalse(response.context["password_form"].is_bound)
        self.assertEqual(self.user.first_name, "Alex")
        self.assertEqual(self.user.last_name, "Potter")
        self.assertEqual(self.user.phone, "12345678")
        self.assertTrue(self.user.accepts_marketing)
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual([(str(message), message.tags) for message in messages], [
            ("Your password has been changed.", "success"),
        ])
        self.assertContains(response, "Your password has been changed.")

    def test_wrong_current_password_preserves_normal_profile_context(self):
        normal = self.client.get(self.profile_url)
        response = self.client.post(
            self.password_url, self.password_data(old_password="Incorrect-current-57!"),
        )
        self.assert_field_error(response, "old_password", "password_incorrect", "p-current-password-errors")
        for key in ("customer", "meta_title", "current_path", "site", "primary_nav",
                    "footer_nav", "popular_searches"):
            self.assertEqual(response.context[key], normal.context[key])
        self.assertTrue(response.context["af_config"]["authenticated"])
        self.assertContains(response, f'href="{self.profile_url}" aria-current="page"')
        self.assertContains(response, 'value="Alex"')
        self.assertContains(response, 'name="accepts_marketing" checked')
        self.assertNotContains(response, "Incorrect-current-57!")
        self.assertNotContains(response, self.new_password)

    def test_mismatched_confirmation(self):
        response = self.client.post(
            self.password_url, self.password_data(new_password2="Different-pottery-93!"),
        )
        self.assert_field_error(response, "new_password2", "password_mismatch", "p-confirm-password-errors")

    def test_required_password_fields(self):
        for field, error_id in (
            ("old_password", "p-current-password-errors"),
            ("new_password1", "p-new-password-errors"),
            ("new_password2", "p-confirm-password-errors"),
        ):
            with self.subTest(field=field):
                response = self.client.post(self.password_url, self.password_data(**{field: ""}))
                self.assert_field_error(response, field, "required", error_id)

    def test_configured_password_validators(self):
        for password, code in (
            ("Ab9!", "password_too_short"),
            ("password", "password_too_common"),
            ("839261740582", "password_entirely_numeric"),
            ("profile@example.com", "password_too_similar"),
        ):
            with self.subTest(code=code):
                response = self.client.post(self.password_url, self.password_data(
                    new_password1=password, new_password2=password,
                ))
                self.assert_field_error(response, "new_password2", code, "p-confirm-password-errors")

    def test_existing_short_current_password_is_accepted(self):
        self.user.set_password("old")
        self.user.save()
        self.client.force_login(self.user)
        response = self.client.post(self.password_url, self.password_data(old_password="old"))
        self.assertRedirects(response, self.profile_url)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.new_password))

    def test_profile_details_post_still_works_without_changing_password(self):
        response = self.client.post(self.profile_url, {
            "first_name": "  Sam  ", "last_name": "  Clay  ", "phone": "  87654321  ",
            **self.password_data(),
        }, follow=True)
        self.assertRedirects(response, self.profile_url)
        self.assert_password_unchanged()
        self.assertEqual(self.user.first_name, "Sam")
        self.assertEqual(self.user.last_name, "Clay")
        self.assertEqual(self.user.phone, "87654321")
        self.assertFalse(self.user.accepts_marketing)
        self.assertContains(response, "Your details have been saved.")

    def test_password_post_ignores_profile_fields(self):
        response = self.client.post(self.password_url, {
            **self.password_data(), "first_name": "Changed", "phone": "999",
        })
        self.assertRedirects(response, self.profile_url)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Alex")
        self.assertEqual(self.user.phone, "12345678")
        self.assertTrue(self.user.accepts_marketing)

    def test_password_change_requires_login(self):
        self.client.logout()
        response = self.client.post(self.password_url, self.password_data())
        self.assertRedirects(
            response, f'{reverse("login")}?next={self.profile_url}', fetch_redirect_response=False,
        )
        self.assert_password_unchanged()
        response = self.client.post(response.url, {
            "email": self.user.email, "password": self.old_password,
        }, follow=True)
        self.assertRedirects(response, self.profile_url)
        self.assertFalse(response.context["password_form"].is_bound)
        self.assert_password_unchanged()

    def test_password_change_requires_post(self):
        for client in (self.client, Client()):
            for method in (client.get, client.head):
                response = method(self.password_url)
                self.assertEqual(response.status_code, 405)
                self.assertEqual(response.headers["Allow"], "POST")
        self.assert_password_unchanged()

    def test_expired_session_password_submission_returns_to_profile_after_login(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        page = client.get(self.profile_url)
        # Expire the server-side session while the browser still holds the password form.
        Session.objects.filter(session_key=client.session.session_key).update(
            expire_date=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        response = client.post(self.password_url, {
            **self.password_data(), "csrfmiddlewaretoken": str(page.context["csrf_token"]),
        })
        self.assertRedirects(
            response, f'{reverse("login")}?next={self.profile_url}', fetch_redirect_response=False,
        )
        self.assertNotIn(SESSION_KEY, client.session)
        self.assert_password_unchanged()
        login_page = client.get(response.url)
        response = client.post(response.url, {
            "email": self.user.email, "password": self.old_password,
            "csrfmiddlewaretoken": str(login_page.context["csrf_token"]),
        }, follow=True)
        self.assertRedirects(response, self.profile_url)
        self.assertEqual(client.session[SESSION_KEY], str(self.user.pk))
        self.assertFalse(response.context["password_form"].is_bound)
        self.assertNotContains(response, "Your password has been changed.")
        self.assertNotContains(response, self.new_password)
        self.assert_password_unchanged()

    def test_password_change_enforces_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.post(self.password_url, self.password_data())
        self.assertEqual(response.status_code, 403)
        self.assert_password_unchanged()

        profile = client.get(self.profile_url)
        token = str(profile.context["csrf_token"])
        response = client.post(self.password_url, {
            **self.password_data(), "csrfmiddlewaretoken": token,
        })
        self.assertRedirects(response, self.profile_url)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.new_password))


@override_settings(
    LANGUAGE_CODE="en", SECURE_SSL_REDIRECT=False,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    STORAGES={
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class AccountPasswordResetTests(TestCase):
    old_password = "Original-studio-57!"
    new_password = "Updated-pottery-92!"
    confirmation = "If an eligible account exists for that email address, you will receive a password reset link shortly."

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="reset@example.com", password=cls.old_password, first_name="Alex",
        )
        get_user_model().objects.create_user(
            email="inactive@example.com", password=cls.old_password, is_active=False,
        )
        get_user_model().objects.create_user(email="unusable@example.com", password=None)

    def setUp(self):
        self.request_url = reverse("forgot_password")
        self.done_url = reverse("password_reset_done")
        self.complete_url = reverse("password_reset_complete")

    def request_link(self):
        mail.outbox.clear()
        response = self.client.post(self.request_url, {"email": self.user.email})
        self.assertRedirects(response, self.done_url)
        self.assertEqual(len(mail.outbox), 1)
        return urlsplit(re.search(r"https?://\S+", mail.outbox[0].body).group()).path

    def open_link(self, client=None):
        link = self.request_link()
        client = client or self.client
        response = client.get(link, follow=True)
        self.assertTrue(response.context["validlink"])
        self.assertTemplateUsed(response, "frontend/account/password_reset_confirm.html")
        return link, response.redirect_chain[-1][0], response

    def password_data(self, **overrides):
        return {
            "new_password1": self.new_password,
            "new_password2": self.new_password,
            **overrides,
        }

    def assert_password_unchanged(self):
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.old_password))

    def test_request_page_keeps_style_and_login_link(self):
        response = self.client.get(self.request_url)
        self.assertTemplateUsed(response, "frontend/account/password_reset_form.html")
        self.assertFalse(response.context["form"].is_bound)
        self.assertContains(response, 'class="auth-layout"')
        self.assertContains(response, "Reset your password")
        self.assertContains(response, f'action="{self.request_url}"')
        self.assertContains(response, f'href="{reverse("login")}"')
        self.assertNotContains(response, "email delivery is not connected")
        login = self.client.get(reverse("login"))
        self.assertContains(login, f'href="{self.request_url}"')

    def test_invalid_email_has_inline_errors_and_sends_nothing(self):
        for email, code in (("", "required"), ("not-an-email", "invalid")):
            with self.subTest(email=email):
                response = self.client.post(self.request_url, {"email": email})
                self.assertEqual(response.status_code, 200)
                form = response.context["form"]
                self.assertEqual(form.errors.as_data()["email"][0].code, code)
                self.assertContains(response, 'aria-describedby="au-femail-errors"')
                self.assertContains(response, 'id="au-femail-errors" role="alert"')
                for error in form.errors["email"]:
                    self.assertContains(response, error)
                self.assertEqual(len(mail.outbox), 0)

    def test_requests_have_same_confirmation_without_revealing_accounts(self):
        for email, count in (
            (self.user.email, 1), ("unknown@example.com", 0),
            ("inactive@example.com", 0), ("unusable@example.com", 0),
        ):
            with self.subTest(email=email):
                mail.outbox.clear()
                response = self.client.post(self.request_url, {"email": email}, follow=True)
                self.assertRedirects(response, self.done_url)
                self.assertTemplateUsed(response, "frontend/account/password_reset_done.html")
                self.assertContains(response, self.confirmation)
                self.assertNotContains(response, email)
                self.assertEqual(len(mail.outbox), count)

    def test_email_contains_working_link_and_does_not_change_password(self):
        link = self.request_link()
        email = mail.outbox[0]
        self.assertEqual(email.to, [self.user.email])
        self.assertEqual(email.from_email, settings.DEFAULT_FROM_EMAIL)
        self.assertEqual(email.subject, "Reset your Atelier Form password")
        self.assertIn("http://testserver" + link, email.body)
        self.assertNotIn(self.old_password, email.body)
        self.assertContains(self.client.get(link, follow=True), "Set a new password")
        self.assert_password_unchanged()

    def test_email_lookup_is_case_insensitive_and_https_links_use_request_host(self):
        response = self.client.post(
            self.request_url, {"email": "RESET@EXAMPLE.COM"}, secure=True,
        )
        self.assertRedirects(response, self.done_url)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        self.assertIn("https://testserver/account/reset/", mail.outbox[0].body)

    def test_confirmation_hides_token_and_requires_the_browser_session(self):
        link, form_url, response = self.open_link()
        self.assertTrue(form_url.endswith("/set-password/"))
        self.assertNotIn(link.rstrip("/").split("/")[-1], form_url)
        self.assertFalse(response.context["form"].is_bound)
        self.assertContains(response, 'autocomplete="new-password"', count=2)
        self.assertIn("no-store", response.headers["Cache-Control"])
        other_browser = Client().get(form_url)
        self.assertFalse(other_browser.context["validlink"])
        self.assertNotContains(other_browser, 'name="new_password1"')

    def test_invalid_confirmation_passwords_show_errors_without_saving(self):
        _, form_url, _ = self.open_link()
        cases = (
            ({"new_password1": ""}, "new_password1", "required"),
            ({"new_password2": ""}, "new_password2", "required"),
            ({"new_password2": "Different-pottery-93!"}, "new_password2", "password_mismatch"),
            ({"new_password1": "Ab9!", "new_password2": "Ab9!"}, "new_password2", "password_too_short"),
            ({"new_password1": "password", "new_password2": "password"}, "new_password2", "password_too_common"),
            ({"new_password1": "839261740582", "new_password2": "839261740582"}, "new_password2", "password_entirely_numeric"),
            ({"new_password1": self.user.email, "new_password2": self.user.email}, "new_password2", "password_too_similar"),
        )
        for data, field, code in cases:
            with self.subTest(code=code, field=field):
                response = self.client.post(form_url, self.password_data(**data))
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["validlink"])
                errors = response.context["form"].errors
                self.assertIn(code, [error.code for error in errors.as_data()[field]])
                self.assertContains(response, f'id="id_{field}-errors" role="alert"')
                self.assertRegex(response.content.decode(), rf'aria-describedby="[^"]*id_{field}-errors')
                for error in errors[field]:
                    self.assertContains(response, error)
                self.assertNotContains(response, self.new_password)
                self.assert_password_unchanged()

    def test_success_resets_password_and_requires_sign_in(self):
        previous_session = Client()
        previous_session.force_login(self.user)
        _, form_url, _ = self.open_link()
        response = self.client.post(form_url, self.password_data(), follow=True)
        self.assertRedirects(response, self.complete_url)
        self.assertTemplateUsed(response, "frontend/account/password_reset_complete.html")
        self.assertContains(response, "Your password has been reset.")
        self.assertContains(response, f'href="{reverse("login")}"')
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.new_password))
        self.assertFalse(self.user.check_password(self.old_password))
        self.assertEqual(self.user.first_name, "Alex")
        profile_url = reverse("account_profile")
        self.assertRedirects(
            previous_session.get(profile_url), f'{reverse("login")}?next={profile_url}',
        )
        old_login = self.client.post(reverse("login"), {
            "email": self.user.email, "password": self.old_password,
        })
        self.assertContains(old_login, "Invalid email or password.")
        new_login = self.client.post(reverse("login"), {
            "email": self.user.email, "password": self.new_password,
        })
        self.assertRedirects(new_login, reverse("account_overview"))

    def test_used_link_and_confirmation_session_cannot_reset_again(self):
        link, form_url, _ = self.open_link()
        self.client.post(form_url, self.password_data())
        for url in (link, form_url):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertFalse(response.context["validlink"])
                self.assertContains(response, "Reset link unavailable")
                self.assertNotContains(response, 'name="new_password1"')
                self.client.post(url, self.password_data(
                    new_password1="Another-pottery-93!", new_password2="Another-pottery-93!",
                ))
                self.user.refresh_from_db()
                self.assertTrue(self.user.check_password(self.new_password))

    def test_tampered_and_malformed_links_cannot_reset_password(self):
        link = self.request_link()
        invalid_links = (
            link.rstrip("/") + "tampered/",
            reverse("password_reset_confirm", kwargs={"uidb64": "invalid", "token": "invalid"}),
        )
        for url in invalid_links:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertFalse(response.context["validlink"])
                self.assertContains(response, "This password reset link is invalid")
                self.assertContains(response, f'href="{self.request_url}"')
                self.assertNotContains(response, 'name="new_password1"')
                self.client.post(url, self.password_data())
                self.assert_password_unchanged()

    @override_settings(PASSWORD_RESET_TIMEOUT=60)
    def test_expired_link_cannot_reset_password(self):
        link, form_url, _ = self.open_link()
        future = default_token_generator._now() + timedelta(seconds=61)
        with patch.object(default_token_generator, "_now", return_value=future):
            for url in (link, form_url):
                with self.subTest(url=url):
                    response = self.client.get(url)
                    self.assertFalse(response.context["validlink"])
                    self.assertContains(response, "has expired")
                    self.client.post(url, self.password_data())
                    self.assert_password_unchanged()

    def test_request_enforces_csrf(self):
        client = Client(enforce_csrf_checks=True)
        denied = client.post(self.request_url, {"email": self.user.email})
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(len(mail.outbox), 0)
        page = client.get(self.request_url)
        accepted = client.post(self.request_url, {
            "email": self.user.email, "csrfmiddlewaretoken": str(page.context["csrf_token"]),
        })
        self.assertRedirects(accepted, self.done_url)
        self.assertEqual(len(mail.outbox), 1)

    def test_confirmation_enforces_csrf(self):
        client = Client(enforce_csrf_checks=True)
        _, form_url, page = self.open_link(client)
        denied = client.post(form_url, self.password_data())
        self.assertEqual(denied.status_code, 403)
        self.assert_password_unchanged()
        accepted = client.post(form_url, {
            **self.password_data(), "csrfmiddlewaretoken": str(page.context["csrf_token"]),
        })
        self.assertRedirects(accepted, self.complete_url)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.new_password))

    def test_delivery_failure_keeps_generic_confirmation(self):
        with patch("django.core.mail.EmailMultiAlternatives.send", side_effect=OSError("Mail unavailable")):
            with self.assertLogs("django.contrib.auth", level="ERROR"):
                response = self.client.post(self.request_url, {"email": self.user.email}, follow=True)
        self.assertRedirects(response, self.done_url)
        self.assertContains(response, self.confirmation)
        self.assertNotContains(response, self.user.email)
        self.assert_password_unchanged()


@override_settings(
    LANGUAGE_CODE="en", SECURE_SSL_REDIRECT=False,
    STORAGES={
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class AccountProfileEditingTests(TestCase):
    password = "Original-studio-57!"

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="profile-edit@example.com", password=cls.password,
            first_name="Alex", last_name="Potter", phone="12345678", accepts_marketing=True,
        )

    def setUp(self):
        self.url = reverse("account_profile")
        self.client.force_login(self.user)

    def data(self, **overrides):
        return {"first_name": "Sam", "last_name": "Clay", "phone": "+65 1234 5678",
                "accepts_marketing": "on", **overrides}

    def saved_data(self):
        return get_user_model().objects.filter(pk=self.user.pk).values().get()

    def assert_invalid(self, data, field, code):
        before = self.saved_data()
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        form = response.context["profile_form"]
        self.assertTrue(form.is_bound)
        self.assertIn(code, [error.code for error in form.errors.as_data()[field]])
        for error in form.errors[field]:
            self.assertContains(response, escape(error))
        error_id = {"first_name": "p-first-errors", "last_name": "p-last-errors",
                    "phone": "p-phone-errors"}[field]
        self.assertContains(response, f'aria-describedby="{error_id}"')
        self.assertContains(response, f'id="{error_id}" role="alert"')
        self.assertEqual(self.saved_data(), before)
        self.assertEqual(response.context["customer"].first_name, before["first_name"])
        self.assertEqual(response.context["customer"].last_name, before["last_name"])
        self.assertFalse(response.context["password_form"].is_bound)
        self.assertNotContains(response, "Your details have been saved.")
        self.assertContains(response, f'href="{self.url}" aria-current="page"')
        return response

    def test_get_uses_saved_details_and_read_only_email(self):
        response = self.client.get(self.url)
        form = response.context["profile_form"]
        self.assertIsInstance(form, ProfileForm)
        self.assertFalse(form.is_bound)
        self.assertNotIn("email", form.fields)
        for field in ("first_name", "last_name", "phone", "accepts_marketing"):
            self.assertEqual(form[field].value(), getattr(self.user, field))
        self.assertContains(response, 'maxlength="80"', count=2)
        self.assertContains(response, 'maxlength="32"')
        self.assertContains(response, 'name="accepts_marketing" checked')
        self.assertContains(response, f'id="p-email" type="email" value="{self.user.email}" disabled')
        self.assertNotContains(response, 'name="email"')

    def test_valid_update_trims_details_and_preserves_authentication(self):
        response = self.client.post(self.url, self.data(
            first_name="  Sam  ", last_name="  Clay  ", phone="  +65 1234 5678  ",
        ), follow=True)
        self.assertRedirects(response, self.url)
        self.user.refresh_from_db()
        self.assertEqual((self.user.first_name, self.user.last_name, self.user.phone),
                         ("Sam", "Clay", "+65 1234 5678"))
        self.assertTrue(self.user.accepts_marketing)
        self.assertTrue(self.user.check_password(self.password))
        self.assertEqual(self.client.session[SESSION_KEY], str(self.user.pk))
        self.assertContains(response, "Your details have been saved.", count=1)
        self.assertContains(response, 'value="Sam"')
        self.assertFalse(response.context["profile_form"].is_bound)
        self.assertNotContains(self.client.get(self.url), "Your details have been saved.")

    def test_missing_empty_and_whitespace_names_are_rejected(self):
        for field in ("first_name", "last_name"):
            for value in (None, "", "   "):
                with self.subTest(field=field, value=value):
                    data = self.data(**{field: value})
                    if value is None:
                        data.pop(field)
                    self.assert_invalid(data, field, "required")

    def test_overlong_names_and_phone_are_rejected_without_saving(self):
        for field, length in (("first_name", 81), ("last_name", 81), ("phone", 33)):
            with self.subTest(field=field):
                self.assert_invalid(self.data(**{field: "X" * length}), field, "max_length")

    def test_exact_length_boundaries_are_allowed_after_trimming(self):
        response = self.client.post(self.url, self.data(
            first_name=" " + "A" * 80 + " ", last_name=" " + "B" * 80 + " ",
            phone=" " + "1" * 32 + " ",
        ))
        self.assertRedirects(response, self.url)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "A" * 80)
        self.assertEqual(self.user.last_name, "B" * 80)
        self.assertEqual(self.user.phone, "1" * 32)

    def test_optional_phone_can_be_omitted_empty_or_whitespace(self):
        for value in (None, "", "   "):
            with self.subTest(value=value):
                data = self.data(phone=value)
                if value is None:
                    data.pop("phone")
                self.assertRedirects(self.client.post(self.url, data), self.url)
                self.user.refresh_from_db()
                self.assertEqual(self.user.phone, "")

    def test_invalid_submission_retains_values_and_checkbox_state(self):
        for checked in (False, True):
            with self.subTest(checked=checked):
                data = self.data(first_name="", last_name="  Sam & <Clay>  ", phone="  98765  ")
                if not checked:
                    data.pop("accepts_marketing")
                response = self.assert_invalid(data, "first_name", "required")
                self.assertContains(response, 'value="  Sam &amp; &lt;Clay&gt;  "')
                self.assertContains(response, 'value="  98765  "')
                self.assertNotContains(response, 'value="Alex"')
                self.assertEqual(response.context["profile_form"]["first_name"].value(), "")
                checkbox = re.search(r'<input[^>]*name="accepts_marketing"[^>]*>', response.content.decode()).group()
                self.assertEqual("checked" in checkbox, checked)

    def test_marketing_preference_can_be_unchecked_and_checked(self):
        data = self.data()
        data.pop("accepts_marketing")
        self.assertRedirects(self.client.post(self.url, data), self.url)
        self.user.refresh_from_db()
        self.assertFalse(self.user.accepts_marketing)
        self.assertRedirects(self.client.post(self.url, self.data()), self.url)
        self.user.refresh_from_db()
        self.assertTrue(self.user.accepts_marketing)

    def test_email_tampering_is_ignored(self):
        get_user_model().objects.create_user(email="taken@example.com", password=self.password)
        original_email = self.user.email
        for email in ("new@example.com", "invalid", "taken@example.com"):
            with self.subTest(email=email):
                response = self.client.post(self.url, self.data(email=email), follow=True)
                self.assertRedirects(response, self.url)
                self.user.refresh_from_db()
                self.assertEqual(self.user.email, original_email)
                self.assertContains(response, f'value="{original_email}" disabled')

    def test_get_and_post_require_login(self):
        client = Client()
        before = self.saved_data()
        for response in (client.get(self.url), client.post(self.url, self.data())):
            self.assertRedirects(response, f'{reverse("login")}?next={self.url}', fetch_redirect_response=False)
        self.assertEqual(self.saved_data(), before)

    def test_csrf_required_for_profile_update(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        before = self.saved_data()
        self.assertEqual(client.post(self.url, self.data()).status_code, 403)
        self.assertEqual(self.saved_data(), before)
        page = client.get(self.url)
        response = client.post(self.url, {
            **self.data(), "csrfmiddlewaretoken": str(page.context["csrf_token"]),
        })
        self.assertRedirects(response, self.url)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Sam")

    def test_profile_error_does_not_bind_or_change_password(self):
        response = self.assert_invalid(self.data(
            first_name="", old_password=self.password,
            new_password1="Updated-pottery-92!", new_password2="Updated-pottery-92!",
        ), "first_name", "required")
        self.assertFalse(response.context["password_form"].is_bound)
        self.assertNotContains(response, self.password)
        self.assertNotContains(response, "Updated-pottery-92!")

    def test_password_error_uses_unbound_profile_with_saved_preferences(self):
        before = self.saved_data()
        response = self.client.post(reverse("account_change_password"), {
            "old_password": "Wrong-password-77!", "new_password1": "Updated-pottery-92!",
            "new_password2": "Updated-pottery-92!", "first_name": "", "accepts_marketing": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.saved_data(), before)
        self.assertFalse(response.context["profile_form"].is_bound)
        self.assertFalse(response.context["profile_form"].errors)
        self.assertContains(response, 'value="Alex"')
        self.assertContains(response, 'name="accepts_marketing" checked')
        self.assertContains(response, 'id="p-current-password-errors" role="alert"')


@override_settings(
    LANGUAGE_CODE="en", SECURE_SSL_REDIRECT=False, TIME_ZONE="UTC",
    STORAGES={
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class AccountNavigationTests(TestCase):
    password = "Original-studio-57!"
    page_names = ("account_overview", "account_profile", "account_orders",
                  "account_addresses", "account_wishlist")

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="navigation@example.com", password=cls.password,
            first_name="Alex", last_name="Potter",
            date_joined=datetime(2024, 1, 2, 12, tzinfo=timezone.utc),
        )

    def setUp(self):
        self.client.force_login(self.user)

    def assert_active_section(self, response, name):
        self.assertEqual(response.status_code, 200)
        nav = re.search(r'<nav class="account-nav".*?</nav>', response.content.decode(), re.S).group()
        self.assertEqual(nav.count('aria-current="page"'), 1)
        self.assertIn(f'href="{reverse(name)}" aria-current="page"', nav)
        for page in self.page_names:
            self.assertIn(f'href="{reverse(page)}"', nav)

    def test_account_links_and_active_sections(self):
        for name in self.page_names:
            with self.subTest(page=name):
                self.assert_active_section(self.client.get(reverse(name) + "?page=1"), name)

    def test_logged_out_navigation_returns_through_login(self):
        for name in self.page_names:
            with self.subTest(page=name):
                client = Client()
                url = reverse(name)
                response = client.get(url)
                self.assertRedirects(response, f'{reverse("login")}?next={url}', fetch_redirect_response=False)
                response = client.post(response.url, {"email": self.user.email, "password": self.password}, follow=True)
                self.assertRedirects(response, url)
                self.assert_active_section(response, name)
                self.assertContains(response, "Welcome back, Alex.", count=1)

    def test_membership_date_uses_date_joined(self):
        response = self.client.get(reverse("account_overview"))
        self.assertContains(response, "A member since 2 January 2024.")
        self.assertNotContains(response, "A member since .")

    def make_order(self):
        return Order.objects.create(order_number="NAV-0001", user=self.user,
                                    customer_email=self.user.email)

    def test_order_detail_keeps_orders_highlighted(self):
        order = self.make_order()
        # Isolate navigation from the explicitly deferred Windows strftime bug.
        # These scoped test doubles do not change production order formatting.
        with patch.object(Order, "date", new_callable=PropertyMock, return_value="2 January 2024"), \
             patch.object(Order, "timeline", new_callable=PropertyMock, return_value=[]):
            response = self.client.get(reverse("account_order_detail", args=[order.order_number]))
        self.assert_active_section(response, "account_orders")
        self.assertContains(response, order.order_number)
        self.assertContains(response, "All orders")

    def test_order_detail_still_rejects_other_users_orders(self):
        other = get_user_model().objects.create_user(email="other@example.com", password=self.password)
        order = self.make_order()
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("account_order_detail", args=[order.order_number])).status_code, 404)

    def test_messages_appear_once_on_each_account_page(self):
        order = self.make_order()
        paths = [reverse(name) for name in self.page_names]
        paths.append(reverse("account_order_detail", args=[order.order_number]))
        queued = ((messages.SUCCESS, "Account success.", "status"),
                  (messages.INFO, "Account information.", "status"),
                  (messages.ERROR, "Account error <example>.", "alert"))

        def queue_messages(request, text):
            for level, message, _ in queued:
                messages.add_message(request, level, message)

        # Order-containing pages need the same narrowly scoped date-display doubles.
        with patch.object(Order, "date", new_callable=PropertyMock, return_value="2 January 2024"), \
             patch.object(Order, "timeline", new_callable=PropertyMock, return_value=[]):
            for path in paths:
                with self.subTest(path=path):
                    with patch("frontend.views.messages.success", side_effect=queue_messages):
                        response = self.client.post(reverse("account_profile"), {
                            "first_name": "Alex", "last_name": "Potter", "phone": "",
                        })
                    self.assertEqual(response.status_code, 302)
                    response = self.client.get(path)
                    for _, message, role in queued:
                        self.assertContains(response, escape(message), count=1)
                        self.assertContains(response, f'role="{role}">{escape(message)}</p>')
                    next_page = self.client.get(reverse("account_profile"))
                    for _, message, _ in queued:
                        self.assertNotContains(next_page, escape(message))


@override_settings(
    STORAGES={
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class SellerDashboardAnalyticsTests(TestCase):
    """Gate 2 backend validation for frontend.views.seller_dashboard.

    Each seller/maker/product/order is built directly through the ORM,
    matching this file's existing convention (no third-party factory
    library, no cross-app fixture import).
    """

    password = "Studio-owner-57!"

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.seller = User.objects.create_user(
            email="alice.analytics@example.com", password=cls.password, is_seller=True)
        cls.other_seller = User.objects.create_user(
            email="bob.analytics@example.com", password=cls.password, is_seller=True)

        cls.category = Category.objects.create(slug="analytics-category", name="Analytics Category")

        cls.maker = Maker.objects.create(
            slug="alice-analytics", name="Alice", owner=cls.seller,
            discipline="Ceramics", location="Singapore")
        cls.other_maker = Maker.objects.create(
            slug="bob-analytics", name="Bob", owner=cls.other_seller,
            discipline="Woodwork", location="Singapore")

    def setUp(self):
        self.client.force_login(self.seller)

    # -- local fixture helpers ---------------------------------------------

    def make_product(self, maker, slug, *, price="20.00", stock_quantity=50, category=None,
                     is_made_to_order=False):
        return Product.objects.create(
            slug=slug, name=slug.replace("-", " ").title(), maker=maker,
            category=category or self.category, price=Decimal(price),
            stock_quantity=stock_quantity, is_active=True,
            is_made_to_order=is_made_to_order,
        )

    def make_variant(self, product, *, label, stock_quantity, is_active=True):
        return ProductVariant.objects.create(
            product=product, group="colour", label=label,
            sku=f"{product.slug[:20].upper()}-{label[:6].upper()}",
            stock_quantity=stock_quantity, is_active=is_active,
        )

    def make_order(self, *, user=None, payment_status=PaymentStatus.PAID,
                   status=OrderStatus.CONFIRMED, placed_at=None):
        placed_at = placed_at or django_timezone.now()
        return Order.objects.create(
            order_number=OrderNumberSequence.next_number(placed_at.year),
            user=user, status=status, payment_status=payment_status,
            customer_email=(user.email if user else "buyer@example.test"),
            placed_at=placed_at,
        )

    def make_order_item(self, order, product, *, quantity=1, unit_price=None):
        unit_price = Decimal(unit_price) if unit_price is not None else product.price
        return OrderItem.objects.create(
            order=order, product=product, maker=product.maker,
            product_slug=product.slug, product_name=product.name,
            maker_name=product.maker.name, unit_price=unit_price, quantity=quantity,
            line_total=unit_price * quantity,
        )

    def get_dashboard(self, period="all"):
        return self.client.get(reverse("seller_dashboard") + f"?period={period}")

    # -- 1. seller isolation -------------------------------------------------

    def test_seller_isolation_across_all_metrics(self):
        alice_product = self.make_product(self.maker, "alice-mug", price="20.00")
        bob_product = self.make_product(self.other_maker, "bob-chair", price="100.00")

        alice_order = self.make_order(user=self.seller)
        self.make_order_item(alice_order, alice_product, quantity=2)  # 2 units, $40.00

        bob_order = self.make_order(user=self.other_seller)
        self.make_order_item(bob_order, bob_product, quantity=5)  # 5 units, $500.00

        # a product being on someone else's wishlist must not count for this seller
        WishlistItem.objects.create(user=self.other_seller, product=alice_product)
        WishlistItem.objects.create(user=self.seller, product=bob_product)

        Review.objects.create(product=alice_product, user=self.other_seller, rating=5, is_published=True)
        Review.objects.create(product=bob_product, user=self.seller, rating=1, is_published=True)

        self.make_variant(alice_product, label="Small", stock_quantity=2)
        self.make_variant(bob_product, label="Oak", stock_quantity=1)

        SellerFulfillment.objects.create(order=alice_order, maker=self.maker)
        SellerFulfillment.objects.create(order=bob_order, maker=self.other_maker)

        response = self.get_dashboard()
        ctx = response.context

        self.assertEqual(ctx["total_revenue"], Decimal("40.00"))
        self.assertEqual(ctx["total_units"], 2)
        self.assertEqual(ctx["total_orders"], 1)
        self.assertEqual(ctx["average_order_value"], Decimal("40.00"))
        self.assertEqual(ctx["total_wishlist_saves"], 1)
        self.assertEqual(ctx["review_count"], 1)
        self.assertEqual(float(ctx["avg_rating"]), 5.0)
        self.assertEqual(ctx["pending_dispatch_count"], 1)

        best_seller_ids = [row["product_id"] for row in ctx["best_sellers"]]
        self.assertIn(alice_product.id, best_seller_ids)
        self.assertNotIn(bob_product.id, best_seller_ids)

        low_stock_ids = [p.id for p in ctx["low_stock_products"]]
        self.assertIn(alice_product.id, low_stock_ids)
        self.assertNotIn(bob_product.id, low_stock_ids)

        # Gate 3: the existing "Your products" / "Incoming order lines" sections
        # still render this seller's own data, and never the other seller's.
        self.assertContains(response, alice_product.name)
        self.assertNotContains(response, bob_product.name)
        self.assertContains(response, alice_order.order_number)
        self.assertNotContains(response, bob_order.order_number)

    # -- 2. paid vs unpaid ----------------------------------------------------

    def test_only_paid_orders_count_toward_financial_metrics(self):
        product = self.make_product(self.maker, "paid-vs-unpaid", price="30.00")
        paid_order = self.make_order(payment_status=PaymentStatus.PAID)
        self.make_order_item(paid_order, product, quantity=1)

        unpaid_order = self.make_order(payment_status=PaymentStatus.UNPAID, status=OrderStatus.PENDING)
        self.make_order_item(unpaid_order, product, quantity=10)  # would dominate if wrongly counted

        ctx = self.get_dashboard().context
        self.assertEqual(ctx["total_revenue"], Decimal("30.00"))
        self.assertEqual(ctx["total_units"], 1)
        self.assertEqual(ctx["total_orders"], 1)
        self.assertEqual(ctx["average_order_value"], Decimal("30.00"))

        best_seller = ctx["best_sellers"][0]
        self.assertEqual(best_seller["units"], 1)
        self.assertEqual(best_seller["revenue"], Decimal("30.00"))

    # -- 3. distinct order counting -------------------------------------------

    def test_one_order_multiple_lines_counts_as_one_order(self):
        product_a = self.make_product(self.maker, "multi-line-a", price="10.00")
        product_b = self.make_product(self.maker, "multi-line-b", price="15.00")
        order = self.make_order()
        self.make_order_item(order, product_a, quantity=1)
        self.make_order_item(order, product_b, quantity=1)

        self.assertEqual(self.get_dashboard().context["total_orders"], 1)

    # -- 4. AOV ----------------------------------------------------------------

    def test_average_order_value_computation(self):
        product = self.make_product(self.maker, "aov-product", price="50.00")
        order1 = self.make_order()
        self.make_order_item(order1, product, quantity=1)  # $50
        order2 = self.make_order()
        self.make_order_item(order2, product, quantity=3)  # $150
        # total revenue $200 across 2 orders -> AOV $100

        ctx = self.get_dashboard().context
        self.assertEqual(ctx["total_revenue"], Decimal("200.00"))
        self.assertEqual(ctx["total_orders"], 2)
        self.assertEqual(ctx["average_order_value"], Decimal("100.00"))

    def test_average_order_value_is_safe_zero_with_no_paid_orders(self):
        response = self.get_dashboard()
        self.assertEqual(response.status_code, 200)
        ctx = response.context
        self.assertEqual(ctx["total_orders"], 0)
        self.assertEqual(ctx["average_order_value"], Decimal("0"))

    # -- 5. time-window filtering ----------------------------------------------

    def test_time_window_filtering_7d(self):
        product = self.make_product(self.maker, "time-window", price="10.00")
        recent_order = self.make_order(placed_at=django_timezone.now() - timedelta(days=1))
        self.make_order_item(recent_order, product, quantity=1)

        old_order = self.make_order(placed_at=django_timezone.now() - timedelta(days=10))
        self.make_order_item(old_order, product, quantity=5)

        ctx_7d = self.get_dashboard(period="7d").context
        self.assertEqual(ctx_7d["total_orders"], 1)
        self.assertEqual(ctx_7d["total_units"], 1)

        ctx_all = self.get_dashboard(period="all").context
        self.assertEqual(ctx_all["total_orders"], 2)
        self.assertEqual(ctx_all["total_units"], 6)

    def test_time_window_filtering_24h(self):
        """Near-boundary check: just inside 24h is included, just outside is
        not -- not merely "2h vs 30h", which a coarser off-by-a-lot bug would
        also pass."""
        product = self.make_product(self.maker, "time-window-24h", price="10.00")
        within = self.make_order(placed_at=django_timezone.now() - timedelta(hours=23, minutes=59))
        self.make_order_item(within, product, quantity=1)

        outside = self.make_order(placed_at=django_timezone.now() - timedelta(hours=24, minutes=1))
        self.make_order_item(outside, product, quantity=1)

        self.assertEqual(self.get_dashboard(period="24h").context["total_orders"], 1)

    def test_operational_metrics_are_not_time_filtered(self):
        """Wishlist/rating/pending-dispatch/low-stock reflect current state,
        not the selected period -- an old paid order's unfulfilled dispatch
        must still show up even under a narrow window (Finding G)."""
        product = self.make_product(self.maker, "operational", price="10.00")
        old_order = self.make_order(placed_at=django_timezone.now() - timedelta(days=30))
        self.make_order_item(old_order, product, quantity=1)
        SellerFulfillment.objects.create(order=old_order, maker=self.maker)
        WishlistItem.objects.create(user=self.other_seller, product=product)
        Review.objects.create(product=product, user=self.other_seller, rating=4, is_published=True)
        self.make_variant(product, label="Tiny", stock_quantity=1)

        ctx = self.get_dashboard(period="24h").context
        # financial metrics ARE windowed and exclude the old order
        self.assertEqual(ctx["total_orders"], 0)
        # operational metrics are NOT windowed
        self.assertEqual(ctx["pending_dispatch_count"], 1)
        self.assertEqual(ctx["total_wishlist_saves"], 1)
        self.assertEqual(ctx["review_count"], 1)
        self.assertEqual([p.id for p in ctx["low_stock_products"]], [product.id])

    # -- 6. best-seller join multiplication -------------------------------------

    def test_best_seller_totals_are_not_inflated_by_wishlist_joins(self):
        """Reproduces Finding D exactly: one product, two separate paid
        OrderItem rows, four WishlistItem rows. Before the fix this returned
        units=20/revenue=$200.00 (5 units x 4 wishlist rows) instead of the
        correct units=5/revenue=$50.00 -- Count(distinct=True) alone does not
        protect Sum() in the same annotate() call."""
        product = self.make_product(self.maker, "popular-mug", price="10.00")
        order = self.make_order()
        self.make_order_item(order, product, quantity=2)  # line 1: 2 units, $20.00
        self.make_order_item(order, product, quantity=3)  # line 2: 3 units, $30.00

        for i in range(4):
            wisher = get_user_model().objects.create_user(
                email=f"wisher{i}@example.com", password=self.password)
            WishlistItem.objects.create(user=wisher, product=product)

        response = self.get_dashboard()
        best_sellers = list(response.context["best_sellers"])
        self.assertEqual(len(best_sellers), 1)
        row = best_sellers[0]
        self.assertEqual(row["units"], 5)
        self.assertEqual(row["revenue"], Decimal("50.00"))
        self.assertEqual(row["wishlist_saves"], 4)

        # Gate 3: the corrected (non-inflated) numbers actually reach the page
        self.assertContains(response, product.name)

    # -- 7. pending dispatch payment state ---------------------------------------

    def test_pending_dispatch_counts_only_paid_unfulfilled(self):
        product = self.make_product(self.maker, "dispatch-product", price="10.00")

        paid_order = self.make_order(payment_status=PaymentStatus.PAID)
        self.make_order_item(paid_order, product, quantity=1)
        SellerFulfillment.objects.create(order=paid_order, maker=self.maker)  # counts

        unpaid_order = self.make_order(payment_status=PaymentStatus.UNPAID, status=OrderStatus.PENDING)
        self.make_order_item(unpaid_order, product, quantity=1)
        SellerFulfillment.objects.create(order=unpaid_order, maker=self.maker)  # must not count

        cancelled_order = self.make_order(payment_status=PaymentStatus.FAILED, status=OrderStatus.CANCELLED)
        self.make_order_item(cancelled_order, product, quantity=1)
        SellerFulfillment.objects.create(order=cancelled_order, maker=self.maker)  # must not count

        fulfilled_paid_order = self.make_order(payment_status=PaymentStatus.PAID)
        self.make_order_item(fulfilled_paid_order, product, quantity=1)
        SellerFulfillment.objects.create(order=fulfilled_paid_order, maker=self.maker,
                                         status=FulfillmentStatus.FULFILLED)  # already shipped, must not count

        # paid, then cancelled (e.g. an admin cancels ahead of a refund) --
        # nothing left to pack even though payment_status is still PAID
        paid_cancelled_order = self.make_order(payment_status=PaymentStatus.PAID,
                                               status=OrderStatus.CANCELLED)
        self.make_order_item(paid_cancelled_order, product, quantity=1)
        SellerFulfillment.objects.create(order=paid_cancelled_order, maker=self.maker)  # must not count

        self.assertEqual(self.get_dashboard().context["pending_dispatch_count"], 1)

    # -- 8. low stock -------------------------------------------------------------

    def test_low_stock_uses_actual_relation_threshold_and_excludes_sold_out(self):
        threshold = settings.COMMERCE["LOW_STOCK_THRESHOLD"]

        low_product = self.make_product(self.maker, "low-stock-product")
        self.make_variant(low_product, label="Low", stock_quantity=threshold)  # at threshold -> included

        sold_out_product = self.make_product(self.maker, "sold-out-product")
        self.make_variant(sold_out_product, label="None", stock_quantity=0)  # sold out -> excluded

        healthy_product = self.make_product(self.maker, "healthy-product")
        self.make_variant(healthy_product, label="Plenty", stock_quantity=threshold + 50)  # excluded

        other_seller_product = self.make_product(self.other_maker, "other-seller-low-stock")
        self.make_variant(other_seller_product, label="Low", stock_quantity=1)  # must not leak

        inactive_product = self.make_product(self.maker, "inactive-variant-product")
        self.make_variant(inactive_product, label="Retired", stock_quantity=1,
                          is_active=False)  # not offered for sale -> excluded

        made_to_order_product = self.make_product(self.maker, "made-to-order-product",
                                                   is_made_to_order=True)
        self.make_variant(made_to_order_product, label="Low", stock_quantity=1)  # stock is irrelevant -> excluded

        response = self.get_dashboard()
        self.assertEqual(response.status_code, 200)
        low_stock_ids = {p.id for p in response.context["low_stock_products"]}
        self.assertEqual(low_stock_ids, {low_product.id})

        # Gate 3: within the Low stock alerts panel specifically, only the
        # qualifying product appears -- excluded products are expected to
        # still show up elsewhere on the page (e.g. in "Your products"),
        # so the check is scoped rather than page-wide.
        html = response.content.decode()
        low_stock_html = re.search(r'Low stock alerts.*?</section>', html, re.S).group()
        self.assertIn(low_product.name, low_stock_html)
        self.assertNotIn(healthy_product.name, low_stock_html)
        self.assertNotIn(made_to_order_product.name, low_stock_html)
        self.assertNotIn(inactive_product.name, low_stock_html)

    # -- 9. reviews -----------------------------------------------------------------

    def test_review_metrics(self):
        product = self.make_product(self.maker, "reviewed-product")
        other_product = self.make_product(self.other_maker, "other-reviewed-product")

        Review.objects.create(product=product, user=self.other_seller, rating=5, is_published=True)
        reviewer2 = get_user_model().objects.create_user(email="reviewer2@example.com", password=self.password)
        Review.objects.create(product=product, user=reviewer2, rating=3, is_published=True)
        reviewer3 = get_user_model().objects.create_user(email="reviewer3@example.com", password=self.password)
        Review.objects.create(product=product, user=reviewer3, rating=1, is_published=False)  # excluded
        Review.objects.create(product=other_product, user=self.seller, rating=5, is_published=True)  # excluded

        ctx = self.get_dashboard().context
        self.assertEqual(ctx["review_count"], 2)
        self.assertAlmostEqual(float(ctx["avg_rating"]), 4.0)

    # -- 10. invalid period / empty seller ---------------------------------------

    def test_invalid_period_falls_back_to_default(self):
        response = self.client.get(reverse("seller_dashboard") + "?period=bogus")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["period_key"], "30d")

    def test_empty_seller_does_not_crash(self):
        """Also the regression guard for Finding E: before the fix, this
        request 500'd with FieldError on `variants__stock_quantity`."""
        response = self.get_dashboard()
        self.assertEqual(response.status_code, 200)
        ctx = response.context
        self.assertEqual(ctx["total_revenue"], 0)
        self.assertEqual(ctx["total_units"], 0)
        self.assertEqual(ctx["total_orders"], 0)
        self.assertEqual(ctx["average_order_value"], Decimal("0"))
        self.assertEqual(ctx["total_wishlist_saves"], 0)
        self.assertIsNone(ctx["avg_rating"])
        self.assertEqual(ctx["review_count"], 0)
        self.assertEqual(ctx["pending_dispatch_count"], 0)
        self.assertEqual(list(ctx["best_sellers"]), [])
        self.assertEqual(list(ctx["low_stock_products"]), [])

        # Gate 3: a seller with nothing yet gets a sensible neutral empty state
        # everywhere, never a raw `None` for the missing rating.
        self.assertContains(response, "No reviews yet")
        self.assertContains(response, "No sales yet in this period.")
        self.assertContains(response, "Nothing running low right now.")
        self.assertContains(response, "No products yet.")
        self.assertContains(response, "No incoming orders yet.")

    # -- 11. Gate 3 presentation -----------------------------------------------

    def test_dashboard_renders_kpi_labels_and_validated_values(self):
        """The already-validated backend values actually reach the page, and
        the existing product/incoming-order sections survive alongside them."""
        product = self.make_product(self.maker, "presentation-product", price="25.00")
        order = self.make_order()
        self.make_order_item(order, product, quantity=2)  # $50.00 revenue

        response = self.get_dashboard()
        self.assertEqual(response.status_code, 200)

        for label in ("Revenue", "Orders", "Units sold", "Average order value",
                     "Wishlist saves", "Awaiting dispatch", "Best sellers",
                     "Low stock alerts", "Your products", "Incoming order lines"):
            self.assertContains(response, label)

        # tied to the same context values Gate 2 already validated, not
        # hardcoded numbers/currency-symbol assumptions
        self.assertContains(response, money_filter(response.context["total_revenue"]))
        self.assertContains(response, money_filter(response.context["average_order_value"]))

    def test_period_selector_marks_the_selected_chip(self):
        response = self.get_dashboard(period="7d")
        html = response.content.decode()
        chips_html = re.search(r'<nav class="chips".*?</nav>', html, re.S).group()
        # exactly one chip is marked selected, and it is the requested period
        self.assertEqual(chips_html.count('aria-current="page"'), 1)
        self.assertRegex(chips_html, r'href="\?period=7d"[^>]*aria-current="page"')


@override_settings(
    STORAGES={
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class SellerOrderDetailBrowserTests(TestCase):
    """CP2: the server-rendered seller order page and its fulfilment form.

    Writes must reach orders.services.update_seller_fulfillment(); these tests
    assert its observable effects (fields, shipped_at, parent sync) rather
    than re-deriving them.
    """

    password = "Studio-owner-57!"

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice = User.objects.create_user(
            email="alice.fulfil@example.com", password=cls.password, is_seller=True)
        cls.bob = User.objects.create_user(
            email="bob.fulfil@example.com", password=cls.password, is_seller=True)
        cls.buyer = User.objects.create_user(
            email="buyer.fulfil@example.com", password=cls.password)

        category = Category.objects.create(slug="fulfil-category", name="Fulfil Category")
        cls.alice_maker = Maker.objects.create(
            slug="alice-fulfil", name="Alice Studio", owner=cls.alice,
            discipline="Ceramics", location="Singapore")
        cls.bob_maker = Maker.objects.create(
            slug="bob-fulfil", name="Bob Workshop", owner=cls.bob,
            discipline="Woodwork", location="Singapore")
        cls.alice_product = Product.objects.create(
            slug="alice-fulfil-vase", name="Alice Fulfil Vase", maker=cls.alice_maker,
            category=category, price=Decimal("20.00"), stock_quantity=10, is_active=True)
        cls.bob_product = Product.objects.create(
            slug="bob-fulfil-stool", name="Bob Fulfil Stool", maker=cls.bob_maker,
            category=category, price=Decimal("30.00"), stock_quantity=10, is_active=True)

    def setUp(self):
        # Order X: one commercial order, one line from each seller.
        self.order = self.make_order()
        self.make_order_item(self.order, self.alice_product, quantity=2)  # 40.00
        self.make_order_item(self.order, self.bob_product, quantity=1)    # 30.00
        self.alice_f = SellerFulfillment.objects.create(
            order=self.order, maker=self.alice_maker,
            carrier="SF Express", tracking_number="SF-ALICE-1")
        self.bob_f = SellerFulfillment.objects.create(
            order=self.order, maker=self.bob_maker,
            carrier="FedEx", tracking_number="FX-BOB-999")

        self.bob_only_order = self.make_order()
        self.make_order_item(self.bob_only_order, self.bob_product)
        self.bob_only_f = SellerFulfillment.objects.create(
            order=self.bob_only_order, maker=self.bob_maker)

    # -- helpers -------------------------------------------------------------

    def make_order(self, **fields):
        return Order.objects.create(
            order_number=OrderNumberSequence.next_number(),
            status=OrderStatus.CONFIRMED, payment_status=PaymentStatus.PAID,
            customer_email="buyer.fulfil@example.com",
            shipping_address_snapshot={
                "first_name": "Wei", "last_name": "Buyer", "address_line_1": "1 Kiln Lane",
                "city": "Shanghai", "postal_code": "200000", "country": "China",
            },
            **fields,
        )

    def make_order_item(self, order, product, *, quantity=1):
        return OrderItem.objects.create(
            order=order, product=product, maker=product.maker,
            product_slug=product.slug, product_name=product.name,
            maker_name=product.maker.name, unit_price=product.price, quantity=quantity,
            line_total=product.price * quantity,
        )

    def url(self, order):
        return reverse("seller_order_detail", args=[order.order_number])

    def post_update(self, order, **data):
        payload = {"status": FulfillmentStatus.UNFULFILLED, "carrier": "", "tracking_number": ""}
        payload.update(data)
        return self.client.post(self.url(order), payload)

    def snapshot(self, fulfillment):
        fulfillment.refresh_from_db()
        return (fulfillment.status, fulfillment.carrier, fulfillment.tracking_number,
                fulfillment.shipped_at)

    # -- authentication / access --------------------------------------------

    def test_anonymous_user_is_sent_to_login(self):
        response = self.client.get(self.url(self.order))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("login")))

    def test_anonymous_post_is_sent_to_login_and_changes_nothing(self):
        before = self.snapshot(self.alice_f)
        response = self.post_update(self.order, carrier="DHL")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("login")))
        self.assertEqual(self.snapshot(self.alice_f), before)

    def test_non_seller_is_forbidden(self):
        self.client.force_login(self.buyer)
        self.assertEqual(self.client.get(self.url(self.order)).status_code, 403)
        before = self.snapshot(self.alice_f)
        self.assertEqual(self.post_update(self.order, carrier="DHL").status_code, 403)
        self.assertEqual(self.snapshot(self.alice_f), before)

    def test_seller_can_open_an_order_containing_their_items(self):
        self.client.force_login(self.alice)
        response = self.client.get(self.url(self.order))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.order.order_number)

    def test_other_sellers_order_is_not_found(self):
        self.client.force_login(self.alice)
        self.assertEqual(self.client.get(self.url(self.bob_only_order)).status_code, 404)
        before = self.snapshot(self.bob_only_f)
        response = self.post_update(self.bob_only_order, status=FulfillmentStatus.FULFILLED,
                                    carrier="DHL")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.snapshot(self.bob_only_f), before)

    def test_unknown_order_number_is_not_found(self):
        self.client.force_login(self.alice)
        response = self.client.get(reverse("seller_order_detail", args=["PS-0000-000000"]))
        self.assertEqual(response.status_code, 404)

    # -- seller isolation on a shared order ----------------------------------

    def test_shared_order_shows_only_own_items_subtotal_and_fulfilment(self):
        self.client.force_login(self.alice)
        response = self.client.get(self.url(self.order))
        self.assertEqual(response.status_code, 200)

        self.assertContains(response, "Alice Fulfil Vase")
        self.assertNotContains(response, "Bob Fulfil Stool")
        self.assertContains(response, money_filter(Decimal("40.00")))  # Alice's subtotal
        self.assertEqual(response.context["seller_subtotal"], Decimal("40.00"))
        self.assertEqual(response.context["fulfillment"], self.alice_f)

        self.assertContains(response, "SF Express")
        self.assertContains(response, "SF-ALICE-1")
        self.assertNotContains(response, "FedEx")
        self.assertNotContains(response, "FX-BOB-999")
        # The parent commercial total (70.00) is not part of the seller view.
        self.assertNotContains(response, money_filter(Decimal("70.00")))

    # -- dashboard link ------------------------------------------------------

    def test_dashboard_incoming_line_links_to_seller_order_detail(self):
        self.client.force_login(self.alice)
        response = self.client.get(reverse("seller_dashboard"))
        self.assertContains(response, f'href="{self.url(self.order)}"')
        self.assertNotContains(response, f'href="{self.url(self.bob_only_order)}"')

    # -- valid update --------------------------------------------------------

    def test_valid_update_goes_through_service_and_syncs_parent(self):
        self.client.force_login(self.alice)
        bob_before = self.snapshot(self.bob_f)
        self.order.carrier, self.order.tracking_number = "LEGACY-CARRIER", "LEGACY-TRACK"
        self.order.save(update_fields=["carrier", "tracking_number"])

        response = self.post_update(self.order, status=FulfillmentStatus.FULFILLED,
                                    carrier="ZTO", tracking_number="ZTO-123")
        # Not fetched here: that GET would consume the one-time success message.
        self.assertRedirects(response, self.url(self.order), fetch_redirect_response=False)

        self.alice_f.refresh_from_db()
        self.assertEqual(self.alice_f.status, FulfillmentStatus.FULFILLED)
        self.assertEqual(self.alice_f.carrier, "ZTO")
        self.assertEqual(self.alice_f.tracking_number, "ZTO-123")
        self.assertIsNotNone(self.alice_f.shipped_at)  # service sets it on first FULFILLED

        self.assertEqual(self.snapshot(self.bob_f), bob_before)

        self.order.refresh_from_db()
        # Alice fulfilled, Bob still unfulfilled -> service aggregates to PARTIAL.
        self.assertEqual(self.order.fulfillment_status, FulfillmentStatus.PARTIAL)
        # Seller writes never touch the parent's legacy carrier/tracking fields.
        self.assertEqual(self.order.carrier, "LEGACY-CARRIER")
        self.assertEqual(self.order.tracking_number, "LEGACY-TRACK")

        page = self.client.get(response["Location"])
        self.assertContains(page, "Fulfilment updated.")

    def test_single_seller_order_fully_fulfilled_syncs_parent_to_fulfilled(self):
        alice_only = self.make_order()
        self.make_order_item(alice_only, self.alice_product)
        SellerFulfillment.objects.create(order=alice_only, maker=self.alice_maker)
        self.client.force_login(self.alice)

        self.post_update(alice_only, status=FulfillmentStatus.FULFILLED)
        alice_only.refresh_from_db()
        self.assertEqual(alice_only.fulfillment_status, FulfillmentStatus.FULFILLED)

    def test_tracking_only_update_leaves_shipped_at_unset(self):
        self.client.force_login(self.alice)
        self.post_update(self.order, status=FulfillmentStatus.UNFULFILLED,
                         carrier="EMS", tracking_number="EMS-1")
        self.alice_f.refresh_from_db()
        self.assertEqual(self.alice_f.tracking_number, "EMS-1")
        self.assertIsNone(self.alice_f.shipped_at)

    # -- invalid input -------------------------------------------------------

    def assert_rejected_without_change(self, **data):
        self.client.force_login(self.alice)
        alice_before, bob_before = self.snapshot(self.alice_f), self.snapshot(self.bob_f)
        parent_before = self.order.fulfillment_status

        response = self.post_update(self.order, **data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertContains(response, 'class="field-error"')
        self.assertEqual(self.snapshot(self.alice_f), alice_before)
        self.assertEqual(self.snapshot(self.bob_f), bob_before)
        self.order.refresh_from_db()
        self.assertEqual(self.order.fulfillment_status, parent_before)
        return response

    def test_invalid_status_is_rejected(self):
        response = self.assert_rejected_without_change(status="flying", carrier="DHL")
        self.assertIn("status", response.context["form"].errors)

    def test_over_length_carrier_is_rejected(self):
        response = self.assert_rejected_without_change(
            status=FulfillmentStatus.FULFILLED, carrier="X" * 81)
        self.assertIn("carrier", response.context["form"].errors)

    def test_over_length_tracking_number_is_rejected(self):
        response = self.assert_rejected_without_change(
            status=FulfillmentStatus.FULFILLED, tracking_number="X" * 81)
        self.assertIn("tracking_number", response.context["form"].errors)

    # -- missing SellerFulfillment ------------------------------------------

    def test_order_without_seller_fulfillment_is_readable_but_not_editable(self):
        legacy = self.make_order(carrier="LEGACY-CARRIER", tracking_number="LEGACY-TRACK")
        self.make_order_item(legacy, self.alice_product)
        self.client.force_login(self.alice)

        response = self.client.get(self.url(legacy))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alice Fulfil Vase")
        self.assertIsNone(response.context["fulfillment"])
        self.assertContains(response, "Fulfilment details are not available for this order.")
        self.assertNotContains(response, 'name="tracking_number"')
        # Parent fields are not presented as if they were this seller's own.
        self.assertNotContains(response, "LEGACY-CARRIER")
        self.assertNotContains(response, "LEGACY-TRACK")

    def test_post_without_seller_fulfillment_is_not_found_and_creates_nothing(self):
        legacy = self.make_order()
        self.make_order_item(legacy, self.alice_product)
        self.client.force_login(self.alice)

        response = self.post_update(legacy, status=FulfillmentStatus.FULFILLED, carrier="DHL")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(SellerFulfillment.objects.filter(order=legacy).exists())

    # -- CSRF ----------------------------------------------------------------

    def test_post_requires_csrf_token_rendered_by_the_form(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.alice)
        payload = {"status": FulfillmentStatus.FULFILLED, "carrier": "DHL",
                   "tracking_number": "DHL-1"}

        before = self.snapshot(self.alice_f)
        self.assertEqual(client.post(self.url(self.order), payload).status_code, 403)
        self.assertEqual(self.snapshot(self.alice_f), before)

        page = client.get(self.url(self.order))
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"',
                          page.content.decode()).group(1)
        response = client.post(self.url(self.order), {**payload, "csrfmiddlewaretoken": token})
        self.assertEqual(response.status_code, 302)
        self.alice_f.refresh_from_db()
        self.assertEqual(self.alice_f.carrier, "DHL")
        self.assertEqual(self.alice_f.status, FulfillmentStatus.FULFILLED)


@override_settings(
    STORAGES={
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class SellerDispatchEligibilityBrowserTests(TestCase):
    """CP-M6: the seller order page surfaces the service's dispatch rules as
    form errors (never a 500), and agrees with the seller API."""

    password = "Studio-owner-57!"

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.seller = User.objects.create_user(
            email="dispatch.seller@example.com", password=cls.password, is_seller=True)
        category = Category.objects.create(slug="dispatch-category", name="Dispatch Category")
        cls.maker = Maker.objects.create(
            slug="dispatch-maker", name="Dispatch Studio", owner=cls.seller,
            discipline="Ceramics", location="Singapore")
        cls.product = Product.objects.create(
            slug="dispatch-bowl", name="Dispatch Bowl", maker=cls.maker,
            category=category, price=Decimal("25.00"), stock_quantity=10, is_active=True)

    def setUp(self):
        self.client.force_login(self.seller)

    def make_order(self, *, status, payment_status):
        order = Order.objects.create(
            order_number=OrderNumberSequence.next_number(),
            status=status, payment_status=payment_status,
            customer_email="dispatch.buyer@example.com",
        )
        OrderItem.objects.create(
            order=order, product=self.product, maker=self.maker,
            product_slug=self.product.slug, product_name=self.product.name,
            maker_name=self.maker.name, unit_price=self.product.price, quantity=1,
            line_total=self.product.price,
        )
        fulfillment = SellerFulfillment.objects.create(order=order, maker=self.maker)
        return order, fulfillment

    def post(self, order, **data):
        payload = {"status": FulfillmentStatus.UNFULFILLED, "carrier": "", "tracking_number": ""}
        payload.update(data)
        return self.client.post(reverse("seller_order_detail", args=[order.order_number]), payload)

    @staticmethod
    def snapshot(fulfillment):
        row = SellerFulfillment.objects.get(pk=fulfillment.pk)
        return (row.status, row.carrier, row.tracking_number, row.shipped_at)

    def test_dispatching_an_ineligible_order_shows_a_form_error(self):
        cases = [("unpaid", OrderStatus.PENDING, PaymentStatus.UNPAID),
                 ("paid but cancelled", OrderStatus.CANCELLED, PaymentStatus.PAID)]
        for label, status, payment_status in cases:
            with self.subTest(order=label):
                order, fulfillment = self.make_order(status=status, payment_status=payment_status)
                response = self.post(order, status=FulfillmentStatus.FULFILLED,
                                     carrier="DHL", tracking_number="DHL-1")
                self.assertEqual(response.status_code, 200)
                self.assertIn("status", response.context["form"].errors)
                self.assertContains(response, "This order cannot be dispatched")
                self.assertContains(response, 'class="field-error"')
                self.assertEqual(self.snapshot(fulfillment),
                                 (FulfillmentStatus.UNFULFILLED, "", "", None))
                order.refresh_from_db()
                self.assertEqual(order.fulfillment_status, FulfillmentStatus.UNFULFILLED)

    def test_tracking_correction_after_a_refund_is_saved(self):
        order, fulfillment = self.make_order(status=OrderStatus.CONFIRMED,
                                             payment_status=PaymentStatus.REFUNDED)
        shipped_at = django_timezone.now() - timedelta(days=2)
        SellerFulfillment.objects.filter(pk=fulfillment.pk).update(
            status=FulfillmentStatus.FULFILLED, shipped_at=shipped_at,
            carrier="SF Express", tracking_number="OLD")

        response = self.post(order, status=FulfillmentStatus.FULFILLED,
                             carrier="SF Express", tracking_number="NEW")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.snapshot(fulfillment),
                         (FulfillmentStatus.FULFILLED, "SF Express", "NEW", shipped_at))

    def test_carrier_only_update_on_an_unpaid_order_is_saved(self):
        order, fulfillment = self.make_order(status=OrderStatus.PENDING,
                                             payment_status=PaymentStatus.UNPAID)
        response = self.post(order, carrier="DHL", tracking_number="DHL-5")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.snapshot(fulfillment),
                         (FulfillmentStatus.UNFULFILLED, "DHL", "DHL-5", None))

    def test_browser_and_api_reject_the_same_dispatch_identically(self):
        browser_order, browser_f = self.make_order(status=OrderStatus.PENDING,
                                                   payment_status=PaymentStatus.UNPAID)
        api_order, api_f = self.make_order(status=OrderStatus.PENDING,
                                           payment_status=PaymentStatus.UNPAID)

        browser = self.post(browser_order, status=FulfillmentStatus.FULFILLED)
        api_client = APIClient()
        api_client.force_authenticate(user=self.seller)
        api = api_client.patch(f"/api/seller/orders/{api_order.uuid}/fulfilment/",
                               data={"status": FulfillmentStatus.FULFILLED}, format="json")

        self.assertEqual(browser.status_code, 200)
        self.assertEqual(api.status_code, 400)
        self.assertEqual([str(e) for e in browser.context["form"].errors["status"]],
                         [str(e) for e in api.data["errors"]["status"]])
        self.assertEqual(self.snapshot(browser_f), self.snapshot(api_f))
        self.assertEqual(self.snapshot(api_f), (FulfillmentStatus.UNFULFILLED, "", "", None))


@override_settings(
    LANGUAGE_CODE="en", SECURE_SSL_REDIRECT=False,
    STORAGES={
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class CraftyChatbotTests(TestCase):
    def get_all_ids(self, html_content):
        """Extract all HTML element IDs from rendered HTML string."""
        return re.findall(r'\bid=["\']([^"\']+)["\']', html_content)

    def test_fullpage_chat_and_concierge_have_no_drawer_or_duplicate_ids(self):
        for path in (reverse("chat_page"), reverse("concierge_page")):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                html = response.content.decode("utf-8")

                # Must contain full-page workbench
                self.assertIn("crafty-fullpage", html)
                self.assertContains(response, 'id="crafty-messages"')
                self.assertContains(response, 'id="crafty-input"')
                self.assertContains(response, 'id="crafty-form"')
                self.assertContains(response, 'id="crafty-settings-modal"')

                # Must NOT contain the drawer partial elements
                self.assertNotContains(response, 'id="crafty-drawer"')
                self.assertNotContains(response, 'id="crafty-launcher"')
                self.assertNotContains(response, 'id="crafty-backdrop"')

                # Verify strictly zero duplicate IDs across entire page
                ids = self.get_all_ids(html)
                duplicate_ids = [id_val for id_val in set(ids) if ids.count(id_val) > 1]
                self.assertEqual(
                    duplicate_ids, [],
                    f"Found duplicate IDs on {path}: {duplicate_ids}"
                )

    def test_standard_pages_render_drawer_widget_without_duplicate_crafty_ids(self):
        for path in (reverse("home"), reverse("shop")):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                html = response.content.decode("utf-8")

                # Drawer widget elements must be present
                self.assertContains(response, 'id="crafty-drawer"')
                self.assertContains(response, 'id="crafty-launcher"')
                self.assertContains(response, 'id="crafty-messages"')
                self.assertContains(response, 'id="crafty-settings-modal"')

                # Fullpage container must NOT be present
                self.assertNotIn("crafty-fullpage", html)

                # Check all crafty-* IDs have no duplicates
                crafty_ids = [id_val for id_val in self.get_all_ids(html) if id_val.startswith("crafty-")]
                duplicate_crafty_ids = [id_val for id_val in set(crafty_ids) if crafty_ids.count(id_val) > 1]
                self.assertEqual(
                    duplicate_crafty_ids, [],
                    f"Found duplicate crafty IDs on {path}: {duplicate_crafty_ids}"
                )

    @patch("frontend.chatbot_service.call_gemini")
    def test_chat_api_endpoint(self, mock_gemini):
        mock_gemini.return_value = {"status": "ok", "reply": "Hello from mock artisan"}
        user = get_user_model().objects.create_user(email="concierge.tester@example.com", password="Pass-123-word!")
        self.client.force_login(user)
        response = self.client.post(
            reverse("chat_api"),
            data=json.dumps({"message": "Hello Crafty"}),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertIn("reply", data)

    def test_chat_api_requires_authentication(self):
        response = self.client.post(
            reverse("chat_api"),
            data=json.dumps({"message": "Hello Crafty"}),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertEqual(data.get("status"), "error")

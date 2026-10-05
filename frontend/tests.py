"""Browser account registration, login, profile and password tests."""

import json
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
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
from django.utils.html import escape

from orders.models import Order

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
        response = self.client.post(
            reverse("chat_api"),
            data=json.dumps({"message": "Hello Crafty"}),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertIn("reply", data)


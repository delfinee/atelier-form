"""Browser account profile, password-change and password-reset tests."""

import re
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import HASH_SESSION_KEY, SESSION_KEY, get_user_model
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.tokens import default_token_generator
from django.contrib.messages import get_messages
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse


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
            response, f'{reverse("login")}?next={self.password_url}', fetch_redirect_response=False,
        )
        self.assert_password_unchanged()

    def test_password_change_requires_post(self):
        response = self.client.get(self.password_url)
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.headers["Allow"], "POST")
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

"""Browser account profile and password-change regression tests."""

from django.conf import settings
from django.contrib.auth import HASH_SESSION_KEY, SESSION_KEY, get_user_model
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.messages import get_messages
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

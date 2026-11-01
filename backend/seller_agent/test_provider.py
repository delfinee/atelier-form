from unittest.mock import patch
from django.conf import settings
from django.test import TestCase, override_settings
from .models import ProviderSecret
from . import provider, planner


@override_settings(SELLER_AGENT_API_KEY='', SELLER_AGENT_USE_LLM=False,
                   SECRET_KEY='test-deployment-encryption-key')
class ProviderTests(TestCase):
    def test_stored_key_is_encrypted_and_works_in_shared_mode(self):
        key = 'test-private-provider-key-123456789'
        encrypted = provider.encrypt_key(key)
        self.assertNotIn(key, encrypted)
        ProviderSecret.objects.create(provider='deepseek', encrypted_key=encrypted)
        self.assertEqual(provider.api_key(), key)
        self.assertTrue(planner.enabled(shared_demo=True))
        self.assertFalse(planner.enabled())
        with override_settings(SECRET_KEY='another-deployment-key'):
            self.assertEqual(provider.api_key(), '')
        with override_settings(SELLER_AGENT_API_KEY='environment-key'):
            self.assertEqual(provider.api_key(), 'environment-key')

    def test_rotation_and_status_do_not_expose_key(self):
        key = 'test-private-provider-key-123456789'
        ProviderSecret.objects.create(provider='deepseek', encrypted_key=provider.encrypt_key(key))
        with override_settings(SECRET_KEY='new-key', SECRET_KEY_FALLBACKS=[settings.SECRET_KEY]):
            self.assertEqual(provider.api_key(), key)
        with override_settings(ALLOWED_HOSTS=['testserver'], SECURE_SSL_REDIRECT=False):
            response = self.client.get('/api/seller-agent/v1/status/')
            self.assertNotContains(response, key)

    @override_settings(ALLOWED_HOSTS=['testserver'], SECURE_SSL_REDIRECT=False)
    def test_provider_configuration_has_no_public_write_route(self):
        self.assertEqual(self.client.get('/api/seller-provider-setup/').status_code, 404)
        self.assertEqual(self.client.post('/api/seller-provider-setup/', {}).status_code, 404)

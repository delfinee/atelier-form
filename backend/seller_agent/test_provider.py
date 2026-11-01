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

    def test_temporary_setup_requires_secret_and_cannot_overwrite(self):
        import hashlib
        token = 'test-private-setup-token'
        options = dict(ALLOWED_HOSTS=['dip-new-repo.vercel.app'], SECURE_SSL_REDIRECT=False)
        with override_settings(**options), patch('seller_agent.bootstrap.TOKEN_HASH', hashlib.sha256(token.encode()).hexdigest()), patch('seller_agent.bootstrap.EXPIRES', 9999999999):
            url = '/api/seller-provider-setup/'
            self.assertEqual(self.client.get(url, HTTP_HOST='dip-new-repo.vercel.app').status_code, 404)
            self.assertEqual(self.client.post(url, {}, HTTP_HOST='dip-new-repo.vercel.app').status_code, 404)
            result = self.client.post(url, {'api_key':'test-provider-key-123456'}, content_type='application/json',
                HTTP_HOST='dip-new-repo.vercel.app', HTTP_AUTHORIZATION='Bearer '+token)
            self.assertEqual(result.status_code, 201)
            result = self.client.post(url, {'api_key':'another-provider-key-9999'}, content_type='application/json',
                HTTP_HOST='dip-new-repo.vercel.app', HTTP_AUTHORIZATION='Bearer '+token)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(provider.api_key(), 'test-provider-key-123456')

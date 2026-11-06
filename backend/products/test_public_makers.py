from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from frontend import services
from orders.tests.factories import make_category, make_maker, make_product
from products.makers import public_makers
from products.models import Maker


@override_settings(
    ALLOWED_HOSTS=['testserver', 'school.test'], SECURE_SSL_REDIRECT=False,
    SELLER_SHARED_DEMO_ENABLED=False, SELLER_SHARED_DEMO_HOSTS=['school.test'],
    SELLER_AGENT_ENABLED=True, SELLER_AGENT_USE_LLM=False, SELLER_AGENT_API_KEY='',
    STORAGES={**settings.STORAGES, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}},
)
class PublicMakerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.chen = make_maker('chen-meilin', 'chen mei lin')
        cls.lu = make_maker('lu-wenjing', 'Lu Wenjing')
        cls.xu = make_maker('xu-anying', 'Xu Anying')
        Maker.objects.filter(pk__in=[cls.chen.pk, cls.lu.pk, cls.xu.pk]).update(is_featured=True)
        cls.cai = make_maker('cai-store', 'cai store')
        cls.actor = get_user_model().objects.create_user(email=settings.SELLER_SHARED_DEMO_EMAIL,
            password=None, first_name='School', last_name='Demo', is_seller=True)
        cls.school = make_maker(settings.SELLER_SHARED_DEMO_SHOP, 'School Demo', owner=cls.actor)
        cls.tester = make_maker('seller-tester', 'Seller Tester')
        cls.category = make_category('ceramics', 'Ceramics')
        cls.product = make_product(maker=cls.school, category=cls.category, slug='keep-demo-cup')

    def test_public_query_excludes_internal_accounts_without_changing_records(self):
        self.assertEqual(set(public_makers().values_list('slug', flat=True)),
                         {'chen-meilin', 'lu-wenjing', 'xu-anying', 'cai-store'})
        self.school.refresh_from_db()
        self.assertTrue(self.school.is_active)
        self.assertEqual(self.school.owner_id, self.actor.pk)
        self.assertTrue(self.school.products.filter(pk=self.product.pk).exists())

    def test_homepage_restores_chen_and_lu_in_both_languages(self):
        for language in ['en', 'zh-hans']:
            response = self.client.get('/', HTTP_ACCEPT_LANGUAGE=language)
            self.assertEqual([m.slug for m in response.context['makers']], ['chen-meilin', 'lu-wenjing'])
            self.assertNotContains(response, 'School Demo')

    def test_makers_page_and_api_keep_real_sellers(self):
        page = self.client.get('/makers/')
        self.assertNotContains(page, 'School Demo')
        self.assertNotContains(page, 'Seller Tester')
        self.assertContains(page, 'cai store')
        response = self.client.get('/api/makers/').json()
        rows = response.get('items', response.get('results', []))
        self.assertEqual([m['slug'] for m in rows], ['cai-store', 'chen-meilin', 'lu-wenjing', 'xu-anying'])

    def test_internal_profile_routes_are_not_public(self):
        for path in [f'/makers/{self.school.slug}/', f'/api/makers/{self.school.slug}/',
                     f'/api/makers/{self.school.slug}/products/']:
            self.assertEqual(self.client.get(path).status_code, 404, path)
        self.assertEqual(self.client.get('/api/makers/chen-meilin/').status_code, 200)

    def test_search_does_not_suggest_internal_profile(self):
        self.assertEqual(services.search('School Demo')['makers'], [])
        self.assertEqual(services.search('Seller Tester')['makers'], [])

    def test_configured_account_remains_hidden_after_renaming(self):
        self.school.slug, self.school.name = 'renamed-internal', 'Internal actor'
        self.school.save()
        self.assertNotIn(self.school.pk, public_makers().values_list('pk', flat=True))

    def test_shared_workspace_and_its_existing_product_stay_available(self):
        visitor = Client(HTTP_HOST='school.test')
        snapshot = visitor.get('/api/seller-agent/v1/snapshot/').json()
        self.assertIn(self.product.slug, [p['slug'] for p in snapshot['products']])
        self.assertEqual(self.client.get('/api/products/keep-demo-cup/').status_code, 200)

from django.test import Client, TestCase, override_settings
from django.conf import settings
from orders.tests.factories import make_seller_user
from config.seller_phone import TEMPLATES as PHONE_TEMPLATES
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from imagery.models import SiteImage
from orders.tests.factories import make_category, make_maker, make_product


@override_settings(ROOT_URLCONF='config.seller_phone_urls', DEBUG=False,
    ALLOWED_HOSTS=['phone.test'], SELLER_AGENT_ENABLED=True, WECHAT_SELLER_ENABLED=True,
    WECHAT_SELLER_DEV_LOGIN=False, WECHAT_APP_SECRET='', SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True, LOGIN_URL='/account/login/',
    LOGIN_REDIRECT_URL='/seller/ai/', TEMPLATES=PHONE_TEMPLATES,
    STORAGES={**settings.STORAGES, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class PhonePreviewTests(TestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST='phone.test')

    def test_phone_host_exposes_only_agent_and_linking_routes(self):
        for path in ('/admin/', '/checkout/', '/api/auth/register/', '/seller/ai/mini-preview/'):
            self.assertEqual(self.client.get(path, secure=True).status_code, 404)

    def test_no_public_developer_identity_or_private_snapshot(self):
        response = self.client.post('/api/seller-agent/v1/session/developer/', {}, secure=True)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get('/api/seller-agent/v1/snapshot/', secure=True).status_code, 401)
        self.assertEqual(self.client.post('/api/seller-agent/v1/session/login/',
            {'code':'unconfigured'}, secure=True).status_code, 503)

    def test_account_link_requires_login_and_https_login_form_has_csrf(self):
        response = self.client.get('/seller/ai/link/', secure=True)
        self.assertContains(response, '/account/login/?next=/seller/ai/link/')
        client = Client(HTTP_HOST='phone.test', enforce_csrf_checks=True)
        self.assertContains(client.get('/account/login/', secure=True), 'csrfmiddlewaretoken')
        self.assertEqual(client.post('/account/login/', {'username':'x', 'password':'y'}, secure=True).status_code, 403)

    def test_existing_seller_can_sign_in_without_external_next_redirect(self):
        user = make_seller_user('phone@test.invalid')
        user.set_password('only-a-test-password')
        user.save()
        response = self.client.post('/account/login/?next=https://other.invalid/',
            {'username':user.email,'password':'only-a-test-password','next':'https://other.invalid/'}, secure=True)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('other.invalid', response['Location'])
        self.assertContains(self.client.get('/seller/ai/link/', secure=True), user.email)

    def editor_fixture(self):
        user = make_seller_user('editor@test.invalid')
        maker = make_maker('editor', 'Editor', owner=user)
        category = make_category()
        product = make_product(maker=maker, category=category, slug='editor-mug')
        self.client.force_login(user)
        return maker, category, product

    def editor_payload(self, category, **extra):
        image = BytesIO()
        Image.new('RGB', (24, 30), '#407050').save(image, 'PNG')
        return {'name': 'Edited mug', 'category': category.pk, 'price': '25.50',
            'stock_quantity': '7', 'is_active': 'on',
            'product_variants-TOTAL_FORMS': '1', 'product_variants-INITIAL_FORMS': '0',
            'product_variants-0-group': 'size', 'product_variants-0-label': 'Small',
            'product_variants-0-sku': 'EDITOR-SMALL', 'product_variants-0-stock_quantity': '3',
            'product_variants-0-is_active': 'on',
            'product_images-TOTAL_FORMS': '1', 'product_images-INITIAL_FORMS': '0',
            'product_images-0-sort_order': '0', 'product_images-0-is_primary': 'on',
            'product_images-0-upload': SimpleUploadedFile('photo.png', image.getvalue(), 'image/png'), **extra}

    def test_phone_editor_saves_photo_options_and_publication(self):
        maker, category, product = self.editor_fixture()
        path = '/seller/products/editor-mug/edit/'
        self.assertContains(self.client.get(path, secure=True), 'multipart/form-data')
        response = self.client.post(path, self.editor_payload(category), secure=True)
        self.assertEqual(response.status_code, 302)
        product.refresh_from_db()
        self.assertTrue(product.is_active)
        self.assertEqual(str(product.price), '25.50')
        self.assertEqual(product.product_variants.get().stock_quantity, 3)
        photo = SiteImage.objects.get(name=product.product_images.get().image)
        self.assertEqual(photo.content_type, 'image/jpeg')
        self.assertEqual((photo.width, photo.height), (24, 30))
        self.assertContains(self.client.get('/seller/products/', secure=True), 'Edited mug')
        response = self.client.get('/img/' + photo.name + '.jpg', secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/jpeg')

    def test_invalid_form_never_saves_photo_or_partial_product_changes(self):
        maker, category, product = self.editor_fixture()
        response = self.client.post('/seller/products/editor-mug/edit/',
            self.editor_payload(category, price='-1'), secure=True)
        self.assertEqual(response.status_code, 200)
        product.refresh_from_db()
        self.assertEqual(str(product.price), '20.00')
        self.assertFalse(SiteImage.objects.exists())
        self.assertFalse(product.product_variants.exists())

    def test_fake_image_rejected_and_editor_is_owner_scoped(self):
        maker, category, product = self.editor_fixture()
        payload = self.editor_payload(category)
        payload['product_images-0-upload'] = SimpleUploadedFile('fake.png', b'<script>bad</script>', 'image/png')
        response = self.client.post('/seller/products/editor-mug/edit/', payload, secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(SiteImage.objects.exists())
        other = make_maker('other-editor', 'Other', owner=make_seller_user('other-editor@test.invalid'))
        make_product(maker=other, category=category, slug='other-editor-mug')
        self.assertEqual(self.client.post('/seller/products/other-editor-mug/edit/',
            self.editor_payload(category), secure=True).status_code, 404)
        maker.is_active = False
        maker.save()
        self.assertEqual(self.client.get('/seller/products/editor-mug/edit/', secure=True).status_code, 403)

    def test_oversized_image_is_rejected_without_saving(self):
        maker, category, product = self.editor_fixture()
        payload = self.editor_payload(category)
        valid = payload['product_images-0-upload'].read()
        payload['product_images-0-upload'] = SimpleUploadedFile('large.png', valid + b'\0' * (5 * 1024 * 1024), 'image/png')
        self.assertContains(self.client.post('/seller/products/editor-mug/edit/', payload, secure=True), 'smaller than 5 MB')
        self.assertFalse(SiteImage.objects.exists())

    def test_source_bundle_requires_seller_and_streams_only_fixed_file(self):
        self.assertEqual(self.client.get('/seller/download/', secure=True).status_code, 302)
        self.editor_fixture()
        with TemporaryDirectory() as directory, override_settings(BASE_DIR=Path(directory)):
            self.assertEqual(self.client.get('/seller/download/', secure=True).status_code, 404)
            bundle = Path(directory) / '.seller-agent-runtime/delivery/Atelier-Form-Seller-WeChat.zip'
            bundle.parent.mkdir(parents=True)
            bundle.write_bytes(b'PK-acceptance-fixture')
            response = self.client.get('/seller/download/', secure=True)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b''.join(response.streaming_content), b'PK-acceptance-fixture')
            self.assertEqual(response['Cache-Control'], 'private, no-store')

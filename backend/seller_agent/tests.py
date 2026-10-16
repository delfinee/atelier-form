from datetime import timedelta
from unittest.mock import Mock, patch
from uuid import uuid4
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, Client, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from products.models import Product, ProductVariant
from orders.models import SellerFulfillment, PaymentStatus, OrderStatus
from orders.tests.factories import make_category, make_maker, make_seller_user, make_buyer, make_product, make_bare_order, make_order_item
from .models import Conversation, Change, WechatIdentity, WechatSession, LinkTicket
from .auth import digest

BASE='/api/seller-agent/v1/'


@override_settings(SELLER_AGENT_ENABLED=True, SELLER_AGENT_USE_LLM=False, WECHAT_SELLER_ENABLED=True,
    WECHAT_SELLER_DEV_LOGIN=True, DEBUG=True, ALLOWED_HOSTS=['testserver','127.0.0.1','localhost','public.test'])
class SellerAgentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.seller=make_seller_user('seller@test.invalid')
        cls.other=make_seller_user('other@test.invalid')
        cls.buyer=make_buyer('new-seller@test.invalid')
        cls.maker=make_maker('studio','Studio',owner=cls.seller)
        cls.other_maker=make_maker('other','Other',owner=cls.other)
        cls.category=make_category('ceramics','Ceramics')
        cls.product=make_product(maker=cls.maker,category=cls.category,slug='blue-bowl',name='Blue Bowl',stock_quantity=10)
        cls.foreign=make_product(maker=cls.other_maker,category=cls.category,slug='foreign-bowl')
        cls.option_product=make_product(maker=cls.maker,category=cls.category,slug='cup',name='Cup')
        cls.variant=ProductVariant.objects.create(product=cls.option_product,label='Blue',sku='BLUE',stock_quantity=2)
        cls.high_variant=ProductVariant.objects.create(product=cls.option_product,label='Red',sku='RED',stock_quantity=80)

    def setUp(self):
        cache.clear()
        self.web=APIClient()
        self.web.force_authenticate(self.seller)
        self.c=self.web.post(BASE+'conversations/',{},format='json').data['id']
        self.path=BASE+'conversations/'+self.c+'/'

    def prepare(self,action='stock',target='blue-bowl',values=None,request_id=None):
        r=self.web.post(self.path+'changes/',{'request_id':request_id or str(uuid4()),'action':action,
            'target':target,'values':values if values is not None else {'quantity':5}},format='json')
        self.assertEqual(r.status_code,200,r.data)
        return r.data

    def confirm(self,d,client=None,**body):
        return (client or self.web).post(BASE+f"changes/{d['id']}/confirm/",body or {'confirmed':True},format='json')

    def mini(self):
        client=APIClient(HTTP_HOST='127.0.0.1:8780')
        session=client.post(BASE+'session/developer/',{},format='json')
        self.assertEqual(session.status_code,201,session.data)
        client.credentials(HTTP_AUTHORIZATION='SellerWechat '+session.data['token'])
        return client,session.data

    def link(self,client,user=None):
        ticket=client.post(BASE+'link/start/',{},format='json').data
        self.web.force_authenticate(user or self.seller)
        response=self.web.post(BASE+'link/approve/',{'token':ticket['url'].split('#token=')[1],
            'verification_code':ticket['verification_code'],'confirmed':True},format='json')
        self.assertEqual(response.status_code,200,response.data)
        return ticket

    def message(self,text,client=None,request_id=None):
        return (client or self.web).post(self.path+'messages/',{'request_id':request_id or str(uuid4()),'text':text},format='json')

    def test_developer_session_never_provisions_a_user_or_shop(self):
        users=get_user_model().objects.count()
        client,session=self.mini()
        self.assertEqual(get_user_model().objects.count(),users)
        self.assertIsNone(WechatIdentity.objects.get().user_id)
        self.assertEqual(WechatSession.objects.get().token_hash,digest(session['token']))
        self.assertFalse(client.get(BASE+'me/').data['linked'])
        self.assertEqual(client.get(BASE+'snapshot/').status_code,403)
        self.assertEqual(client.post(BASE+'conversations/',{},format='json').status_code,403)

    def test_developer_login_not_exposed_on_public_host_or_production(self):
        for options in ({'HTTP_HOST':'public.test'}, {'HTTP_HOST':'127.0.0.1','REMOTE_ADDR':'192.0.2.4'}):
            self.assertEqual(APIClient(**options).post(BASE+'session/developer/',{},format='json').status_code,403)
        with override_settings(DEBUG=False):
            self.assertEqual(APIClient(HTTP_HOST='127.0.0.1').post(BASE+'session/developer/',{},format='json').status_code,403)

    def test_binding_requires_website_auth_explicit_approval_and_matching_code(self):
        mini,_=self.mini()
        ticket=mini.post(BASE+'link/start/',{},format='json').data
        body={'token':ticket['url'].split('#token=')[1],'verification_code':ticket['verification_code'],'confirmed':True}
        self.assertIn(mini.post(BASE+'link/approve/',body,format='json').status_code,(401,403))
        self.assertEqual(self.web.post(BASE+'link/approve/',{**body,'confirmed':False},format='json').status_code,400)
        self.assertEqual(self.web.post(BASE+'link/approve/',{**body,'verification_code':'AAAAAA'},format='json').status_code,400)
        self.assertEqual(self.web.post(BASE+'link/approve/',body,format='json').status_code,200)
        self.assertEqual(self.web.post(BASE+'link/approve/',body,format='json').status_code,400)
        self.assertTrue(mini.get(BASE+'me/').data['is_seller'])
        self.assertEqual(mini.post(BASE+'link/start/',{},format='json').status_code,400)

    def test_expired_link_and_unlink_revoke_all_sessions(self):
        mini,_=self.mini()
        ticket=mini.post(BASE+'link/start/',{},format='json').data
        LinkTicket.objects.update(expires_at=timezone.now()-timedelta(seconds=1))
        body={'token':ticket['url'].split('#token=')[1],'verification_code':ticket['verification_code'],'confirmed':True}
        self.assertEqual(self.web.post(BASE+'link/approve/',body,format='json').status_code,400)
        self.link(mini)
        identity=WechatIdentity.objects.get()
        self.assertEqual(self.web.post(BASE+f'links/{identity.uuid}/unlink/',{'confirmed':True},format='json').status_code,200)
        self.assertEqual(mini.get(BASE+'me/').status_code,401)
        identity.refresh_from_db()
        self.assertIsNone(identity.user_id)

    @override_settings(WECHAT_APP_ID='test-app',WECHAT_APP_SECRET='not-a-real-secret')
    @patch('seller_agent.wechat.requests.get')
    def test_real_login_adapter_does_not_grant_seller_role_or_return_secrets(self,get):
        get.return_value=Mock()
        get.return_value.json.return_value={'openid':'private-openid','session_key':'private-session-key'}
        client=APIClient()
        r=client.post(BASE+'session/login/',{'code':'one-time'},format='json')
        self.assertEqual(r.status_code,200,r.data)
        self.assertFalse(r.data['linked'])
        self.assertNotIn('private',str(r.data))
        self.assertIsNone(WechatIdentity.objects.get().user_id)
        self.assertEqual(client.post(BASE+'session/login/',{'code':'one-time'},format='json').status_code,401)
        self.assertEqual(get.call_count,1)

    @override_settings(WECHAT_APP_ID='test-app',WECHAT_APP_SECRET='not-a-real-secret')
    @patch('seller_agent.wechat.requests.get')
    def test_invalid_appsecret_reports_server_configuration_without_leaking_upstream_data(self,get):
        get.return_value=Mock()
        get.return_value.json.return_value={'errcode':40125,'errmsg':'invalid appsecret, private-upstream-details'}
        response=APIClient().post(BASE+'session/login/',{'code':'fresh-code'},format='json')
        self.assertEqual(response.status_code,503)
        self.assertIn('server AppSecret',str(response.data))
        self.assertNotIn('private-upstream-details',str(response.data))
        self.assertFalse(WechatSession.objects.exists())
        self.assertFalse(WechatIdentity.objects.exists())

    @override_settings(WECHAT_APP_ID='',WECHAT_APP_SECRET='')
    def test_missing_official_access_is_reported_as_blocked_not_simulated(self):
        self.assertFalse(self.web.get(BASE+'status/').data['wechat_configured'])
        self.assertEqual(APIClient().post(BASE+'session/login/',{'code':'x'},format='json').status_code,503)
        self.assertFalse(WechatSession.objects.exists())

    def test_same_conversation_and_data_in_both_channels(self):
        mini,_=self.mini()
        self.link(mini)
        self.assertEqual(mini.get(self.path).status_code,200)
        r=self.message('my products',client=mini)
        self.assertEqual(r.status_code,200,r.data)
        self.assertNotIn('foreign-bowl',[p['slug'] for p in r.data['products']])
        self.assertEqual(self.web.get(self.path).data['messages'][0]['channel'],'developer')
        d=self.prepare()
        self.assertEqual(self.confirm(d,client=mini).status_code,200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity,5)
        self.assertEqual(self.web.get(self.path).data['changes'][0]['confirmed_channel'],'developer')

    def test_other_seller_cannot_read_or_confirm(self):
        d=self.prepare()
        self.web.force_authenticate(self.other)
        self.assertEqual(self.web.get(self.path).status_code,404)
        self.assertEqual(self.confirm(d).status_code,404)
        other_c=self.web.post(BASE+'conversations/',{},format='json').data['id']
        r=self.web.post(BASE+f'conversations/{other_c}/changes/',{'request_id':str(uuid4()),'action':'stock',
            'target':'blue-bowl','values':{'quantity':500}},format='json')
        self.assertEqual(r.status_code,404)

    def test_preview_does_not_change_stock_and_confirmation_is_idempotent(self):
        request_id=str(uuid4())
        d=self.prepare(request_id=request_id)
        self.assertEqual(self.prepare(request_id=request_id)['id'],d['id'])
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity,10)
        self.assertEqual(self.confirm(d,confirmed=False).status_code,400)
        first=self.confirm(d)
        self.assertEqual(first.status_code,200,first.data)
        self.assertEqual(self.confirm(d).data,first.data)
        self.assertEqual(Change.objects.count(),1)

    def test_stale_stock_superseded_preview_and_expiry_rejected(self):
        d=self.prepare()
        Product.objects.filter(pk=self.product.pk).update(stock_quantity=7)
        self.assertEqual(self.confirm(d).status_code,400)
        fresh=self.prepare(values={'quantity':8})
        self.assertEqual(self.confirm(d).status_code,400)
        Change.objects.filter(uuid=fresh['id']).update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.confirm(fresh).status_code,400)

    def test_variant_inventory_is_authoritative_and_low_option_is_visible(self):
        r=self.web.post(self.path+'changes/',{'request_id':str(uuid4()),'action':'stock','target':'cup','values':{'quantity':4}},format='json')
        self.assertEqual(r.status_code,400)
        d=self.prepare(target='cup',values={'quantity':4,'variant':str(self.variant.uuid)})
        self.assertEqual(self.confirm(d).status_code,200)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity,4)
        r=self.message('low stock')
        self.assertIn('cup',[p['slug'] for p in r.data['products']])

    def test_made_to_order_does_not_report_synthetic_stock_as_real_inventory(self):
        Product.objects.filter(pk=self.product.pk).update(is_made_to_order=True)
        result=self.message('my products')
        product=next(p for p in result.data['products'] if p['slug']=='blue-bowl')
        self.assertIsNone(product['quantity'])
        self.assertTrue(product['made_to_order'])

    def test_price_change_and_privilege_fields(self):
        d=self.prepare(action='price',values={'price':'35.50'})
        self.assertEqual(self.confirm(d).status_code,200)
        self.product.refresh_from_db()
        self.assertEqual(str(self.product.price),'35.50')
        r=self.web.post(self.path+'changes/',{'request_id':str(uuid4()),'action':'stock','target':'blue-bowl',
            'values':{'quantity':4,'maker':self.other_maker.pk}},format='json')
        self.assertEqual(r.status_code,400)

    def test_new_seller_collects_draft_without_escalating_permissions(self):
        self.web.force_authenticate(self.buyer)
        self.c=self.web.post(BASE+'conversations/',{},format='json').data['id']
        self.path=BASE+'conversations/'+self.c+'/'
        self.assertEqual(self.message('new listing').data['missing'][0],'name')
        r=self.message('name=My Mug; category=ceramics; description=Handmade mug; price=20; quantity=3')
        self.assertEqual(r.status_code,200,r.data)
        self.assertNotIn('change',r.data)
        self.assertFalse(Change.objects.exists())
        self.buyer.refresh_from_db()
        self.assertFalse(self.buyer.is_seller)

    def test_listing_creates_only_unpublished_product_after_confirmation(self):
        r=self.message('name=My Mug; category=ceramics; description=Handmade mug; price=20; quantity=3')
        self.assertEqual(r.status_code,200,r.data)
        self.assertFalse(Product.objects.filter(name='My Mug').exists())
        self.assertEqual(self.confirm(r.data['change']).status_code,200)
        p=Product.objects.get(name='My Mug')
        self.assertEqual(p.maker_id,self.maker.pk)
        self.assertFalse(p.is_active)
        self.assertEqual(p.stock_quantity,3)

    def test_guided_message_retry_creates_one_preview(self):
        key=str(uuid4())
        a=self.message('set stock Blue Bowl to 6',request_id=key)
        b=self.message('set stock Blue Bowl to 6',request_id=key)
        self.assertEqual(a.status_code,200,a.data)
        self.assertEqual(a.data,b.data)
        self.assertEqual(Change.objects.count(),1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity,10)

    def test_new_listing_starts_fresh_instead_of_reusing_previous_details(self):
        self.message('name=Earlier Mug; category=ceramics; description=Handmade; price=20; quantity=3')
        response=self.message('new listing')
        self.assertEqual(response.data['listing'],{})
        self.assertEqual(response.data['missing'][0],'name')
        self.assertNotIn('change',response.data)

    def test_revoked_seller_role_blocks_an_existing_preview(self):
        d=self.prepare()
        get_user_model().objects.filter(pk=self.seller.pk).update(is_seller=False)
        self.assertEqual(self.confirm(d).status_code,403)

    def order(self,paid=True):
        order=make_bare_order(status=OrderStatus.CONFIRMED,payment_status=PaymentStatus.PAID if paid else PaymentStatus.UNPAID)
        make_order_item(order=order,product=self.product)
        make_order_item(order=order,product=self.foreign)
        a=SellerFulfillment.objects.create(order=order,maker=self.maker)
        b=SellerFulfillment.objects.create(order=order,maker=self.other_maker)
        return order,a,b

    def test_multi_seller_fulfillment_preserves_parent_and_other_seller(self):
        order,a,b=self.order()
        rows=self.message('my orders').data['orders']
        self.assertEqual(len(rows),1)
        self.assertEqual(len(rows[0]['items']),1)
        d=self.prepare('fulfillment',str(order.uuid),{'carrier':'Test Courier','tracking_number':'TEST123456'})
        self.assertEqual(self.confirm(d).status_code,200)
        order.refresh_from_db();a.refresh_from_db();b.refresh_from_db()
        self.assertEqual(a.status,'fulfilled')
        self.assertEqual(b.status,'unfulfilled')
        self.assertEqual(order.fulfillment_status,'partial')
        self.assertEqual(order.carrier,'')
        self.assertEqual(order.status,OrderStatus.CONFIRMED)
        self.assertEqual(self.confirm(d).status_code,200)

    def test_unpaid_or_changed_order_cannot_be_dispatched(self):
        order,_,_=self.order(paid=False)
        r=self.web.post(self.path+'changes/',{'request_id':str(uuid4()),'action':'fulfillment','target':str(order.uuid),
            'values':{'carrier':'Test','tracking_number':'TEST123456'}},format='json')
        self.assertEqual(r.status_code,400)
        order.payment_status=PaymentStatus.PAID;order.save()
        d=self.prepare('fulfillment',str(order.uuid),{'carrier':'Test','tracking_number':'TEST123456'})
        order.payment_status=PaymentStatus.REFUNDED;order.save()
        self.assertEqual(self.confirm(d).status_code,400)

    def test_order_cards_and_pending_query_follow_dispatch_eligibility(self):
        order, own, other = self.order()
        row = self.message('my orders').data['orders'][0]
        self.assertTrue(row['can_ship'])
        for field, value in [('status', OrderStatus.CANCELLED), ('payment_status', PaymentStatus.UNPAID)]:
            order.status = OrderStatus.CONFIRMED
            order.payment_status = PaymentStatus.PAID
            setattr(order, field, value)
            order.save()
            self.assertFalse(self.message('my orders').data['orders'][0]['can_ship'])
            self.assertEqual(self.message('pending orders').data['orders'], [])
        order.status = OrderStatus.CONFIRMED
        order.payment_status = PaymentStatus.PAID
        order.save()
        self.assertEqual(len(self.message('pending orders').data['orders']), 1)
        own.shipped_at = timezone.now()
        own.save()
        self.assertFalse(self.message('my orders').data['orders'][0]['can_ship'])

    def test_web_link_has_csrf_protection_and_preserves_handoff_before_login(self):
        client=Client(enforce_csrf_checks=True)
        self.assertEqual(client.get('/seller/ai/link/').status_code,200)
        client.force_login(self.seller)
        self.assertEqual(client.post(BASE+'link/approve/',{'token':'fake','verification_code':'ABCDEF','confirmed':True}).status_code,403)

    @override_settings(SELLER_AGENT_USE_LLM=True,SELLER_AGENT_API_KEY='test')
    @patch('seller_agent.planner.requests.post')
    def test_ai_timeout_or_forged_target_never_changes_commerce(self,post):
        import requests
        post.side_effect=requests.Timeout()
        r=self.message('Which item needs my attention?')
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.data['engine'],'guided')
        post.side_effect=None
        post.return_value=Mock()
        post.return_value.json.return_value={'choices':[{'message':{'content':'{"intent":"stock","target":"foreign-bowl","values":{"quantity":0}}'}}]}
        rejected = self.message('Change that item for me')
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(rejected.data['engine'], 'guided')
        self.assertIn('unavailable', rejected.data['notice'])
        self.assertFalse(Change.objects.exists())

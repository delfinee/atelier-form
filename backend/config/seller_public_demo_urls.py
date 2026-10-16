from django.urls import path, include
from django.contrib.auth.views import LogoutView
from django.views.generic import RedirectView
from frontend import views_seller
from imagery.views import site_image
from seller_agent import views, public_demo, release_views, api
from django.http import HttpResponse

def unavailable(request, exception=None):
    return HttpResponse('This page is not available in the public demo.', status=404)

def forbidden(request, exception=None):
    return HttpResponse('This operation is not allowed.', status=403)

def failed(request):
    return HttpResponse('The demo could not complete this request. Please retry.', status=500)

handler404 = unavailable
handler403 = forbidden
handler500 = failed

urlpatterns = [
    path('', public_demo.home, name='demo_home'),
    path('demo/start/', public_demo.start),
    path('healthz/', release_views.health),
    path('seller/ai/', views.desk, name='seller_ai'),
    path('seller/products/', views_seller.seller_product_list,
         {'template_name': 'seller_agent/phone_products.html'}, name='seller_product_list'),
    path('seller/products/new/', views_seller.seller_product_create,
         {'template_name': 'seller_agent/phone_product_form.html'}, name='seller_product_create'),
    path('seller/products/<slug:slug>/edit/', views_seller.seller_product_edit,
         {'template_name': 'seller_agent/phone_product_form.html'}, name='seller_product_edit'),
    path('img/<slug:name>.jpg', site_image, name='site_image'),
    path('account/login/', RedirectView.as_view(url='/')),
    path('account/logout/', LogoutView.as_view(next_page='/'), name='logout'),
    path('api/seller-agent/v1/', include('seller_agent.urls')),
]

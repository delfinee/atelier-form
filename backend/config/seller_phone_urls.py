"""Only seller-agent and account-linking routes are public in phone previews."""
from django.contrib.auth.views import LoginView, LogoutView
from django.http import HttpResponseNotFound, HttpResponseServerError
from django.urls import include, path
from django.views.generic import RedirectView
from seller_agent import views
from frontend import views_seller
from imagery.views import site_image


def not_found(request, exception):
    return HttpResponseNotFound('This page is not available in the seller phone preview.')


def server_error(request):
    return HttpResponseServerError('The seller service could not complete this request. Please retry.')


handler404 = not_found
handler500 = server_error

urlpatterns = [
    path('', RedirectView.as_view(url='/seller/ai/', permanent=False)),
    path('api/seller-agent/v1/', include('seller_agent.urls')),
    path('seller/ai/', views.desk, name='seller_ai'),
    path('seller/ai/link/', views.link),
    path('seller/download/', views.download_bundle, name='seller_download'),
    path('seller/products/', views_seller.seller_product_list,
        {'template_name': 'seller_agent/phone_products.html'}, name='seller_product_list'),
    path('seller/products/new/', views_seller.seller_product_create,
        {'template_name': 'seller_agent/phone_product_form.html'}, name='seller_product_create'),
    path('seller/products/<slug:slug>/edit/', views_seller.seller_product_edit,
        {'template_name': 'seller_agent/phone_product_form.html'}, name='seller_product_edit'),
    path('img/<slug:name>.jpg', site_image, name='site_image'),
    path('account/login/', LoginView.as_view(
        template_name='seller_agent/phone_login.html', redirect_authenticated_user=True), name='login'),
    path('account/logout/', LogoutView.as_view(), name='logout'),
]

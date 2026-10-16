from django.urls import path
from . import customer

urlpatterns = [
    path("session/wechat/", customer.WechatLogin.as_view()),
    path("catalog/", customer.Catalog.as_view()),
    path("conversation/", customer.State.as_view()),
    path("messages/", customer.Chat.as_view()),
    path("quotes/<uuid:uuid>/confirm/", customer.Confirm.as_view()),
    path("quotes/<uuid:uuid>/demo-payment/", customer.DemoPayment.as_view()),
]

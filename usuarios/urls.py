from django.urls import path

from .views import login_demo, logout_demo

urlpatterns = [
    path("login/", login_demo, name="login"),
    path("logout/", logout_demo, name="logout"),
]

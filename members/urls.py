"""Members URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.urls import path
from members import views

app_name = "members"

urlpatterns = [
    path("profile/<str:pk>", views.ProfileView.as_view(), name="profile"),
    path("addnewchild", views.add_new_child_view, name="add_new_child"),
    path("addchildkey", views.add_child_key_view, name="add_key_child"),
    path("children", views.child_list, name="child_list"),
    path("adminlist", views.AdminListView.as_view(), name="admin_list"),
    path("adminupdate/<str:pk>", views.AdminUpdateView.as_view(), name="admin_update"),
    path("child/<str:pk>/edit", views.edit_child, name="edit_child"),
    path("dettach/<str:pk>", views.dettach_child, name="dettach_child"),
    path("deregister/<str:pk>", views.deregister_child, name="deregister_child"),
    path(
        "deregister_confirm/<str:pk>/<str:action>",
        views.deregister_confirm,
        name="deregister_confirm",
    ),
    path(
        "dettach_confirm/<str:pk>",
        views.dettach_confirm,
        name="dettach_confirm",
    ),
    path(
        "childaccountcreate/<str:pk>",
        views.ChildAccountCreate.as_view(),
        name="child_account_create",
    ),
    path(
        "childaccountcreateconfirm/<str:uidb36>/<str:key>/",
        views.ChildAccountCreateConfirm.as_view(),
        name="child_account_create_confirm",
    ),
    path(
        "childaccountcreatedone",
        views.ChildAccountCreateDone.as_view(),
        name="child_account_create_done",
    ),
]

from django.urls import path

from . import api

urlpatterns = [
    path("auth/login/", api.login_view, name="api_login"),
    path("auth/me/", api.me_view, name="api_me"),
    path("auth/profile/", api.profile_view, name="api_profile"),
    path("auth/password/", api.password_view, name="api_password"),
    path("summary/", api.summary_view, name="api_summary"),
    path("dashboard/", api.dashboard_view, name="api_dashboard"),
    path("form-options/", api.form_options_view, name="api_form_options"),
    path("medicines/", api.medicines_view, name="api_medicines"),
    path("medicines/<int:pk>/", api.medicine_detail_view, name="api_medicine_detail"),
    path("medicines/<int:pk>/restock/", api.medicine_restock_view, name="api_medicine_restock"),
    path("medicines/<int:pk>/adjust/", api.medicine_adjust_view, name="api_medicine_adjust"),
    path("movements/", api.movements_view, name="api_movements"),
    path("release/", api.release_view, name="api_release"),
]
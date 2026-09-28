from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView

from boxapp import views

admin.site.site_header = "B4H Portal"
admin.site.site_title = "B4H Portal"
admin.site.index_title = "Monitor & manage"

urlpatterns = [
    # Must come before admin.site.urls. admin_view() makes each one staff-login only.
    path("admin/box-image/", admin.site.admin_view(views.box_image), name="box_image"),
    path("admin/live/<int:device_id>/stream/", admin.site.admin_view(views.live_stream), name="live_stream"),
    path("admin/live/<int:device_id>/snapshot/", admin.site.admin_view(views.live_snapshot), name="live_snapshot"),
    path("admin/box-log/download/", admin.site.admin_view(views.log_file_download), name="box_log_file"),
    path("admin/", admin.site.urls),
    path("", RedirectView.as_view(url="/admin/", permanent=False)),
]

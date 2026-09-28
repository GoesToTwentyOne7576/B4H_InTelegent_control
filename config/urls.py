from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView
from boxapp import views
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

path(
    "admin/movement-alarm/",
    admin.site.admin_view(views.movement_alarm_page),
    name="movement_alarm",
),
path(
    "admin/movement-alarm/create/",
    admin.site.admin_view(views.movement_alarm_create),
    name="movement_alarm_create",
),
path(
    "admin/movement-alarm/<int:rule_id>/toggle/",
    admin.site.admin_view(views.movement_alarm_toggle),
    name="movement_alarm_toggle",
),
path(
    "admin/movement-alarm/<int:rule_id>/delete/",
    admin.site.admin_view(views.movement_alarm_delete),
    name="movement_alarm_delete",
),
path(
    "admin/movement-alarm/event/<int:event_id>/ack/",
    admin.site.admin_view(views.movement_alarm_ack),
    name="movement_alarm_ack",
),

    
]

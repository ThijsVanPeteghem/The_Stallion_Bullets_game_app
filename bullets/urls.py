from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("spelregels/", views.rules, name="rules"),
    path("spelers/", views.players, name="players"),
    path("spelers/<int:player_id>/", views.player_detail, name="player_detail"),
    path("spelers/<int:player_id>/bewerken/", views.edit_player, name="edit_player"),
    path("seizoenen/", views.seasons, name="seasons"),
    path("seizoenen/<int:season_id>/", views.season_detail, name="season_detail"),
    path("seizoenen/<int:season_id>/verwijderen/", views.delete_season, name="delete_season"),
    path("seizoenen/<int:season_id>/stand/", views.season_standings_view, name="season_standings"),
    path("avonden/nieuw/", views.new_evening, name="new_evening"),
    path("avonden/<int:evening_id>/", views.evening_detail, name="evening_detail"),
    path("avonden/<int:evening_id>/tussenstand/", views.evening_standings_view, name="evening_standings"),
    path("avonden/<int:evening_id>/schema-opnieuw/", views.regenerate_schedule_view, name="regenerate_schedule"),
    path("avonden/<int:evening_id>/verwijderen/", views.delete_evening, name="delete_evening"),
    path("avonden/<int:evening_id>/print/", views.print_evening, name="print_evening"),
    path("wedstrijden/<int:match_id>/bewerken/", views.edit_match, name="edit_match"),
]

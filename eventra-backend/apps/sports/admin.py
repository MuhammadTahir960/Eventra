from django.contrib import admin

from .models import League, Sport, Team


@admin.register(Sport)
class SportAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(League)
class LeagueAdmin(admin.ModelAdmin):
    list_display = ("name", "sport")
    list_filter = ("sport",)
    search_fields = ("name", "sport__name")
    list_select_related = ("sport",)


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "sport")
    list_filter = ("sport",)
    search_fields = ("name", "sport__name")
    list_select_related = ("sport",)

from django.contrib import admin
from .models import Collectible, PlayerCollectible, GroupName

@admin.register(GroupName)
class GroupNameAdmin(admin.ModelAdmin):
    list_display = ("group_name", "plural")

    def has_add_permission(self, request):
        return not GroupName.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(Collectible)
class CollectibleAdmin(admin.ModelAdmin):
    list_display = ("name", "emoji", "cost", "requirement_type", "requirement_value")
    search_fields = ("name", "bio", "requirement_type")
    list_filter = ("requirement_type",)


@admin.register(PlayerCollectible)
class PlayerCollectibleAdmin(admin.ModelAdmin):
    list_display = ("player", "collectible", "obtained_at")
    search_fields = ("player__id", "collectible__name")
    readonly_fields = ("player", "collectible", "obtained_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
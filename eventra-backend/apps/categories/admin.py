from django.contrib import admin

from .models import Category


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "sort_order", "admin_only", "is_active")
    list_filter = ("is_active", "admin_only")
    search_fields = ("name", "slug")
    ordering = ("sort_order", "name")

    def get_queryset(self, request):
        return Category.all_objects.all()

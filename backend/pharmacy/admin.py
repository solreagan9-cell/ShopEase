from django.contrib import admin

from .models import Category, Medicine, MedicineRelease, StockMovement


@admin.register(Medicine)
class MedicineAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "generic_name",
        "strength",
        "category",
        "batch_number",
        "quantity",
        "reorder_level",
        "requires_prescription",
        "unit_price",
        "expiry_date",
    )
    search_fields = ("name", "generic_name", "batch_number", "barcode")
    list_filter = ("category", "requires_prescription", "expiry_date")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    search_fields = ("name",)


@admin.register(MedicineRelease)
class MedicineReleaseAdmin(admin.ModelAdmin):
    list_display = ("medicine", "quantity", "unit_price", "released_to", "released_by", "released_at")
    search_fields = ("medicine__name", "released_to")


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    """The stock history is a record, so it is read-only here."""

    list_display = (
        "created_at", "medicine_name", "batch_number", "kind",
        "quantity_change", "quantity_after", "reason", "created_by",
    )
    list_filter = ("kind",)
    search_fields = ("medicine_name", "batch_number", "note")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
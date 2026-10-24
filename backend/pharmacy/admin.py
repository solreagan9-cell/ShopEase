from django.contrib import admin
from .models import Medicine


@admin.register(Medicine)
class MedicineAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "generic_name",
        "category",
        "batch_number",
        "quantity",
        "unit_price",
        "expiry_date",
    )
    search_fields = ("name", "generic_name", "batch_number")
    list_filter = ("category", "expiry_date")
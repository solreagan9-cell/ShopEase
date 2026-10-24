from datetime import date

from django.db.models import DecimalField, ExpressionWrapper, F, Sum

from .models import Medicine


def sidebar_analytics(request):
    if not request.user.is_authenticated:
        return {}

    today = date.today()
    medicines = Medicine.objects.all()
    total = medicines.count()

    value = medicines.aggregate(
        v=Sum(ExpressionWrapper(
            F("quantity") * F("unit_price"),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        ))
    )["v"] or 0

    healthy = medicines.filter(quantity__gt=10, expiry_date__gte=today).count()
    health_pct = round(healthy / total * 100) if total else 0

    return {
        "analytics": {
            "value": value,
            "total": total,
            "health_pct": health_pct,
            "low": medicines.filter(quantity__lte=10).count(),
            "expired": medicines.filter(expiry_date__lt=today).count(),
        }
    }
import json
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum
from django.utils import timezone
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods, require_POST
from PIL import Image

from .models import Category, Medicine, MedicineRelease

NEW_CATEGORY = "__new__"

MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}

DEFAULT_CATEGORIES = [
    "Pain relief",
    "Antibiotic",
    "Antihistamine",
    "Vitamins & supplements",
    "Cough & cold",
    "Antacid",
    "First aid",
    "Diabetes",
    "Hypertension",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def medicine_api_data(medicine):
    return {
        "id": medicine.id,
        "name": medicine.name,
        "generic_name": medicine.generic_name,
        "category": medicine.category,
        "batch_number": medicine.batch_number,
        "supplier": medicine.supplier,
        "quantity": medicine.quantity,
        "unit": medicine.unit,
        "unit_label": medicine.get_unit_display(),
        "unit_price": str(medicine.unit_price),
        "expiry_date": medicine.expiry_date.isoformat(),
        "image_url": medicine.image.url if medicine.image else "",
        "created_at": medicine.created_at.isoformat(),
    }


def _medicine_form_values(request):
    return {
        "name": request.POST.get("name", "").strip(),
        "generic_name": request.POST.get("generic_name", "").strip(),
        "category": request.POST.get("category", "").strip(),
        "new_category": request.POST.get("new_category", "").strip(),
        "batch_number": request.POST.get("batch_number", "").strip(),
        "supplier": request.POST.get("supplier", "").strip(),
        "quantity": request.POST.get("quantity", "0").strip(),
        "unit": request.POST.get("unit", "tablet").strip(),
        "unit_price": request.POST.get("unit_price", "0").strip(),
        "expiry_date": request.POST.get("expiry_date", "").strip(),
    }


def _validate_image(upload, errors):
    """Return the uploaded image if it is valid, otherwise None (and add an error)."""
    if not upload:
        return None
    if upload.size > MAX_IMAGE_BYTES:
        errors.append("The photo is too large (max 5 MB).")
        return None
    try:
        with Image.open(upload) as img:
            img.verify()
            fmt = img.format
    except Exception:
        errors.append("The uploaded file is not a valid image.")
        return None
    upload.seek(0)
    if fmt not in ALLOWED_IMAGE_FORMATS:
        errors.append("The photo must be a JPG, PNG, WEBP or GIF image.")
        return None
    return upload


def get_category_names():
    """Return all category names. Seeds defaults and existing medicine categories."""
    known = {n.lower() for n in Category.objects.values_list("name", flat=True)}
    existing_in_medicines = Medicine.objects.order_by().values_list(
        "category", flat=True
    ).distinct()

    for name in DEFAULT_CATEGORIES + list(existing_in_medicines):
        name = (name or "").strip()
        if name and name.lower() not in known:
            Category.objects.create(name=name)
            known.add(name.lower())

    return list(Category.objects.order_by("name").values_list("name", flat=True))


def resolve_category(values, errors):
    """Return the final category name (or '' if invalid) and add errors if needed."""
    if values["category"] == NEW_CATEGORY:
        name = " ".join(values["new_category"].split())
        if not name:
            errors.append("Enter the name of the new category.")
            return ""
        if len(name) > 100:
            errors.append("Category name is too long (max 100 characters).")
            return ""
        match = Category.objects.filter(name__iexact=name).first()
        return match.name if match else name

    return values["category"]


def save_category(name):
    if name and not Category.objects.filter(name__iexact=name).exists():
        Category.objects.create(name=name)


def _form_context(values, page_title, form_mode, medicine=None):
    context = {
        "values": values,
        "page_title": page_title,
        "form_mode": form_mode,
        "categories": get_category_names(),
        "units": Medicine.UNIT_CHOICES,
    }
    if medicine is not None:
        context["medicine"] = medicine
    return context


def generate_batch_number():
    prefix = f"BN-{date.today().year}-"
    last = (
        Medicine.objects.filter(batch_number__startswith=prefix)
        .order_by("-batch_number")
        .first()
    )
    try:
        number = int(last.batch_number.split("-")[-1]) + 1 if last else 1
    except ValueError:
        number = Medicine.objects.filter(batch_number__startswith=prefix).count() + 1
    return f"{prefix}{number:03d}"


def _validate_common(values, errors):
    """Validate quantity, unit, price and expiry. Returns parsed values."""
    try:
        quantity = int(values["quantity"])
        if quantity < 0:
            errors.append("Quantity cannot be negative.")
    except ValueError:
        quantity = 0
        errors.append("Quantity must be a whole number.")

    valid_units = {value for value, _label in Medicine.UNIT_CHOICES}
    if values["unit"] not in valid_units:
        errors.append("Choose a valid unit.")

    try:
        unit_price = Decimal(values["unit_price"])
        if (
            not unit_price.is_finite()
            or unit_price < 0
            or unit_price.as_tuple().exponent < -2
        ):
            errors.append("Enter a valid non-negative price with at most 2 decimal places.")
        elif unit_price <= 0:
            errors.append("Unit price must be greater than zero.")
    except (InvalidOperation, ValueError):
        unit_price = Decimal("0.00")
        errors.append("Enter a valid unit price.")

    try:
        expiry_date = date.fromisoformat(values["expiry_date"])
    except ValueError:
        expiry_date = None
        errors.append("Enter a valid expiry date.")

    return quantity, unit_price, expiry_date


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@login_required
def dashboard(request):
    today = date.today()
    medicines = Medicine.objects.all()
    soon = today + timedelta(days=30)

    context = {
        "low_stock_count": medicines.filter(quantity__lte=10).count(),
        "expired_count": medicines.filter(expiry_date__lt=today).count(),
        "expiring_count": medicines.filter(
            expiry_date__gte=today, expiry_date__lte=soon
        ).count(),
        "recent_medicines": medicines.order_by("-created_at")[:5],
        "today": today,
    }
    context.update(_analytics_context())

    return render(request, "pharmacy/dashboard.html", context)


# ---------------------------------------------------------------------------
# Medicine inventory
# ---------------------------------------------------------------------------

@login_required
def medicine_list(request):
    query = request.GET.get("q", "").strip()
    stock_filter = request.GET.get("stock", "").strip()
    medicines = Medicine.objects.all()

    if query:
        medicines = medicines.filter(
            Q(name__icontains=query)
            | Q(generic_name__icontains=query)
            | Q(category__icontains=query)
            | Q(batch_number__icontains=query)
            | Q(supplier__icontains=query)
        )

    today = date.today()

    if stock_filter == "low":
        medicines = medicines.filter(quantity__lte=10)
    elif stock_filter == "expired":
        medicines = medicines.filter(expiry_date__lt=today)
    elif stock_filter == "expiring":
        medicines = medicines.filter(
            expiry_date__gte=today,
            expiry_date__lte=today + timedelta(days=30),
        )

    paginator = Paginator(medicines.order_by("name"), 12)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "pharmacy/medicine_list.html", {
        "page_obj": page_obj,
        "query": query,
        "stock_filter": stock_filter,
        "today": today,
    })


@login_required
def medicine_create(request):
    if request.method == "POST":
        values = _medicine_form_values(request)
        values["batch_number"] = generate_batch_number()
        errors = []

        category_name = resolve_category(values, errors)

        if not (values["name"] and category_name and values["expiry_date"]):
            errors.append(
                "Complete the medicine name, category, and expiry date."
            )

        quantity, unit_price, expiry_date = _validate_common(values, errors)
        image = _validate_image(request.FILES.get("image"), errors)

        if Medicine.objects.filter(batch_number=values["batch_number"]).exists():
            errors.append("That batch number already exists.")

        if errors:
            for error in errors:
                messages.error(request, error)
            return render(
                request,
                "pharmacy/medicine_form.html",
                _form_context(values, "Add medicine", "create"),
            )

        save_category(category_name)

        Medicine.objects.create(
            name=values["name"],
            generic_name=values["generic_name"],
            category=category_name,
            batch_number=values["batch_number"],
            supplier=values["supplier"],
            quantity=quantity,
            unit=values["unit"],
            unit_price=unit_price,
            expiry_date=expiry_date,
            image=image,
        )

        messages.success(request, f'{values["name"]} was added to inventory.')
        return redirect("pharmacy:medicine_list")

    return render(
        request,
        "pharmacy/medicine_form.html",
        _form_context(
            {"batch_number": generate_batch_number(), "unit": "tablet"},
            "Add medicine",
            "create",
        ),
    )


@login_required
def medicine_edit(request, pk):
    medicine = get_object_or_404(Medicine, pk=pk)

    if request.method == "POST":
        values = _medicine_form_values(request)
        errors = []

        category_name = resolve_category(values, errors)

        if not (
            values["name"] and category_name
            and values["batch_number"] and values["expiry_date"]
        ):
            errors.append("Complete the required medicine fields.")

        quantity, unit_price, expiry_date = _validate_common(values, errors)
        new_image = _validate_image(request.FILES.get("image"), errors)
        remove_image = request.POST.get("remove_image") == "1"

        if Medicine.objects.filter(
            batch_number=values["batch_number"]
        ).exclude(pk=medicine.pk).exists():
            errors.append("That batch number already exists.")

        if errors:
            for error in errors:
                messages.error(request, error)
            return render(
                request,
                "pharmacy/medicine_form.html",
                _form_context(values, "Edit medicine", "edit", medicine),
            )

        save_category(category_name)

        for field in ("name", "generic_name", "batch_number", "supplier", "unit"):
            setattr(medicine, field, values[field])

        medicine.category = category_name
        medicine.quantity = quantity
        medicine.unit_price = unit_price
        medicine.expiry_date = expiry_date

        if new_image:
            if medicine.image:
                medicine.image.delete(save=False)
            medicine.image = new_image
        elif remove_image and medicine.image:
            medicine.image.delete(save=False)
            medicine.image = None

        medicine.save()

        messages.success(request, f"{medicine.name} was updated.")
        return redirect("pharmacy:medicine_list")

    values = {
        "name": medicine.name,
        "generic_name": medicine.generic_name,
        "category": medicine.category,
        "batch_number": medicine.batch_number,
        "supplier": medicine.supplier,
        "quantity": medicine.quantity,
        "unit": medicine.unit,
        "unit_price": medicine.unit_price,
        "expiry_date": medicine.expiry_date.isoformat(),
    }

    return render(
        request,
        "pharmacy/medicine_form.html",
        _form_context(values, "Edit medicine", "edit", medicine),
    )


@login_required
@require_POST
def medicine_delete(request, pk):
    medicine = get_object_or_404(Medicine, pk=pk)
    name = medicine.name
    if medicine.image:
        medicine.image.delete(save=False)
    medicine.delete()
    messages.success(request, f"{name} was deleted from inventory.")
    return redirect("pharmacy:medicine_list")


# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------

def parse_medicine_json(request):
    try:
        data = json.loads(request.body or b"{}")
        if not isinstance(data, dict):
            return None, "Request must contain a JSON object."
        return data, None
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, "Invalid JSON."


def validate_medicine_json(data):
    required = ("name", "category", "batch_number", "expiry_date")

    for field in required:
        if not str(data.get(field, "")).strip():
            return f"{field.replace('_', ' ').title()} is required."

    try:
        quantity = int(data.get("quantity", 0))
        if quantity < 0:
            return "Quantity cannot be negative."
    except (ValueError, TypeError):
        return "Quantity must be a whole number."

    try:
        price = Decimal(str(data.get("unit_price", "")))
        if not price.is_finite() or price < 0 or price.as_tuple().exponent < -2:
            return "Enter a valid non-negative price with at most 2 decimal places."
    except (InvalidOperation, ValueError, TypeError):
        return "Enter a valid unit price."

    try:
        expiry = date.fromisoformat(str(data["expiry_date"]))
    except (ValueError, TypeError):
        return "Enter a valid expiry date in YYYY-MM-DD format."

    limits = {
        "name": 200,
        "generic_name": 200,
        "category": 100,
        "batch_number": 100,
        "supplier": 200,
    }

    for field, limit in limits.items():
        value = str(data.get(field, "")).strip()
        if len(value) > limit:
            return f"{field.replace('_', ' ').title()} is too long."
        data[field] = value

    data["quantity"] = quantity
    data["unit_price"] = price
    data["expiry_date"] = expiry
    return None


@login_required
@csrf_protect
@require_http_methods(["GET", "POST"])
def medicine_api(request):
    if request.method == "GET":
        medicines = Medicine.objects.all()
        query = request.GET.get("search", "").strip()

        if query:
            medicines = medicines.filter(
                Q(name__icontains=query)
                | Q(generic_name__icontains=query)
                | Q(category__icontains=query)
                | Q(batch_number__icontains=query)
                | Q(supplier__icontains=query)
            )

        rows = [medicine_api_data(m) for m in medicines]
        today = date.today()

        return JsonResponse({
            "medicines": rows,
            "total_medicines": len(rows),
            "total_stock": sum(m["quantity"] for m in rows),
            "low_stock_count": sum(
                m["quantity"] <= 10 for m in rows
            ),
            "expired_count": sum(
                date.fromisoformat(m["expiry_date"]) < today
                for m in rows
            ),
        })

    data, error = parse_medicine_json(request)
    if error:
        return JsonResponse({"error": error}, status=400)

    error = validate_medicine_json(data)
    if error:
        return JsonResponse({"error": error}, status=400)

    try:
        with transaction.atomic():
            medicine = Medicine.objects.create(**{
                field: data[field]
                for field in (
                    "name", "generic_name", "category", "batch_number",
                    "supplier", "quantity", "unit_price", "expiry_date"
                )
            })
    except IntegrityError:
        return JsonResponse(
            {"error": "That batch number already exists."},
            status=409,
        )

    return JsonResponse(medicine_api_data(medicine), status=201)


@login_required
@csrf_protect
@require_http_methods(["GET", "PUT", "DELETE"])
def medicine_detail_api(request, pk):
    try:
        medicine = Medicine.objects.get(pk=pk)
    except Medicine.DoesNotExist:
        return JsonResponse({"error": "Medicine not found."}, status=404)

    if request.method == "GET":
        return JsonResponse(medicine_api_data(medicine))

    if request.method == "DELETE":
        medicine.delete()
        return JsonResponse({"message": "Medicine deleted."})

    data, error = parse_medicine_json(request)
    if error:
        return JsonResponse({"error": error}, status=400)

    error = validate_medicine_json(data)
    if error:
        return JsonResponse({"error": error}, status=400)

    fields = (
        "name", "generic_name", "category", "batch_number",
        "supplier", "quantity", "unit_price", "expiry_date"
    )

    for field in fields:
        setattr(medicine, field, data[field])

    try:
        with transaction.atomic():
            medicine.save()
    except IntegrityError:
        return JsonResponse(
            {"error": "That batch number already exists."},
            status=409,
        )

    return JsonResponse(medicine_api_data(medicine))


# ---------------------------------------------------------------------------
# Release medicine
# ---------------------------------------------------------------------------

@login_required
def release_medicine(request):
    today = date.today()
    medicines = Medicine.objects.filter(
        quantity__gt=0, expiry_date__gte=today
    ).order_by("name")

    selected = ""

    if request.method == "POST":
        selected = request.POST.get("medicine", "")
        released_to = request.POST.get("released_to", "").strip()
        note = request.POST.get("note", "").strip()

        try:
            qty = int(request.POST.get("quantity", "0"))
        except ValueError:
            qty = 0

        with transaction.atomic():
            med = (
                Medicine.objects.select_for_update()
                .filter(pk=selected or None)
                .first()
            )

            if not med:
                messages.error(request, "Please select a medicine.")
            elif qty <= 0:
                messages.error(request, "Quantity must be at least 1.")
            elif med.expiry_date < today:
                messages.error(request, f"{med.name} is expired and cannot be released.")
            elif qty > med.quantity:
                messages.error(
                    request,
                    f"Only {med.quantity} {med.get_unit_display().lower()}(s) in stock for {med.name}.",
                )
            else:
                med.quantity -= qty
                med.save(update_fields=["quantity"])
                MedicineRelease.objects.create(
                    medicine=med,
                    quantity=qty,
                    unit_price=med.unit_price,
                    released_to=released_to[:120],
                    note=note[:255],
                    released_by=request.user,
                )
                messages.success(request, f"Released {qty} of {med.name}.")
                return redirect("pharmacy:release_medicine")

    recent = MedicineRelease.objects.select_related("medicine", "released_by")[:10]

    return render(request, "pharmacy/medicine_release.html", {
        "medicines": medicines,
        "recent": recent,
        "selected": selected,
    })


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

def _analytics_context():
    today = date.today()
    local_today = timezone.localdate()
    medicines = Medicine.objects.all()
    money = ExpressionWrapper(
        F("quantity") * F("unit_price"),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )

    product_count = medicines.count()
    total_units = medicines.aggregate(t=Sum("quantity"))["t"] or 0
    inventory_value = medicines.aggregate(v=Sum(money))["v"] or Decimal("0.00")

    expired = medicines.filter(expiry_date__lt=today).count()
    out_of_stock = medicines.filter(quantity=0, expiry_date__gte=today).count()
    low = medicines.filter(
        quantity__gt=0, quantity__lte=10, expiry_date__gte=today
    ).count()
    healthy = medicines.filter(quantity__gt=10, expiry_date__gte=today).count()

    def pct(n):
        return round(n / product_count * 100) if product_count else 0

    by_category = list(
        medicines.values("category")
        .annotate(units=Sum("quantity"), value=Sum(money))
        .order_by("-units", "category")
    )
    units_by_category = by_category[:8]
    value_by_category = sorted(
        by_category, key=lambda r: r["value"] or 0, reverse=True
    )[:6]

    def expiring_between(start_days, end_days):
        return medicines.filter(
            expiry_date__gte=today + timedelta(days=start_days),
            expiry_date__lte=today + timedelta(days=end_days),
        ).count()

    expiry_labels = ["Expired", "0-30 days", "31-90 days", "91-180 days", "180+ days"]
    expiry_values = [
        expired,
        expiring_between(0, 30),
        expiring_between(31, 90),
        expiring_between(91, 180),
        medicines.filter(expiry_date__gt=today + timedelta(days=180)).count(),
    ]

    days = [local_today - timedelta(days=i) for i in range(6, -1, -1)]
    per_day = {d: 0 for d in days}
    releases_week = MedicineRelease.objects.filter(released_at__date__gte=days[0])
    for qty, at in releases_week.values_list("quantity", "released_at"):
        d = timezone.localtime(at).date()
        if d in per_day:
            per_day[d] += qty

    released_week_units = sum(per_day.values())
    released_week_value = releases_week.aggregate(v=Sum(money))["v"] or Decimal("0.00")

    top_released = list(
        MedicineRelease.objects.filter(
            released_at__date__gte=local_today - timedelta(days=29)
        )
        .values("medicine__name")
        .annotate(units=Sum("quantity"))
        .order_by("-units")[:5]
    )

    chart_data = {
        "categoryUnits": {
            "labels": [r["category"] for r in units_by_category],
            "values": [r["units"] or 0 for r in units_by_category],
        },
        "releasesDaily": {
            "labels": [d.strftime("%b %d") for d in days],
            "values": [per_day[d] for d in days],
        },
        "expiry": {"labels": expiry_labels, "values": expiry_values},
        "status": {
            "labels": ["Healthy", "Low stock", "Out of stock", "Expired"],
            "values": [healthy, low, out_of_stock, expired],
        },
        "categoryValue": {
            "labels": [r["category"] for r in value_by_category],
            "values": [float(r["value"] or 0) for r in value_by_category],
        },
        "topReleased": {
            "labels": [r["medicine__name"] for r in top_released],
            "values": [r["units"] or 0 for r in top_released],
        },
    }

    return {
        "chart_data": chart_data,
        "product_count": product_count,
        "total_units": total_units,
        "inventory_value": inventory_value,
        "healthy_pct": pct(healthy),
        "fresh_pct": pct(product_count - expired),
        "low_pct": pct(low),
        "released_week_units": released_week_units,
        "released_week_value": released_week_value,
        "date_from": days[0],
        "date_to": days[-1],
    }


@login_required
def analytics_page(request):
    return render(request, "pharmacy/analytics.html", _analytics_context())


@login_required
@ensure_csrf_cookie
def frontend_app(request):
    return render(request, "frontend/index.html")
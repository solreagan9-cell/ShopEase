"""
JSON API used by the separate frontend (the /frontend folder).

Authentication uses a signed token sent in the "Authorization: Bearer <token>"
header, so no cookies or CSRF tokens are needed between the two apps.
"""
import json
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import (
    DecimalField,
    ExpressionWrapper,
    F,
    ProtectedError,
    Q,
    Sum,
)
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from . import views as legacy  # reuse the validation helpers from views.py
from .models import Medicine, MedicineRelease, StockMovement

User = get_user_model()

TOKEN_SALT = "pharmacy.api.token"
TOKEN_MAX_AGE = 60 * 60 * 24 * 7  # tokens last 7 days
DEFAULT_REORDER_LEVEL = 10

DOSAGE_FORM_VALUES = {value for value, _label in Medicine.DOSAGE_FORMS}

ADJUST_REASONS = {
    "damaged": "Damaged",
    "expired": "Expired / disposed",
    "lost": "Lost or missing",
    "count": "Stock count correction",
    "returned": "Returned by customer",
    "other": "Other",
}
REMOVE_REASONS = ("damaged", "expired", "lost", "count", "other")
ADD_REASONS = ("count", "returned", "other")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_token(user):
    return signing.dumps({"uid": user.pk}, salt=TOKEN_SALT)


def user_from_request(request):
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    try:
        data = signing.loads(header[7:], salt=TOKEN_SALT, max_age=TOKEN_MAX_AGE)
    except signing.BadSignature:  # also covers expired tokens
        return None
    return User.objects.filter(pk=data.get("uid"), is_active=True).first()


def api(methods, auth=True):
    """Restrict HTTP methods, require a valid token, and skip CSRF checks."""

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.method not in methods:
                return JsonResponse({"error": "Method not allowed."}, status=405)
            if auth:
                user = user_from_request(request)
                if user is None:
                    return JsonResponse(
                        {"error": "Authentication required."}, status=401
                    )
                request.user = user
            return view(request, *args, **kwargs)

        return csrf_exempt(wrapper)

    return decorator


def json_body(request):
    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def fail(*messages, status=400):
    return JsonResponse({"errors": list(messages)}, status=status)


def user_json(user):
    return {
        "username": user.username,
        "first_name": user.first_name,
        "full_name": user.get_full_name() or user.username,
    }


def profile_json(user):
    data = user_json(user)
    data["last_name"] = user.last_name
    return data


def medicine_json(request, medicine, today=None):
    today = today or date.today()
    if medicine.expiry_date < today:
        status = "expired"
    elif medicine.quantity <= medicine.reorder_level:
        status = "low"
    else:
        status = "good"

    image_url = ""
    if medicine.image:
        image_url = request.build_absolute_uri(medicine.image.url)

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
        "image_url": image_url,
        "status": status,
        "reorder_level": medicine.reorder_level,
        "requires_prescription": medicine.requires_prescription,
        "strength": medicine.strength,
        "dosage_form": medicine.dosage_form,
        "dosage_form_label": medicine.get_dosage_form_display() if medicine.dosage_form else "",
        "barcode": medicine.barcode,
    }


def release_json(release):
    return {
        "id": release.id,
        "released_at": release.released_at.isoformat(),
        "medicine": release.medicine.name,
        "quantity": release.quantity,
        "total": str(release.total),
        "released_to": release.released_to,
        "released_by": release.released_by.username if release.released_by else "",
    }


def movement_json(movement):
    return {
        "id": movement.id,
        "created_at": movement.created_at.isoformat(),
        "medicine": movement.medicine_name,
        "batch_number": movement.batch_number,
        "kind": movement.kind,
        "kind_label": movement.get_kind_display(),
        "quantity_change": movement.quantity_change,
        "quantity_after": movement.quantity_after,
        "reason": movement.reason,
        "supplier": movement.supplier,
        "note": movement.note,
        "by": movement.created_by.username if movement.created_by else "",
    }


def log_movement(medicine, kind, change, user, reason="", supplier="", note=""):
    StockMovement.objects.create(
        medicine=medicine,
        medicine_name=medicine.name,
        batch_number=medicine.batch_number,
        kind=kind,
        quantity_change=change,
        quantity_after=medicine.quantity,
        reason=reason[:60],
        supplier=supplier[:200],
        note=note[:255],
        created_by=user,
    )


def parse_extras(request, errors):
    """Read and validate the extra pharmacy fields from a multipart form."""
    post = request.POST
    strength = post.get("strength", "").strip()
    dosage_form = post.get("dosage_form", "").strip()
    barcode = post.get("barcode", "").strip()
    raw_level = post.get("reorder_level", "").strip()
    requires_rx = post.get("requires_prescription", "") in ("1", "on", "true", "True")

    if len(strength) > 50:
        errors.append("Strength is too long (50 characters at most).")
    if dosage_form and dosage_form not in DOSAGE_FORM_VALUES:
        errors.append("Choose a valid dosage form.")
    if len(barcode) > 64:
        errors.append("Barcode is too long (64 characters at most).")

    reorder_level = DEFAULT_REORDER_LEVEL
    if raw_level != "":
        try:
            reorder_level = int(raw_level)
            if reorder_level < 0 or reorder_level > 100000:
                errors.append("Reorder level must be between 0 and 100000.")
        except ValueError:
            errors.append("Reorder level must be a whole number.")

    return {
        "strength": strength,
        "dosage_form": dosage_form,
        "barcode": barcode,
        "reorder_level": reorder_level,
        "requires_prescription": requires_rx,
    }


def medicine_counts(today):
    qs = Medicine.objects.all()
    return {
        "low": qs.filter(quantity__lte=F("reorder_level")).count(),
        "expired": qs.filter(expiry_date__lt=today).count(),
        "expiring": qs.filter(
            expiry_date__gte=today, expiry_date__lte=today + timedelta(days=30)
        ).count(),
    }


def sidebar_numbers(today):
    qs = Medicine.objects.all()
    money = ExpressionWrapper(
        F("quantity") * F("unit_price"),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )
    total = qs.count()
    healthy = qs.filter(quantity__gt=F("reorder_level"), expiry_date__gte=today).count()
    value = qs.aggregate(v=Sum(money))["v"] or Decimal("0.00")
    counts = medicine_counts(today)
    return {
        "value": float(value),
        "health_pct": round(healthy / total * 100) if total else 0,
        "low": counts["low"],
        "expired": counts["expired"],
    }


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@api(["POST"], auth=False)
def login_view(request):
    data = json_body(request)
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))

    user = authenticate(request, username=username, password=password)
    if user is None or not user.is_active:
        return JsonResponse({"error": "Invalid username or password."}, status=401)

    return JsonResponse({"token": make_token(user), "user": user_json(user)})


@api(["GET"])
def me_view(request):
    return JsonResponse({"user": user_json(request.user)})


@api(["GET", "POST"])
def profile_view(request):
    user = request.user

    if request.method == "GET":
        return JsonResponse({"user": profile_json(user)})

    data = json_body(request)
    user.first_name = str(data.get("first_name", "")).strip()[:150]
    user.last_name = str(data.get("last_name", "")).strip()[:150]
    user.save(update_fields=["first_name", "last_name"])
    return JsonResponse({"user": profile_json(user)})


@api(["POST"])
def password_view(request):
    data = json_body(request)
    current = str(data.get("current_password", ""))
    new = str(data.get("new_password", ""))
    confirm = str(data.get("confirm_password", ""))

    if not request.user.check_password(current):
        return fail("Your current password is incorrect.")
    if new != confirm:
        return fail("The new passwords do not match.")
    try:
        validate_password(new, request.user)
    except ValidationError as exc:
        return fail(*exc.messages)

    request.user.set_password(new)
    request.user.save()
    return JsonResponse({"message": "Your password was changed."})


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@api(["GET"])
def summary_view(request):
    return JsonResponse(sidebar_numbers(date.today()))


@api(["GET"])
def dashboard_view(request):
    today = date.today()
    ctx = legacy._analytics_context()
    recent = Medicine.objects.order_by("-created_at")[:5]

    qs = Medicine.objects.all()
    total = qs.count()
    counts = medicine_counts(today)
    sidebar = sidebar_numbers(today)

    # Stock status uses each medicine's own reorder level
    not_expired = qs.filter(expiry_date__gte=today)
    good_n = not_expired.filter(quantity__gt=F("reorder_level")).count()
    low_n = not_expired.filter(quantity__gt=0, quantity__lte=F("reorder_level")).count()
    out_n = not_expired.filter(quantity=0).count()

    charts = dict(ctx["chart_data"])
    charts["status"] = {
        "labels": ["In stock", "Low stock", "Out of stock", "Expired"],
        "values": [good_n, low_n, out_n, counts["expired"]],
    }

    return JsonResponse({
        "kpis": {
            "inventory_value": float(ctx["inventory_value"]),
            "product_count": ctx["product_count"],
            "total_units": ctx["total_units"],
            "released_week_units": ctx["released_week_units"],
            "released_week_value": float(ctx["released_week_value"]),
        },
        "rings": {
            "healthy_pct": sidebar["health_pct"],
            "fresh_pct": ctx["fresh_pct"],
            "low_pct": round(counts["low"] / total * 100) if total else 0,
        },
        "counts": counts,
        "recent": [medicine_json(request, m, today) for m in recent],
        "charts": charts,
        "sidebar": sidebar,
    })


# ---------------------------------------------------------------------------
# Medicines
# ---------------------------------------------------------------------------

@api(["GET"])
def form_options_view(request):
    return JsonResponse({
        "categories": legacy.get_category_names(),
        "units": [
            {"value": value, "label": label}
            for value, label in Medicine.UNIT_CHOICES
        ],
        "dosage_forms": [
            {"value": value, "label": label}
            for value, label in Medicine.DOSAGE_FORMS
        ],
        "next_batch_number": legacy.generate_batch_number(),
    })


@api(["GET", "POST"])
def medicines_view(request):
    today = date.today()

    if request.method == "GET":
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
                | Q(barcode__icontains=query)
                | Q(strength__icontains=query)
            )

        if stock_filter == "low":
            medicines = medicines.filter(quantity__lte=F("reorder_level"))
        elif stock_filter == "expired":
            medicines = medicines.filter(expiry_date__lt=today)
        elif stock_filter == "expiring":
            medicines = medicines.filter(
                expiry_date__gte=today,
                expiry_date__lte=today + timedelta(days=30),
            )

        paginator = Paginator(medicines.order_by("name"), 12)
        page = paginator.get_page(request.GET.get("page"))

        return JsonResponse({
            "results": [medicine_json(request, m, today) for m in page],
            "page": page.number,
            "num_pages": paginator.num_pages,
            "count": paginator.count,
            "start_index": page.start_index(),
            "end_index": page.end_index(),
            "has_previous": page.has_previous(),
            "has_next": page.has_next(),
        })

    # POST: create a medicine (multipart form so a photo can be uploaded)
    values = legacy._medicine_form_values(request)
    values["batch_number"] = legacy.generate_batch_number()
    errors = []

    category_name = legacy.resolve_category(values, errors)

    if not (values["name"] and category_name and values["expiry_date"]):
        errors.append("Complete the medicine name, category, and expiry date.")

    quantity, unit_price, expiry_date = legacy._validate_common(values, errors)
    image = legacy._validate_image(request.FILES.get("image"), errors)
    extras = parse_extras(request, errors)

    if Medicine.objects.filter(batch_number=values["batch_number"]).exists():
        errors.append("That batch number already exists.")

    if errors:
        return fail(*errors)

    legacy.save_category(category_name)

    with transaction.atomic():
        medicine = Medicine.objects.create(
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
            **extras,
        )
        if quantity > 0:
            log_movement(
                medicine, "initial", quantity, request.user,
                reason="Initial stock", supplier=values["supplier"],
            )

    return JsonResponse({"medicine": medicine_json(request, medicine, today)}, status=201)


@api(["GET", "POST", "DELETE"])
def medicine_detail_view(request, pk):
    medicine = Medicine.objects.filter(pk=pk).first()
    if medicine is None:
        return JsonResponse({"error": "Medicine not found."}, status=404)

    today = date.today()

    if request.method == "GET":
        return JsonResponse({"medicine": medicine_json(request, medicine, today)})

    if request.method == "DELETE":
        name = medicine.name
        try:
            if medicine.image:
                medicine.image.delete(save=False)
            medicine.delete()
        except ProtectedError:
            return JsonResponse(
                {"error": f"{name} has release history and cannot be deleted."},
                status=409,
            )
        return JsonResponse({"message": f"{name} was deleted from inventory."})

    # POST: update a medicine (multipart form)
    values = legacy._medicine_form_values(request)
    values["batch_number"] = medicine.batch_number  # batch number can never be changed
    errors = []

    category_name = legacy.resolve_category(values, errors)

    if not (values["name"] and category_name and values["expiry_date"]):
        errors.append("Complete the required medicine fields.")

    quantity, unit_price, expiry_date = legacy._validate_common(values, errors)
    new_image = legacy._validate_image(request.FILES.get("image"), errors)
    extras = parse_extras(request, errors)
    remove_image = request.POST.get("remove_image") == "1"

    if errors:
        return fail(*errors)

    legacy.save_category(category_name)

    old_quantity = medicine.quantity

    for field in ("name", "generic_name", "batch_number", "supplier", "unit"):
        setattr(medicine, field, values[field])
    for field, value in extras.items():
        setattr(medicine, field, value)

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

    with transaction.atomic():
        medicine.save()
        if quantity != old_quantity:
            log_movement(
                medicine, "adjustment", quantity - old_quantity, request.user,
                reason="Edited in medicine form",
            )

    return JsonResponse({"medicine": medicine_json(request, medicine, today)})


@api(["POST"])
def medicine_restock_view(request, pk):
    """Receive a delivery: adds to the existing quantity and logs it."""
    today = date.today()
    data = json_body(request)
    errors = []

    try:
        qty = int(data.get("quantity", 0))
    except (TypeError, ValueError):
        qty = 0
    if qty < 1 or qty > 1000000:
        errors.append("Enter a quantity between 1 and 1,000,000.")

    supplier = str(data.get("supplier", "")).strip()
    note = str(data.get("note", "")).strip()
    if len(supplier) > 200:
        errors.append("Supplier name is too long.")
    if len(note) > 255:
        errors.append("Note is too long.")

    new_price = None
    raw_price = str(data.get("unit_price", "")).strip()
    if raw_price != "":
        try:
            new_price = Decimal(raw_price)
            if (
                not new_price.is_finite()
                or new_price <= 0
                or new_price.as_tuple().exponent < -2
            ):
                errors.append("Enter a valid price greater than zero, with at most 2 decimals.")
        except InvalidOperation:
            errors.append("Enter a valid unit price.")

    if errors:
        return fail(*errors)

    with transaction.atomic():
        med = Medicine.objects.select_for_update().filter(pk=pk).first()
        if med is None:
            return JsonResponse({"error": "Medicine not found."}, status=404)
        if med.expiry_date < today:
            return fail(
                f"{med.name} is expired and cannot be restocked. "
                "Add the new delivery as a new medicine batch instead."
            )

        med.quantity += qty
        fields = ["quantity"]
        if supplier:
            med.supplier = supplier
            fields.append("supplier")
        if new_price is not None:
            med.unit_price = new_price
            fields.append("unit_price")
        med.save(update_fields=fields)

        log_movement(
            med, "restock", qty, request.user,
            reason="Delivery received", supplier=supplier or med.supplier, note=note,
        )

    return JsonResponse({
        "message": f"Received {qty} {med.get_unit_display().lower()}(s) of {med.name}.",
        "medicine": medicine_json(request, med, today),
    })


@api(["POST"])
def medicine_adjust_view(request, pk):
    """Add or remove stock for a reason (damaged, expired, count correction...)."""
    today = date.today()
    data = json_body(request)
    errors = []

    direction = str(data.get("direction", "")).strip()
    reason_key = str(data.get("reason", "")).strip()
    note = str(data.get("note", "")).strip()

    try:
        qty = int(data.get("quantity", 0))
    except (TypeError, ValueError):
        qty = 0

    if direction not in ("add", "remove"):
        errors.append("Choose whether to add or remove stock.")
    if qty < 1 or qty > 1000000:
        errors.append("Enter a quantity between 1 and 1,000,000.")

    allowed = ADD_REASONS if direction == "add" else REMOVE_REASONS
    if reason_key not in allowed:
        errors.append("Choose a reason for this adjustment.")
    if reason_key == "other" and not note:
        errors.append("Please explain the reason in the note.")
    if len(note) > 255:
        errors.append("Note is too long.")

    if errors:
        return fail(*errors)

    with transaction.atomic():
        med = Medicine.objects.select_for_update().filter(pk=pk).first()
        if med is None:
            return JsonResponse({"error": "Medicine not found."}, status=404)

        if direction == "remove":
            if qty > med.quantity:
                return fail(
                    f"Only {med.quantity} {med.get_unit_display().lower()}(s) "
                    f"in stock for {med.name}."
                )
            change = -qty
        else:
            change = qty

        med.quantity += change
        med.save(update_fields=["quantity"])

        log_movement(
            med, "adjustment", change, request.user,
            reason=ADJUST_REASONS[reason_key], note=note,
        )

    verb = "Removed" if direction == "remove" else "Added"
    return JsonResponse({
        "message": f"{verb} {qty} {med.get_unit_display().lower()}(s) "
                   f"{'from' if direction == 'remove' else 'to'} {med.name}.",
        "medicine": medicine_json(request, med, today),
    })


@api(["GET"])
def movements_view(request):
    query = request.GET.get("q", "").strip()
    kind = request.GET.get("kind", "").strip()

    movements = StockMovement.objects.select_related("created_by")

    if query:
        movements = movements.filter(
            Q(medicine_name__icontains=query)
            | Q(batch_number__icontains=query)
            | Q(reason__icontains=query)
            | Q(note__icontains=query)
            | Q(supplier__icontains=query)
        )
    if kind in dict(StockMovement.KIND_CHOICES):
        movements = movements.filter(kind=kind)

    paginator = Paginator(movements, 15)
    page = paginator.get_page(request.GET.get("page"))

    return JsonResponse({
        "results": [movement_json(m) for m in page],
        "page": page.number,
        "num_pages": paginator.num_pages,
        "count": paginator.count,
        "start_index": page.start_index(),
        "end_index": page.end_index(),
        "has_previous": page.has_previous(),
        "has_next": page.has_next(),
    })


# ---------------------------------------------------------------------------
# Release medicine
# ---------------------------------------------------------------------------

@api(["GET", "POST"])
def release_view(request):
    today = date.today()

    if request.method == "GET":
        available = Medicine.objects.filter(
            quantity__gt=0, expiry_date__gte=today
        ).order_by("name")
        recent = MedicineRelease.objects.select_related("medicine", "released_by")[:10]
        return JsonResponse({
            "medicines": [medicine_json(request, m, today) for m in available],
            "recent": [release_json(r) for r in recent],
        })

    data = json_body(request)
    released_to = str(data.get("released_to", "")).strip()
    note = str(data.get("note", "")).strip()

    try:
        qty = int(data.get("quantity", 0))
    except (TypeError, ValueError):
        qty = 0

    try:
        pk = int(data.get("medicine"))
    except (TypeError, ValueError):
        pk = None

    with transaction.atomic():
        med = Medicine.objects.select_for_update().filter(pk=pk).first() if pk else None

        if not med:
            return fail("Please select a medicine.")
        if qty <= 0:
            return fail("Quantity must be at least 1.")
        if med.expiry_date < today:
            return fail(f"{med.name} is expired and cannot be released.")
        if med.requires_prescription and not note:
            return fail(
                f"{med.name} requires a prescription. "
                "Enter the prescription number in the note field."
            )
        if qty > med.quantity:
            return fail(
                f"Only {med.quantity} {med.get_unit_display().lower()}(s) "
                f"in stock for {med.name}."
            )

        med.quantity -= qty
        med.save(update_fields=["quantity"])
        release = MedicineRelease.objects.create(
            medicine=med,
            quantity=qty,
            unit_price=med.unit_price,
            released_to=released_to[:120],
            note=note[:255],
            released_by=request.user,
        )

        parts = []
        if released_to:
            parts.append("To " + released_to)
        if note:
            parts.append(note)
        log_movement(
            med, "release", -qty, request.user,
            reason="Dispensed", note=" · ".join(parts),
        )

    return JsonResponse(
        {"message": f"Released {qty} of {med.name}.", "release": release_json(release)},
        status=201,
    )
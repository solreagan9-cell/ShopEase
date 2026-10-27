from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Medicine(models.Model):
    UNIT_CHOICES = [
        ("tablet", "Tablet"),
        ("capsule", "Capsule"),
        ("strip", "Strip"),
        ("box", "Box"),
        ("bottle", "Bottle"),
        ("sachet", "Sachet"),
        ("vial", "Vial"),
        ("ampule", "Ampule"),
        ("tube", "Tube"),
        ("piece", "Piece"),
    ]

    DOSAGE_FORMS = [
        ("tablet", "Tablet"),
        ("capsule", "Capsule"),
        ("syrup", "Syrup"),
        ("suspension", "Suspension"),
        ("injection", "Injection"),
        ("cream", "Cream / ointment"),
        ("drops", "Drops"),
        ("inhaler", "Inhaler"),
        ("powder", "Powder / sachet"),
        ("other", "Other"),
    ]

    name = models.CharField(max_length=200)
    generic_name = models.CharField(max_length=200, blank=True)
    category = models.CharField(max_length=100)
    batch_number = models.CharField(max_length=100, unique=True)
    supplier = models.CharField(max_length=200, blank=True)
    quantity = models.PositiveIntegerField(default=0)
    unit = models.CharField(max_length=20, choices=UNIT_CHOICES, default="tablet")
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    expiry_date = models.DateField()
    image = models.ImageField(upload_to="medicines/", blank=True, null=True)

    # Real-pharmacy details
    reorder_level = models.PositiveIntegerField(default=10)
    requires_prescription = models.BooleanField(default=False)
    strength = models.CharField(max_length=50, blank=True)
    dosage_form = models.CharField(max_length=30, choices=DOSAGE_FORMS, blank=True)
    barcode = models.CharField(max_length=64, blank=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["expiry_date"]),
            models.Index(fields=["quantity"]),
        ]

    def __str__(self):
        return f"{self.name} - {self.batch_number}"


class MedicineRelease(models.Model):
    medicine = models.ForeignKey(
        Medicine, on_delete=models.PROTECT, related_name="releases"
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)  # price at time of release
    released_to = models.CharField(max_length=120, blank=True)
    note = models.CharField(max_length=255, blank=True)
    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    released_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-released_at"]

    @property
    def total(self):
        return self.unit_price * self.quantity

    def __str__(self):
        return f"{self.quantity} x {self.medicine.name}"


class StockMovement(models.Model):
    """One line in the stock history: every change to a medicine's quantity."""

    KIND_CHOICES = [
        ("initial", "Initial stock"),
        ("restock", "Restock"),
        ("adjustment", "Adjustment"),
        ("release", "Release"),
    ]

    medicine = models.ForeignKey(
        Medicine, null=True, blank=True, on_delete=models.SET_NULL, related_name="movements"
    )
    # Copies, so the history stays readable even if the medicine is deleted later
    medicine_name = models.CharField(max_length=200)
    batch_number = models.CharField(max_length=100)

    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    quantity_change = models.IntegerField()
    quantity_after = models.PositiveIntegerField()
    reason = models.CharField(max_length=60, blank=True)
    supplier = models.CharField(max_length=200, blank=True)
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.quantity_change:+d} {self.medicine_name}"
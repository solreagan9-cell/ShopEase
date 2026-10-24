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
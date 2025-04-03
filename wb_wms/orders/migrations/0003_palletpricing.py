# Generated by Django 4.2.10 on 2025-04-03 06:34

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0002_container_box_price_container_pallet_prices"),
    ]

    operations = [
        migrations.CreateModel(
            name="PalletPricing",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "weight_category",
                    models.CharField(
                        choices=[
                            ("0-200 кг", "0-200 кг"),
                            ("200-300 кг", "200-300 кг"),
                            ("300-400 кг", "300-400 кг"),
                            ("400-500 кг", "400-500 кг"),
                            ("Другой вес", "Другой вес"),
                        ],
                        max_length=50,
                        unique=True,
                        verbose_name="Весовая категория",
                    ),
                ),
                (
                    "price",
                    models.DecimalField(
                        decimal_places=2, max_digits=10, verbose_name="Цена за паллету"
                    ),
                ),
                (
                    "description",
                    models.TextField(blank=True, null=True, verbose_name="Описание"),
                ),
                (
                    "is_active",
                    models.BooleanField(default=True, verbose_name="Активен"),
                ),
            ],
            options={
                "verbose_name": "Цена паллеты",
                "verbose_name_plural": "Цены паллет",
                "ordering": ["weight_category"],
            },
        ),
    ]

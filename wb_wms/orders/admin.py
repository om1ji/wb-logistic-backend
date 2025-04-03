from django.contrib import admin

from .models import (
    AdditionalService,
    BoxPricing,
    City,
    Container,
    Marketplace,
    Order,
    PalletPricing,
    Pricing,
    User,
    Warehouse,
    Driver,
    Truck,
)


class WarehouseAdmin(admin.ModelAdmin):
    list_display = ("name", "marketplace", "city", "marketplace_name", "city_name")
    search_fields = ("name", "marketplace__name", "city__name")
    list_filter = ("marketplace", "city")

    def marketplace_name(self, obj):
        return obj.marketplace.name

    def city_name(self, obj):
        return obj.city.name

    marketplace_name.short_description = "Маркетплейс"
    city_name.short_description = "Город"


class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "client_name",
        "phone_number",
        "warehouse",
        "status",
        "total_price",
        "created_at",
    )
    search_fields = ("id", "client_name", "phone_number")
    list_filter = ("status", "warehouse")
    readonly_fields = ("total_price",)
    filter_horizontal = ("services",)

    fieldsets = (
        ("Основная информация", {"fields": ("status", "warehouse", "total_price")}),
        (
            "Информация о клиенте",
            {
                "fields": (
                    "client_name",
                    "phone_number",
                    "company",
                    "email",
                    "telegram_user_id",
                )
            },
        ),
        (
            "Информация о грузе",
            {
                "fields": (
                    "cargo_type",
                    "container_type",
                    "box_count",
                    "pallet_count",
                    "length",
                    "width",
                    "height",
                    "weight",
                )
            },
        ),
        (
            "Дополнительные услуги",
            {"fields": ("services", "pickup_address", "additional_services")},
        ),
    )


class PricingAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "pricing_type",
        "specification",
        "base_price",
        "unit_price",
        "warehouse",
        "is_active",
    )
    list_filter = ("pricing_type", "warehouse", "is_active")
    search_fields = ("name", "specification")


class PalletPricingAdmin(admin.ModelAdmin):
    list_display = (
        "weight_category", 
        "price", 
        "is_active",
        "description",
    )
    list_filter = ("is_active", "weight_category")
    search_fields = ("weight_category", "description")
    
    fieldsets = (
        (
            "Основная информация", 
            {
                "fields": (
                    "weight_category", 
                    "price", 
                    "is_active",
                )
            }
        ),
        (
            "Дополнительно", 
            {
                "fields": ("description",),
                "classes": ("collapse",),
            }
        ),
    )
    
    actions = ["duplicate_pricing"]
    
    def duplicate_pricing(self, request, queryset):
        """
        Действие для дублирования выбранных тарифов
        """
        for pricing in queryset:
            pricing.pk = None  # Создаем новый объект
            pricing.is_active = False  # Деактивируем
            pricing.description = f"Копия: {pricing.description or pricing.weight_category}"
            pricing.save()
        
        self.message_user(request, f"Создано {queryset.count()} копий тарифов")
    
    duplicate_pricing.short_description = "Дублировать выбранные тарифы"


class AdditionalServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "service_type", "price", "requires_location", "is_active")
    list_filter = ("service_type", "requires_location", "is_active")
    search_fields = ("name", "description")

    fieldsets = (
        (
            "Основная информация",
            {"fields": ("name", "service_type", "price", "is_active")},
        ),
        ("Дополнительные настройки", {"fields": ("requires_location", "description")}),
    )


class MarketplaceAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)


class CityAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)


class UserAdmin(admin.ModelAdmin):
    list_display = ("username", "email", "first_name", "last_name", "phone", "is_staff")
    search_fields = ("username", "email", "first_name", "last_name", "phone")
    list_filter = ("is_staff", "is_active", "groups")
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Персональная информация", {"fields": ("first_name", "last_name", "email", "phone", "company_name")}),
        ("Разрешения", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Важные даты", {"fields": ("last_login", "date_joined", "created_at")}),
    )


class BoxPricingAdmin(admin.ModelAdmin):
    list_display = (
        "size_category",
        "volume_range",
        "price",
        "is_active",
        "description",
    )
    list_filter = ("is_active", "size_category", "volume_range")
    search_fields = ("size_category", "description")
    
    fieldsets = (
        (
            "Основная информация", 
            {
                "fields": (
                    "size_category",
                    "volume_range",
                    "price",
                    "is_active",
                )
            }
        ),
        (
            "Дополнительно", 
            {
                "fields": ("description",),
                "classes": ("collapse",),
            }
        ),
    )
    
    actions = ["duplicate_pricing"]
    
    def duplicate_pricing(self, request, queryset):
        """
        Действие для дублирования выбранных тарифов
        """
        for pricing in queryset:
            pricing.pk = None  # Создаем новый объект
            pricing.is_active = False  # Деактивируем
            pricing.description = f"Копия: {pricing.description or pricing.size_category}"
            pricing.save()
        
        self.message_user(request, f"Создано {queryset.count()} копий тарифов")
    
    duplicate_pricing.short_description = "Дублировать выбранные тарифы"


@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'phone', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('full_name', 'phone')
    ordering = ('-created_at',)


@admin.register(Truck)
class TruckAdmin(admin.ModelAdmin):
    list_display = ('brand', 'model', 'plate_number', 'is_active', 'created_at')
    list_filter = ('is_active', 'brand')
    search_fields = ('brand', 'model', 'plate_number')
    ordering = ('-created_at',)


# Регистрация моделей в админ-панели
# Основные рабочие модели
admin.site.register(Order, OrderAdmin)
admin.site.register(AdditionalService, AdditionalServiceAdmin)
admin.site.register(Pricing, PricingAdmin)
admin.site.register(PalletPricing, PalletPricingAdmin)
admin.site.register(BoxPricing, BoxPricingAdmin)

# Справочные модели
admin.site.register(Warehouse, WarehouseAdmin)
admin.site.register(Marketplace, MarketplaceAdmin)
admin.site.register(City, CityAdmin)

# Модель пользователя
admin.site.register(User, UserAdmin)

# Container не регистрируем в админке, так как не требует вмешательства человека
# admin.site.register(Container)

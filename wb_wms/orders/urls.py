from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views
from .views import (
    AdditionalServiceViewSet,
    test_pricing,
    OrderViewSet,
    DriverViewSet,
    TruckViewSet,
    assign_driver,
    reject_order,
    get_service_names,
)

app_name = "orders"

# Роутер для водителей и грузовиков
driver_router = DefaultRouter()
driver_router.register(r'drivers', DriverViewSet)
driver_router.register(r'trucks', TruckViewSet)

urlpatterns = [
    # Основные маршруты для заказов
    path(
        "",
        views.OrderViewSet.as_view({"get": "list", "post": "create"}),
        name="order-list",
    ),
    path(
        "<uuid:pk>/",
        views.OrderViewSet.as_view(
            {
                "get": "retrieve",
                "put": "update",
                "patch": "partial_update",
                "delete": "destroy",
            }
        ),
        name="order-detail",
    ),
    # Маршруты для водителей и грузовиков в отдельном пространстве
    path('transport/', include(driver_router.urls)),
    path('<uuid:order_id>/assign_driver/', assign_driver, name='assign-driver'),
    path('<uuid:order_id>/reject/', reject_order, name='reject-order'),
    path(
        "warehouses/",
        views.WarehouseViewSet.as_view({"get": "list"}),
        name="warehouse-list",
    ),
    path(
        "containers/",
        views.ContainerTypesViewSet.as_view({"get": "list"}),
        name="container-list",
    ),
    path(
        "pricing/",
        views.PricingViewSet.as_view({"get": "list", "post": "create"}),
        name="pricing-list",
    ),
    path(
        "pricing/<int:pk>/",
        views.PricingViewSet.as_view(
            {
                "get": "retrieve",
                "put": "update",
                "patch": "partial_update",
                "delete": "destroy",
            }
        ),
        name="pricing-detail",
    ),
    path(
        "calculate-price/",
        views.PricingViewSet.as_view({"post": "calculate_price"}),
        name="calculate-price",
    ),
    path(
        "additional_services/",
        views.PricingViewSet.as_view({"get": "get_additional_services"}),
        name="additional-services",
    ),
    path(
        "services/",
        views.AdditionalServiceViewSet.as_view({"get": "list", "post": "create"}),
        name="services-list",
    ),
    path(
        "services/<int:pk>/",
        views.AdditionalServiceViewSet.as_view(
            {
                "get": "retrieve",
                "put": "update",
                "patch": "partial_update",
                "delete": "destroy",
            }
        ),
        name="service-detail",
    ),
    path("services/names/", get_service_names, name="service-names"),
    path("test-pricing/", test_pricing, name="test-pricing"),
    path(
        "send-telegram-notification/",
        views.send_telegram_notification,
        name="send-telegram-notification",
    ),
    path("health/", views.health_check, name="health-check"),
]

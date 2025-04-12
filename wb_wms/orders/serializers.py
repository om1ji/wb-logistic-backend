import datetime
import json
import uuid
from decimal import Decimal

from django.db import connection
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.response import Response

from .models import (
    AdditionalService,
    City,
    Container,
    Marketplace,
    Order,
    Pricing,
    User,
    Warehouse,
    Driver,
    Truck,
)


class MarketplaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Marketplace
        fields = "__all__"


class WarehouseSerializer(serializers.ModelSerializer):
    city_name = serializers.CharField(source="city.name", read_only=True)
    marketplace_name = serializers.CharField(source="marketplace.name", read_only=True)

    class Meta:
        model = Warehouse
        fields = ["id", "name", "marketplace", "marketplace_name", "city", "city_name"]

    def list(self, request):
        warehouses = Warehouse.objects.all()
        serializer = self.serializer_class(warehouses, many=True)
        return Response(serializer.data)


class DriverSerializer(serializers.ModelSerializer):
    class Meta:
        model = Driver
        fields = ['id', 'full_name', 'phone', 'is_active']


class TruckSerializer(serializers.ModelSerializer):
    class Meta:
        model = Truck
        fields = ['id', 'brand', 'truck_model', 'plate_number', 'is_active']


class OrderSerializer(serializers.ModelSerializer):
    containers_info = serializers.SerializerMethodField()
    client_info = serializers.SerializerMethodField()
    driver = DriverSerializer(read_only=True)
    truck = TruckSerializer(read_only=True)

    class Meta:
        model = Order
        fields = "__all__"
        read_only_fields = ("created_at",)

    def get_containers_info(self, obj):
        if isinstance(obj, Order):
            try:
                return [
                    {
                        "type": container.container_type,
                        "size": (
                            container.box_size
                            if container.container_type == "Коробка"
                            else container.pallet_weight
                        ),
                        "quantity": container.quantity,
                    }
                    for container in obj.containers.all()
                ]
            except AttributeError:
                # Обрабатываем случай, когда containers не существует
                # Возвращаем информацию на основе box_count и pallet_count
                containers_info = []
                if obj.box_count and obj.box_count > 0:
                    containers_info.append({
                        "type": "Коробка",
                        "size": obj.container_type if obj.cargo_type == "box" else "",
                        "quantity": obj.box_count
                    })
                if obj.pallet_count and obj.pallet_count > 0:
                    containers_info.append({
                        "type": "Паллета",
                        "size": obj.container_type if obj.cargo_type == "pallet" else "",
                        "quantity": obj.pallet_count
                    })
                return containers_info
        return []

    def get_client_info(self, obj):
        if isinstance(obj, Order):
            try:
                if hasattr(obj, "user_id") and obj.user_id:
                    return {
                        "company_name": obj.user_id.company_name,
                        "client_name": obj.user_id.username,
                        "email": obj.user_id.email,
                        "phone": obj.user_id.phone,
                    }
            except Exception:
                pass
            
            # Если user_id не существует или произошла ошибка, используем прямые поля заказа
            return {
                "company_name": obj.company or "",
                "client_name": obj.client_name or "",
                "email": obj.email or "",
                "phone": obj.phone_number or "",
            }
        return {}

    def to_internal_value(self, data):
        return data

    def calculate_order_price(self, data):
        """Рассчитать стоимость заказа"""
        total_price = Decimal("0.00")

        # Извлекаем данные
        delivery_data = data.get("delivery", {})
        cargo_type_data = data.get("cargoType", {})
        additional_services = data.get("additionalServices", [])

        # 1. Расчет стоимости доставки
        if delivery_data and "warehouse" in delivery_data:
            warehouse_id = delivery_data["warehouse"]
            delivery_pricing = Pricing.objects.filter(
                pricing_type="delivery", warehouse__id=warehouse_id, is_active=True
            ).first()

            if delivery_pricing:
                total_price += delivery_pricing.base_price

        # 2. Расчет стоимости по типу груза
        if cargo_type_data:
            # Обработка коробок (всегда обрабатываем, если они есть)
            if (
                "quantities" in cargo_type_data
                and "Коробка" in cargo_type_data["quantities"]
                and int(cargo_type_data["quantities"]["Коробка"]) > 0
            ):
                # Определяем размер коробки
                box_size = None
                if (
                    "selectedBoxSizes" in cargo_type_data
                    and cargo_type_data["selectedBoxSizes"]
                ):
                    box_size = cargo_type_data["selectedBoxSizes"][0]

                # Получаем количество
                quantity = int(cargo_type_data["quantities"]["Коробка"])

                if quantity > 0:
                    # Ищем тариф для коробок указанного размера
                    box_pricing = None
                    if box_size:
                        box_pricing = Pricing.objects.filter(
                            pricing_type="box", specification=box_size, is_active=True
                        ).first()

                    # Если тариф для указанного размера не найден, ищем любой тариф для коробок
                    if not box_pricing:
                        box_pricing = Pricing.objects.filter(
                            pricing_type="box", is_active=True
                        ).first()

                    if box_pricing:
                        # Базовая цена + (цена за единицу * количество)
                        box_cost = box_pricing.base_price + (
                            box_pricing.unit_price * Decimal(quantity)
                        )
                        total_price += box_cost

            # Обработка паллет (всегда обрабатываем, если они есть)
            if (
                "quantities" in cargo_type_data
                and "Паллета" in cargo_type_data["quantities"]
                and int(cargo_type_data["quantities"]["Паллета"]) > 0
            ):
                # Определяем вес паллеты
                pallet_weight = None
                if (
                    "selectedPalletWeights" in cargo_type_data
                    and cargo_type_data["selectedPalletWeights"]
                ):
                    pallet_weight = cargo_type_data["selectedPalletWeights"][0]

                # Получаем количество
                quantity = int(cargo_type_data["quantities"]["Паллета"])

                if quantity > 0:
                    # Ищем тариф для паллет указанного веса
                    pallet_pricing = None
                    if pallet_weight:
                        pallet_pricing = Pricing.objects.filter(
                            pricing_type="pallet",
                            specification=pallet_weight,
                            is_active=True,
                        ).first()

                    # Если тариф для указанного веса не найден, ищем любой тариф для паллет
                    if not pallet_pricing:
                        pallet_pricing = Pricing.objects.filter(
                            pricing_type="pallet", is_active=True
                        ).first()

                    if pallet_pricing:
                        # Базовая цена + (цена за единицу * количество)
                        pallet_cost = pallet_pricing.base_price + (
                            pallet_pricing.unit_price * Decimal(quantity)
                        )
                        total_price += pallet_cost
                    else:
                        # Если тариф не найден, используем базовую стоимость
                        total_price += Decimal("2000.00") * Decimal(quantity)

        # 3. Расчет стоимости дополнительных услуг
        for service_id in additional_services:
            # Проверяем, есть ли такая услуга в новой таблице AdditionalService
            service = AdditionalService.objects.filter(
                id=service_id, is_active=True
            ).first()

            if service:
                total_price += service.price
            else:
                # Если не нашли в новой модели, ищем в старой системе тарифов
                service_pricing = Pricing.objects.filter(
                    id=service_id, is_active=True
                ).first()

                if service_pricing:
                    total_price += service_pricing.base_price

        # Округляем до 2 знаков после запятой
        return total_price.quantize(Decimal("0.01"))

    def create(self, validated_data):
        try:
            # 1. Получаем необходимые данные из validated_data
            delivery_data = validated_data.get("delivery", {})
            cargo_type_data = validated_data.get("cargoType", {})
            client_data = validated_data.get("clientData", {})
            additional_services = validated_data.get("additionalServices", [])
            pickup_address = validated_data.get("pickupAddress", "")

            # 2. Получаем ID склада
            warehouse = None
            if delivery_data and "warehouse" in delivery_data:
                warehouse_id = delivery_data["warehouse"]
                try:
                    warehouse = Warehouse.objects.get(id=warehouse_id)
                except Warehouse.DoesNotExist:
                    pass

            # 3. Определяем тип груза и контейнера
            cargo_type = "mixed"
            container_type = None
            box_count = 0
            pallet_count = 0

            # Обработка выбранных типов груза
            if "type" in cargo_type_data:
                primary_cargo_type = cargo_type_data["type"]
                if primary_cargo_type == "Коробка":
                    cargo_type = "box"
                    container_type = (
                        cargo_type_data.get("selectedBoxSizes", [""])[0]
                        if cargo_type_data.get("selectedBoxSizes")
                        else None
                    )
                elif primary_cargo_type == "Паллета":
                    cargo_type = "pallet"
                    container_type = (
                        cargo_type_data.get("selectedPalletWeights", [""])[0]
                        if cargo_type_data.get("selectedPalletWeights")
                        else None
                    )

            # Заполняем количество коробок и паллет
            if "quantities" in cargo_type_data:
                if "Коробка" in cargo_type_data["quantities"]:
                    box_count = int(cargo_type_data["quantities"]["Коробка"])
                if "Паллета" in cargo_type_data["quantities"]:
                    pallet_count = int(cargo_type_data["quantities"]["Паллета"])

            # 4. Рассчитываем стоимость заказа
            total_price = self.calculate_order_price(validated_data)

            # 5. Создаем заказ через ORM
            order = Order.objects.create(
                status="new",
                total_price=total_price,
                warehouse=warehouse,
                cargo_type=cargo_type,
                container_type=container_type,
                box_count=box_count,
                pallet_count=pallet_count,
                client_name=client_data.get("name", ""),
                phone_number=client_data.get("phone", ""),
                company=client_data.get("company", ""),
                email=client_data.get("email", ""),
                pickup_address=pickup_address,
                telegram_user_id=client_data.get("user_id")
            )
            
            # Логируем данные для отладки
            print(f"Creating order with telegram_user_id: {order.telegram_user_id}, from client data: {client_data}")

            # 6. Добавляем дополнительные услуги, если они есть
            if additional_services:
                for service_id in additional_services:
                    try:
                        service = AdditionalService.objects.get(id=service_id)
                        order.services.add(service)
                    except Exception as e:
                        print(
                            f"Error adding service {service_id} to order {order.id}: {e}"
                        )

            # 7. Возвращаем созданный заказ
            return order

        except Exception as e:
            import traceback

            print(f"Error creating order: {e}")
            print(traceback.format_exc())
            print(f"Validated data: {validated_data}")
            raise serializers.ValidationError(f"Failed to create order: {e}")

    def update(self, instance, validated_data):
        # Обновляем только статус, если он передан
        if "status" in validated_data:
            instance.status = validated_data["status"]
            instance.save()
        return instance

    def delete(self, instance):
        instance.delete()
        return instance

    def list(self, request):
        orders = Order.objects.all()
        serializer = self.serializer_class(orders, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk):
        order = Order.objects.get(pk=pk)
        serializer = self.serializer_class(order)
        return Response(serializer.data)

    def destroy(self, request, pk):
        order = Order.objects.get(pk=pk)
        order.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ContainerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Container
        fields = "__all__"

    def list(self, request):
        containers = Container.objects.all()
        serializer = self.serializer_class(containers, many=True)
        return Response(serializer.data)


class PricingSerializer(serializers.ModelSerializer):
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)

    class Meta:
        model = Pricing
        fields = [
            "id",
            "name",
            "pricing_type",
            "specification",
            "warehouse",
            "warehouse_name",
            "base_price",
            "unit_price",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ("created_at", "updated_at")


class AdditionalServiceSerializer(serializers.ModelSerializer):
    """Сериализатор для дополнительных услуг"""

    service_type_display = serializers.CharField(
        source="get_service_type_display", read_only=True
    )

    class Meta:
        model = AdditionalService
        fields = [
            "id",
            "name",
            "price",
            "service_type",
            "service_type_display",
            "requires_location",
            "description",
            "is_active",
            "created_at",
        ]
        read_only_fields = ("created_at",)

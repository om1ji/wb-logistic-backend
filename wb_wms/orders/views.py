import datetime
import json
import logging
import os
import traceback
import uuid
from decimal import Decimal
from django.utils import timezone

import requests
from django.db import connection
from django.db.models import DecimalField, ExpressionWrapper, F, Prefetch, Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework import status, viewsets, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response

from .models import (
    AdditionalService, 
    Container, 
    Marketplace, 
    Order, 
    Pricing, 
    Warehouse, 
    PalletPricing, 
    BoxPricing,
    Driver,
    Truck
)
from .serializers import (
    AdditionalServiceSerializer,
    MarketplaceSerializer,
    OrderSerializer,
    PricingSerializer,
    WarehouseSerializer,
    DriverSerializer,
    TruckSerializer,
)

logger = logging.getLogger(__name__)

TELEGRAM_BOT_URL = os.getenv('TELEGRAM_BOT_URL')

class MarketplaceViewSet(viewsets.ModelViewSet):
    queryset = Marketplace.objects.all()
    serializer_class = MarketplaceSerializer

    @action(detail=False, methods=["get"])
    def with_warehouses(self, request):
        marketplaces = Marketplace.objects.prefetch_related(
            Prefetch("warehouse_set", queryset=Warehouse.objects.select_related("city"))
        ).all()

        data = []
        for marketplace in marketplaces:
            warehouses = [
                {"id": w.id, "name": w.name, "city": w.city.name}
                for w in marketplace.warehouse_set.all()
            ]

            data.append(
                {
                    "id": marketplace.id,
                    "name": marketplace.name,
                    "warehouses": warehouses,
                }
            )

        return Response(data)


class ContainerTypesViewSet(viewsets.ViewSet):
    def list(self, request):
        data = {
            "box_sizes": [
                {"id": size[0], "label": size[1]} for size in Container.BOX_SIZES
            ],
            "pallet_weights": [
                {"id": weight[0], "label": weight[1]}
                for weight in Container.PALLET_WEIGHT
            ],
            "container_types": [
                {"id": type[0], "label": type[1]} for type in Container.CONTAINER_TYPES
            ],
        }
        return Response(data)


class WarehouseViewSet(viewsets.ModelViewSet):
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer

    def list(self, request):
        warehouses = Warehouse.objects.all()
        serializer = self.serializer_class(warehouses, many=True)
        return Response(serializer.data)


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer

    def create(self, request, *args, **kwargs):
        try:
            # Получаем данные из запроса
            delivery_data = request.data.get("delivery", {})
            cargo_data = request.data.get("cargo", {})
            client_data = request.data.get("client", {})
            additional_services = request.data.get("additional_services", [])
            pickup_address = request.data.get("pickup_address", "")

            # Получаем или создаем склад
            warehouse_id = delivery_data.get("warehouse_id")
            try:
                warehouse = Warehouse.objects.get(id=warehouse_id)
            except Warehouse.DoesNotExist:
                return Response(
                    {"error": "Warehouse not found"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Создаем заказ
            order = Order(
                warehouse=warehouse,
                cargo_type=cargo_data.get("cargo_type", ""),
                container_type=cargo_data.get("container_type", ""),
                box_count=cargo_data.get("box_count", 0),
                pallet_count=cargo_data.get("pallet_count", 0),
                client_name=client_data.get("name", ""),
                phone_number=client_data.get("phone", ""),
                company=client_data.get("company", ""),
                email=client_data.get("email", ""),
                pickup_address=pickup_address,
                status="new"
            )

            # Сохраняем размеры и вес если они есть
            dimensions = cargo_data.get("dimensions", {})
            if dimensions:
                order.length = dimensions.get("length") or None
                order.width = dimensions.get("width") or None
                order.height = dimensions.get("height") or None
                order.weight = dimensions.get("weight") or None

            # Сохраняем дополнительную информацию
            order.additional_services = {
                "cargo": cargo_data,
                "client": client_data,
                "delivery": delivery_data
            }

            # Сначала сохраняем заказ, чтобы создать запись в базе
            order.save()

            # Добавляем дополнительные услуги
            if additional_services:
                services = AdditionalService.objects.filter(
                    id__in=additional_services,
                    is_active=True
                )
                order.services.add(*services)

            # Теперь, когда все услуги добавлены, рассчитываем полную стоимость
            order.total_price = order.calculate_price()
            order.save()  # Сохраняем обновленную цену

            # Формируем данные для уведомления в Telegram
            telegram_data = {
                "order_id": str(order.id),
                "sequence_number": order.sequence_number,
                "warehouse_name": str(order.warehouse),
                "cargo_type": order.cargo_type,
                "box_size": order.container_type,  # Для обратной совместимости
                "container_type": order.container_type,
                "box_count": order.box_count,
                "pallet_count": order.pallet_count,
                "company_name": order.company,
                "client_name": order.client_name,
                "client_phone": order.phone_number,
                "cost": str(order.total_price),
                "pickup_address": order.pickup_address or "Не указан",
                "additional_services": [
                    {
                        "name": str(service),
                        "price": str(service.price)
                    } for service in order.services.all()
                ]
            }

            # Отправляем уведомление в Telegram
            try:
                response = requests.post(
                    f"{TELEGRAM_BOT_URL}/api/send_notification",
                    json=telegram_data
                )
                logger.info(f"Telegram notification sent: {response.json()}")
            except Exception as e:
                logger.error(f"Error sending Telegram notification: {str(e)}")

            # Формируем ответ
            return Response(
                {
                    "success": True,
                    "message": "Order created successfully",
                    "order": {
                        "id": str(order.id),
                        "sequence_number": order.sequence_number,
                        "status": order.status,
                        "total_price": str(order.total_price),
                        "created_at": order.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                        "warehouse_id": order.warehouse.id,
                        "pickup_address": order.pickup_address,
                        "client": {
                            "name": order.client_name,
                            "phone": order.phone_number,
                            "company": order.company,
                            "email": order.email
                        },
                        "cargo": {
                            "type": order.cargo_type,
                            "container_type": order.container_type,
                            "box_count": order.box_count,
                            "pallet_count": order.pallet_count,
                            "dimensions": {
                                "length": str(order.length) if order.length else "",
                                "width": str(order.width) if order.width else "",
                                "height": str(order.height) if order.height else "",
                                "weight": str(order.weight) if order.weight else ""
                            }
                        },
                        "additional_services": [
                            {
                                "id": service.id,
                                "name": service.name,
                                "price": str(service.price)
                            }
                            for service in order.services.all()
                        ]
                    }
                },
                status=status.HTTP_201_CREATED
            )

        except Exception as e:
            logger.error(f"Error creating order: {str(e)}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(instance, "_prefetched_objects_cache", None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}

        return Response(serializer.data)

    def perform_update(self, serializer):
        serializer.save()

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_destroy(self, instance):
        instance.delete()

    def list(self, request):
        orders = Order.objects.all()
        serializer = self.serializer_class(orders, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        order = self.get_object()
        serializer = self.serializer_class(order)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def assign_driver(self, request, pk=None):
        """
        Назначает водителя и грузовик на заказ
        """
        try:
            order = self.get_object()
            driver_id = request.data.get('driver_id')
            truck_id = request.data.get('truck_id')
            
            if not driver_id or not truck_id:
                return Response(
                    {'error': 'Необходимо указать ID водителя и грузовика'},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
            try:
                driver = Driver.objects.get(id=driver_id, is_active=True)
                truck = Truck.objects.get(id=truck_id, is_active=True)
            except (Driver.DoesNotExist, Truck.DoesNotExist):
                return Response(
                    {'error': 'Водитель или грузовик не найден'},
                    status=status.HTTP_404_NOT_FOUND
                )
                
            order.driver = driver
            order.truck = truck
            order.driver_assigned_at = timezone.now()
            order.status = 'accepted'
            order.save()
            
            # Отправляем уведомление в Telegram
            telegram_data = {
                "order_id": str(order.id),
                "sequence_number": order.sequence_number,
                "driver_name": driver.full_name,
                "truck_info": f"{truck.brand} - {truck.plate_number}",
                "notification_type": "driver_assigned"
            }
            
            try:
                response = requests.post(
                    f"{TELEGRAM_BOT_URL}/api/send_notification",
                    json=telegram_data
                )
                logger.info(f"Telegram notification sent: {response.json()}")
            except Exception as e:
                logger.error(f"Error sending Telegram notification: {str(e)}")
            
            return Response({
                'success': True,
                'message': 'Водитель и грузовик успешно назначены',
                'driver': DriverSerializer(driver).data,
                'truck': TruckSerializer(truck).data
            })
            
        except Exception as e:
            logger.error(f"Error assigning driver and truck: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class ContainerTypesViewSet(viewsets.ViewSet):
    def list(self, request):
        data = {
            "box_sizes": [
                {"id": size[0], "label": size[1]} for size in Container.BOX_SIZES
            ],
            "pallet_weights": [
                {"id": weight[0], "label": weight[1]}
                for weight in Container.PALLET_WEIGHT
            ],
            "container_types": [
                {"id": type[0], "label": type[1]} for type in Container.CONTAINER_TYPES
            ],
        }
        return Response(data)


@api_view(["POST"])
def send_telegram_notification(request):
    """Отправить уведомление в Telegram"""
    try:
        # Получаем данные из запроса
        order_data = request.data

        # Отправляем запрос к Telegram боту
        response = requests.post(f"{TELEGRAM_BOT_URL}/api/send_notification", json=order_data)

        if response.status_code == 200:
            return Response({"status": "success"}, status=status.HTTP_200_OK)
        else:
            return Response(
                {"status": "error", "message": response.text},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
    except Exception as e:
        return Response(
            {"status": "error", "message": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
def health_check(request):
    return Response({"status": "ok"})


class PricingViewSet(viewsets.ModelViewSet):
    queryset = Pricing.objects.all()
    serializer_class = PricingSerializer

    @action(detail=False, methods=["post"])
    def calculate_price(self, request):
        """Рассчитать стоимость заказа на основе переданных данных формы"""
        try:
            # Извлекаем данные
            delivery_data = request.data.get("delivery", {})
            cargo_type_data = request.data.get("cargo", {})
            additional_services = request.data.get("additionalServices", [])

            # Log the received data for debugging
            logger.info(f"Received price calculation request: {request.data}")
            logger.info(f"Extracted cargo data: {cargo_type_data}")

            total_price = Decimal("0.00")

            # 1. Расчет стоимости доставки
            delivery_price = Decimal("0.00")
            if delivery_data:
                warehouse_id = delivery_data.get("warehouse_id") or delivery_data.get(
                    "warehouse"
                )
                if warehouse_id:
                    try:
                        # Ищем тариф доставки для выбранного склада
                        delivery_pricing = Pricing.objects.filter(
                            pricing_type="delivery",
                            warehouse__id=warehouse_id,
                            is_active=True,
                        ).first()

                        # If no pricing found for specific warehouse, use any delivery pricing
                        if not delivery_pricing:
                            delivery_pricing = Pricing.objects.filter(
                                pricing_type="delivery", is_active=True
                            ).first()
                            logger.info(
                                f"No specific delivery pricing found for warehouse {warehouse_id}, using first available"
                            )

                        if delivery_pricing:
                            delivery_price = delivery_pricing.base_price
                            total_price += delivery_price
                            logger.info(
                                f"Added delivery price: {delivery_price} using pricing {delivery_pricing.id}"
                            )
                        else:
                            total_price += delivery_price
                    except Exception as e:
                        logger.error(f"Error calculating delivery price: {str(e)}")
                        total_price += delivery_price

            # 2. Расчет стоимости по типу груза
            if cargo_type_data:
                # Determine cargo type and counts
                cargo_type = cargo_type_data.get("cargo_type", "")
                box_count = int(cargo_type_data.get("box_count", 0))
                pallet_count = int(cargo_type_data.get("pallet_count", 0))
                container_type = cargo_type_data.get("container_type", "")

                logger.info(
                    f"Processing cargo: type={cargo_type}, box_count={box_count}, pallet_count={pallet_count}"
                )

                # Process boxes
                if box_count > 0:
                    box_price = None
                    
                    if container_type == "Другой размер":
                        try:
                            # Получаем размеры из поля dimensions
                            dimensions = cargo_type_data.get("dimensions", {})
                            length = float(dimensions.get("length", 0))
                            width = float(dimensions.get("width", 0))
                            height = float(dimensions.get("height", 0))
                            
                            # Проверяем, что все размеры больше 0
                            if length > 0 and width > 0 and height > 0:
                                # Определяем диапазон объема
                                volume_range = BoxPricing.calculate_volume(length, width, height)
                                print(volume_range)
                                
                                # Ищем цену для данного диапазона объема
                                box_pricing = BoxPricing.objects.filter(
                                    size_category="Другой размер",
                                    volume_range=volume_range,
                                    is_active=True
                                ).first()
                                
                                if box_pricing:
                                    box_price = box_pricing.price
                                    logger.info(f"Using box price from BoxPricing: {box_price} for volume range {volume_range}")
                                else:
                                    # Если не нашли цену в БД, используем значения по умолчанию
                                    default_prices = BoxPricing.get_default_prices()
                                    box_price = Decimal(str(default_prices.get(volume_range, "450.00")))
                                    logger.info(f"Using default box price: {box_price} for volume range {volume_range}")
                            else:
                                # Если какой-то из размеров равен 0, используем минимальную цену
                                box_price = Decimal("450.00")
                                logger.warning("One or more dimensions are 0, using minimum price")
                        except Exception as e:
                            # В случае ошибки используем минимальную цену
                            box_price = Decimal("450.00")
                            logger.error(f"Error calculating custom box price: {e}")
                    else:
                        # Для стандартного размера ищем цену в БД
                        box_pricing = BoxPricing.objects.filter(
                            size_category=container_type,
                            is_active=True
                        ).first()
                        
                        if box_pricing:
                            box_price = box_pricing.price
                            logger.info(f"Using box price from BoxPricing: {box_price} for size {container_type}")
                        else:
                            # Если не нашли цену в БД, используем значения по умолчанию
                            default_prices = BoxPricing.get_default_prices()
                            box_price = Decimal(str(default_prices.get(container_type, "450.00")))
                            logger.info(f"Using default box price: {box_price} for size {container_type}")
                    
                    box_cost = box_price * Decimal(box_count)
                    total_price += box_cost
                    logger.info(f"Added box price: {box_cost} for {box_count} boxes at {box_price} each")

                # Process pallets
                if pallet_count > 0:
                    pallet_price = None
                    
                    if container_type:
                        try:
                            if container_type == "Другой вес":
                                # Получаем вес из dimensions
                                dimensions = cargo_type_data.get("dimensions", {})
                                weight = float(dimensions.get("weight", 0))
                                
                                if weight > 0:
                                    if weight <= 500:
                                        # Если вес до 500 кг, используем стандартную цену
                                        pallet_price = Decimal("5000.00")
                                    else:
                                        # Для веса больше 500 кг считаем дополнительную стоимость
                                        # За каждые 100 кг свыше 500 кг добавляем 1000 рублей
                                        extra_weight = weight - 500  # Излишек веса
                                        extra_hundreds = (extra_weight + 99) // 100  # Округляем вверх до сотен
                                        extra_cost = extra_hundreds * 1000  # 1000 руб. за каждые 100 кг
                                        pallet_price = Decimal("5000.00") + Decimal(str(extra_cost))
                                        logger.info(f"Calculated custom weight price: base 5000 + {extra_cost} for {extra_weight}kg over 500kg")
                                else:
                                    # Если вес не указан или равен 0, используем минимальную цену
                                    pallet_price = Decimal("2000.00")
                                    logger.warning("Weight is 0 or not specified, using minimum price")
                            else:
                                # Для стандартных весовых категорий ищем цену в БД
                                pallet_pricing = PalletPricing.objects.filter(
                                    weight_category=container_type,
                                    is_active=True
                                ).first()
                                
                                if pallet_pricing:
                                    pallet_price = pallet_pricing.price
                                    logger.info(f"Using pallet price from PalletPricing: {pallet_price} for category {container_type}")
                                else:
                                    # Если не нашли, используем стандартные цены
                                    default_prices = PalletPricing.get_default_prices()
                                    pallet_price = Decimal(str(default_prices.get(container_type, "2000.00")))
                                    logger.info(f"Using default pallet price: {pallet_price} for category {container_type}")
                        except Exception as e:
                            # В случае ошибки используем минимальную цену
                            pallet_price = Decimal("2000.00")
                            logger.error(f"Error getting pallet price: {e}")
                    else:
                        # Если тип не указан, используем минимальную цену
                        pallet_price = Decimal("2000.00")
                        logger.info(f"Using minimum pallet price: {pallet_price}")
                    
                    pallet_cost = pallet_price * Decimal(pallet_count)
                    total_price += pallet_cost
                    logger.info(f"Added pallet price: {pallet_cost} for {pallet_count} pallets at {pallet_price} each")

            # 3. Расчет стоимости дополнительных услуг
            additional_services_cost = Decimal("0.00")
            for service_id in additional_services:
                try:
                    service = AdditionalService.objects.filter(
                        id=service_id, is_active=True
                    ).first()
                    if service:
                        additional_services_cost += service.price
                        logger.info(
                            f"Added additional service price: {service.price} for {service.name}"
                        )
                except Exception as e:
                    logger.error(
                        f"Error processing additional service {service_id}: {str(e)}"
                    )

            total_price += additional_services_cost

            # Округляем до 2 знаков после запятой
            total_price = total_price.quantize(Decimal("0.01"))

            logger.info(f"Final calculated price: {total_price}")

            # Prepare pricing details
            cargo_price = total_price - delivery_price - additional_services_cost

            return Response(
                {
                    "total_price": total_price,
                    "currency": "RUB",
                    "details": {
                        "delivery": str(delivery_price),
                        "cargo": str(cargo_price),
                        "additional_services": str(additional_services_cost),
                    },
                }
            )
        except Exception as e:
            logger.error(f"Error calculating price: {str(e)}")
            return Response(
                {"error": f"Error calculating price: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=False, methods=["get"])
    def get_additional_services(self, request):
        """
        Получение списка дополнительных услуг, сгруппированных по категориям
        """
        # Получаем все активные дополнительные услуги
        services = AdditionalService.objects.filter(is_active=True)

        # Группируем услуги по типам
        service_groups = []

        # Получаем все возможные типы услуг из модели
        service_types = dict(AdditionalService.SERVICE_TYPES)

        # Для каждого типа услуг создаем группу
        for service_type, type_display in service_types.items():
            # Получаем услуги данного типа
            type_services = services.filter(service_type=service_type)

            # Если есть услуги данного типа, добавляем группу
            if type_services.exists():
                service_group = {"title": type_display, "services": []}

                # Добавляем каждую услугу в группу
                for service in type_services:
                    service_group["services"].append(
                        {
                            "id": service.id,
                            "name": service.name,
                            "price": f"{service.price} ₽",
                            "requires_location": service.requires_location,
                            "description": service.description,
                        }
                    )

                service_groups.append(service_group)

        # Добавляем услуги без типа в отдельную группу
        other_services = services.filter(service_type__isnull=True)
        if other_services.exists():
            other_group = {"title": "Другие услуги", "services": []}

            for service in other_services:
                other_group["services"].append(
                    {
                        "id": service.id,
                        "name": service.name,
                        "price": f"{service.price} ₽",
                        "requires_location": service.requires_location,
                        "description": service.description,
                    }
                )

            service_groups.append(other_group)

        return Response({"serviceGroups": service_groups})


class AdditionalServiceViewSet(viewsets.ModelViewSet):
    """
    ViewSet для управления дополнительными услугами
    """

    queryset = AdditionalService.objects.all()
    serializer_class = AdditionalServiceSerializer

    def get_queryset(self):
        """
        Опционально фильтрует услуги по типу или активности
        """
        queryset = AdditionalService.objects.all()

        # Фильтрация по типу услуги
        service_type = self.request.query_params.get("type", None)
        if service_type:
            queryset = queryset.filter(service_type=service_type)

        # Фильтрация по активности
        is_active = self.request.query_params.get("active", None)
        if is_active is not None:
            is_active = is_active.lower() == "true"
            queryset = queryset.filter(is_active=is_active)

        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)


@csrf_exempt
@require_http_methods(["POST"])
def create_order(request):
    """
    Создание заказа через Django ORM
    """
    try:
        # Получение данных заказа
        try:
            order_data = json.loads(request.body.decode("utf-8"))
            logging.info(f"Received order data: {order_data}")
        except json.JSONDecodeError:
            return JsonResponse(
                {
                    "success": False,
                    "message": "Invalid JSON",
                },
                status=400,
            )

        # Получаем данные из запроса
        delivery_data = order_data.get("delivery", {})
        cargo_data = order_data.get("cargo", {})
        client_data = order_data.get("client", {})
        pickup_address = order_data.get("pickup_address", "")
        additional_services = order_data.get("additional_services", [])

        # Получаем или создаем склад
        warehouse_id = delivery_data.get("warehouse_id") or delivery_data.get("warehouse")
        try:
            warehouse = Warehouse.objects.get(id=warehouse_id) if warehouse_id else None
        except Warehouse.DoesNotExist:
            return JsonResponse(
                {
                    "success": False,
                    "message": "Warehouse not found",
                },
                status=400,
            )

        # Создаем заказ через ORM
        order = Order(
            warehouse=warehouse,
            cargo_type=cargo_data.get("cargo_type", ""),
            container_type=cargo_data.get("container_type", ""),
            box_count=cargo_data.get("box_count", 0),
            pallet_count=cargo_data.get("pallet_count", 0),
            client_name=client_data.get("name", ""),
            phone_number=client_data.get("phone", ""),
            company=client_data.get("company", ""),
            email=client_data.get("email", ""),
            pickup_address=pickup_address,
            status="new"
        )

        # Сохраняем размеры и вес если они есть
        dimensions = cargo_data.get("dimensions", {})
        if dimensions:
            order.length = dimensions.get("length") or None
            order.width = dimensions.get("width") or None
            order.height = dimensions.get("height") or None
            order.weight = dimensions.get("weight") or None

        # Сохраняем дополнительную информацию
        order.additional_services = {
            "cargo": cargo_data,
            "client": client_data,
            "delivery": delivery_data
        }

        # Сначала сохраняем заказ, чтобы создать запись в базе
        order.save()

        # Добавляем дополнительные услуги
        if additional_services:
            services = AdditionalService.objects.filter(
                id__in=additional_services,
                is_active=True
            )
            order.services.add(*services)

        # Теперь, когда все услуги добавлены, рассчитываем полную стоимость
        order.total_price = order.calculate_price()
        order.save()  # Сохраняем обновленную цену

        # Формируем данные для уведомления в Telegram
        telegram_data = {
            "order_id": str(order.id),
            "sequence_number": order.sequence_number,
            "warehouse_name": str(order.warehouse) if order.warehouse else "Не указан",
            "cargo_type": order.cargo_type,
            "box_size": order.container_type,  # Для обратной совместимости
            "container_type": order.container_type,
            "box_count": order.box_count,
            "pallet_count": order.pallet_count,
            "company_name": order.company,
            "client_name": order.client_name,
            "client_email": order.email,
            "client_phone": order.phone_number,
            "telegram_user_id": client_data.get("telegram_user_id"),
            "cost": str(order.total_price),
            "pickup_address": order.pickup_address or "Не указан",
            "comments": client_data.get("comments", "Нет комментариев"),
            "additional_services": [
                {
                    "name": str(service),
                    "price": str(service.price)
                } for service in order.services.all()
            ]
        }

        # Отправляем уведомление в Telegram
        try:
            response = requests.post(
                f"{TELEGRAM_BOT_URL}/api/send_notification",
                json=telegram_data
            )
            logger.info(f"Telegram notification sent: {response.json()}")
        except Exception as e:
            logger.error(f"Error sending Telegram notification: {str(e)}")

        # Формируем ответ
        return JsonResponse(
            {
                "success": True,
                "message": "Order created successfully",
                "order": {
                    "id": str(order.id),
                    "sequence_number": order.sequence_number,
                    "status": order.status,
                    "total_price": str(order.total_price),
                    "created_at": order.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "warehouse_id": order.warehouse.id if order.warehouse else None,
                    "pickup_address": order.pickup_address,
                    "client": {
                        "name": order.client_name,
                        "phone": order.phone_number,
                        "company": order.company,
                        "email": order.email
                    },
                    "cargo": {
                        "type": order.cargo_type,
                        "container_type": order.container_type,
                        "box_count": order.box_count,
                        "pallet_count": order.pallet_count,
                        "dimensions": {
                            "length": str(order.length) if order.length else "",
                            "width": str(order.width) if order.width else "",
                            "height": str(order.height) if order.height else "",
                            "weight": str(order.weight) if order.weight else ""
                        }
                    },
                    "additional_services": [
                        {
                            "id": service.id,
                            "name": service.name,
                            "price": str(service.price)
                        }
                        for service in order.services.all()
                    ]
                }
            },
            status=201,
        )

    except Exception as e:
        logger.error(f"Error creating order: {str(e)}")
        logger.error(traceback.format_exc())
        return JsonResponse(
            {"success": False, "error": str(e)},
            status=500
        )


@api_view(["GET"])
def test_pricing(request):
    """
    Тестовый эндпоинт для проверки расчета стоимости
    """
    try:
        # Получаем склад
        warehouse = Warehouse.objects.get(
            id=6
        )  # Используем склад с ID 6 (Яндекс.Маркет Томилино)

        # Получаем тариф доставки
        delivery_pricing = Pricing.objects.filter(
            pricing_type="delivery", warehouse=warehouse
        ).first()

        delivery_cost = delivery_pricing.base_price if delivery_pricing else 0

        # Получаем тариф для коробок
        box_pricing = Pricing.objects.filter(pricing_type="box").first()

        box_cost = 0
        if box_pricing:
            box_count = 5  # Фиксированное количество коробок для теста
            box_cost = box_pricing.base_price + (box_pricing.unit_price * box_count)

        # Получаем тариф для дополнительных услуг
        additional_services = []
        additional_services_cost = 0
        for service_id in [1, 5]:  # Фиксированные ID дополнительных услуг для теста
            service = Pricing.objects.filter(id=service_id).first()
            if service:
                price_str = str(service.base_price)
                additional_services.append(
                    {"id": service_id, "name": service.name, "price": price_str}
                )
                additional_services_cost += service.base_price

        # Рассчитываем общую стоимость (все значения должны быть Decimal)
        total_price = delivery_cost + box_cost + additional_services_cost

        return Response(
            {
                "warehouse": {"id": warehouse.id, "name": warehouse.name},
                "delivery": {
                    "found": delivery_pricing is not None,
                    "name": delivery_pricing.name if delivery_pricing else None,
                    "price": str(delivery_cost),
                },
                "box": {
                    "found": box_pricing is not None,
                    "name": box_pricing.name if box_pricing else None,
                    "price": str(box_cost),
                    "count": 5,
                },
                "additional_services": additional_services,
                "additional_services_cost": str(additional_services_cost),
                "total_price": str(total_price),
            }
        )

    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DriverViewSet(viewsets.ModelViewSet):
    queryset = Driver.objects.filter(is_active=True)
    serializer_class = DriverSerializer


class TruckViewSet(viewsets.ModelViewSet):
    queryset = Truck.objects.filter(is_active=True)
    serializer_class = TruckSerializer


@api_view(['POST'])
def assign_driver(request, order_id):
    """
    Назначает водителя и грузовик для заказа
    """
    try:
        order = Order.objects.get(id=order_id)
        driver_id = request.data.get('driver_id')
        truck_id = request.data.get('truck_id')

        if not driver_id or not truck_id:
            return Response(
                {"error": "Необходимо указать водителя и транспорт"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            driver = Driver.objects.get(id=driver_id)
            truck = Truck.objects.get(id=truck_id)
        except (Driver.DoesNotExist, Truck.DoesNotExist):
            return Response(
                {"error": "Водитель или транспорт не найден"},
                status=status.HTTP_404_NOT_FOUND
            )

        order.driver = driver
        order.truck = truck
        order.status = 'accepted'  # Обновляем статус заказа
        order.save()

        return Response({
            "status": "success",
            "driver": {
                "id": driver.id,
                "full_name": driver.full_name,
                "phone": driver.phone
            },
            "truck": {
                "id": truck.id,
                "brand": truck.brand,
                "truck_model": truck.truck_model,
                "plate_number": truck.plate_number
            }
        })
    except Order.DoesNotExist:
        return Response(
            {"error": "Заказ не найден"},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error assigning driver to order: {e}")
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

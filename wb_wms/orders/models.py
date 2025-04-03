import uuid
from decimal import Decimal
import logging

from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)

STATUS = [
    ("Создан", "Создан"),
    ("Ожидает оплаты", "Ожидает оплаты"),
    ("Принят", "Принят"),
    ("На складе", "На складе"),
    ("В пути", "В пути"),
    ("Доставлен", "Доставлен"),
    ("Отменен", "Отменен"),
]


class Marketplace(models.Model):
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class City(models.Model):
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Warehouse(models.Model):
    name = models.CharField(max_length=255)
    marketplace = models.ForeignKey(Marketplace, on_delete=models.CASCADE)
    city = models.ForeignKey(City, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.marketplace.name} - {self.name}"


class PalletPricing(models.Model):
    """
    Модель для хранения цен на паллеты в зависимости от веса
    """
    WEIGHT_CATEGORIES = [
        ("0-200 кг", "0-200 кг"),
        ("200-300 кг", "200-300 кг"),
        ("300-400 кг", "300-400 кг"),
        ("400-500 кг", "400-500 кг"),
        ("Другой вес", "Другой вес"),
    ]
    
    weight_category = models.CharField(
        max_length=50, 
        choices=WEIGHT_CATEGORIES, 
        unique=True,
        verbose_name="Весовая категория"
    )
    price = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        verbose_name="Цена за паллету"
    )
    description = models.TextField(
        blank=True, 
        null=True, 
        verbose_name="Описание"
    )
    is_active = models.BooleanField(
        default=True, 
        verbose_name="Активен"
    )
    
    class Meta:
        verbose_name = "Цена паллеты"
        verbose_name_plural = "Цены паллет"
        ordering = ["weight_category"]
    
    def __str__(self):
        return f"{self.weight_category} - {self.price} руб."
        
    @classmethod
    def get_default_prices(cls):
        """
        Возвращает словарь с ценами для всех весовых категорий
        """
        defaults = {
            "0-200 кг": 2000.00,
            "200-300 кг": 3000.00,
            "300-400 кг": 4000.00, 
            "400-500 кг": 5000.00,
            "Другой вес": 6000.00,
        }
        
        # Получаем все активные настройки цен из базы данных
        db_prices = cls.objects.filter(is_active=True)
        
        # Если есть настройки в базе, используем их
        if db_prices.exists():
            for pricing in db_prices:
                defaults[pricing.weight_category] = float(pricing.price)
                
        return defaults


class Container(models.Model):
    CONTAINER_TYPES = [
        ("Коробка", "Коробка"),
        ("Паллета", "Паллета"),
    ]

    BOX_SIZES = [
        ("60x40x40 см", "60x40x40 см"),
        ("50x40x40 см", "50x40x40 см"),
        ("45x45x45 см", "45x45x45 см"),
        ("Другой размер", "Другой размер"),
    ]

    PALLET_WEIGHT = [
        ("0-200 кг", "0-200 кг"),
        ("200-300 кг", "200-300 кг"),
        ("300-400 кг", "300-400 кг"),
        ("400-500 кг", "400-500 кг"),
        ("Другой вес", "Другой вес"),
    ]

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    container_type = models.CharField(max_length=255, choices=CONTAINER_TYPES)
    box_size = models.CharField(
        max_length=255, choices=BOX_SIZES, null=True, blank=True
    )
    pallet_weight = models.CharField(
        max_length=255, choices=PALLET_WEIGHT, null=True, blank=True
    )
    quantity = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Pricing fields
    box_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=450.00, 
        verbose_name="Цена за коробку",
        help_text="Цена за одну коробку (по умолчанию 450 руб.)",
    )
    
    # Dictionary to store pallet prices based on weight categories
    pallet_prices = models.JSONField(
        default=dict, 
        verbose_name="Цены для паллет",
        help_text="Цены для паллет разных весовых категорий в формате JSON",
    )
    
    @staticmethod
    def get_default_pallet_prices():
        """Returns default pallet prices based on weight categories"""
        return PalletPricing.get_default_prices()
    
    def save(self, *args, **kwargs):
        # If pallet_prices is empty, set default values
        if not self.pallet_prices:
            self.pallet_prices = self.get_default_pallet_prices()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.container_type} - {self.box_size if self.container_type == 'Коробка' else self.pallet_weight}"
    
    def get_price(self, weight_category=None):
        """
        Returns the price for this container.
        For boxes, returns the box_price.
        For pallets, returns the price for the specified weight category.
        """
        if self.container_type == "Коробка":
            return self.box_price
        elif self.container_type == "Паллета":
            # Получаем актуальные цены на паллеты из базы данных
            pallet_prices = PalletPricing.get_default_prices()
            
            if weight_category and weight_category in pallet_prices:
                return Decimal(str(pallet_prices[weight_category]))
            elif self.pallet_weight in pallet_prices:
                return Decimal(str(pallet_prices[self.pallet_weight]))
            else:
                # Default to first weight category if none specified
                first_category = next(iter(pallet_prices.keys()), None)
                return Decimal(str(pallet_prices.get(first_category, 0)))
        return Decimal('0.00')


class User(AbstractUser):
    phone = models.CharField(max_length=255)
    telegram_id = models.CharField(max_length=255)
    company_name = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.username


class Driver(models.Model):
    full_name = models.CharField(max_length=255, verbose_name="ФИО")
    phone = models.CharField(max_length=20, verbose_name="Телефон", blank=True, default="")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Водитель"
        verbose_name_plural = "Водители"
        ordering = ["-created_at"]

    def __str__(self):
        return self.full_name


class Truck(models.Model):
    brand = models.CharField(max_length=100, verbose_name="Марка")
    truck_model = models.CharField(max_length=100, verbose_name="Модель", default="")
    plate_number = models.CharField(max_length=20, verbose_name="Гос. номер")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Грузовик"
        verbose_name_plural = "Грузовики"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.brand} {self.truck_model} - {self.plate_number}"


class Order(models.Model):
    STATUS_CHOICES = (
        ("new", "Новый"),
        ("processing", "В обработке"),
        ("completed", "Выполнен"),
        ("canceled", "Отменен"),
    )

    # Информация о заказе
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sequence_number = models.PositiveIntegerField(
        unique=True,
        editable=False,
        verbose_name="Порядковый номер",
        help_text="Автоматически присваиваемый порядковый номер заказа"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="new",
        verbose_name="Статус заказа",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    # Информация о доставке
    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.PROTECT, verbose_name="Склад доставки"
    )

    # Информация о грузе
    cargo_type = models.CharField(max_length=50, verbose_name="Тип груза")
    container_type = models.CharField(
        max_length=50, blank=True, null=True, verbose_name="Тип контейнера"
    )
    box_count = models.PositiveIntegerField(
        blank=True, null=True, verbose_name="Количество коробок"
    )
    pallet_count = models.PositiveIntegerField(
        blank=True, null=True, verbose_name="Количество паллет"
    )
    length = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True, verbose_name="Длина, см"
    )
    width = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="Ширина, см",
    )
    height = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="Высота, см",
    )
    weight = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True, verbose_name="Вес, кг"
    )

    # Контактная информация
    client_name = models.CharField(max_length=255, verbose_name="Имя клиента")
    phone_number = models.CharField(max_length=20, verbose_name="Телефон")
    company = models.CharField(
        max_length=255, blank=True, null=True, verbose_name="Компания"
    )
    email = models.EmailField(blank=True, null=True, verbose_name="Email")

    # Ценовая информация
    total_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, verbose_name="Общая стоимость"
    )

    # Дополнительные услуги
    additional_services = models.JSONField(
        default=list, blank=True, verbose_name="Дополнительные услуги"
    )
    services = models.ManyToManyField(
        "AdditionalService", blank=True, verbose_name="Дополнительные услуги"
    )
    pickup_address = models.TextField(
        blank=True, null=True, verbose_name="Адрес забора груза"
    )

    # Ссылка на пользователя Telegram (если заказ создан через бота)
    telegram_user_id = models.BigIntegerField(
        blank=True, null=True, verbose_name="ID пользователя Telegram"
    )

    # Добавляем поля для водителя и грузовика
    driver = models.ForeignKey(
        Driver,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Водитель"
    )
    truck = models.ForeignKey(
        Truck,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Грузовик"
    )
    driver_assigned_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата назначения водителя"
    )

    class Meta:
        verbose_name = "Заказ"
        verbose_name_plural = "Заказы"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Заказ №{self.sequence_number} - {self.client_name}"

    def calculate_price(self):
        """
        Рассчитывает стоимость заказа на основе тарифов
        """
        total_price = Decimal("0.00")

        # Расчет стоимости доставки
        if hasattr(self, "warehouse") and self.warehouse:
            delivery_pricing = Pricing.objects.filter(
                pricing_type="delivery", warehouse=self.warehouse
            ).first()

            if delivery_pricing:
                total_price += delivery_pricing.base_price
                logger.info(f"Added delivery price: {delivery_pricing.base_price}")

        # Получаем данные о грузе из additional_services
        cargo_data = self.additional_services.get("cargo", {})
        
        # Расчет стоимости груза в зависимости от типа (коробки или паллеты)
        if self.box_count > 0:
            # Получаем тип контейнера для коробок
            box_container_type = cargo_data.get("box_container_type", "")
            box_price = None
            
            if box_container_type == "Другой размер":
                # Для нестандартного размера рассчитываем объем
                try:
                    # Получаем размеры из поля dimensions
                    dimensions = cargo_data.get("dimensions", {})
                    length = float(dimensions.get("length", 0))
                    width = float(dimensions.get("width", 0))
                    height = float(dimensions.get("height", 0))
                    
                    # Проверяем, что все размеры больше 0
                    if length > 0 and width > 0 and height > 0:
                        # Определяем диапазон объема
                        volume_range = BoxPricing.calculate_volume(length, width, height)
                        
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
                    size_category=box_container_type,
                    is_active=True
                ).first()
                
                if box_pricing:
                    box_price = box_pricing.price
                    logger.info(f"Using box price from BoxPricing: {box_price} for size {box_container_type}")
                else:
                    # Если не нашли цену в БД, используем значения по умолчанию
                    default_prices = BoxPricing.get_default_prices()
                    box_price = Decimal(str(default_prices.get(box_container_type, "450.00")))
                    logger.info(f"Using default box price: {box_price} for size {box_container_type}")
            
            box_total = box_price * Decimal(self.box_count)
            total_price += box_total
            logger.info(f"Added box price: {box_total} for {self.box_count} boxes at {box_price} each")

        if self.pallet_count > 0:
            # Получаем тип контейнера для паллет
            pallet_container_type = cargo_data.get("pallet_container_type", "")
            pallet_price = None
            
            if pallet_container_type == "Другой вес":
                try:
                    # Получаем вес из dimensions
                    dimensions = cargo_data.get("dimensions", {})
                    weight = float(dimensions.get("weight", 0))
                    
                    if weight > 0:
                        if weight <= 500:
                            # Если вес до 500 кг, используем стандартную цену
                            pallet_price = Decimal("5000.00")
                            logger.info(f"Using standard pallet price: {pallet_price} for weight {weight}kg")
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
                except Exception as e:
                    # В случае ошибки используем минимальную цену
                    pallet_price = Decimal("2000.00")
                    logger.error(f"Error calculating custom pallet price: {e}")
            else:
                # Для стандартных весовых категорий ищем цену в БД
                pallet_pricing = PalletPricing.objects.filter(
                    weight_category=pallet_container_type,
                    is_active=True
                ).first()
                
                if pallet_pricing:
                    pallet_price = pallet_pricing.price
                    logger.info(f"Using pallet price from PalletPricing: {pallet_price} for category {pallet_container_type}")
                else:
                    # Если не нашли, используем стандартные цены
                    default_prices = PalletPricing.get_default_prices()
                    pallet_price = Decimal(str(default_prices.get(pallet_container_type, "2000.00")))
                    logger.info(f"Using default pallet price: {pallet_price} for category {pallet_container_type}")
            
            pallet_total = pallet_price * Decimal(self.pallet_count)
            total_price += pallet_total
            logger.info(f"Added pallet price: {pallet_total} for {self.pallet_count} pallets at {pallet_price} each")

        # Расчет стоимости дополнительных услуг
        services_total = Decimal("0.00")
        for service in self.services.filter(is_active=True):
            services_total += service.price
            logger.info(f"Added service price: {service.price} for {service.name}")
        total_price += services_total
        logger.info(f"Total additional services cost: {services_total}")

        logger.info(f"Final calculated price: {total_price}")
        return total_price

    def save(self, *args, **kwargs):
        if not self.sequence_number:
            # Получаем максимальный номер из базы
            last_number = Order.objects.all().aggregate(models.Max('sequence_number'))['sequence_number__max']
            # Присваиваем следующий номер
            self.sequence_number = (last_number or 0) + 1
        
        # Пропускаем расчет цены при первом сохранении
        if not self.id:
            super().save(*args, **kwargs)
            return

        # Рассчитываем стоимость только при последующих сохранениях
        try:
            self.total_price = self.calculate_price()
        except Exception as e:
            import traceback
            print(f"Error calculating price: {e}")
            print(traceback.format_exc())
            self.total_price = 0

        try:
            super().save(*args, **kwargs)
        except Exception as e:
            import traceback
            print(f"Error saving order: {e}")
            print(traceback.format_exc())
            raise


class Pricing(models.Model):
    PRICING_TYPES = (
        ("box", "Коробка"),
        ("pallet", "Паллета"),
        ("delivery", "Доставка"),
        ("pickup", "Забор груза"),
        ("palletizing", "Паллетирование"),
        ("loader", "Услуги грузчика"),
        ("other", "Другое"),
    )

    name = models.CharField(max_length=255, verbose_name="Название")
    pricing_type = models.CharField(
        max_length=50, choices=PRICING_TYPES, verbose_name="Тип тарифа"
    )
    specification = models.CharField(
        max_length=100, blank=True, null=True, verbose_name="Спецификация"
    )
    base_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, verbose_name="Базовая цена"
    )
    unit_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, verbose_name="Цена за единицу"
    )
    description = models.TextField(blank=True, null=True, verbose_name="Описание")
    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.CASCADE, blank=True, null=True, verbose_name="Склад"
    )
    is_active = models.BooleanField(default=True, verbose_name="Активен")

    class Meta:
        verbose_name = "Тариф"
        verbose_name_plural = "Тарифы"

    def __str__(self):
        if self.warehouse:
            return f"{self.name} ({self.get_pricing_type_display()}) - {self.warehouse.name}"
        return f"{self.name} ({self.get_pricing_type_display()})"


class AdditionalService(models.Model):
    """
    Модель для хранения дополнительных услуг
    """

    SERVICE_TYPES = (
        ("pickup", "Забор груза"),
        ("palletizing", "Паллетирование"),
        ("loader", "Услуги грузчика"),
        ("other", "Другое"),
    )

    name = models.CharField(max_length=255, verbose_name="Название услуги")
    price = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, verbose_name="Стоимость"
    )
    service_type = models.CharField(
        max_length=50,
        choices=SERVICE_TYPES,
        blank=True,
        null=True,
        verbose_name="Тип услуги",
    )
    requires_location = models.BooleanField(default=False, verbose_name="Требует адрес")
    description = models.TextField(blank=True, null=True, verbose_name="Описание")
    is_active = models.BooleanField(default=True, verbose_name="Активна")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Дополнительная услуга"
        verbose_name_plural = "Дополнительные услуги"
        ordering = ["service_type", "name"]

    def __str__(self):
        return f'{self.name} ({self.get_service_type_display() if self.service_type else "Без типа"})'


class BoxPricing(models.Model):
    """
    Модель для хранения цен на коробки в зависимости от размера
    """
    BOX_SIZES = [
        ("60x40x40 см", "60x40x40 см"),
        ("50x40x40 см", "50x40x40 см"),
        ("45x45x45 см", "45x45x45 см"),
        ("Другой размер", "Другой размер"),
    ]
    
    VOLUME_RANGES = [
        ("V ≤ 0.1", "До 0.1 м³"),
        ("0.1 < V ≤ 0.2", "От 0.1 до 0.2 м³"),
        ("V > 0.2", "Более 0.2 м³"),
    ]
    
    size_category = models.CharField(
        max_length=50, 
        choices=BOX_SIZES,
        default="60x40x40 см",
        verbose_name="Размер коробки"
    )
    volume_range = models.CharField(
        max_length=50,
        choices=VOLUME_RANGES,
        null=True,
        blank=True,
        verbose_name="Диапазон объема"
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Цена за коробку"
    )
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name="Описание"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен"
    )
    
    class Meta:
        verbose_name = "Цена коробки"
        verbose_name_plural = "Цены коробок"
        unique_together = [['size_category', 'volume_range']]
        ordering = ["size_category", "volume_range"]
    
    def __str__(self):
        if self.size_category == "Другой размер":
            return f"{self.get_volume_range_display()} - {self.price} руб."
        return f"{self.size_category} - {self.price} руб."
        
    @classmethod
    def get_default_prices(cls):
        """
        Возвращает словарь с ценами для всех размеров коробок
        и диапазонов объемов для нестандартных размеров
        """
        defaults = {
            # Стандартные размеры
            "60x40x40 см": 450.00,
            "50x40x40 см": 450.00,
            "45x45x45 см": 450.00,
            # Нестандартные размеры (по объему)
            "V ≤ 0.1": 450.00,
            "0.1 < V ≤ 0.2": 600.00,
            "V > 0.2": 700.00,
        }
        
        # Получаем все активные настройки цен из базы данных
        db_prices = cls.objects.filter(is_active=True)
        
        # Если есть настройки в базе, используем их
        if db_prices.exists():
            for pricing in db_prices:
                if pricing.size_category == "Другой размер":
                    if pricing.volume_range:
                        defaults[pricing.volume_range] = float(pricing.price)
                else:
                    defaults[pricing.size_category] = float(pricing.price)
                
        return defaults
    
    @staticmethod
    def calculate_volume(length, width, height):
        """
        Рассчитывает объем коробки в кубических метрах
        и возвращает соответствующий диапазон объема
        """
        # Переводим сантиметры в метры и вычисляем объем
        volume = (length * width * height) / 1_000_000
        
        if volume <= 0.1:
            return "V ≤ 0.1"
        elif volume <= 0.2:
            return "0.1 < V ≤ 0.2"
        else:
            return "V > 0.2"

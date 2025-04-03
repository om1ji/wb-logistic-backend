from django.core.management.base import BaseCommand
from orders.models import BoxPricing


class Command(BaseCommand):
    help = 'Инициализирует таблицу цен на коробки начальными значениями'

    def handle(self, *args, **options):
        # Список стандартных размеров и цен
        standard_sizes = [
            {"size_category": "60x40x40 см", "price": 450.00},
            {"size_category": "50x40x40 см", "price": 450.00},
            {"size_category": "45x45x45 см", "price": 450.00},
        ]
        
        # Список цен для нестандартных размеров (по объему)
        volume_prices = [
            {"size_category": "Другой размер", "volume_range": "V ≤ 0.1", "price": 450.00},
            {"size_category": "Другой размер", "volume_range": "0.1 < V ≤ 0.2", "price": 600.00},
            {"size_category": "Другой размер", "volume_range": "V > 0.2", "price": 700.00},
        ]

        # Счетчики для отчета
        created_count = 0
        updated_count = 0
        
        # Создаем записи для стандартных размеров
        for price_data in standard_sizes:
            size_category = price_data["size_category"]
            price = price_data["price"]
            
            pricing, created = BoxPricing.objects.get_or_create(
                size_category=size_category,
                defaults={
                    "price": price,
                    "description": f"Стандартная цена для коробки {size_category}",
                    "is_active": True
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(
                    f'Создана запись о цене для коробки {size_category}: {price} руб.'
                ))
            else:
                if options.get('force_update'):
                    pricing.price = price
                    pricing.save()
                    updated_count += 1
                    self.stdout.write(self.style.WARNING(
                        f'Обновлена запись о цене для коробки {size_category}: {price} руб.'
                    ))
        
        # Создаем записи для нестандартных размеров (по объему)
        for price_data in volume_prices:
            size_category = price_data["size_category"]
            volume_range = price_data["volume_range"]
            price = price_data["price"]
            
            pricing, created = BoxPricing.objects.get_or_create(
                size_category=size_category,
                volume_range=volume_range,
                defaults={
                    "price": price,
                    "description": f"Цена для коробки нестандартного размера ({volume_range})",
                    "is_active": True
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(
                    f'Создана запись о цене для коробки {size_category} ({volume_range}): {price} руб.'
                ))
            else:
                if options.get('force_update'):
                    pricing.price = price
                    pricing.save()
                    updated_count += 1
                    self.stdout.write(self.style.WARNING(
                        f'Обновлена запись о цене для коробки {size_category} ({volume_range}): {price} руб.'
                    ))
        
        # Итоговый отчет
        if created_count > 0:
            self.stdout.write(self.style.SUCCESS(f'Успешно создано {created_count} записей о ценах коробок'))
        if updated_count > 0:
            self.stdout.write(self.style.SUCCESS(f'Успешно обновлено {updated_count} записей о ценах коробок'))
        
        if created_count == 0 and updated_count == 0:
            self.stdout.write(self.style.NOTICE('Все цены коробок уже существуют в БД'))
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--force-update',
            action='store_true',
            dest='force_update',
            help='Обновлять существующие записи',
        ) 
from django.core.management.base import BaseCommand
from orders.models import PalletPricing


class Command(BaseCommand):
    help = 'Инициализирует таблицу цен на паллеты начальными значениями'

    def handle(self, *args, **options):
        # Список весовых категорий и цен
        default_prices = [
            {"weight_category": "0-200 кг", "price": 2000.00},
            {"weight_category": "200-300 кг", "price": 3000.00},
            {"weight_category": "300-400 кг", "price": 4000.00},
            {"weight_category": "400-500 кг", "price": 5000.00},
            {"weight_category": "Другой вес", "price": 6000.00},
        ]

        # Счетчики для отчета
        created_count = 0
        updated_count = 0
        
        for price_data in default_prices:
            weight_category = price_data["weight_category"]
            price = price_data["price"]
            
            # Проверяем, существует ли уже такая запись
            pricing, created = PalletPricing.objects.get_or_create(
                weight_category=weight_category,
                defaults={
                    "price": price,
                    "description": f"Стандартная цена для паллеты {weight_category}",
                    "is_active": True
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(
                    f'Создана запись о цене для паллеты {weight_category}: {price} руб.'
                ))
            else:
                # Если запись уже существует, обновляем только если указан флаг force_update
                if options.get('force_update'):
                    pricing.price = price
                    pricing.save()
                    updated_count += 1
                    self.stdout.write(self.style.WARNING(
                        f'Обновлена запись о цене для паллеты {weight_category}: {price} руб.'
                    ))
        
        # Итоговый отчет
        if created_count > 0:
            self.stdout.write(self.style.SUCCESS(f'Успешно создано {created_count} записей о ценах паллет'))
        if updated_count > 0:
            self.stdout.write(self.style.SUCCESS(f'Успешно обновлено {updated_count} записей о ценах паллет'))
        
        if created_count == 0 and updated_count == 0:
            self.stdout.write(self.style.NOTICE('Все цены паллет уже существуют в БД'))
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--force-update',
            action='store_true',
            dest='force_update',
            help='Обновлять существующие записи',
        ) 
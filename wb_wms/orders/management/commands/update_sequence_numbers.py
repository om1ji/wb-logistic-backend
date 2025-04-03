from django.core.management.base import BaseCommand
from orders.models import Order
from django.db import models

class Command(BaseCommand):
    help = 'Updates sequence numbers for existing orders'

    def handle(self, *args, **options):
        # Получаем все заказы без порядкового номера, сортируем по дате создания
        orders = Order.objects.filter(sequence_number__isnull=True).order_by('created_at')
        
        if not orders:
            self.stdout.write(self.style.SUCCESS('No orders need updating'))
            return
            
        # Получаем максимальный существующий номер
        last_number = Order.objects.exclude(sequence_number__isnull=True).aggregate(
            models.Max('sequence_number'))['sequence_number__max'] or 0
            
        count = 0
        for order in orders:
            last_number += 1
            order.sequence_number = last_number
            order.save(update_fields=['sequence_number'])
            count += 1
            
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully updated sequence numbers for {count} orders'
            )
        ) 
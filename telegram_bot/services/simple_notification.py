import logging
import requests
import json
from typing import Dict, Union, Optional

logger = logging.getLogger(__name__)

# Глобальные настройки
TELEGRAM_API_URL = "https://api.telegram.org/bot"
BOT_TOKEN = None
ADMIN_GROUP_ID = None

def init_notification_service(token: str, group_id: str):
    """
    Инициализирует сервис уведомлений с токеном бота и ID группы администраторов
    """
    global BOT_TOKEN, ADMIN_GROUP_ID
    BOT_TOKEN = token
    ADMIN_GROUP_ID = group_id

def build_message_for_admin(order_data: Dict) -> str:
    """
    Создает текстовое сообщение для администраторов на основе данных заказа
    """
    try:
        message_parts = []
        
        message_parts.append(f"📦 Новый заказ #{order_data.get('sequence_number', 'N/A')}")
        
        if warehouse := order_data.get('warehouse_name'):
            message_parts.append(f"\n🏭 Склад: {warehouse}")

        # Добавляем информацию о грузе
        cargo_info = []
        
        # Получаем информацию о грузе из новой структуры
        cargo_data = order_data.get('cargo_info', {})
        
        # Обрабатываем коробки
        boxes = cargo_data.get('boxes', {})
        box_count = boxes.get('count')
        if box_count and int(box_count) > 0:
            cargo_info.append(f"📦 Коробки:")
            cargo_info.append(f"• Количество: {box_count}")
            
            # Если выбран стандартный размер
            box_type = boxes.get('container_type')
            if box_type and box_type != "Другой размер":
                cargo_info.append(f"• Размер: {box_type}")
            # Если выбран кастомный размер, показываем размеры
            else:
                dimensions = boxes.get('dimensions', {})
                length = dimensions.get('length')
                width = dimensions.get('width')
                height = dimensions.get('height')
                if length and width and height:
                    cargo_info.append(f"• Размеры (Д×Ш×В): {length}×{width}×{height} см")
                
        # Обрабатываем паллеты
        pallets = cargo_data.get('pallets', {})
        pallet_count = pallets.get('count')
        if pallet_count and int(pallet_count) > 0:
            cargo_info.append(f"🔧 Паллеты:")
            cargo_info.append(f"• Количество: {pallet_count}")
            
            # Если выбрана стандартная категория веса
            pallet_type = pallets.get('container_type')
            if pallet_type and pallet_type != "Другой вес":
                cargo_info.append(f"• Категория веса: {pallet_type}")
            # Если выбран кастомный вес, показываем его
            else:
                if weight := pallets.get('weight'):
                    cargo_info.append(f"• Вес: {weight} кг")
        
        # Если есть информация о грузе, добавляем её в сообщение
        if cargo_info:
            message_parts.append("\n" + "\n".join(cargo_info))

        if services := order_data.get('additional_services', []):
            services_info = []
            for service in services:
                if name := service.get('name'):
                    price = service.get('price', 0)
                    services_info.append(f"• {name}: {price} ₽")
            if services_info:
                message_parts.append("\n🛠 Дополнительные услуги:\n" + "\n".join(services_info))

        company_info = []
        if company := order_data.get('company_name'):
            company_info.append(f"🏢 Компания: {company}")
        if contact := order_data.get('client_name'):
            company_info.append(f"👤 Контактное лицо: {contact}")
        if phone := order_data.get('client_phone'):
            company_info.append(f"📱 Телефон: {phone}")

        if company_info:
            message_parts.append("\n" + "\n".join(company_info))

        pickup_address = order_data.get('pickup_address')
        if pickup_address != "" and pickup_address != "Не указан":
            message_parts.append(f"\n📍 Адрес забора груза:\n{pickup_address}")

        if total_cost := order_data.get('cost'):
            message_parts.append(f"\n💰 Стоимость: {total_cost} ₽")
            
        return "\n".join(message_parts)
        
    except Exception as e:
        logger.error(f"Error building admin message: {str(e)}")
        return "Ошибка при формировании сообщения для заказа"

def build_user_message(notification_data: Dict) -> str:
    """
    Создает текстовое сообщение для пользователя
    """
    try:
        notification_type = notification_data.get("notification_type")
        sequence_number = notification_data.get("sequence_number", "")
        
        # Базовая информация о заказе, которая добавляется к любому уведомлению
        order_details = []
        
        # Добавляем информацию о грузе
        cargo_type = notification_data.get("cargo_type", "")
        box_count = notification_data.get("box_count")
        pallet_count = notification_data.get("pallet_count")
        
        if cargo_type:
            order_details.append(f"🚚 Тип груза: {cargo_type}")
        
        if box_count and int(box_count) > 0:
            order_details.append(f"📦 Количество коробок: {box_count}")
            
        if pallet_count and int(pallet_count) > 0:
            order_details.append(f"🔧 Количество паллет: {pallet_count}")
            
        # Добавляем дополнительные услуги
        if services := notification_data.get("additional_services", []):
            services_text = []
            for service in services:
                if isinstance(service, dict) and (name := service.get("name")):
                    price = service.get("price", "")
                    services_text.append(f"• {name}" + (f": {price} ₽" if price else ""))
                elif isinstance(service, str):
                    services_text.append(f"• {service}")
                    
            if services_text:
                order_details.append("\n🛠 Дополнительные услуги:\n" + "\n".join(services_text))
        
        # Формируем сообщение в зависимости от типа уведомления
        if notification_type == "order_accepted":
            # Формируем сообщение для клиента о принятии заказа
            driver_name = notification_data.get("driver_name", "Не указан")
            driver_phone = notification_data.get("driver_phone", "")
            truck_info = notification_data.get("truck_info", "")
            
            message_text = f"✅ Ваш заказ #{sequence_number} принят!\n\n"
            
            # Добавляем информацию о водителе и грузовике
            driver_info = []
            driver_info.append(f"🚚 Грузовик: {truck_info}")
            driver_info.append(f"👨‍✈️ Водитель: {driver_name}")
            
            if driver_phone:
                driver_info.append(f"📱 Телефон: {driver_phone}")
                
            message_text += "\n".join(driver_info)
            
            # Добавляем информацию о заказе
            if order_details:
                message_text += "\n\n📋 Информация о заказе:\n" + "\n".join(order_details)
                
            return message_text
            
        elif notification_type == "order_rejected":
            # Формируем сообщение для клиента об отклонении заказа
            message_text = f"❌ Ваш заказ #{sequence_number} был отклонен.\n\n"
            
            # Добавляем причину отклонения, если она указана
            if reason := notification_data.get("reject_reason"):
                message_text += f"Причина: {reason}\n\n"
                
            # Добавляем информацию о заказе
            if order_details:
                message_text += "📋 Информация о заказе:\n" + "\n".join(order_details)
                
            message_text += "\n\nПожалуйста, свяжитесь с нами для уточнения деталей."
            return message_text
            
        else:
            logger.warning(f"Unknown notification type: {notification_type}")
            return "Уведомление о статусе заказа"
    except Exception as e:
        logger.error(f"Error building user message: {str(e)}")
        return "Уведомление о статусе заказа"

def build_inline_keyboard(order_id: str) -> Dict:
    """
    Создает встроенную клавиатуру для сообщений администраторов
    """
    return {
        "inline_keyboard": [
            [
                {
                    "text": "✅ Принять",
                    "callback_data": f"order_accept_{order_id}"
                },
                {
                    "text": "❌ Отклонить",
                    "callback_data": f"order_reject_{order_id}"
                }
            ]
        ]
    }

def send_telegram_message(chat_id: Union[str, int], text: str, reply_markup: Optional[Dict] = None) -> bool:
    """
    Отправляет сообщение в Telegram с помощью прямого HTTP запроса
    """
    if not BOT_TOKEN:
        logger.error("Bot token not initialized")
        return False
        
    url = f"{TELEGRAM_API_URL}{BOT_TOKEN}/sendMessage"
    
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        
        if response.status_code == 200:
            return True
        else:
            logger.error(f"Failed to send message to {chat_id}: {response.status_code} {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error sending message to {chat_id}: {str(e)}")
        return False

def send_admin_notification(order_data: Dict) -> bool:
    """
    Отправляет уведомление о новом заказе в группу администраторов
    """
    if not ADMIN_GROUP_ID:
        logger.error("Admin group ID not initialized")
        return False
        
    
    # Создаем текст сообщения
    message_text = build_message_for_admin(order_data)
    
    # Создаем клавиатуру
    keyboard = build_inline_keyboard(order_data.get('order_id', ''))
    
    # Отправляем сообщение
    return send_telegram_message(ADMIN_GROUP_ID, message_text, keyboard)

def send_user_notification(notification_data: Dict) -> bool:
    """
    Отправляет уведомление пользователю о статусе заказа
    """
    user_id = notification_data.get("telegram_user_id")
    if not user_id:
        logger.error("No telegram_user_id provided for user notification")
        return False
        
    
    # Создаем текст сообщения
    message_text = build_user_message(notification_data)
    
    # Отправляем сообщение без клавиатуры
    return send_telegram_message(user_id, message_text)

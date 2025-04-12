import logging
import requests
from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
import os 
from dotenv import load_dotenv
from services.simple_notification import send_user_notification

load_dotenv()

router = Router()
logger = logging.getLogger(__name__)

WB_BACKEND_URL = os.getenv("WB_BACKEND_URL")

bot = None

async def get_drivers():
    try:
        logger.info(f"Getting drivers from {WB_BACKEND_URL}/orders/transport/drivers/")
        response = requests.get(f"{WB_BACKEND_URL}/orders/transport/drivers/")
        if response.status_code == 200:
            return response.json()
        logger.warning(f"Failed to get drivers: {response.status_code} - {response.text}")
        return []
    except Exception as e:
        logger.error(f"Error getting drivers: {e}")
        return []

# Функция для получения списка грузовиков
async def get_trucks():
    try:
        logger.info(f"Getting trucks from {WB_BACKEND_URL}/orders/transport/trucks/")
        response = requests.get(f"{WB_BACKEND_URL}/orders/transport/trucks/")
        if response.status_code == 200:
            return response.json()
        logger.warning(f"Failed to get trucks: {response.status_code} - {response.text}")
        return []
    except Exception as e:
        logger.error(f"Error getting trucks: {e}")
        return []

# Обработчик нажатия кнопки "Отклонить"
@router.callback_query(F.data.startswith("order_reject_"))
async def reject_order(callback: CallbackQuery):
    try:
        # Получаем ID заказа
        order_id = callback.data.split("_")[2]
        
        # Обновляем статус заказа в базе данных
        response = requests.post(
            f"{WB_BACKEND_URL}/orders/{order_id}/reject/",
            json={"status": "rejected"}
        )
        
        if response.status_code in [200, 201, 202, 204]:
            logger.info(f"Order {order_id} rejected successfully")
            
            # Обновляем сообщение, убираем кнопки
            await callback.message.edit_text(
                text=callback.message.text + "\n\n❌ Заказ отклонен",
                reply_markup=None
            )
            
            # Отправляем сообщение в чат
            await callback.answer("Заказ успешно отклонен")
            
            # Получаем информацию о заказе
            try:
                # Получаем данные о заказе напрямую из API
                order_response = requests.get(f"{WB_BACKEND_URL}/orders/{order_id}/")
                
                if order_response.status_code == 200:
                    order_data = order_response.json()
                    telegram_user_id = order_data.get('telegram_user_id')
                    
                    # Диагностическое логирование
                    logger.info(f"Reject order data received: {order_data.keys()}")
                    if 'services' in order_data:
                        services = order_data.get('services', [])
                        logger.info(f"Reject services data type: {type(services)}, content: {services}")
                    
                    # Отправляем уведомление пользователю
                    if telegram_user_id:
                        try:
                            # Формируем информацию о заказе для уведомления
                            notification_data = {
                                "notification_type": "order_rejected",
                                "telegram_user_id": telegram_user_id,
                                "sequence_number": order_data.get('sequence_number', order_id),
                                "cargo_type": order_data.get('cargo_type', ''),
                                "box_count": order_data.get('box_count', 0),
                                "pallet_count": order_data.get('pallet_count', 0),
                            }
                            
                            # Обработка дополнительных услуг с помощью общей функции
                            if 'services' in order_data:
                                services_data = order_data.get('services', [])
                                services_list = await process_services_data(services_data)
                                notification_data["additional_services"] = services_list
                            
                            logger.info(f"Sending rejection notification with data: {notification_data}")
                            
                            # Отправляем уведомление
                            success = send_user_notification(notification_data)
                            if success:
                                logger.info(f"Rejection notification sent to user {telegram_user_id}")
                            else:
                                logger.error(f"Failed to send rejection notification to user {telegram_user_id}")
                        except Exception as e:
                            logger.error(f"Error preparing rejection notification: {str(e)}", exc_info=True)
                else:
                    logger.error(f"Failed to get order data: {order_response.status_code} - {order_response.text}")
            except Exception as e:
                logger.error(f"Error processing rejection notification: {str(e)}")
        else:
            logger.error(f"Error rejecting order: {response.status_code} - {response.text}")
            await callback.answer("Ошибка при отклонении заказа")
    except Exception as e:
        logger.error(f"Error in reject_order: {str(e)}")
        await callback.answer("Произошла ошибка")

# Обработчик нажатия кнопки "Принять"
@router.callback_query(F.data.startswith("order_accept_"))
async def accept_order(callback: CallbackQuery):
    try:
        order_id = callback.data.split("_")[2]  # Получаем ID заказа
        
        # Получаем telegram_user_id из сообщения
        message_lines = callback.message.text.split('\n')
        order_id_line = message_lines[0]
        
        # Получаем список водителей
        drivers = await get_drivers()
        if not drivers:
            await callback.answer("Нет доступных водителей")
            return

        # Создаем клавиатуру с водителями
        keyboard = []
        for driver in drivers:
            if driver.get("is_active", True):  # Только активные водители
                keyboard.append([
                    InlineKeyboardButton(
                        text=driver["full_name"],
                        callback_data=f"driver_{driver['id']}_{order_id}"  # ID водителя и заказа
                    )
                ])

        # Добавляем кнопку отмены
        keyboard.append([
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data=f"cancel_{order_id}"
            )
        ])

        # Обновляем сообщение с новой клавиатурой
        await callback.message.edit_reply_markup(
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        await callback.answer("Выберите водителя")
    except Exception as e:
        logger.error(f"Error in accept_order: {e}")
        await callback.answer("Произошла ошибка")

# Обработчик выбора водителя
@router.callback_query(F.data.startswith("driver_"))
async def select_driver(callback: CallbackQuery):
    try:
        # Получаем ID водителя и заказа
        parts = callback.data.split("_")
        driver_id = parts[1]
        order_id = parts[2]

        # Получаем список грузовиков
        trucks = await get_trucks()
        if not trucks:
            await callback.answer("Нет доступных грузовиков")
            return

        # Создаем клавиатуру с грузовиками
        keyboard = []
        for truck in trucks:
            if truck.get("is_active", True):  # Только активные грузовики
                keyboard.append([
                    InlineKeyboardButton(
                        text=f"{truck['brand']} {truck['truck_model']} - {truck['plate_number']}",
                        callback_data=f"truck_{truck['id']}_{driver_id}_{order_id}"  # ID грузовика, водителя и заказа
                    )
                ])

        # Добавляем кнопку отмены
        keyboard.append([
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data=f"cancel_{order_id}"
            )
        ])

        # Обновляем сообщение с новой клавиатурой
        await callback.message.edit_reply_markup(
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        await callback.answer("Выберите транспорт")
    except Exception as e:
        logger.error(f"Error in select_driver: {e}")
        await callback.answer("Произошла ошибка")

# Обработчик выбора грузовика
@router.callback_query(F.data.startswith("truck_"))
async def select_truck(callback: CallbackQuery):
    try:
        # Получаем ID грузовика, водителя и заказа
        parts = callback.data.split("_")
        truck_id = parts[1]
        driver_id = parts[2]
        order_id = parts[3]

        # Создаем клавиатуру подтверждения
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Подтвердить",
                        callback_data=f"confirm_{driver_id}_{truck_id}_{order_id}"  # ID водителя, грузовика и заказа
                    ),
                    InlineKeyboardButton(
                        text="❌ Отмена",
                        callback_data=f"cancel_{order_id}"
                    )
                ]
            ]
        )

        # Получаем информацию о водителе и грузовике для отображения
        driver = next((d for d in await get_drivers() if str(d["id"]) == driver_id), None)
        truck = next((t for t in await get_trucks() if str(t["id"]) == truck_id), None)

        confirmation_text = ""
        
        if driver:
            confirmation_text += f"\n👨‍✈️ Водитель: {driver['full_name']}"
        if truck:
            confirmation_text += f"\n🚛 Транспорт: {truck['brand']} {truck['truck_model']} - {truck['plate_number']}"

        # Обновляем сообщение
        await callback.message.edit_text(
            text=callback.message.text + "\n\n" + confirmation_text,
            reply_markup=keyboard
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in select_truck: {e}")
        await callback.answer("Произошла ошибка")

# Обработчик подтверждения выбора
@router.callback_query(F.data.startswith("confirm_"))
async def confirm_selection(callback: CallbackQuery):
    try:
        # Получаем ID водителя, грузовика и заказа
        parts = callback.data.split("_")
        driver_id = parts[1]
        truck_id = parts[2]
        order_id = parts[3]

        # Отправляем запрос на бэкенд для назначения водителя и грузовика
        response = requests.post(
            f"{WB_BACKEND_URL}/orders/{order_id}/assign_driver/",
            json={
                "driver_id": driver_id,
                "truck_id": truck_id
            }
        )

        if response.status_code == 200:
            result = response.json()
            logger.info(f"Driver and truck assigned successfully: {result}")
            
            # Получаем информацию о водителе и грузовике для отображения
            driver = next((d for d in await get_drivers() if str(d["id"]) == driver_id), None)
            truck = next((t for t in await get_trucks() if str(t["id"]) == truck_id), None)
            
            # Обновляем сообщение
            await callback.message.edit_text(
                text=callback.message.text + "\n\n" + f"✅ Заказ успешно принят\n\n",
                reply_markup=None
            )
            
            # Пытаемся получить информацию о заказе для уведомления
            try:
                order_response = requests.get(f"{WB_BACKEND_URL}/orders/{order_id}/")
                order_data = {}
                
                if order_response.status_code == 200:
                    order_data = order_response.json()
                    telegram_user_id = order_data.get('telegram_user_id')
                else:
                    # Если не получилось получить заказ, пытаемся извлечь telegram_user_id из сообщения
                    message_text = callback.message.text
                    lines = message_text.split('\n')
                    telegram_user_id = None
                    
                    # Пытаемся найти информацию о telegram_user_id в сообщении
                    for line in lines:
                        if 'telegram user id:' in line.lower():
                            try:
                                telegram_user_id = line.split(':')[1].strip()
                                break
                            except:
                                pass
                
                # Диагностическое логирование в confirm_selection
                logger.info(f"Confirm order data received: {order_data.keys()}")
                if 'services' in order_data:
                    services = order_data.get('services', [])
                    logger.info(f"Confirm services data type: {type(services)}, content: {services}")
                
                # Если нашли telegram_user_id, отправляем уведомление пользователю
                if telegram_user_id:
                    try:
                        # Формируем данные для отправки уведомления
                        notification_data = {
                            "notification_type": "order_accepted",
                            "telegram_user_id": telegram_user_id,
                            "driver_name": driver.get('full_name', 'Не указан') if driver else 'Не указан',
                            "driver_phone": driver.get('phone', '') if driver else '',
                            "truck_info": f"{truck.get('brand', '')} {truck.get('plate_number', '')}" if truck else 'Не указан',
                            "sequence_number": order_data.get('sequence_number', order_id)
                        }
                        
                        # Добавляем информацию о заказе
                        if 'cargo_type' in order_data:
                            notification_data["cargo_type"] = order_data.get('cargo_type', '')
                        
                        if 'box_count' in order_data:
                            notification_data["box_count"] = order_data.get('box_count', 0)
                        
                        if 'pallet_count' in order_data:
                            notification_data["pallet_count"] = order_data.get('pallet_count', 0)
                        
                        # Обработка дополнительных услуг с помощью общей функции
                        if 'services' in order_data:
                            services_data = order_data.get('services', [])
                            services_list = await process_services_data(services_data)
                            notification_data["additional_services"] = services_list
                        
                        logger.info(f"Sending notification with data: {notification_data}")
                        
                        # Отправляем уведомление напрямую через сервис без использования очередей
                        success = send_user_notification(notification_data)
                        if success:
                            logger.info(f"User notification sent to {telegram_user_id}")
                        else:
                            logger.error(f"Failed to send user notification to {telegram_user_id}")
                    except Exception as e:
                        logger.error(f"Error preparing notification data: {str(e)}", exc_info=True)
            except Exception as e:
                logger.error(f"Error processing order data or sending notification: {e}")
        else:
            logger.error(f"Error assigning driver and truck: {response.status_code} - {response.text}")
            await callback.answer("Ошибка при назначении водителя и транспорта")
    except Exception as e:
        logger.error(f"Error in confirm_selection: {e}")
        await callback.answer("Произошла ошибка")

# Обработчик отмены
@router.callback_query(F.data.startswith("cancel_"))
async def cancel_selection(callback: CallbackQuery):
    try:
        order_id = callback.data.split("_")[1]
        
        # Возвращаем исходные кнопки принять/отклонить
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Принять",
                        callback_data=f"order_accept_{order_id}"
                    ),
                    InlineKeyboardButton(
                        text="❌ Отклонить",
                        callback_data=f"order_reject_{order_id}"
                    )
                ]
            ]
        )
        await callback.message.edit_reply_markup(reply_markup=keyboard)
        await callback.answer("Действие отменено")
    except Exception as e:
        logger.error(f"Error in cancel_selection: {e}")
        await callback.answer("Произошла ошибка")

async def get_service_names(service_ids):
    """
    Получает названия дополнительных услуг по их ID через API
    
    Args:
        service_ids: Список ID услуг в виде строк
        
    Returns:
        Словарь {id: {"name": name, "price": price}}
    """
    if not service_ids:
        return {}
        
    try:
        # Используем синхронный requests, так как это вызывается из асинхронной функции
        # В идеале следует использовать aiohttp для асинхронных запросов
        service_response = requests.get(
            f"{WB_BACKEND_URL}/orders/services/names/?ids={','.join(service_ids)}"
        )
        
        if service_response.status_code == 200:
            return service_response.json()
        else:
            logger.warning(f"Failed to get service names: {service_response.status_code} - {service_response.text}")
            return {}
    except Exception as e:
        logger.error(f"Error fetching service names: {str(e)}")
        return {}

async def process_services_data(services_data):
    """
    Обрабатывает данные о дополнительных услугах, получая их названия через API
    
    Args:
        services_data: Список данных об услугах в различных форматах
        
    Returns:
        Список обработанных услуг с названиями
    """
    services_list = []
    service_ids = []
    
    # Собираем все ID услуг
    for service in services_data:
        if isinstance(service, dict) and 'id' in service:
            service_ids.append(str(service['id']))
        elif isinstance(service, int):
            service_ids.append(str(service))
    
    # Если есть ID услуг, запрашиваем их названия
    service_names = {}
    if service_ids:
        service_names = await get_service_names(service_ids)
    
    # Формируем список услуг с названиями
    for service in services_data:
        if isinstance(service, dict) and 'id' in service:
            service_id = str(service['id'])
            if service_id in service_names:
                name = service_names[service_id].get('name', f"Услуга {service_id}")
                price = service_names[service_id].get('price', '')
                services_list.append({"name": name, "price": price})
            else:
                name = service.get('name', f"Услуга {service_id}")
                price = service.get('price', '')
                services_list.append({"name": name, "price": price})
        elif isinstance(service, int):
            service_id = str(service)
            if service_id in service_names:
                name = service_names[service_id].get('name', f"Услуга {service_id}")
                price = service_names[service_id].get('price', '')
                services_list.append({"name": name, "price": price})
            else:
                services_list.append({"name": f"Услуга {service}", "price": ""})
        elif isinstance(service, str):
            services_list.append({"name": service, "price": ""})
            
    return services_list

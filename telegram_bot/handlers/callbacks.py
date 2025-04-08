import logging
from typing import Union

import requests
from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from services.api_client import ApiClient
import os 
from dotenv import load_dotenv

load_dotenv()

router = Router()
logger = logging.getLogger(__name__)

# Используем WB_BACKEND_URL вместо API_BASE_URL
WB_BACKEND_URL = os.getenv("WB_BACKEND_URL", "http://localhost:8000")

# Переменная bot будет установлена из bot.py
bot = None

# Функция для получения списка водителей
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
        # Удаляем сообщение
        await callback.message.delete()
    except Exception as e:
        logger.error(f"Error deleting message: {e}")
        await callback.answer("Ошибка при удалении сообщения")

# Обработчик нажатия кнопки "Принять"
@router.callback_query(F.data.startswith("order_accept_"))
async def accept_order(callback: CallbackQuery):
    try:
        order_id = callback.data.split("_")[2]  # Получаем ID заказа
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
                        callback_data=f"driver_{driver['id']}_{order_id}"  # Добавляем order_id
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
        _, driver_id, order_id = callback.data.split("_")

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
                        callback_data=f"truck_{truck['id']}_{driver_id}_{order_id}"  # Добавляем order_id
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
        _, truck_id, driver_id, order_id = callback.data.split("_")

        # Создаем клавиатуру подтверждения
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Подтвердить",
                        callback_data=f"confirm_{driver_id}_{truck_id}_{order_id}"  # Добавляем order_id
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
        _, driver_id, truck_id, order_id = callback.data.split("_")

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
            await callback.message.edit_text(
                text=callback.message.text + "\n\n" + f"✅ Заказ успешно принят\n\n",
                reply_markup=None
            )
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

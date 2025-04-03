import asyncio
import logging
import os
from typing import Dict, List, Optional, Union

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from handlers import callbacks, commands
from handlers.callbacks import router as callbacks_router

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))
group = os.getenv("TELEGRAM_GROUP_ID")
dp = Dispatcher()

callbacks_router.bot = bot

dp.include_router(callbacks_router)
dp.include_router(commands.router)

app = FastAPI()


def message_builder(order_data: Dict) -> Dict[str, Union[str, InlineKeyboardMarkup]]:
    """
    Builds a message for Telegram notification with inline keyboard
    """
    try:
        # Формируем основной текст сообщения
        message_parts = []
        
        # Заголовок с номером заказа
        message_parts.append(f"📦 Новый заказ #{order_data.get('sequence_number', 'N/A')}")
        
        # Информация о складе
        if warehouse := order_data.get('warehouse_name'):
            message_parts.append(f"\n🏭 Склад: {warehouse}")

        # Информация о грузе
        cargo_info = []
        if order_data.get('cargo_type') == 'boxes':
            if box_size := order_data.get('container_type'):
                cargo_info.append(f"📏 Размер коробки: {box_size}")
            if box_count := order_data.get('box_quantity'):
                cargo_info.append(f"📦 Количество коробок: {box_count}")
        elif order_data.get('cargo_type') == 'pallets':
            if pallet_count := order_data.get('pallet_quantity'):
                cargo_info.append(f"🔧 Количество паллет: {pallet_count}")

        if cargo_info:
            message_parts.append("\n📦 Информация о грузе:\n" + "\n".join(cargo_info))

        # Дополнительные услуги
        if services := order_data.get('additional_services', []):
            services_info = []
            for service in services:
                if name := service.get('name'):
                    price = service.get('price', 0)
                    services_info.append(f"• {name}: {price} ₽")
            if services_info:
                message_parts.append("\n🛠 Дополнительные услуги:\n" + "\n".join(services_info))

        # Информация о компании
        company_info = []
        if company := order_data.get('company_name'):
            company_info.append(f"🏢 Компания: {company}")
        if contact := order_data.get('contact_name'):
            company_info.append(f"👤 Контактное лицо: {contact}")
        if phone := order_data.get('contact_phone'):
            company_info.append(f"📱 Телефон: {phone}")

        if company_info:
            message_parts.append("\n" + "\n".join(company_info))

        # Адрес забора груза
        if pickup_address := order_data.get('pickup_address'):
            message_parts.append(f"\n📍 Адрес забора груза:\n{pickup_address}")

        # Общая стоимость
        if total_cost := order_data.get('total_cost'):
            message_parts.append(f"\n💰 Стоимость: {total_cost} ₽")

        # Комментарии
        if comments := order_data.get('comments'):
            message_parts.append(f"\n💭 Комментарии:\n{comments}")

        print(order_data.get('order_id'))

        # Создаем клавиатуру с кнопками
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Принять",
                        callback_data=f"order_accept_{order_data.get('order_id')}"
                    ),
                    InlineKeyboardButton(
                        text="❌ Отклонить",
                        callback_data=f"order_reject_{order_data.get('order_id')}"
                    )
                ]
            ]
        )

        return {
            "text": "\n".join(message_parts),
            "reply_markup": keyboard
        }
    except Exception as e:
        logger.error(f"Error building message: {e}")
        return {
            "text": "Ошибка при формировании сообщения",
            "reply_markup": None
        }


@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    await message.answer(
        f"Привет, {message.from_user.full_name}! Я бот для управления заказами."
    )


async def send_notification(chat_id: Union[str, int], order_data: Dict) -> None:
    """
    Sends notification about new order to specified chat
    """
    try:
        message = message_builder(order_data)
        await bot.send_message(
            chat_id=chat_id,
            text=message["text"],
            reply_markup=message["reply_markup"]
        )
    except Exception as e:
        logger.error(f"Error sending notification: {e}")


# Эндпоинт для приема уведомлений
@app.post("/api/send_notification")
async def send_notification_endpoint(request: Request):
    try:
        order_data = await request.json()
        await send_notification(group, order_data)
        return {"status": "success"}
    except Exception as e:
        logging.error(f"Error sending notification: {str(e)}")
        return {"status": "error", "message": str(e)}


# Запуск FastAPI сервера вместе с ботом
async def main() -> None:
    # Запускаем бота
    bot_task = asyncio.create_task(dp.start_polling(bot))

    # Запускаем FastAPI сервер
    config = uvicorn.Config(app, host="0.0.0.0", port=8080)
    server = uvicorn.Server(config)
    await server.serve()


@app.get("/health")
async def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    asyncio.run(main())

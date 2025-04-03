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

data = {
    "delivery": {
        "warehouse_id": 1,
        "marketplace": 1
    },
    "cargo": {
        "cargo_type": "pallet",
        "container_type": "200-300 кг",
        "box_count": 2,
        "pallet_count": 4,
        "dimensions": {
            "length": "",
            "width": "",
            "height": "",
            "weight": ""
        }
    },
    "client": {
        "name": "Амаль",
        "phone": "+79273284327",
        "company": "ИП Амаль",
        "email": ""
    },
    "additional_services": [
        1
    ],
    "pickup_address": "Проспект Победы 89"
}

data2 = {
    "delivery": {
        "warehouse_id": 1,
        "marketplace": 1
    },
    "cargo": {
        "cargo_type": "pallet",
        "container_type": "0-200 кг",
        "box_count": 0,
        "pallet_count": 1,
        "dimensions": {
            "length": "",
            "width": "",
            "height": "",
            "weight": ""
        }
    },
    "client": {
        "name": "Амаль",
        "phone": "+79083363804",
        "company": "ИП Амаль",
        "email": ""
    },
    "additional_services": [],
    "pickup_address": ""
}

def message_builder(order_data: Dict) -> Dict[str, Union[str, InlineKeyboardMarkup]]:
    """
    Builds a message for Telegram notification with inline keyboard
    """
    print(order_data)
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


@app.post("/api/send_notification")
async def send_notification_endpoint(request: Request):
    try:
        order_data = await request.json()
        await send_notification(group, order_data)
        return {"status": "success"}
    except Exception as e:
        logging.error(f"Error sending notification: {str(e)}")
        return {"status": "error", "message": str(e)}


async def main() -> None:
    bot_task = asyncio.create_task(dp.start_polling(bot))

    config = uvicorn.Config(app, host="0.0.0.0", port=8080)
    server = uvicorn.Server(config)
    await server.serve()


@app.get("/health")
async def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    asyncio.run(main())

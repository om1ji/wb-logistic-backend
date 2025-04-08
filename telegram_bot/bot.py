import asyncio
import logging
import os
from typing import Dict, List, Optional, Union

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from dotenv import load_dotenv
from flask import Flask, request, jsonify

from handlers import callbacks, commands
from handlers.callbacks import router as callbacks_router

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_GROUP_ID = os.getenv("TELEGRAM_GROUP_ID")
WB_BACKEND_URL = os.getenv("WB_BACKEND_URL", "http://localhost:8000")

# Проверка наличия обязательных переменных
if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN not set")
    exit(1)
if not TELEGRAM_GROUP_ID:
    logger.error("TELEGRAM_GROUP_ID not set")
    exit(1)

bot = Bot(token=TELEGRAM_BOT_TOKEN)
group = TELEGRAM_GROUP_ID
dp = Dispatcher()

callbacks_router.bot = bot

dp.include_router(callbacks_router)
dp.include_router(commands.router)

# Заменяем FastAPI на Flask
app = Flask(__name__)

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


async def send_notification(chat_id: Union[str, int], order_data: Dict) -> bool:
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
        return True
    except Exception as e:
        logger.error(f"Error sending notification: {e}")
        return False


# Создаем глобальный event loop для обработки асинхронных запросов
notification_queue = []
notification_processing = False
notification_loop = None

def process_notifications():
    """Обрабатывает уведомления из очереди"""
    global notification_processing
    if notification_processing:
        return
    
    notification_processing = True
    
    async def process_queue():
        global notification_processing, notification_queue
        while notification_queue:
            try:
                chat_id, data = notification_queue.pop(0)
                success = await send_notification(chat_id, data)
                logger.info(f"Notification sent: {success}")
            except Exception as e:
                logger.error(f"Error processing notification queue: {e}")
        notification_processing = False
    
    # Запускаем обработку уведомлений в event loop
    asyncio.run_coroutine_threadsafe(process_queue(), notification_loop)


# Заменяем FastAPI-роут на Flask-роут
@app.route("/api/send_notification", methods=["POST"])
def send_notification_endpoint():
    try:
        order_data = request.json
        
        # Добавляем уведомление в очередь
        notification_queue.append((group, order_data))
        
        # Запускаем обработку уведомлений
        process_notifications()
        
        return jsonify({"status": "success"})
    except Exception as e:
        logging.error(f"Error queuing notification: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


# Заменяем FastAPI health check на Flask-роут
@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok"})


async def main() -> None:
    global notification_loop
    # Переменная для отслеживания завершения работы
    shutdown_event = asyncio.Event()
    flask_thread = None
    
    try:
        # Создаем event loop для уведомлений
        notification_loop = asyncio.get_event_loop()
        
        # Выводим информацию о настройках
        logger.info(f"Starting Telegram bot with group ID: {group}")
        logger.info(f"WB_BACKEND_URL: {WB_BACKEND_URL}")
        
        # Запускаем Flask в отдельном потоке
        import threading
        # Настраиваем Flask для работы с сигналами остановки
        def run_with_shutdown():
            try:
                app.run(host="0.0.0.0", port=8080, threaded=True)
            except Exception as e:
                logger.error(f"Flask server error: {e}")
                
        flask_thread = threading.Thread(target=run_with_shutdown)
        flask_thread.daemon = True
        flask_thread.start()
        logger.info("Flask server started in background thread")
        
        # Запускаем бота
        logger.info("Starting Telegram bot polling")
        await dp.start_polling(bot)
    except (KeyboardInterrupt, asyncio.CancelledError) as e:
        logger.info(f"Received shutdown signal: {type(e).__name__}")
    finally:
        # Корректное завершение работы
        logger.info("Shutting down...")
        
        # Останавливаем бота
        try:
            await dp.stop_polling()
            logger.info("Bot polling stopped")
        except Exception as e:
            logger.error(f"Error stopping bot: {e}")
        
        # Ждем завершения потока Flask
        if flask_thread and flask_thread.is_alive():
            logger.info("Waiting for Flask thread to terminate...")
            flask_thread.join(timeout=3.0)  # Ждем не более 3 секунд
            
        logger.info("Bot and server stopped")


if __name__ == "__main__":
    asyncio.run(main())

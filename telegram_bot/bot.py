import logging
import os
from flask import Flask, request, jsonify
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message
from dotenv import load_dotenv

from handlers import callbacks, commands
from handlers.callbacks import router as callbacks_router
from services.simple_notification import init_notification_service, send_admin_notification, send_user_notification

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

# Настройка бота
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

# Инициализация сервисов
callbacks_router.bot = bot
init_notification_service(TELEGRAM_BOT_TOKEN, TELEGRAM_GROUP_ID)

# Регистрация роутеров
dp.include_router(callbacks_router)
dp.include_router(commands.router)

# Инициализация Flask
app = Flask(__name__)

@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    await message.answer(
        f"Привет, {message.from_user.full_name}! Я бот для управления заказами."
    )

# Flask API для отправки уведомлений
@app.route("/api/send_notification", methods=["POST"])
def send_notification_endpoint():
    """
    Отправляет уведомление администраторам о новом заказе
    """
    try:
        order_data = request.json
        logger.info(f"Received admin notification: {order_data}")
        
        success = send_admin_notification(order_data)
        
        if success:
            return jsonify({"status": "success"})
        else:
            return jsonify({"status": "error", "message": "Failed to send notification"}), 500
            
    except Exception as e:
        logger.error(f"Error sending admin notification: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/send_user_notification", methods=["POST"])
def send_user_notification_endpoint():
    """
    Отправляет уведомление пользователю о статусе заказа
    """
    try:
        notification_data = request.json
        user_id = notification_data.get("telegram_user_id")
        
        logger.info(f"Received user notification request for user_id: {user_id}")
        
        if not user_id:
            logger.error("No telegram_user_id provided in the request")
            return jsonify({"status": "error", "message": "No telegram_user_id provided"}), 400
        
        success = send_user_notification(notification_data)
        
        if success:
            return jsonify({"status": "success"})
        else:
            return jsonify({"status": "error", "message": "Failed to send notification"}), 500
            
    except Exception as e:
        logger.error(f"Error sending user notification: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok"})

async def main() -> None:
    # Переменная для отслеживания завершения работы
    import threading
    
    try:
        def run_flask():
            try:
                app.run(host="0.0.0.0", port=8080, threaded=True)
            except Exception as e:
                logger.error(f"Flask server error: {e}")
                
        flask_thread = threading.Thread(target=run_flask)
        flask_thread.daemon = True
        flask_thread.start()
        
        await dp.start_polling(bot)
        
    except (KeyboardInterrupt, Exception) as e:
        logger.info(f"Received shutdown signal: {type(e).__name__}")
        
    finally:
        await dp.stop_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

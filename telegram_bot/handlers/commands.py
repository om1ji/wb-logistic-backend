import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("start"))
async def cmd_start(message: Message):
    """
    Handles the /start command
    """
    try:
        await message.answer(
            "👋 Привет! Я бот для управления заказами.\n\n"
            "Я буду отправлять уведомления о новых заказах и помогать с их обработкой.\n\n"
            "Доступные команды:\n"
            "/help - показать справку\n"
            "/about - информация о боте"
        )
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await message.answer("Произошла ошибка при обработке команды")

@router.message(Command("help"))
async def cmd_help(message: Message):
    """
    Handles the /help command
    """
    try:
        await message.answer(
            "📚 Справка по командам:\n\n"
            "/start - начать работу с ботом\n"
            "/help - показать эту справку\n"
            "/about - информация о боте\n\n"
            "При получении нового заказа я отправлю уведомление с информацией и кнопками для принятия или отклонения заказа.\n"
            "После принятия заказа вам нужно будет выбрать водителя и транспорт."
        )
    except Exception as e:
        logger.error(f"Error in help command: {e}")
        await message.answer("Произошла ошибка при обработке команды")

@router.message(Command("about"))
async def cmd_about(message: Message):
    """
    Handles the /about command
    """
    try:
        await message.answer(
            "ℹ️ О боте:\n\n"
            "Я помогаю управлять заказами на доставку.\n"
            "Я умею:\n"
            "• Отправлять уведомления о новых заказах\n"
            "• Помогать с назначением водителей и транспорта\n"
            "• Отслеживать статус заказов\n\n"
            "Разработан для WB WMS"
        )
    except Exception as e:
        logger.error(f"Error in about command: {e}")
        await message.answer("Произошла ошибка при обработке команды")

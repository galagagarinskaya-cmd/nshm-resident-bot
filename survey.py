import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import TelegramError
import json

from database import Database
from sheets_service import SheetsService

logger = logging.getLogger(__name__)

db = Database()
sheets = SheetsService()

# Survey questions structure
SURVEY_BLOCKS = {
    1: {
        "title": "Блок 1: Твоё ID (База)",
        "questions": [
            "Как тебя зовут в реале? (укажи Ф.И.О. полностью для титров и документов)",
            "Когда у тебя ДР? (формат: ДД.MM.ГГГГ)",
            "Твой номер телефона (чтобы мы тебя не теряли)",
            "Твой ник в Telegram (для закрытых чатов и лички)",
            "Ссылка на профиль ВКонтакте (это БАЗА)",
            "Где живешь? (регион(-ы) и город(-а) твоего постоянного проживания)"
        ]
    },
    2: {
        "title": "Блок 2: Твой путь (Учеба и работа)",
        "questions": [
            "Твой текущий левел в учебе? (школа / колледж / вуз — укажи класс или курс)",
            "Твоя роль в медиа будущего? (на кого учишься или кем реально хочешь стать?)",
            "Воркаешь где-то прямо сейчас? (да / нет / фриланс)",
            "Если да — где? (напиши название команды или организации)",
            "Мутишь свой блог, формат или рубрику? Кидай ссылку, заценим твой контент!"
        ]
    },
    3: {
        "title": "Блок 3: Твой бэкграунд в НШМ VK",
        "questions": [
            "В каких движах НШМ ты уже был? (вспомни все марафоны и ивенты, где ты был)",
            "Твоя главная цель в комьюнити прямо сейчас? Чего ждешь от «своих»?",
            "Насколько вероятно, что ты посоветуешь наш стать резидентом своим знакомым? (оцени от 0 до 10, где 10 — «уже всем советую»)"
        ]
    },
    4: {
        "title": "Блок 4: Твой вайб",
        "questions": [
            "Где чекаешь новости? (твои главные источники, чтобы быть в курсе)",
            "За какими блогерами следишь?",
            "В каких соцсетях зависаешь чаще всего?",
            "Твой топ-3 TG-каналов прямо сейчас?",
            "Три канала на YouTube, которые всегда в реках?",
            "Любимые сообщества во ВКонтакте, куда заходишь каждый день?",
            "Что слушаешь? Напиши топ-3 исполнителя, которых слушаешь 24/7"
        ]
    },
    5: {
        "title": "Блок 5: Level Up",
        "questions": [
            "Каких знаний тебе реально не хватило, когда начал практиковаться после обучения? (честно про hard- and soft-skills)",
            "Если завтра запустим новый курс, какая тема тебе зайдет?"
        ]
    }
}

async def send_survey_intro(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Send survey introduction"""
    intro_text = """Приветик! Как твоя первая неделя в НШМ? Надеемся, ты уже осваиваешься и чувствуешь себя среди своих хаах

Теперь ты официально резидент, и скоро тебе станут доступны возможности нашего сообщества: аккредитации на ивенты, закрытое обучение и кастинги. Но чтобы мы не писали тебе в личку по сто раз с вопросами, пройти плиз этого бота, это займет всего пару минут. Нам оч важно иметь твою актуальную инфу под рукой, чтобы предлагать именно те проекты, которые тебе реально зайдут🫶🫶🫶"""

    keyboard = [
        [InlineKeyboardButton("Окей, погнали!", callback_data="start_survey")],
        [InlineKeyboardButton("Назад", callback_data="survey_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=intro_text,
            reply_markup=reply_markup
        )
    except TelegramError as e:
        logger.error(f"Error sending survey intro: {e}")

async def start_survey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start survey"""
    query = update.callback_query
    user_id = query.from_user.id

    await query.answer()

    # Mark survey as sent
    from database import Database
    db = Database()
    db.mark_survey_sent(user_id)

    # Show first question
    await show_survey_question(update, context, block=1, question_idx=0)

async def show_survey_question(update: Update, context: ContextTypes.DEFAULT_TYPE, block: int, question_idx: int):
    """Show survey question"""
    query = update.callback_query
    user_id = query.from_user.id

    if block not in SURVEY_BLOCKS:
        # Survey complete
        await show_survey_complete(update, context)
        return

    block_data = SURVEY_BLOCKS[block]
    questions = block_data["questions"]

    if question_idx >= len(questions):
        # Move to next block
        await show_survey_question(update, context, block + 1, 0)
        return

    question = questions[question_idx]
    full_text = f"{block_data['title']}\n\nВопрос {question_idx + 1}/{len(questions)}:\n\n{question}"

    keyboard = [[
        InlineKeyboardButton("← Назад", callback_data=f"survey_back:{block}:{question_idx}"),
        InlineKeyboardButton("→ Дальше", callback_data=f"survey_next:{block}:{question_idx}")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await query.edit_message_text(
            text=full_text,
            reply_markup=reply_markup
        )
    except TelegramError:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=full_text,
                reply_markup=reply_markup
            )
        except TelegramError as e:
            logger.error(f"Error sending survey question: {e}")

    # Store current state
    state_data = json.dumps({"block": block, "question_idx": question_idx})
    from database import Database
    db = Database()
    db.set_user_state(user_id, "survey_question", block, state_data)

async def handle_survey_response(update: Update, context: ContextTypes.DEFAULT_TYPE, answer: str):
    """Handle user's survey response"""
    user_id = update.effective_user.id

    from database import Database
    db = Database()
    state = db.get_user_state(user_id)

    if state:
        state_data = json.loads(state["data"]) if state["data"] else {}
        block = state_data.get("block", 1)
        question_idx = state_data.get("question_idx", 0)

        if block in SURVEY_BLOCKS:
            question = SURVEY_BLOCKS[block]["questions"][question_idx]
            db.save_survey_response(user_id, block, question, answer)

async def show_survey_complete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show survey completion message"""
    query = update.callback_query
    user_id = query.from_user.id

    complete_text = """Спасибо за прохождение опроса! 🫶

Мы получили всю нужную информацию и скоро свяжемся с тобой по поводу персональных возможностей в проекте."""

    keyboard = [[InlineKeyboardButton("Спасибо!", callback_data="survey_done")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await query.edit_message_text(
            text=complete_text,
            reply_markup=reply_markup
        )
    except TelegramError as e:
        logger.error(f"Error showing survey complete: {e}")

    # Notify admins
    from config import TELEGRAM_ADMIN_IDS
    from database import Database
    db = Database()
    user_info = db.get_user(user_id)

    admin_message = f"✅ Резидент завершил опрос:\n\n{user_info['first_name']} {user_info['last_name']}"

    for admin_id in TELEGRAM_ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=admin_message)
        except TelegramError as e:
            logger.error(f"Error sending admin notification: {e}")

    # Update sheets
    survey_responses = db.get_survey_responses(user_id)
    # TODO: Sync to Google Sheets

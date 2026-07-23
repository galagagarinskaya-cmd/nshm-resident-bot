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

# Видео кружков перед каждым блоком
CIRCLE_VIDEOS = {
    1: "videos/survey_block1_gala.mp4",
    2: "videos/survey_block2_roma.mp4",
    3: "videos/survey_block3_nika.mp4",
    4: "videos/survey_block4_alina.mp4",
    5: "videos/survey_block5_yulia.mp4",
}

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

async def send_survey_intro(bot, user_id: int):
    """Send survey introduction after 3 days"""
    intro_text = """Приветик! Как твоя первая неделя в НШМ? Надеемся, ты уже осваиваешься и чувствуешь себя среди своих 🫶

Теперь ты официально резидент, и скоро тебе станут доступны возможности нашего сообщества: аккредитации на ивенты, закрытое обучение и кастинги. Но чтобы мы не писали тебе в личку по сто раз с вопросами, пройти плиз этого бота, это займет всего пару минут. Нам оч важно иметь твою актуальную инфу под рукой, чтобы предлагать именно те проекты, которые тебе реально зайдут 🫶"""

    keyboard = [
        [InlineKeyboardButton("Окей, погнали!", callback_data="start_survey")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await bot.send_message(
            chat_id=user_id,
            text=intro_text,
            reply_markup=reply_markup
        )
        db.mark_survey_sent(user_id)
        logger.info(f"✅ Survey notification sent to user {user_id}")
    except TelegramError as e:
        logger.info(f"Cannot send survey intro to user {user_id} (bot hasn't been contacted): {e}")

async def show_block_circle(context: ContextTypes.DEFAULT_TYPE, user_id: int, block: int):
    """Send circle video at end of block"""
    if block not in CIRCLE_VIDEOS:
        return

    video_path = CIRCLE_VIDEOS[block]
    circle_names = {1: "Гала 🎬", 2: "Рома 🎬", 3: "Ника 🎬", 4: "Алина 🎬", 5: "Юля 🎬"}

    try:
        with open(video_path, "rb") as video_file:
            # Try video_note first, fall back to regular video
            try:
                await context.bot.send_video_note(
                    chat_id=user_id,
                    video_note=video_file,
                    duration=60
                )
                logger.info(f"Sent circle video (video_note) for block {block} to user {user_id}")
            except TelegramError as e:
                if "Voice_messages_forbidden" in str(e) or "video_notes_forbidden" in str(e):
                    # Fall back to regular video
                    video_file.seek(0)
                    await context.bot.send_video(
                        chat_id=user_id,
                        video=video_file
                    )
                    logger.info(f"Sent circle video (regular video) for block {block} to user {user_id}")
                else:
                    raise
    except FileNotFoundError:
        logger.error(f"Circle video not found: {video_path}")
    except TelegramError as e:
        logger.error(f"Error sending circle video: {e}")

async def start_survey_questions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start survey questions after intro"""
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    # Show first question
    await show_survey_question(user_id, context, block=1, question_idx=0)

async def start_survey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start survey"""
    query = update.callback_query
    user_id = query.from_user.id

    await query.answer()

    # Mark survey as sent
    db.mark_survey_sent(user_id)

    # Notify user survey started
    intro_text = """Приветик! Как твоя первая неделя в НШМ? Надеемся, ты уже осваиваешься и чувствуешь себя среди своих 🫶

Теперь давайте пройдём опрос — это займет всего пару минут. Нам оч важно иметь твою актуальную инфу под рукой!"""

    keyboard = [[InlineKeyboardButton("🚀 ГААААЗ", callback_data="survey_start_questions")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(chat_id=user_id, text=intro_text, reply_markup=reply_markup)

async def show_survey_question(user_id: int, context: ContextTypes.DEFAULT_TYPE, block: int, question_idx: int):
    """Show survey question and wait for text answer"""
    if block not in SURVEY_BLOCKS:
        # Survey complete - show final video
        await show_survey_complete_final(context, user_id)
        return

    block_data = SURVEY_BLOCKS[block]
    questions = block_data["questions"]

    if question_idx >= len(questions):
        # End of block - show circle video before moving to next block
        await show_block_circle(context, user_id, block)
        # Move to next block
        await show_survey_question(user_id, context, block + 1, 0)
        return

    question = questions[question_idx]
    full_text = f"{block_data['title']}\n\nВопрос {question_idx + 1}/{len(questions)}:\n\n{question}"

    # Add back button if not first question
    if question_idx > 0 or block > 1:
        keyboard = [[InlineKeyboardButton("← Назад", callback_data=f"survey_back:{block}:{question_idx}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            chat_id=user_id,
            text=full_text,
            reply_markup=reply_markup
        )
    else:
        await context.bot.send_message(
            chat_id=user_id,
            text=full_text + "\n\n_(Напиши ответ текстом)_",
            parse_mode="Markdown"
        )

    # Store current state
    state_data = json.dumps({"block": block, "question_idx": question_idx})
    db.set_user_state(user_id, "survey_question", block, state_data)

async def handle_survey_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text answer from user"""
    user_id = update.effective_user.id
    answer_text = update.message.text.strip() if update.message.text else ""

    # Validate answer (not empty, not a command)
    if not answer_text or answer_text.startswith("/"):
        await context.bot.send_message(
            chat_id=user_id,
            text="⚠️ Пожалуйста, напиши нормальный ответ (не команду и не пусто)"
        )
        return

    state = db.get_user_state(user_id)

    if not state or state.get("current_state") != "survey_question":
        return

    state_data = json.loads(state["data"]) if state["data"] else {}
    block = state_data.get("block", 1)
    question_idx = state_data.get("question_idx", 0)

    if block not in SURVEY_BLOCKS:
        return

    # Save answer
    question = SURVEY_BLOCKS[block]["questions"][question_idx]
    db.save_survey_response(user_id, block, question_idx, question, answer_text)
    logger.info(f"✅ Saved answer from user {user_id}: block {block}, q {question_idx}")

    # Move to next question
    await show_survey_question(user_id, context, block, question_idx + 1)

async def handle_survey_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle back button to edit previous answer"""
    query = update.callback_query
    user_id = query.from_user.id

    parts = query.data.split(":")
    block = int(parts[1])
    question_idx = int(parts[2])

    await query.answer()

    # Go to previous question
    if question_idx > 0:
        await show_survey_question(user_id, context, block, question_idx - 1)
    elif block > 1:
        # Go to last question of previous block
        prev_block = block - 1
        prev_questions_count = len(SURVEY_BLOCKS[prev_block]["questions"])
        await show_survey_question(user_id, context, prev_block, prev_questions_count - 1)

async def handle_survey_response(update: Update, context: ContextTypes.DEFAULT_TYPE, answer: str):
    """Handle user's survey response"""
    user_id = update.effective_user.id

    state = db.get_user_state(user_id)

    if state:
        state_data = json.loads(state["data"]) if state["data"] else {}
        block = state_data.get("block", 1)
        question_idx = state_data.get("question_idx", 0)

        if block in SURVEY_BLOCKS:
            question = SURVEY_BLOCKS[block]["questions"][question_idx]
            db.save_survey_response(user_id, block, question, answer)

async def show_survey_complete_final(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Show survey completion with final video"""
    complete_text = """Спасибо за прохождение опроса! 🫶

Мы получили всю нужную информацию и скоро свяжемся с тобой по поводу персональных возможностей в проекте."""

    await context.bot.send_message(chat_id=user_id, text=complete_text)

    # Send final circle video (Kolya)
    final_video = "videos/survey_final_kolya.mov"
    try:
        with open(final_video, "rb") as video_file:
            try:
                await context.bot.send_video_note(
                    chat_id=user_id,
                    video_note=video_file,
                    duration=60
                )
                logger.info(f"Sent final circle video (video_note) to user {user_id}")
            except TelegramError as e:
                if "Voice_messages_forbidden" in str(e) or "video_notes_forbidden" in str(e):
                    video_file.seek(0)
                    await context.bot.send_video(
                        chat_id=user_id,
                        video=video_file
                    )
                    logger.info(f"Sent final circle video (regular video) to user {user_id}")
                else:
                    raise
    except FileNotFoundError:
        logger.error(f"Final video not found: {final_video}")
    except TelegramError as e:
        logger.error(f"Error sending final circle video: {e}")

    # Sync all survey responses to Google Sheets
    db = Database()
    user_info = db.get_user(user_id)
    survey_responses = db.get_survey_responses(user_id)

    if survey_responses:
        try:
            sheets = SheetsService()
            synced = sheets.sync_survey_responses(user_id, survey_responses)
            if synced:
                logger.info(f"✅ Synced {len(survey_responses)} survey responses to Sheets for user {user_id}")
                # Mark survey as completed only on a real successful sync
                db.mark_survey_completed(user_id)
                logger.info(f"✅ Marked survey completed for user {user_id}")
            else:
                logger.error(f"❌ Sheets sync failed for user {user_id} (returned False) — not marking completed")
        except Exception as e:
            logger.error(f"Error syncing to Sheets: {e}")
    else:
        logger.warning(f"⚠️ No survey responses found for user {user_id}")

    # Notify admins
    from config import TELEGRAM_ADMIN_IDS

    if user_info:
        who = f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip()
    else:
        who = f"user {user_id}"
    admin_message = f"✅ Резидент завершил опрос:\n\n{who}"

    for admin_id in TELEGRAM_ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=admin_message)
        except TelegramError as e:
            logger.error(f"Error sending admin notification: {e}")

    db.set_user_state(user_id, "survey_complete")

async def show_survey_complete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show survey completion message"""
    query = update.callback_query
    user_id = query.from_user.id

    # Send final circle video (Kolyа)
    final_video = "videos/survey_final_kolya.mp4"
    try:
        with open(final_video, "rb") as video_file:
            await context.bot.send_video_note(
                chat_id=user_id,
                video_note=video_file,
                duration=60
            )
        logger.info(f"Sent final circle video (Kolyа) to user {user_id}")
    except FileNotFoundError:
        logger.error(f"Final video not found: {final_video}")
    except TelegramError as e:
        logger.error(f"Error sending final circle video: {e}")

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

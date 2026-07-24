import logging
import html
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import TelegramError
import json

from database import Database
from sheets_service import SheetsService

logger = logging.getLogger(__name__)

db = Database()
sheets = SheetsService()

# Видео кружков в конце каждого блока
CIRCLE_VIDEOS = {
    1: "videos/survey_block1_gala.mp4",
    2: "videos/survey_block2_roma.mp4",
    3: "videos/survey_block3_nika.mp4",
    4: "videos/survey_block4_lisa.mp4",
    5: "videos/survey_final_kolya.mp4",
}

CIRCLE_NAMES = {1: "Гала 🎬", 2: "Рома 🎬", 3: "Ника 🎬", 4: "Лиза 🎬", 5: "Коля 🎬"}

# Структура опроса: каждый вопрос — {"q": текст, "hint": подсказка в скобках}
SURVEY_BLOCKS = {
    1: {
        "title": "Блок 1: Твоё ID (БАЗА)",
        "questions": [
            {"q": "Как тебя зовут в реале? (укажи ФИО полностью для титров и документов)",
             "hint": "напиши ответ текстом"},
            {"q": "Когда у тебя ДР?",
             "hint": "напиши в формате ДД.ММ.ГГГГ"},
            {"q": "Твой номер телефона (чтобы мы тебя не теряли)",
             "hint": "напиши в формате 8 (XXX) XXX-XX-XX"},
            {"q": "Твой ник в Telegram (для закрытых чатов и лички)",
             "hint": "напиши в формате @НИК"},
            {"q": "Ссылка на профиль ВКонтакте (это БАЗА ахаха)",
             "hint": "пример: https://vk.ru/newschoolmediaa"},
            {"q": "Где живешь? (регион(-ы) и город(-а) твоего постоянного проживания)",
             "hint": "пример: г.Новокузнецк, Кемеровская область (летом); г.Домодедово, Московская область (весь рабочий год)"},
        ]
    },
    2: {
        "title": "Блок 2: Твой путь (study and work)",
        "questions": [
            {"q": "Твой текущий левел в учебе? (школа/колледж/вуз — укажи название заведение, специальность и класс или курс)",
             "hint": "пример: РЭУ им.Плеханова, Медиакоммуникации («Продюсирование в кино и медиа»), 2 курс"},
            {"q": "Кем хочешь работать в будущем?",
             "hint": "пример: продюсер; дизайнер; монтажер"},
            {"q": "Работаешь где-то прямо сейчас?",
             "hint": "пиши один из вариантов: да / нет / фриланс"},
            {"q": "Если ты ответил «да» или «фриланс» в предыдущем вопросе, то расскажи плиз немного подробнее: где и кем?",
             "hint": "пример: Коммьюнити-менеджер в НШМ VK"},
            {"q": "Ведешь свой блог, формат или рубрику?",
             "hint": "кидай ссылки на соцсети, где делаешь контент, заценим"},
        ]
    },
    3: {
        "title": "Блок 3: Твой бэкграунд в НШМ VK",
        "questions": [
            {"q": "В каких движах НШМ ты уже был?",
             "hint": "постарайся вспомнить и прописать все марафоны и ивенты, где ты был"},
            {"q": "Твоя главная цель в комьюнити прямо сейчас? Чего ждешь от «своих»?",
             "hint": "это нам поможет создавать мероприятия и активности, которые идеально будут тебе подходить"},
            {"q": "Насколько вероятно, что ты посоветуешь стать резидентом своим знакомым?",
             "hint": "оцени от 0 до 10, где 10 — «уже давно всем советую»"},
        ]
    },
    4: {
        "title": "Блок 4: Твой вайб",
        "questions": [
            {"q": "Где чекаешь новости?",
             "hint": "присылай ссылки на твои главные источники, чтобы быть в курсе"},
            {"q": "За какими блогерами следишь?",
             "hint": "присылай ссылки на тех, кого любишь"},
            {"q": "В каких соцсетях зависаешь чаще всего?",
             "hint": "например: ВКонтакте, ТикТок, и т.д."},
            {"q": "Твой топ-3 TG-, YouTube-каналов и сообществ ВКонтакте",
             "hint": "присылай в формате TG: 1)ссылка, 2)ссылка, 3)ссылка; YouTube: 1)ссылка, 2)ссылка, 3)ссылка; ВКонтакте: 1)ссылка, 2)ссылка, 3)ссылка"},
            {"q": "Что слушаешь?",
             "hint": "напиши топ-3 исполнителя, которых слушаешь 24/7"},
        ]
    },
    5: {
        "title": "Блок 5: Level Up",
        "questions": [
            {"q": "Каких знаний тебе реально не хватило, когда начал практиковаться после обучения?",
             "hint": "тут напиши честно про hard- and soft-skills"},
            {"q": "Если завтра мы будем запускать новый курс, какая тема тебе зайдет?",
             "hint": "например: нейронки, дизайн, борьба с социофобией"},
        ]
    }
}


def _question_text(block: int, question_idx: int) -> str:
    """Return a single question's text (for saving to the DB)."""
    return SURVEY_BLOCKS[block]["questions"][question_idx]["q"]


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
    """Start survey — go straight into the questions (no intro message)."""
    query = update.callback_query
    user_id = query.from_user.id

    await query.answer()

    # Mark survey as sent
    db.mark_survey_sent(user_id)

    # Straight to the first question — the old intro message is removed.
    await show_survey_question(user_id, context, block=1, question_idx=0)


async def show_survey_question(user_id: int, context: ContextTypes.DEFAULT_TYPE, block: int, question_idx: int):
    """Show survey question and wait for text answer"""
    if block not in SURVEY_BLOCKS:
        # Survey complete
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

    q = questions[question_idx]
    qline = f"Вопрос {question_idx + 1}/{len(questions)}:"
    full_text = (
        f"{html.escape(block_data['title'])}\n\n"
        f"<code>{html.escape(qline)}</code>\n"
        f"<blockquote>{html.escape(q['q'])}</blockquote>\n\n"
        f"[{html.escape(q['hint'])}]"
    )

    # "Back" button on every question except the very first one
    reply_markup = None
    if question_idx > 0 or block > 1:
        keyboard = [[InlineKeyboardButton(
            "Нажми, если ошибся в предыдущем вопросе",
            callback_data=f"survey_back:{block}:{question_idx}"
        )]]
        reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=user_id,
        text=full_text,
        reply_markup=reply_markup,
        parse_mode="HTML"
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
    question = _question_text(block, question_idx)
    db.save_survey_response(user_id, block, question_idx, question, answer_text)
    logger.info(f"✅ Saved answer from user {user_id}: block {block}, q {question_idx}")

    # Push to Sheets right away so partial answers survive if the user drops off
    # mid-survey. A Sheets failure must never break the survey flow.
    try:
        responses_so_far = db.get_survey_responses(user_id)
        if responses_so_far:
            if sheets.sync_survey_responses(user_id, responses_so_far):
                logger.info(f"📤 Synced {len(responses_so_far)} answers so far to Sheets for user {user_id}")
            else:
                logger.warning(f"⚠️ Incremental Sheets sync returned False for user {user_id}")
    except Exception as e:
        logger.error(f"Incremental Sheets sync failed for user {user_id}: {e}")

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


async def show_survey_complete_final(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Show survey completion (the block-5 circle already played before this)."""
    complete_text = """Спасибо за прохождение опроса 🫶

Мы получили всю нужную инфу, теперь, как только появятся крутые события и возможности по твоим интересам, будем присылать именно тебе"""

    await context.bot.send_message(chat_id=user_id, text=complete_text)

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

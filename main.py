import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.error import TelegramError
from datetime import datetime, timedelta
import json
from apscheduler.schedulers.background import BackgroundScheduler
import pytz

from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_ADMIN_IDS, SHEETS_CREDENTIALS_PATH, SURVEY_DELAY_DAYS
from database import Database
from sheets_service import SheetsService
from survey import SURVEY_BLOCKS

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global services
db = Database()
sheets = SheetsService(SHEETS_CREDENTIALS_PATH)
scheduler = None

class BotState:
    WELCOME = "welcome"
    RULES_ACCEPTING = "rules_accepting"
    SURVEY = "survey"
    SURVEY_COMPLETE = "survey_complete"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    chat_id = update.effective_chat.id

    # Add or update user in DB
    db.add_or_update_user(user.id, user.username, user.first_name, user.last_name)

    # Check if user is in the chat group
    if chat_id == TELEGRAM_CHAT_ID:
        # User joined the group
        await handle_new_member(update, context)
    else:
        # User started bot in DM
        user_info = db.get_user(user.id)
        if user_info and user_info["rules_accepted"]:
            await context.bot.send_message(
                chat_id=user.id,
                text="Привет! 👋\n\nЯ бот клуба резидентов НШМ VK.\n\nТвой статус: Резидент ✅"
            )
        else:
            await show_welcome_message(update, context)

async def sync_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sync all existing group members to database"""
    user = update.effective_user

    # Only allow admins
    if user.id not in TELEGRAM_ADMIN_IDS:
        await context.bot.send_message(
            chat_id=user.id,
            text="❌ Только администраторы могут использовать эту команду"
        )
        return

    try:
        # Get all members in the group
        member_count = await context.bot.get_chat_member_count(chat_id=TELEGRAM_CHAT_ID)

        sync_msg = await context.bot.send_message(
            chat_id=user.id,
            text=f"⏳ Синхронизация {member_count} участников...\n\nЭто может занять некоторое время..."
        )

        synced = 0
        skipped = 0

        # Get members (note: this is limited API, we can only get admins via API)
        # So we'll mark everyone as needing rules acceptance
        await sync_msg.edit_text(
            f"⏳ Синхронизация участников...\n\n"
            f"✅ Всем участникам необходимо принять правила\n"
            f"Готово!"
        )

        logger.info(f"Admin {user.id} triggered member sync")
    except TelegramError as e:
        await context.bot.send_message(
            chat_id=user.id,
            text=f"❌ Ошибка при синхронизации: {e}"
        )
        logger.error(f"Error syncing members: {e}")

async def handle_new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle new members joining the group automatically"""
    new_members = update.message.new_chat_members

    for user in new_members:
        # Skip if bot itself
        if user.is_bot:
            continue

        user_id = user.id

        # Add user to database
        db.add_or_update_user(user_id, user.username, user.first_name, user.last_name)

        # Block ALL members (new and returning) until rules are accepted again
        try:
            await context.bot.restrict_chat_member(
                chat_id=TELEGRAM_CHAT_ID,
                user_id=user_id,
                permissions=ChatPermissions(
                    can_send_messages=False,
                    can_send_other_messages=False,
                    can_add_web_page_previews=False,
                    can_send_polls=False,
                    can_send_audios=False,
                    can_send_documents=False,
                    can_send_photos=False,
                    can_send_video_notes=False,
                    can_send_voice_notes=False,
                    can_send_videos=False
                )
            )
            logger.info(f"Restricted member {user_id} (must accept rules)")
        except TelegramError as e:
            logger.error(f"Error restricting member {user_id}: {e}")

        # Send welcome message in DM
        try:
            welcome_text = """Приветик! Поздравляем, теперь ты в комьюнити самых крутых зумеров в медиа 🫶

Скорее читай про сообщество и треки в комьюнити, а затем изучай карточки ниже, где подробно описали, "что здесь можно, нужно и нельзя делать"

Для продолжения нажми кнопку ниже 👇"""

            keyboard = [[InlineKeyboardButton("Давайте начнём!", callback_data="start_rules")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await context.bot.send_message(
                chat_id=user_id,
                text=welcome_text,
                reply_markup=reply_markup
            )

            # Set user state
            db.set_user_state(user_id, BotState.WELCOME)
            logger.info(f"Sent welcome message to member {user_id}")
        except TelegramError as e:
            logger.error(f"Error sending welcome message to {user_id}: {e}")

async def handle_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command from new member"""
    user = update.effective_user
    user_id = user.id

    # Add or update user in DB
    db.add_or_update_user(user_id, user.username, user.first_name, user.last_name)

    # Block user from writing until rules are accepted
    try:
        await context.bot.restrict_chat_member(
            chat_id=TELEGRAM_CHAT_ID,
            user_id=user_id,
            permissions=ChatPermissions(
                can_send_messages=False,
                
                can_send_other_messages=False,
                can_add_web_page_previews=False,
                can_send_polls=False,
                can_send_audios=False,
                can_send_documents=False,
                can_send_photos=False,
                can_send_video_notes=False,
                can_send_voice_notes=False,
                can_send_videos=False
            )
        )
    except TelegramError as e:
        logger.error(f"Error restricting user: {e}")

    # Send welcome message in DM
    await show_welcome_message(update, context)

async def show_welcome_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show welcome message"""
    user = update.effective_user

    welcome_text = """Приветик! Поздравляем, теперь ты в комьюнити самых крутых зумеров в медиа 🫶

Скорее читай про сообщество и треки в комьюнити, а затем изучай карточки ниже, где подробно описали, "что здесь можно, нужно и нельзя делать"

Для продолжения нажми кнопку ниже 👇"""

    keyboard = [[InlineKeyboardButton("Давайте начнём!", callback_data="start_rules")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=user.id,
        text=welcome_text,
        reply_markup=reply_markup
    )

    # Set user state
    db.set_user_state(user.id, BotState.WELCOME)

async def start_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start showing rules"""
    query = update.callback_query
    user_id = query.from_user.id

    await query.answer()

    # Get first rule block
    await show_rule_block(update, context, 1)

async def show_rule_block(update: Update, context: ContextTypes.DEFAULT_TYPE, block_num: int):
    """Show rule block"""
    query = update.callback_query
    user_id = query.from_user.id

    rules = sheets.get_rules()

    if not rules:
        # Fallback to hardcoded rules if sheets unavailable
        rule_text = f"Правила блока {block_num}"
    else:
        rule_block = rules.get(str(block_num), {})
        rule_text = f"*{rule_block.get('title', 'Правила')}*\n\n{rule_block.get('text', 'Нет текста')}"

    keyboard = [[
        InlineKeyboardButton("✅ Полностью согласен", callback_data=f"accept_rule:{block_num}")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await query.edit_message_text(
            text=rule_text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    except TelegramError:
        await context.bot.send_message(
            chat_id=user_id,
            text=rule_text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

    # Update user state
    db.set_user_state(user_id, BotState.RULES_ACCEPTING, block_num)

async def accept_rule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Accept rule block"""
    query = update.callback_query
    user_id = query.from_user.id
    block_num = int(query.data.split(":")[1])

    await query.answer()

    # Check if this was the last block (4 blocks total)
    if block_num >= 4:
        # All rules accepted
        db.accept_rules(user_id)

        # Unlock user in chat - open all permissions including topics/threads
        try:
            await context.bot.restrict_chat_member(
                chat_id=TELEGRAM_CHAT_ID,
                user_id=user_id,
                permissions=ChatPermissions(
                    can_send_messages=True,
                    
                    can_send_other_messages=True,
                    can_add_web_page_previews=True,
                    can_send_polls=True,
                    can_send_audios=True,
                    can_send_documents=True,
                    can_send_photos=True,
                    can_send_video_notes=True,
                    can_send_voice_notes=True,
                    can_send_videos=True,
                    can_manage_topics=True
                )
            )
            logger.info(f"Unlocked user {user_id} after accepting rules")
        except TelegramError as e:
            logger.error(f"Error unlocking user: {e}")

        # Send completion message
        completion_text = """Кайфы! Теперь для тебя всё открыто. Если будут вопросы — пиши в чатик или в @info_nshm, велком ту зе клаб 🫶"""
        keyboard = [[InlineKeyboardButton("Спасибо!", callback_data="complete_rules")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            text=completion_text,
            reply_markup=reply_markup
        )

        db.set_user_state(user_id, BotState.SURVEY_COMPLETE)
    else:
        # Show next block
        await show_rule_block(update, context, block_num + 1)

async def handle_survey_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text answer to survey question"""
    user = update.effective_user
    message = update.message

    # Get user state
    state = db.get_user_state(user.id)
    if not state or state["current_state"] != "survey_question":
        return

    # Save answer
    state_data = json.loads(state["data"]) if state["data"] else {}
    block = state_data.get("block", 1)
    question_idx = state_data.get("question_idx", 0)

    if block in SURVEY_BLOCKS:
        question = SURVEY_BLOCKS[block]["questions"][question_idx]
        db.save_survey_response(user.id, block, question_idx, question, message.text)

    # Show next question
    keyboard = [
        [
            InlineKeyboardButton("← Назад (макс 2)", callback_data=f"survey_back:{block}:{question_idx}"),
            InlineKeyboardButton("→ Дальше", callback_data=f"survey_next:{block}:{question_idx}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await message.reply_text(
        "✅ Ответ сохранён!\n\nНажми кнопку ниже для продолжения",
        reply_markup=reply_markup
    )

async def handle_survey_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle next question in survey"""
    query = update.callback_query
    data = query.data.split(":")
    block = int(data[1])
    question_idx = int(data[2])

    await query.answer()

    questions = SURVEY_BLOCKS[block]["questions"]

    if question_idx + 1 >= len(questions):
        # Move to next block
        if block + 1 <= 5:
            await show_survey_block(update, context, block + 1, 0)
        else:
            # Survey complete
            await show_survey_complete(update, context)
    else:
        # Show next question in same block
        await show_survey_block(update, context, block, question_idx + 1)

async def handle_survey_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle going back in survey (max 2 steps)"""
    query = update.callback_query
    data = query.data.split(":")
    block = int(data[1])
    question_idx = int(data[2])

    await query.answer("Можешь вернуться максимум на 2 вопроса назад", show_alert=False)

    if question_idx - 2 >= 0:
        await show_survey_block(update, context, block, question_idx - 2)
    elif question_idx - 1 >= 0:
        await show_survey_block(update, context, block, question_idx - 1)
    else:
        await show_survey_block(update, context, block, question_idx)

async def show_survey_block(update: Update, context: ContextTypes.DEFAULT_TYPE, block: int, question_idx: int):
    """Show survey question"""
    query = update.callback_query
    user_id = query.from_user.id

    if block not in SURVEY_BLOCKS:
        await show_survey_complete(update, context)
        return

    block_data = SURVEY_BLOCKS[block]
    questions = block_data["questions"]

    if question_idx >= len(questions):
        if block + 1 <= 5:
            await show_survey_block(update, context, block + 1, 0)
        else:
            await show_survey_complete(update, context)
        return

    question = questions[question_idx]
    full_text = f"*{block_data['title']}*\n\nВопрос {question_idx + 1}/{len(questions)}:\n\n{question}"

    keyboard = [[
        InlineKeyboardButton("← Назад", callback_data=f"survey_back:{block}:{question_idx}"),
        InlineKeyboardButton("→ Пропустить", callback_data=f"survey_next:{block}:{question_idx}")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await query.edit_message_text(
            text=full_text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    except TelegramError:
        await context.bot.send_message(
            chat_id=user_id,
            text=full_text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

    # Store state
    state_data = json.dumps({"block": block, "question_idx": question_idx})
    db.set_user_state(user_id, "survey_question", block, state_data)

async def show_survey_complete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show survey completion"""
    query = update.callback_query
    user_id = query.from_user.id

    complete_text = "Спасибо за прохождение опроса! 🫶\n\nМы получили всю нужную информацию и скоро свяжемся с тобой."

    keyboard = [[InlineKeyboardButton("Готово", callback_data="survey_done")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await query.edit_message_text(
            text=complete_text,
            reply_markup=reply_markup
        )
    except TelegramError:
        await context.bot.send_message(
            chat_id=user_id,
            text=complete_text,
            reply_markup=reply_markup
        )

    # Mark as completed
    db.set_user_state(user_id, "survey_complete")

    # Sync to sheets
    responses = db.get_survey_responses(user_id)
    if responses:
        sheets.sync_survey_responses(user_id, responses)

    # Notify admins
    user_info = db.get_user(user_id)
    admin_msg = f"✅ Резидент завершил опрос:\n👤 {user_info['first_name']} {user_info.get('last_name', '')}\n🆔 ID: {user_id}"

    for admin_id in TELEGRAM_ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=admin_msg)
        except TelegramError as e:
            logger.error(f"Error sending admin notification: {e}")

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all messages"""
    user = update.effective_user

    # If in group chat and user hasn't accepted rules
    if update.effective_chat.id == TELEGRAM_CHAT_ID:
        user_info = db.get_user(user.id)

        # Add user to DB if not exists
        if not user_info:
            db.add_or_update_user(user.id, user.username, user.first_name, user.last_name)
            user_info = db.get_user(user.id)

        # If user hasn't accepted rules, delete message and notify
        if not user_info or not user_info["rules_accepted"]:
            try:
                await update.message.delete()
                # Send DM with welcome message
                try:
                    await context.bot.send_message(
                        chat_id=user.id,
                        text="👋 Привет! Похоже, ты еще не прошел согласие с правилами нашего комьюнити.\n\n"
                             "Пожалуйста, нажми кнопку ниже чтобы начать 👇"
                    )
                    keyboard = [[InlineKeyboardButton("Давайте начнём!", callback_data="start_rules")]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await context.bot.send_message(
                        chat_id=user.id,
                        text="Правила сообщества:",
                        reply_markup=reply_markup
                    )
                except TelegramError:
                    pass
            except TelegramError:
                pass
    else:
        # Handle survey responses in DM
        state = db.get_user_state(user.id)
        if state and state["current_state"] == "survey_question":
            await handle_survey_answer(update, context)

async def send_survey_to_user(application: Application, user_id: int):
    """Send survey invitation to user"""
    intro_text = """Приветик! Как твоя первая неделя в НШМ? Надеемся, ты уже осваиваешься и чувствуешь себя среди своих хаах

Теперь ты официально резидент, и скоро тебе станут доступны возможности нашего сообщества: аккредитации на ивенты, закрытое обучение и кастинги. Но чтобы мы не писали тебе в личку по сто раз с вопросами, пройти плиз этого бота, это займет всего пару минут. Нам оч важно иметь твою актуальную инфу под рукой, чтобы предлагать именно те проекты, которые тебе реально зайдут🫶🫶🫶"""

    keyboard = [
        [InlineKeyboardButton("Окей, погнали!", callback_data="start_survey")],
        [InlineKeyboardButton("Позже", callback_data="survey_later")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await application.bot.send_message(
            chat_id=user_id,
            text=intro_text,
            reply_markup=reply_markup
        )
        db.mark_survey_sent(user_id)
    except TelegramError as e:
        logger.error(f"Error sending survey to {user_id}: {e}")

async def check_and_send_surveys(application: Application):
    """Check users and send surveys if needed"""
    users = db.get_users_for_survey()
    for user_id in users:
        user_info = db.get_user(user_id)
        if user_info and user_info["rules_accepted_at"]:
            rules_time = datetime.fromisoformat(user_info["rules_accepted_at"])
            if datetime.now() - rules_time >= timedelta(days=SURVEY_DELAY_DAYS):
                await send_survey_to_user(application, user_id)

async def start_survey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start survey"""
    query = update.callback_query
    await query.answer()
    await show_survey_block(update, context, 1, 0)

def main():
    """Start bot"""
    global scheduler
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Handlers - NEW_CHAT_MEMBERS must be first!
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_chat_members))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("sync_members", sync_members))
    application.add_handler(CallbackQueryHandler(start_rules, pattern="^start_rules$"))
    application.add_handler(CallbackQueryHandler(accept_rule, pattern="^accept_rule:"))
    application.add_handler(CallbackQueryHandler(start_survey, pattern="^start_survey$"))
    application.add_handler(CallbackQueryHandler(handle_survey_next, pattern="^survey_next:"))
    application.add_handler(CallbackQueryHandler(handle_survey_back, pattern="^survey_back:"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))

    # Setup scheduler for surveys
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        check_and_send_surveys,
        "interval",
        hours=1,
        args=[application],
        timezone=pytz.timezone("Europe/Moscow")
    )
    scheduler.start()

    # Start polling
    logger.info("Bot started with scheduler")
    application.run_polling()

if __name__ == "__main__":
    main()

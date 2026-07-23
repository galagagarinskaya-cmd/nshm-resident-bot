import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.error import TelegramError
from datetime import datetime, timedelta
import json
from apscheduler.schedulers.background import BackgroundScheduler
import pytz
import threading

from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_ADMIN_IDS, SHEETS_CREDENTIALS_PATH, SURVEY_DELAY_DAYS, FLASK_PORT
from database import Database
from sheets_service import SheetsService
from survey import (
    SURVEY_BLOCKS, CIRCLE_VIDEOS,
    start_survey as survey_start_survey,
    start_survey_questions,
    handle_survey_answer,
    handle_survey_back
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

db = Database()
sheets = SheetsService(SHEETS_CREDENTIALS_PATH)
scheduler = None

class BotState:
    WELCOME = "welcome"
    RULES_ACCEPTING = "rules_accepting"
    SURVEY = "survey"
    SURVEY_COMPLETE = "survey_complete"

# Карточки для каждого блока правил
RULE_CARDS = {
    1: ["cards/part1_intro.png", "cards/part1_1-3.png", "cards/part1_4-6.png", "cards/part1_7-9.png"],
    2: ["cards/part2_intro.png", "cards/part2_content.png"],
    3: ["cards/part3_intro.png", "cards/part3_1-3.png", "cards/part3_4-6.png", "cards/part3_7-8.png"],
    4: ["cards/part4_intro.png", "cards/part4_content.png"],
}

# ============= NEW MEMBERS HANDLER =============
async def handle_new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle new members joining the group"""
    logger.info(f"✅ NEW MEMBER EVENT TRIGGERED")
    logger.info(f"📋 ACTUAL CHAT ID: {update.effective_chat.id}")

    new_members = update.message.new_chat_members
    logger.info(f"📋 New members count: {len(new_members)}")

    for user in new_members:
        if user.is_bot:
            continue

        user_id = user.id
        logger.info(f"🔔 Processing member: {user.first_name} ({user_id})")

        # Add to DB
        db.add_or_update_user(user_id, user.username, user.first_name, user.last_name)

        # Block all permissions
        try:
            await context.bot.restrict_chat_member(
                chat_id=TELEGRAM_CHAT_ID,
                user_id=user_id,
                permissions=ChatPermissions(
                    can_send_messages=False,
                    can_send_media_messages=False,
                    can_send_other_messages=False,
                    can_add_web_page_previews=False,
                    can_send_polls=False
                )
            )
            logger.info(f"🚫 Restricted member {user_id}")
        except TelegramError as e:
            logger.error(f"❌ Error restricting {user_id}: {e}")

        # Send welcome message in group with button (ONLY ONCE)
        if not db.get_user_state(user_id) or db.get_user_state(user_id).get("current_state") != BotState.WELCOME:
            try:
                welcome_text = f"""Привет, {user.first_name}! 👋

Поздравляем, теперь ты в комьюнити самых крутых зумеров в медиа 🫶

Скорее прочитай про сообщество и треки в коммьюнити, а затем нажми кнопку ниже 👇"""

                keyboard = [
                    [
                        InlineKeyboardButton("Про сообщество", url="https://t.me/c/1914063685/480"),
                        InlineKeyboardButton("Треки в коммьюнити", url="https://t.me/c/1914063685/494")
                    ],
                    [InlineKeyboardButton("Давай начнем!", callback_data="start_rules")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await context.bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID,
                    text=welcome_text,
                    reply_markup=reply_markup
                )
                db.set_user_state(user_id, BotState.WELCOME)
                logger.info(f"📢 Sent welcome message in group to {user_id}")
            except TelegramError as e:
                logger.error(f"❌ Error sending welcome message: {e}")

# ============= RULES HANDLERS =============
async def start_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start showing rule cards"""
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    # Check if already accepted rules
    user_info = db.get_user(user_id)
    if user_info and user_info["rules_accepted"]:
        # Already accepted - go to survey
        await context.bot.send_message(
            chat_id=user_id,
            text="Ты уже принял правила! 🎉\n\nДавай перейдем к опросу 👇"
        )
        await start_survey(user_id, context)
        return

    # Send intro message in DM
    intro_text = """По кнопкам ниже ты можешь подробнее почитать про сообщество и про треки в коммьюнити. А если сразу хочешь начать заполнять анкету, нажимай «Давайте начнём!» (эта кнопка в первом сообщении)"""

    try:
        keyboard = [
            [
                InlineKeyboardButton("Про сообщество", url="https://t.me/c/1914063685/480"),
                InlineKeyboardButton("Треки в коммьюнити", url="https://t.me/c/1914063685/494")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=user_id,
            text=intro_text,
            reply_markup=reply_markup
        )
    except TelegramError as e:
        logger.error(f"Error sending intro: {e}")

    # Start showing rule cards
    await show_rule_card(update, context, block_num=1, card_index=0)

async def show_rule_card(update: Update, context: ContextTypes.DEFAULT_TYPE, block_num: int, card_index: int):
    """Show all rule cards for a block at once"""
    if update.callback_query and update.callback_query.from_user:
        user_id = update.callback_query.from_user.id
        await update.callback_query.answer()
    else:
        user_id = update.effective_user.id

    # Get all cards for this block
    cards = RULE_CARDS.get(block_num, [])

    if not cards:
        await context.bot.send_message(chat_id=user_id, text="❌ Карточки правил не найдены")
        return

    # Send all cards of the block
    try:
        for card_path in cards:
            with open(card_path, 'rb') as photo:
                await context.bot.send_photo(chat_id=user_id, photo=photo)
        logger.info(f"📸 Sent all {len(cards)} rule cards for block {block_num} to {user_id}")
    except FileNotFoundError as e:
        logger.error(f"❌ Card not found: {e}")
        await context.bot.send_message(chat_id=user_id, text="❌ Карточка правил не найдена")
        return
    except TelegramError as e:
        logger.error(f"❌ Error sending cards: {e}")
        return

    # Show accept button after all cards
    keyboard = [[InlineKeyboardButton("✅ Принимаю правила", callback_data=f"accept_rule:{block_num}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=user_id,
        text=f"📖 Ты прочитал все правила раздела {block_num}",
        reply_markup=reply_markup
    )

async def accept_rule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Accept rule block and move to next"""
    query = update.callback_query
    user_id = query.from_user.id
    block_num = int(query.data.split(":")[1])
    await query.answer()

    if block_num == 4:
        # All rules accepted - UNLOCK
        db.accept_rules(user_id)

        try:
            await context.bot.restrict_chat_member(
                chat_id=TELEGRAM_CHAT_ID,
                user_id=user_id,
                permissions=ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True,
                    can_send_polls=True,
                    can_manage_topics=True
                )
            )
            logger.info(f"✅ Unlocked user {user_id}")
        except Exception as e:
            logger.error(f"❌ Error unlocking: {e}")

        # First message — welcome to community
        welcome_message = "Кайфы! Теперь для тебя всё открыто. Если будут вопросы — пиши в чатик или в @info_nshm, велком ту зе клаб 🫶"

        try:
            await context.bot.send_message(chat_id=user_id, text=welcome_message)
            logger.info(f"✅ Sent welcome message to user {user_id}")
        except TelegramError as e:
            logger.error(f"❌ Error sending welcome message: {e}")

        # Second message — survey invitation with button
        survey_text = "Теперь давайте пройдём опрос чтобы мы могли предложить тебе самые интересные проекты 👇"
        keyboard = [[InlineKeyboardButton("Начать опрос", callback_data="start_survey")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await context.bot.send_message(chat_id=user_id, text=survey_text, reply_markup=reply_markup)
            db.set_user_state(user_id, BotState.SURVEY)
            logger.info(f"✅ Rules accepted for user {user_id}. Survey scheduled in {SURVEY_DELAY_DAYS} days")
        except TelegramError as e:
            logger.error(f"❌ Error sending survey invitation: {e}")
    else:
        # Show next block
        await show_rule_card(update, context, block_num=block_num + 1, card_index=0)

# ============= BOT START HANDLER =============
async def bot_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle bot start button click"""
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    # Send welcome message to DM
    welcome_text = """👋 Привет! Я бот резидента НШМ.

Теперь ты можешь начать процесс принятия правил и заполнения опроса.

Нажми /start чтобы начать 👇"""

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=welcome_text
        )
        logger.info(f"Started conversation with user {user_id}")
    except TelegramError as e:
        logger.error(f"Error starting conversation: {e}")

# ============= ANNOUNCE RULES COMMAND =============
async def announce_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send rules announcement to group (admin only)"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # Check if user is admin
    if user_id not in TELEGRAM_ADMIN_IDS:
        await update.message.reply_text("❌ Эта команда доступна только администраторам")
        return

    # Send announcement to group
    text = """🔔 **ВАЖНО для всех участников**

Чтобы активировать доступ в чат, нужно принять правила сообщества.

Нажми кнопку ниже 👇"""

    keyboard = [
        [InlineKeyboardButton("🚀 Старт", callback_data="bot_start")],
        [InlineKeyboardButton("✅ Принять правила", callback_data="start_rules")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await context.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        await update.message.reply_text("✅ Сообщение отправлено в группу!")
        logger.info(f"Admin {user_id} sent rules announcement to group")
    except TelegramError as e:
        logger.error(f"Error sending announcement: {e}")
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ============= START COMMAND =============
async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Restart the rules acceptance process"""
    user_id = update.effective_user.id

    # Reset rules and survey status
    db.reset_rules(user_id)
    db.set_user_state(user_id, BotState.WELCOME)

    # Send restart confirmation
    await update.message.reply_text("🔄 Перезапущен процесс принятия правил!\n\nНажми /start чтобы начать заново.")
    logger.info(f"🔄 User {user_id} restarted rules acceptance")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    chat_id = update.effective_chat.id

    db.add_or_update_user(user.id, user.username, user.first_name, user.last_name)

    if chat_id == TELEGRAM_CHAT_ID:
        # In group - show welcome
        welcome_text = """Приветик! Поздравляем, теперь ты в комьюнити самых крутых зумеров в медиа 🫶

Скорее читай про сообщество и треки в комьюнити, а затем изучай карточки ниже, где подробно описали, "что здесь можно, нужно и нельзя делать"

Для продолжения нажми кнопку ниже 👇"""

        keyboard = [[InlineKeyboardButton("Давайте начнём!", callback_data="start_rules")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(chat_id=user.id, text=welcome_text, reply_markup=reply_markup)
        db.set_user_state(user.id, BotState.WELCOME)
    else:
        # In DM
        user_info = db.get_user(user.id)
        if user_info and user_info["rules_accepted"]:
            menu_text = "Привет! 👋\n\nТвой статус: Резидент ✅"

            # Check if 3 days passed since rules acceptance
            if user_info.get("rules_accepted_at"):
                rules_time = datetime.fromisoformat(user_info["rules_accepted_at"])
                if not rules_time.tzinfo:
                    rules_time = rules_time.replace(tzinfo=pytz.UTC)

                time_passed = datetime.now(pytz.UTC) - rules_time
                days_left = SURVEY_DELAY_DAYS - (time_passed.days)

                if time_passed >= timedelta(days=SURVEY_DELAY_DAYS):
                    menu_text += "\n\nЧто ты хочешь сделать?"
                    keyboard = [[InlineKeyboardButton("🎯 Пройти опрос", callback_data="start_survey")]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                else:
                    menu_text += f"\n\nОпрос будет доступен через {days_left} дн. ⏳"
                    reply_markup = None
            else:
                reply_markup = None

            await context.bot.send_message(chat_id=user.id, text=menu_text, reply_markup=reply_markup)
        else:
            welcome_text = """Приветик! Поздравляем, теперь ты в комьюнити самых крутых зумеров в медиа 🫶

Скорее читай про сообщество и треки в комьюнити, а затем изучай карточки ниже, где подробно описали, "что здесь можно, нужно и нельзя делать"

Для продолжения нажми кнопку ниже 👇"""

            keyboard = [[InlineKeyboardButton("Давайте начнём!", callback_data="start_rules")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await context.bot.send_message(chat_id=user.id, text=welcome_text, reply_markup=reply_markup)
            db.set_user_state(user.id, BotState.WELCOME)

# ============= MESSAGE HANDLERS =============
async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages"""
    user = update.effective_user
    chat_id = update.effective_chat.id

    if chat_id == TELEGRAM_CHAT_ID:
        # In group - check if accepted rules
        user_info = db.get_user(user.id)
        if not user_info or not user_info["rules_accepted"]:
            try:
                await update.message.delete()
            except TelegramError:
                pass
    else:
        # In DM - handle survey answer
        if user.id in context.user_data and "current_block" in context.user_data[user.id]:
            await handle_survey_answer(update, context)

# ============= CARD NAVIGATION =============
async def navigate_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Navigate between rule cards"""
    query = update.callback_query
    parts = query.data.split(":")
    block_num = int(parts[1])
    card_index = int(parts[2])
    await query.answer()
    await show_rule_card(update, context, block_num, card_index)


# ============= SCHEDULER =============
async def check_and_send_surveys(application: Application):
    """Check and send surveys after 3 days"""
    users = db.get_users_for_survey()
    logger.info(f"📊 Checking surveys for {len(users)} users")

    for user_id in users:
        user_info = db.get_user(user_id)
        if not user_info or not user_info.get("rules_accepted_at"):
            continue

        rules_accepted_time = datetime.fromisoformat(user_info["rules_accepted_at"])
        if not rules_accepted_time.tzinfo:
            rules_accepted_time = rules_accepted_time.replace(tzinfo=pytz.UTC)

        time_passed = datetime.now(pytz.UTC) - rules_accepted_time
        if time_passed >= timedelta(days=SURVEY_DELAY_DAYS):
            try:
                from survey import send_survey_intro
                await send_survey_intro(application.bot, user_id)
                logger.info(f"📬 Sent survey to user {user_id}")
            except Exception as e:
                logger.error(f"Error sending survey to user {user_id}: {e}")

def start_admin_panel():
    """Start Flask admin panel in background thread"""
    try:
        from admin_panel import run_admin_panel
        port = os.getenv("PORT", FLASK_PORT)
        logger.info(f"🎛️ Starting admin panel on port {port}")
        run_admin_panel(port=int(port))
    except Exception as e:
        logger.error(f"❌ Error starting admin panel: {e}")

def main():
    """Start bot and admin panel"""
    global scheduler

    # Start admin panel only on Railway (production)
    is_railway = os.getenv("RAILWAY_ENVIRONMENT_NAME") is not None
    if is_railway:
        admin_thread = threading.Thread(target=start_admin_panel, daemon=True)
        admin_thread.start()
        logger.info("🎛️ Admin panel thread started (Railway deployment)")
    else:
        logger.info("⏭️ Skipping admin panel (local development)")

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Handlers - ORDER MATTERS!
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_chat_members))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("restart", restart))
    application.add_handler(CommandHandler("announce_rules", announce_rules))
    application.add_handler(CallbackQueryHandler(bot_start_handler, pattern="^bot_start$"))
    application.add_handler(CallbackQueryHandler(start_rules, pattern="^start_rules$"))
    application.add_handler(CallbackQueryHandler(navigate_cards, pattern="^rule_card:"))
    application.add_handler(CallbackQueryHandler(accept_rule, pattern="^accept_rule:"))
    application.add_handler(CallbackQueryHandler(survey_start_survey, pattern="^start_survey$"))
    application.add_handler(CallbackQueryHandler(start_survey_questions, pattern="^survey_start_questions$"))
    application.add_handler(CallbackQueryHandler(handle_survey_back, pattern="^survey_back:"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_survey_answer), group=1)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages), group=2)

    # Scheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        check_and_send_surveys,
        "interval",
        hours=1,
        args=[application],
        timezone=pytz.timezone("Europe/Moscow")
    )
    scheduler.start()

    # Wait for any previous container's getUpdates poller to fully release
    # before we start polling. Railway overlaps the old and new container
    # during a deploy; without this delay the new poller hits a Telegram
    # "Conflict: terminated by other getUpdates request" at startup, which
    # PTB 20.0 does not recover from (polling silently dies).
    startup_delay = int(os.getenv("STARTUP_DELAY", "30"))
    if startup_delay > 0:
        logger.info(f"⏳ Waiting {startup_delay}s for previous instance to release polling...")
        import time
        time.sleep(startup_delay)

    logger.info("🚀 Bot started")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()

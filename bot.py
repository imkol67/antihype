import asyncio
import logging
import os
import aiosqlite
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DB_PATH = "bot.db"

WELCOME_TEXT = (
    "Здравствуйте! 👋\n"
    "Это бот для анонимной обратной связи и подачи анкет.\n\n"
    "Вы можете написать нам любое сообщение (оно уйдет анонимно), "
    "или заполнить анкету на проверяющего/интервьюера."
)

INTERVIEWER = [
    "Какого Вы пола (мужской/женский)?",
    "Сколько Вам лет?",
    "Тег, по которому Вы собираетесь работать.",
    "Ваш часовой пояс.",
    "Сколько интервью Вы сможете брать и оформлять (то бишь, выкладывать) в неделю?",
    "Насколько Вы грамотный человек?",
    "Готовы ли Вы будете принимать замечания старшей администрации?",
    "У Вас был опыт в подобной сфере (именно интервью)?",
    "Насколько Вы быстро учитесь новому?",
    "Откуда Вы узнали о нашем проекте?",
    "Сможете ли самостоятельно искать людей, у которых будет взято интервью?",
    "Сможете ли договариваться о взятии интервью?",
    "Ваш юз.",
]

CHECKER = [
    "Какого Вы пола (мужской/женский)?",
    "Сколько Вам лет?",
    "Тег, по которому Вы собираетесь работать.",
    "Ваш часовой пояс.",
    "Сколько ботов Вы сможете проверять и писать для них посты в неделю?",
    "Насколько Вы грамотный человек?",
    "Как относитесь к агрессии?",
    "Готовы ли будете принимать замечания старшей администрации?",
    "У Вас был опыт в подобной сфере (именно проверок)?",
    "Сможете ли Вы расписывать абсолютно все ошибки администраторов и проектов в постах?",
    "Если у Вас начнется конфликт с ботом, снизите ли Вы оценку за это в посте?",
    "Насколько быстро Вы учитесь новому?",
    "Откуда узнали о нашем проекте?",
    "Ваш юз.",
]

class Anketa(StatesGroup):
    choosing_action = State()
    choosing_role = State()
    answering = State()

async def db_init():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS tickets (user_id INTEGER PRIMARY KEY, group_msg_id INTEGER NOT NULL)")
        await db.execute("CREATE TABLE IF NOT EXISTS msg_map (group_msg_id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL)")
        await db.commit()

async def get_setting(key: str) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cur.fetchone()
        return row[0] if row else None

async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        await db.commit()

async def set_ticket(user_id: int, group_msg_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO tickets (user_id, group_msg_id) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET group_msg_id = excluded.group_msg_id",
            (user_id, group_msg_id),
        )
        await db.execute("INSERT OR REPLACE INTO msg_map (group_msg_id, user_id) VALUES (?, ?)", (group_msg_id, user_id))
        await db.commit()

async def get_ticket_msg(user_id: int) -> int | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT group_msg_id FROM tickets WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else None

async def get_user_by_msg(group_msg_id: int) -> int | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id FROM msg_map WHERE group_msg_id = ?", (group_msg_id,))
        row = await cur.fetchone()
        return row[0] if row else None

logging.basicConfig(level=logging.INFO)
router = Router()

@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Заполнить анкету", callback_data="action:anketa")],
        [InlineKeyboardButton(text="💬 Обратная связь (Анонимно)", callback_data="action:feedback")]
    ])
    await message.answer(WELCOME_TEXT, reply_markup=kb)
    await state.set_state(Anketa.choosing_action)

@router.message(F.new_chat_members)
async def on_bot_added(message: Message, bot: Bot):
    for member in message.new_chat_members:
        if member.id == bot.id:
            await set_setting("admin_group_id", str(message.chat.id))
            await message.answer("✅ Бот успешно подключен к этой группе! Теперь все сообщения от пользователей будут приходить сюда.")

@router.callback_query(Anketa.choosing_action, F.data.startswith("action:"))
async def choose_action(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[1]
    if action == "anketa":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎤 Интервьюер", callback_data="role:interviewer")],
            [InlineKeyboardButton(text="🔍 Проверяющий", callback_data="role:checker")],
        ])
        await callback.message.edit_text("Выберите, на кого вы хотите подать анкету:", reply_markup=kb)
        await state.set_state(Anketa.choosing_role)
    else:
        await callback.message.edit_text("✍️ Напишите ваше сообщение, и оно анонимно уйдет администрации.")
        await state.clear()
    await callback.answer()

@router.callback_query(Anketa.choosing_role, F.data.startswith("role:"))
async def choose_role(callback: CallbackQuery, state: FSMContext):
    role = callback.data.split(":")[1]
    if role == "interviewer":
        title, questions = "АНКЕТА НА ИНТЕРВЬЮЕРА", INTERVIEWER
    else:
        title, questions = "АНКЕТА НА ПРОВЕРЯЮЩЕГО", CHECKER

    await state.update_data(role=role, title=title, questions=questions, index=0, answers=[])
    await state.set_state(Anketa.answering)
    await callback.message.edit_text(
        f"📋 <b>{title}</b>\n\n<b>Вопрос 1/{len(questions)}</b>\n{questions[0]}"
    )
    await callback.answer()

@router.message(Anketa.answering, F.text)
async def handle_answer(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    questions = data["questions"]
    index = data["index"]
    answers = data["answers"]

    answers.append((questions[index], message.text))
    index += 1

    if index < len(questions):
        await state.update_data(index=index, answers=answers)
        await message.answer(
            f"<b>Вопрос {index + 1}/{len(questions)}</b>\n{questions[index]}"
        )
        return

    await send_anketa(bot, message, data, answers)
    await state.clear()

async def send_anketa(bot: Bot, message: Message, data: dict, answers):
    group_id = await get_setting("admin_group_id")
    if not group_id:
        await message.answer("❌ Ошибка: бот еще не добавлен в группу администрации.")
        return

    role_ru = "Интервьюер" if data["role"] == "interviewer" else "Проверяющий"
    
    header = (
        f"<b>📥 Новая анкета: {role_ru}</b>\n"
        f"<i>ID для ответа: <code>{message.from_user.id}</code></i>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
    )
    body = ""
    for i, (q, a) in enumerate(answers, start=1):
        body += f"<b>{i}. {q}</b>\n{a}\n\n"

    full = header + body
    chunks = [full[i:i + 4000] for i in range(0, len(full), 4000)]

    last_sent = None
    for chunk in chunks:
        last_sent = await bot.send_message(int(group_id), chunk)

    if last_sent:
        await set_ticket(message.from_user.id, last_sent.message_id)

    await message.answer(
        "✅ Ваша анкета отправлена администрации. "
        "Если у них будут вопросы, ответ придёт сюда."
    )

@router.message(F.reply_to_message)
async def admin_reply(message: Message, bot: Bot):
    group_id = await get_setting("admin_group_id")
    if not group_id or str(message.chat.id) != group_id:
        return

    target_msg_id = message.reply_to_message.message_id
    user_id = await get_user_by_msg(target_msg_id)

    if not user_id:
        return

    try:
        await bot.copy_message(
            chat_id=user_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
        )
        await message.reply("✅ Ответ отправлен пользователю.")
        await set_ticket(user_id, message.message_id)
    except Exception as e:
        await message.reply(f"❌ Ошибка отправки: {e}")

@router.message(F.chat.type == "private")
async def user_message(message: Message, state: FSMContext, bot: Bot):
    current = await state.get_state()
    if current is not None: 
        return 

    group_id = await get_setting("admin_group_id")
    if not group_id:
        await message.answer("❌ Бот еще не настроен администрацией.")
        return

    user_id = message.from_user.id
    thread_msg = await get_ticket_msg(user_id)

    header = f"👤 <b>Анонимное сообщение</b>\n<i>ID для ответа: <code>{user_id}</code></i>\n\n"
    
    if thread_msg:
        try:
            sent = await bot.copy_message(
                chat_id=int(group_id),
                from_chat_id=message.chat.id,
                message_id=message.message_id,
                reply_to_message_id=thread_msg,
            )
            await set_ticket(user_id, sent.message_id)
            return
        except Exception:
            pass

    text = message.text or message.caption or "<i>(вложение)</i>"
    sent = await bot.send_message(int(group_id), f"{header}{text}")
    await set_ticket(user_id, sent.message_id)
    await message.answer("✉️ Ваше сообщение отправлено администрации. Ожидайте ответа!")

async def main():
    await db_init()
    
    async def handle(request):
        return web.Response(text="Bot is running!")
    
    app = web.Application()
    app.router.add_get('/', handle)
    
    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    
    print("Бот запущен и заглушка работает!")
    await dp.start_polling(bot)

if name == "main":
    asyncio.run(main())

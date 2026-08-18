import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# ============ НАСТРОЙКИ — поменяй под себя ============
BOT_TOKEN = os.getenv("BOT_TOKEN", "СЮДА_ВСТАВЬ_ТОКЕН_ЕСЛИ_НЕ_ЧЕРЕЗ_ENV")
CHANNEL_USERNAME = "@tvoy_life_code"       # публичный канал Life Code
PAID_CALCULATOR_URL = "https://t.me/tribute/app?startapp=s13EN"  # ссылка на оплату "Код Жизни" через Tribute
IMAGES_DIR = ""                             # картинки лежат прямо в корне репозитория
# ========================================================

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# ---------- Numerology logic (same formula as calculator.html) ----------
LETTER_MAP = {
    'а': 1, 'и': 1, 'с': 1, 'ъ': 1,
    'б': 2, 'й': 2, 'т': 2, 'ы': 2,
    'в': 3, 'к': 3, 'у': 3, 'ь': 3,
    'г': 4, 'л': 4, 'ф': 4, 'э': 4,
    'д': 5, 'м': 5, 'х': 5, 'ю': 5,
    'е': 6, 'н': 6, 'ц': 6, 'я': 6,
    'ё': 7, 'о': 7, 'ч': 7,
    'ж': 8, 'п': 8, 'ш': 8,
    'з': 9, 'р': 9, 'щ': 9,
}


def reduce_to_single(n: int) -> int:
    n = abs(n)
    while n > 9:
        n = sum(int(d) for d in str(n))
    return n


def word_to_digit(word: str) -> int:
    chars = [ch for ch in word.lower() if ch in LETTER_MAP]
    if not chars:
        return 0
    total = sum(LETTER_MAP[ch] for ch in chars)
    return reduce_to_single(total)


def calc_life_number(first_name: str, middle_name: str, last_name: str, day: int, month: int, year: int) -> int:
    name_digit = word_to_digit(first_name)
    middle_digit = word_to_digit(middle_name) if middle_name else 0
    last_digit = word_to_digit(last_name)
    vector = reduce_to_single(name_digit + middle_digit + last_digit)

    date_digits_sum = sum(int(d) for d in str(day)) + sum(int(d) for d in str(month)) + sum(int(d) for d in str(year))
    date_digit = reduce_to_single(date_digits_sum)

    life_number = reduce_to_single(vector + date_digit)
    if life_number == 0:
        life_number = 9
    return life_number


# ---------- FSM states ----------
class Form(StatesGroup):
    first_name = State()
    middle_name = State()
    last_name = State()
    birth_date = State()


# ---------- Handlers ----------
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Привет! Я посчитаю твою личную <b>Цифру Я</b> — программу, которая формирует твою жизнь.\n\n"
        "Напиши своё имя:"
    )
    await state.set_state(Form.first_name)


@dp.message(Form.first_name)
async def process_first_name(message: Message, state: FSMContext):
    await state.update_data(first_name=message.text.strip())
    await message.answer("Отчество (если есть — напиши, если нет, отправь «-»):")
    await state.set_state(Form.middle_name)


@dp.message(Form.middle_name)
async def process_middle_name(message: Message, state: FSMContext):
    val = message.text.strip()
    await state.update_data(middle_name="" if val == "-" else val)
    await message.answer("Фамилия:")
    await state.set_state(Form.last_name)


@dp.message(Form.last_name)
async def process_last_name(message: Message, state: FSMContext):
    await state.update_data(last_name=message.text.strip())
    await message.answer("Дата рождения в формате ДД.ММ.ГГГГ (например 15.05.1990):")
    await state.set_state(Form.birth_date)


@dp.message(Form.birth_date)
async def process_birth_date(message: Message, state: FSMContext):
    text = message.text.strip()
    try:
        day_s, month_s, year_s = text.split(".")
        day, month, year = int(day_s), int(month_s), int(year_s)
        assert 1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2100
    except Exception:
        await message.answer("Не получилось распознать дату. Введи в формате ДД.ММ.ГГГГ, например 15.05.1990:")
        return

    data = await state.get_data()
    life_number = calc_life_number(
        data["first_name"], data.get("middle_name", ""), data["last_name"], day, month, year
    )
    await state.update_data(life_number=life_number)
    await state.set_state(None)

    # Проверка подписки на канал
    is_subscribed = await check_subscription(message.from_user.id)

    if is_subscribed:
        await send_number_card(message.chat.id, life_number)
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Подписаться на Life Code", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
            [InlineKeyboardButton(text="Я подписался(ась) ✅", callback_data="check_sub")]
        ])
        await message.answer(
            f"Твоя Цифра Я = <b>{life_number}</b>\n\n"
            f"Чтобы получить бесплатную расшифровку, что она означает — подпишись на канал Life Code:",
            reply_markup=kb
        )


@dp.callback_query(F.data == "check_sub")
async def recheck_subscription(callback: CallbackQuery, state: FSMContext):
    is_subscribed = await check_subscription(callback.from_user.id)
    if is_subscribed:
        data = await state.get_data()
        life_number = data.get("life_number")
        if life_number:
            await callback.message.delete()
            await send_number_card(callback.message.chat.id, life_number)
        else:
            await callback.message.answer("Что-то пошло не так, напиши /start ещё раз.")
    else:
        await callback.answer("Пока не вижу подписку — попробуй ещё раз через пару секунд.", show_alert=True)


async def check_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception as e:
        logging.warning(f"Subscription check failed: {e}")
        return False


async def send_number_card(chat_id: int, life_number: int):
    image_path = os.path.join(IMAGES_DIR, f"number_{life_number}.jpg")
    bot_username = (await bot.me()).username
    share_link = f"https://t.me/{bot_username}"
    caption = (
        f"Твоя Цифра Я = <b>{life_number}</b>\n\n"
        "Она формирует твою жизнь.\n\n"
        "А как именно она работает? Как прийти к жизни мечты, лёгкости и деньгам — "
        f"узнаешь здесь: {PAID_CALCULATOR_URL}\n\n"
        "Один раз узнаёшь. Пользуешься всю жизнь.\n\n"
        f"Перешли эту ссылку близкому человеку — пусть тоже узнает свою цифру: {share_link}"
    )
    if os.path.exists(image_path):
        photo = FSInputFile(image_path)
        await bot.send_photo(chat_id=chat_id, photo=photo, caption=caption)
    else:
        await bot.send_message(chat_id=chat_id, text=caption)


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

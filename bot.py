import asyncio
import logging
import os
from html import escape

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message
from dotenv import load_dotenv

import db
from prices import PriceNotFound, get_product, to_number

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL_MINUTES", 60))
PROXY = os.getenv("PROXY")
if PROXY and "://" not in PROXY:
    PROXY = "http://" + PROXY

dp = Dispatcher()

HELP_TEXT = (
    "Слежу за ценами и пишу, когда цена падает до нужной.\n\n"
    "/add <ссылка> <цена> - добавить товар\n"
    "/list - мои товары\n"
    "/del <номер> - удалить товар\n"
    "/check - проверить цены прямо сейчас\n\n"
    "Пример:\n/add https://books.toscrape.com/catalogue/sharp-objects_997/index.html 50"
)


def format_price(value):
    return f"{value:,.2f}".replace(",", " ").replace(".00", "")


@dp.message(CommandStart())
@dp.message(Command("help"))
async def cmd_start(message: Message):
    await message.answer(HELP_TEXT, parse_mode=None)


@dp.message(Command("add"))
async def cmd_add(message: Message, command: CommandObject):
    parts = (command.args or "").split()
    if len(parts) != 2 or not parts[0].startswith("http"):
        await message.answer("Формат: /add <ссылка> <цена>", parse_mode=None)
        return

    url, target = parts[0], to_number(parts[1])
    if target is None:
        await message.answer("Не понял цену, напиши числом, например 1500")
        return

    await message.answer("Смотрю товар...")
    try:
        title, price = await get_product(url)
    except PriceNotFound:
        await message.answer("Не получилось найти цену на этой странице")
        return
    except Exception as e:
        logging.warning("add %s: %s", url, e)
        await message.answer("Страница не открылась, проверь ссылку")
        return

    item_id = db.add_item(message.chat.id, url, title, target, price)
    text = (
        f"Добавил под номером {item_id}\n"
        f"<b>{escape(title)}</b>\n"
        f"Сейчас: {format_price(price)}, жду: {format_price(target)}"
    )
    await message.answer(text)
    if price <= target:
        await message.answer("Кстати, цена уже ниже нужной 👆")
        db.update_item(item_id, price, notified=True)


@dp.message(Command("list"))
async def cmd_list(message: Message):
    items = db.get_items(message.chat.id)
    if not items:
        await message.answer("Список пуст. Добавить: /add <ссылка> <цена>", parse_mode=None)
        return
    lines = []
    for item in items:
        mark = "✅" if item["notified"] else "⏳"
        lines.append(
            f"{mark} {item['id']}. <a href=\"{escape(item['url'])}\">{escape(item['title'])}</a>\n"
            f"    сейчас {format_price(item['last_price'])}, жду {format_price(item['target_price'])}"
        )
    await message.answer("\n".join(lines), disable_web_page_preview=True)


@dp.message(Command("del"))
async def cmd_delete(message: Message, command: CommandObject):
    if not command.args or not command.args.strip().isdigit():
        await message.answer("Формат: /del <номер из /list>", parse_mode=None)
        return
    if db.delete_item(message.chat.id, int(command.args)):
        await message.answer("Удалил")
    else:
        await message.answer("Нет такого номера, посмотри /list")


@dp.message(Command("check"))
async def cmd_check(message: Message, bot: Bot):
    items = db.get_items(message.chat.id)
    if not items:
        await message.answer("Проверять нечего")
        return
    await message.answer("Проверяю...")
    found = await check_prices(bot, items)
    if found:
        return
    already = sum(1 for item in db.get_items(message.chat.id) if item["notified"])
    if already:
        await message.answer(f"Новых снижений нет. Ниже нужной цены уже: {already} (писал раньше, см. /list)")
    else:
        await message.answer("Пока ничего не подешевело до нужной цены")


@dp.message(F.text)
async def unknown(message: Message):
    await message.answer("Не понял. Список команд: /help")


async def check_prices(bot, items):
    found = 0
    for item in items:
        try:
            _, price = await get_product(item["url"])
        except Exception as e:
            logging.warning("check %s: %s", item["url"], e)
            continue

        below = price <= item["target_price"]
        if below and not item["notified"]:
            found += 1
            await bot.send_message(
                item["chat_id"],
                f"🔥 Цена упала!\n<b>{escape(item['title'])}</b>\n"
                f"Было {format_price(item['last_price'])}, стало {format_price(price)} "
                f"(ждали {format_price(item['target_price'])})\n{escape(item['url'])}",
            )
        db.update_item(item["id"], price, notified=below)
        await asyncio.sleep(1)
    return found


async def checker(bot):
    while True:
        await asyncio.sleep(CHECK_INTERVAL * 60)
        items = db.get_items()
        logging.info("Плановая проверка, товаров: %s", len(items))
        await check_prices(bot, items)


async def main():
    if not BOT_TOKEN:
        print("Не задан BOT_TOKEN. Создай файл .env по примеру .env.example")
        return
    db.init_db()
    session = AiohttpSession(proxy=PROXY) if PROXY else None
    bot = Bot(BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    asyncio.create_task(checker(bot))
    logging.info("Бот запущен, проверка каждые %s мин.", CHECK_INTERVAL)
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(main())

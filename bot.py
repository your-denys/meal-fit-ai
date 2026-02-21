import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import BOT_TOKEN, GEMINI_API_KEY
from database import init_db
from handlers import common, food, stats, profile, quick
from reminders import reminder_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

def check_config():
    """Проверка обязательных переменных перед запуском."""
    if not BOT_TOKEN or BOT_TOKEN.strip() == "":
        print("Ошибка: не задан BOT_TOKEN. Добавь его в файл .env")
        print("Пример: BOT_TOKEN=123456:ABC-DEF...")
        sys.exit(1)
    if not GEMINI_API_KEY or GEMINI_API_KEY.strip() == "":
        print("Предупреждение: GEMINI_API_KEY не задан. Распознавание по фото работать не будет.")
    return True

log_updates = logging.getLogger("updates")

async def log_updates_middleware(handler, event, data):
    """Логировать каждое входящее обновление — видно, что бот получает сообщения."""
    update = event
    if getattr(update, "message", None):
        msg = update.message
        text = (msg.text or msg.caption or "[фото/другое]")[:60]
        log_updates.info("→ msg от %s: %s", msg.from_user.id, text)
    elif getattr(update, "callback_query", None):
        cq = update.callback_query
        log_updates.info("→ callback от %s: %s", cq.from_user.id, cq.data)
    return await handler(event, data)

async def main():
    check_config()
    init_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.outer_middleware(log_updates_middleware)

    # Сначала профиль, статистика, быстрые кнопки — потом общий обработчик текста (еда)
    dp.include_router(common.router)
    dp.include_router(profile.router)
    dp.include_router(stats.router)
    dp.include_router(quick.router)
    dp.include_router(food.router)

    # Убедиться, что вебхук снят (иначе getUpdates не придёт)
    await bot.delete_webhook(drop_pending_updates=True)
    webhook = await bot.get_webhook_info()
    if webhook.url:
        log_updates.warning("Был вебхук %s — снят. Если бот задеплоен на сервере, останови его.", webhook.url)
    me = await bot.get_me()
    print("", flush=True)
    print("  Бот запущен:", f"@{me.username}", flush=True)
    print("  В Telegram найди именно этого бота (@%s) и напиши: /start" % me.username, flush=True)
    print("  Если бот задеплоен на Render/другом сервере — останови там, иначе сообщения туда уходят.", flush=True)
    print("  Остановка: Ctrl+C", flush=True)
    print("", flush=True)

    async def log_waiting():
        """Раз в 20 сек напоминать, что ждём сообщения — в терминале не тихо."""
        while True:
            await asyncio.sleep(20)
            log_updates.info("Ждём сообщения... (напиши /start боту @%s в Telegram)", me.username)

    asyncio.create_task(log_waiting())
    asyncio.create_task(reminder_loop(bot))
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nБот остановлен.")
    except Exception as e:
        logging.exception("Критическая ошибка при запуске: %s", e)
        sys.exit(1)

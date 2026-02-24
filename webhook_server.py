"""
Точка входа для Render (и других PaaS): webhook вместо polling.
Telegram шлёт обновления на HTTPS URL — сервис просыпается только при запросах, UptimeRobot не нужен.
"""
import asyncio
import logging
import os
import sys

from aiohttp import web

from config import WEBHOOK_BASE_URL, WEBHOOK_SECRET
from bot import setup_bot_dp, log_updates, reminder_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

PORT = int(os.environ.get("PORT", 8080))


async def health(request: web.Request) -> web.Response:
    """GET / — для проверки, что сервис жив (Render, браузер)."""
    return web.Response(text="FitMeal AI bot is alive!", content_type="text/plain")


async def create_app() -> web.Application:
    """Создать бота и диспетчер до старта сервера, зарегистрировать webhook handler."""
    bot, dp = await setup_bot_dp()

    url = f"{WEBHOOK_BASE_URL}/webhook"
    await bot.set_webhook(
        url,
        secret_token=WEBHOOK_SECRET,
        drop_pending_updates=True,
    )
    log_updates.info("Webhook установлен: %s", url)

    me = await bot.get_me()
    log_updates.info("Бот запущен (webhook): @%s", me.username)

    app = web.Application()
    app["bot"] = bot
    app["dp"] = dp

    app.router.add_get("/", health)

    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

    webhook_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        handle_in_background=True,
        secret_token=WEBHOOK_SECRET,
    )
    webhook_handler.register(app, path="/webhook")
    setup_application(app, dp)

    async def start_reminders(app: web.Application) -> None:
        app["reminder_task"] = asyncio.create_task(reminder_loop(bot))

    async def stop_reminders(app: web.Application) -> None:
        if "reminder_task" in app:
            app["reminder_task"].cancel()
            try:
                await app["reminder_task"]
            except asyncio.CancelledError:
                pass

    app.on_startup.append(start_reminders)
    app.on_shutdown.append(stop_reminders)

    return app


async def main() -> None:
    if not WEBHOOK_BASE_URL or not WEBHOOK_BASE_URL.startswith("https://"):
        print(
            "Ошибка: задай WEBHOOK_BASE_URL в .env (HTTPS URL сервиса, "
            "например https://meal-fit-ai-xxx.onrender.com)"
        )
        sys.exit(1)

    print("", flush=True)
    print(f"  Webhook-сервер на 0.0.0.0:{PORT}", flush=True)
    print(f"  URL: {WEBHOOK_BASE_URL}/webhook", flush=True)
    print("  UptimeRobot не нужен — сервис просыпается при запросах от Telegram.", flush=True)
    print("", flush=True)

    app = await create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"  Слушаем порт {PORT}. Остановка: Ctrl+C", flush=True)
    print("", flush=True)
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nСервер остановлен.")
    except Exception as e:
        logging.exception("Ошибка: %s", e)
        sys.exit(1)

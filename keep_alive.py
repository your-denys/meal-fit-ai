"""
Точка входа для Render: HTTP-сервер на PORT (для пингов UptimeRobot) + бот в главном потоке.
Render отдаёт трафик на PORT; внешний сервис пингует URL раз в 5–10 мин — сервис не засыпает.
"""
import os
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = int(os.environ.get("PORT", 8080))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"FitMeal AI bot is alive!")

    def log_message(self, format, *args):
        pass

    def log_error(self, format, *args):
        pass


def run_http():
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    t = threading.Thread(target=run_http, daemon=True)
    t.start()
    print(f"Keep-alive HTTP on 0.0.0.0:{PORT}")

    from bot import main
    asyncio.run(main())

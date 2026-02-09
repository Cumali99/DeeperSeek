"""
Пример: запрос к DeepSeek и озвучка ответа.

По умолчанию: авто-вход по DEEPSEEK_EMAIL + DEEPSEEK_PASSWORD или DEEPSEEK_TOKEN из .env.
Ручной вход: MANUAL_LOGIN=1 — откроется окно Chrome, войдите вручную, скрипт продолжит после загрузки чата.
Веб-поиск: SEARCH=1 — перед отправкой включается переключатель «Поиск» (запрос к gator.volces.com и т.д.).

Запуск: source .venv/bin/activate && python examples/chat_and_speak.py
В .env: ELEVENLABS_API_KEY=..., DEEPSEEK_EMAIL, DEEPSEEK_PASSWORD (или DEEPSEEK_TOKEN).
"""
import asyncio
import os
import sys
from pathlib import Path

# Подставить корень репозитория в PYTHONPATH, если пакет не установлен (pip install -e .)
_repo_root = Path(__file__).resolve().parent.parent
if _repo_root not in (Path(p).resolve() for p in sys.path):
    sys.path.insert(0, str(_repo_root))

try:
    from dotenv import load_dotenv
    load_dotenv(_repo_root / ".env")
except ImportError:
    pass

from DeeperSeek import DeepSeek, play_audio, CONCISE_NO_FLUFF
from DeeperSeek.internal.exceptions import InvalidCredentials

# Ручной вход: MANUAL_LOGIN=1 — открыть браузер и ждать, пока вы войдёте вручную.
MANUAL_LOGIN = os.environ.get("MANUAL_LOGIN", "0").lower() in ("1", "true", "yes")
DEEPSEEK_EMAIL = os.environ.get("DEEPSEEK_EMAIL", "")
DEEPSEEK_PASSWORD = os.environ.get("DEEPSEEK_PASSWORD", "")
TOKEN = os.environ.get("DEEPSEEK_TOKEN", "")
VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"
CHROME_PATH = os.environ.get("CHROME_PATH", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
HEADLESS = os.environ.get("HEADLESS", "1").lower() not in ("0", "false", "no")
# Веб-поиск: SEARCH=1 — перед отправкой включается переключатель «Поиск», ответ может содержать результаты поиска.
USE_SEARCH = os.environ.get("SEARCH", "0").lower() in ("1", "true", "yes")


async def main():
    if not MANUAL_LOGIN and not TOKEN and not (DEEPSEEK_EMAIL and DEEPSEEK_PASSWORD):
        print("Задайте в .env: DEEPSEEK_EMAIL и DEEPSEEK_PASSWORD, или DEEPSEEK_TOKEN, или MANUAL_LOGIN=1.")
        return
    api = DeepSeek(
        token=TOKEN or None,
        email=DEEPSEEK_EMAIL or None,
        password=DEEPSEEK_PASSWORD or None,
        headless=HEADLESS,
        verbose=True,
        browser_executable_path=CHROME_PATH,
        chrome_args=["--no-sandbox", "--disable-dev-shm-usage"],
        attempt_cf_bypass=False,
        manual_login=MANUAL_LOGIN,
        message_prefix=CONCISE_NO_FLUFF,
    )
    try:
        await api.initialize()
    except InvalidCredentials:
        await api.close()
        print(
            "Неверный логин/пароль или токен. Проверьте DEEPSEEK_EMAIL, DEEPSEEK_PASSWORD или DEEPSEEK_TOKEN в .env.\n"
            "С видимым браузером: HEADLESS=0 python examples/chat_and_speak.py"
        )
        raise
    try:
        question = "Как сегодня погода в Анталии? Ответ не должен превышать 10 символов"
        print(f"Отправляю: {question}" + (" (веб-поиск включён)" if USE_SEARCH else ""))
        response = await api.send_message(question, timeout=60 + (60 if USE_SEARCH else 0), search=USE_SEARCH)
        if not response:
            print("Ответ не получен (таймаут или ошибка)")
            return
        print(f"Ответ: {response.text[:200]}...")
        if USE_SEARCH and response.search_results:
            print(f"Веб-поиск: найдено {len(response.search_results)} результатов.")

        print("Озвучиваю...")
        audio = await api.text_to_speech(
            response.text,
            voice_id=VOICE_ID,
            output_path="reply.mp3",
        )
        play_audio(audio)
        print("Готово. Файл: reply.mp3")
    finally:
        await api.close()


if __name__ == "__main__":
    asyncio.run(main())

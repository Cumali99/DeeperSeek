# DeeperSeek Documentation

A Python library made for interacting with DeepSeek.

# Getting started
Make sure you install [Chrome](https://www.google.com/chrome/) or [Chromium](https://www.chromium.org/) before using this library, as it uses `zendriver` to bypass Cloudflare's anti-bot protection, which requires Chrome/Chromium to be installed. 

# Installation

Requires **Python 3.10+** (zendriver).

### macOS with Homebrew (recommended: use a venv)

Homebrew’s Python is “externally managed”, so install into a virtual environment:

```sh
cd /path/to/DeeperSeek
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .   # установить пакет DeeperSeek из репозитория
```

Or run the script: `bash scripts/setup_venv.sh`, then `source .venv/bin/activate`.

### Other systems (Windows / Linux where pip is allowed)
```sh
# Windows
pip install DeeperSeek -U

# Linux/macOS (if not using Homebrew Python)
pip3 install DeeperSeek -U
```

### Headless Linux Servers
```sh
# Install Chromium & X virtual framebuffer
sudo apt install chromium-browser xvfb
pip3 install DeeperSeek -U
```

### Google Colab
```sh
# Install dependencies
!apt install chromium-browser xvfb
!pip install -U selenium_profiles DeeperSeek
```
```py
# Install chromedriver
from selenium_profiles.utils.installer import install_chromedriver
install_chromedriver()
```

# Initialization

You can initialize the class in two ways, either by using a session token or by using an email and password.

Create an instance of `DeepSeek`:
```py
from DeeperSeek import DeepSeek

api = DeepSeek(
    email = "YOUR_EMAIL",
    password = "YOUR_PASSWORD",
    token = "YOUR_SESSION_TOKEN",
    chat_id = "YOUR_CHAT_ID",  # Optional, could be None
    chrome_args = [],
    verbose = False,
    headless = True,
    attempt_cf_bypass = True,
)

await api.initialize()  # Necessary to initialize the class, must be called before using other methods
```

# Parameters

- `email (Optional[str])`: The email to use for logging in. Defaults to `None`.
- `password (Optional[str])`: The password to use for logging in. Defaults to `None`.
- `token (Optional[str])`: The `userToken` cookie from https://chat.deepseek.com/. Defaults to `None`. If you don't have or use a token, you **need** to use the email and password to log in.
- `chat_id (Optional[str])`: The chat ID. Defaults to `None`.
    - To obtain a chat ID, click on any chat, then take the part of the URL that comes after `https://chat.deepseek.com/a/chat/s/`
        - Example: The chat ID in the URL `https://chat.deepseek.com/a/chat/s/6hs721c22-c4f3-42w22-8788-a39eb21413bb` is `6hs721c22-c4f3-42w22-8788-a39eb21413bb`.
- `verbose (bool)`: Whether to print debug messages or not. Defaults to `False`.
- `headless (bool)`: Whether to run Chrome in headless mode or not. Defaults to `True`.
- `chrome_args (list)`: The Chrome arguments to use. Defaults to `[]`.
- `attempt_cf_bypass (bool)`: Whether to attempt to bypass Cloudflare protection or not. Defaults to `True`.

# Obtaining the session token

1. Go to https://chat.deepseek.com/ and open the developer tools by clicking `F12`.
2. Head over to `Application` > `Local Storage` > `https://chat.deepseek.com`.
3. Scroll down till you find `userToken`, click on it, a preview will show up beneath it, right-click on the line that contains `value` and click `Copy value`.

![image](https://raw.githubusercontent.com/theAbdoSabbagh/DeeperSeek/refs/heads/main/docs/assets/guide.png)

## DeepSeek Methods

### Remember to initialize the class first!
```py
from DeeperSeek import DeepSeek
api = DeepSeek(...)
```
### Sending a message
```py
response = await api.send_message(
    "Hey DeepSeek!",
    deepthink = True,  # Whether to use the DeepThink option or not
    search = False,  # Whether to use the Search option or not
    slow_mode = True,  # Whether to send the message in slow mode or not
    slow_mode_delay = 0.25,  # The delay between each character when sending the message in slow mode
    timeout = 60,  # The time to wait for the response before timing out
)  # Returns a Response object
print(response.text, response.deepthink_duration, response.deepthink_content)
```
### Regenerating the last response
```py
response = await api.regenerate_response(
    timeout = 60  # Time to wait for the message to regenerate before timing out.
)  # Regenerates the last response sent by DeepSeek. Returns a Response object
print(response.text)
```
### Resetting the chat
```py
await api.reset_chat()
```
### Logging out
```py
await api.logout()
```
### Retrieving the session token
```py
token = await api.retrieve_token()
print("Session Token:", token)
```
### Switching accounts
```py
await api.switch_account(token = "new_token")
# or
await api.switch_account(email = "new_email", password = "new_password")
```
### Deleting all chat history
```py
await api.delete_chats()
```
### Switching to a different chat
```py
await api.switch_chat("chat_id_here")
```
### Changing the chat theme
```py
from DeeperSeek import Theme
await api.switch_theme(Theme.DARK)
```

### Полный цикл: запрос и озвучка ответа

1. **Запуск** — из корня репозитория, с активированным venv:
   ```sh
   source .venv/bin/activate
   python examples/chat_and_speak.py
   ```

2. **Подготовка**
   - Токен DeepSeek: https://chat.deepseek.com/ → F12 → Application → Local Storage → `userToken` → скопировать значение. Вписать в скрипт в `TOKEN` или в `.env` как `DEEPSEEK_TOKEN=...`.
   - ElevenLabs: ключ в `.env` (`ELEVENLABS_API_KEY`) или передать `api_key` в `text_to_speech`.

3. **Что делает скрипт**: создаёт сессию DeepSeek → отправляет сообщение → получает ответ → озвучивает через ElevenLabs и воспроизводит в системном плеере, сохраняет в `reply.mp3`.

В коде вручную тот же цикл:
```py
import asyncio
from DeeperSeek import DeepSeek, play_audio

async def main():
    api = DeepSeek(token="ВАШ_ТОКЕН", headless=True)
    await api.initialize()
    response = await api.send_message("Ваш вопрос", timeout=60)
    if response:
        audio = await api.text_to_speech(response.text, voice_id="JBFqnCBsd6RMkjVDRZzb", output_path="reply.mp3")
        play_audio(audio)

asyncio.run(main())
```

### Text-to-Speech (ElevenLabs)
Convert response text to speech using ElevenLabs (model: Eleven Flash v2.5 by default). Requires an [ElevenLabs API key](https://elevenlabs.io/app/settings/api-keys) and a voice ID ([list voices](https://elevenlabs.io/docs/api-reference/get-voices)). Set `ELEVENLABS_API_KEY` in the environment or pass `api_key` to the call.

```py
# After getting a response
response = await api.send_message("Hello!")
audio = await api.text_to_speech(
    response.text,
    voice_id="JBFqnCBsd6RMkjVDRZzb",  # Example voice; use your preferred voice_id
    output_path="reply.mp3",  # Optional: save to file
)
# audio is bytes (MP3 by default)

# Play in system default player (no extra deps)
from DeeperSeek import play_audio
play_audio(audio)
```

Standalone (without a DeepSeek instance):
```py
from DeeperSeek import text_to_speech

audio = await text_to_speech(
    "Text to speak",
    voice_id="JBFqnCBsd6RMkjVDRZzb",
    api_key="your_api_key",  # or set ELEVENLABS_API_KEY
    output_path="out.mp3",
)
```

## Frequently Asked Questions
- Why use this project instead of DeepSeek's official API?
    - This project is open-source, and you can use it for free. DeepSeek's official API is closed-source, and you have to pay to use it. In addition, this project has more features than DeepSeek's official API.

- Why not just run DeepSeek on my own machine?
  - You could do that since it's open source. But for some people, this may be a better option. For me, it is, so I created this project.

- What can I do with this project?
    - You can use this project to create your own chatbot or automate your chats on https://chat.deepseek.com/. The possibilities are endless.

- How do I suggest a feature?
    - You can suggest a feature by creating an issue [here](https://github.com/theAbdoSabbagh/DeeperSeek/issues). Please make sure that the feature you are suggesting is not already implemented.

- How do I report a bug?
    - You can report a bug by creating an issue [here](https://github.com/theAbdoSabbagh/DeeperSeek/issues). Please make sure that you are using the latest version of the library before reporting a bug. Also, please make sure that the bug you are reporting has not been reported before.

- Is this project affiliated with DeepSeek?
    - No, this project is not affiliated with DeepSeek in any way.

- Is this project safe to use?
    - Yes, this project is safe to use. However, as with the nature of all similar projects to this one, this is a use-at-your-own-risk project. I am not responsible for any damage caused by this project.

- Will this project be maintained?
    - Yes, as long as it is useful to me and is used by others, I will maintain this project.

## Closing Thoughts
This project is solely maintained by me, and I maintain this project and its dependencies in my free time. If you like this project, please consider starring it on GitHub.

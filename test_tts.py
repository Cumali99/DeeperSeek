import asyncio
from DeeperSeek import text_to_speech, play_audio


async def main():
    audio = await text_to_speech(
        "Привет! Это тест озвучки.",
        voice_id="JBFqnCBsd6RMkjVDRZzb",
        output_path="test.mp3",
    )
    play_audio(audio)
    print("Готово: test.mp3")


if __name__ == "__main__":
    asyncio.run(main())

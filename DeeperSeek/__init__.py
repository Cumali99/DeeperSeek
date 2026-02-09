"""
An unofficial Python wrapper for DeepSeek API
"""

from DeeperSeek.DeeperSeek import DeepSeek
from DeeperSeek.internal.objects import *
from DeeperSeek.internal.exceptions import *
from DeeperSeek.internal.tts import text_to_speech, play_audio, play_audio_file
from DeeperSeek.internal.prompts import CONCISE_NO_FLUFF

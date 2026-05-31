"""Quick voice comparison test for MiniMax TTS."""
import sys
sys.path.insert(0, "src")

from src.providers.tts.minimax_tts import MinimaxTTSProvider
from src.utils.config import load_config

LINES = [
    "大家好，欢迎收看今天的科技快报。今天我们聊三件大事。",
    "OpenAI 发布了最新模型，号称能自我纠错，但社区测试发现它依然会一本正经地胡说八道。",
]

VOICES = [
    ("female-shaonv", "少女"),
    ("Chinese (Mandarin)_News_Anchor", "新闻女声"),
]

config = load_config()

for voice_id, label in VOICES:
    for i, text in enumerate(LINES):
        config_copy = {**config, "tts": {**config["tts"], "voice_id": voice_id}}
        provider = MinimaxTTSProvider(config_copy)
        out = f"data/voice_test/{voice_id}_{i+1}.mp3"
        print(f"[{label}] Synthesizing: {text[:20]}...")
        result = provider.synthesize(text, out)
        print(f"  -> {out}  ({result.duration:.1f}s)")

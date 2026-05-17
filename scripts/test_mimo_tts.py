"""Test script for Mimo TTS provider — exercises different emotions, voices, and parameters.

Usage:
    uv run python scripts/test_mimo_tts.py              # all tests
    uv run python scripts/test_mimo_tts.py --emotion warm  # single emotion
    uv run python scripts/test_mimo_tts.py --list          # list available emotions/voices
"""

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Ensure project root is on sys.path so `src` imports work
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.providers.tts.mimo_tts import MimoTTSProvider, _EMOTION_MAP

_OUTPUT_DIR = _PROJECT_ROOT / "data" / "tts_test_output"


SAMPLE_TEXTS = {
    "opening": "欢迎收看HN TechPulse，今天是每日科技新闻播报。",
    "dashboard": "本期榜单第一名：OpenAI发布全新推理模型，在多项基准测试中超越GPT-5。",
    "story": "DeepMind团队本周在《自然》杂志上发表了一项突破性研究，展示了一种全新的蛋白质折叠预测算法，将准确率提升到了前所未有的99.8%。社区对此反应热烈，有研究者认为这将是结构生物学的分水岭时刻。",
    "controversy": "Rust社区近日就async trait的未来方向展开激烈讨论。支持者认为这将是异步编程的重要里程碑，而反对者则担心复杂度会失控。",
    "closing": "以上就是今天的全部内容，感谢收看HN TechPulse，我们明天再见。",
}


def parse_args():
    parser = argparse.ArgumentParser(description="Test Mimo TTS provider")
    parser.add_argument(
        "--emotion",
        choices=list(_EMOTION_MAP.keys()),
        help="Test only this emotion",
    )
    parser.add_argument(
        "--text",
        choices=list(SAMPLE_TEXTS.keys()),
        default="story",
        help="Text sample to use",
    )
    parser.add_argument(
        "--voice",
        default="Chloe",
        help="Voice name",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="Temperature (0-2)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available emotions and voices, then exit",
    )
    parser.add_argument(
        "--voices",
        nargs="+",
        default=None,
        help="Voices to test in full concat (default: Chloe Echo Iris Sage Hazel)",
    )
    parser.add_argument(
        "--keep-wav",
        action="store_true",
        help="Keep intermediate WAV files",
    )
    return parser.parse_args()


def list_options():
    print("Available emotions:")
    for name, desc in _EMOTION_MAP.items():
        print(f"  {name}: {desc}")
    print("\nAvailable text samples:")
    for name, text in SAMPLE_TEXTS.items():
        print(f"  {name}: {text}")


def test_one(
    provider: MimoTTSProvider,
    text: str,
    output_path: str,
    emotion: str | None = None,
    label: str = "",
) -> bool:
    print(f"\n{'='*60}")
    print(f"Testing: {label}")
    print(f"  emotion: {emotion or 'none (default tone)'}")
    print(f"  text: {text[:60]}{'...' if len(text) > 60 else ''}")
    print(f"  output: {output_path}")

    try:
        result = provider.synthesize(text, output_path, emotion=emotion)
        size_kb = Path(output_path).stat().st_size / 1024
        print(f"  SUCCESS — duration: {result.duration:.2f}s, size: {size_kb:.1f} KB")
        return True
    except Exception as e:
        print(f"  FAILED — {type(e).__name__}: {e}")
        return False


def test_emotions(provider: MimoTTSProvider, text: str, keep_wav: bool = False):
    print("\n" + "=" * 60)
    print("EMOTION SWEEP")
    print("=" * 60)

    results = {}
    for emotion, _desc in _EMOTION_MAP.items():
        output_path = str(_OUTPUT_DIR / f"emotion_{emotion}.mp3")
        ok = test_one(provider, text, output_path, emotion=emotion, label=f"emotion={emotion}")
        results[emotion] = ok

    print(f"\nEmotion sweep summary: {sum(results.values())}/{len(results)} passed")
    for em, ok in results.items():
        print(f"  {em}: {'OK' if ok else 'FAIL'}")


def test_text_samples(provider: MimoTTSProvider, keep_wav: bool = False):
    print("\n" + "=" * 60)
    print("TEXT SAMPLE SWEEP (neutral emotion)")
    print("=" * 60)

    results = {}
    for name, text in SAMPLE_TEXTS.items():
        output_path = str(_OUTPUT_DIR / f"text_{name}.mp3")
        ok = test_one(provider, text, output_path, emotion="neutral", label=f"text={name}")
        results[name] = ok

    print(f"\nText sample sweep summary: {sum(results.values())}/{len(results)} passed")
    for name, ok in results.items():
        print(f"  {name}: {'OK' if ok else 'FAIL'}")


_CONCAT_ORDER = ["opening", "dashboard", "story", "controversy", "closing"]
# Mimo available voices — Chinese only (for a Chinese broadcast)
_VOICE_POOL = ["冰糖", "茉莉", "苏打", "白桦"]


def test_full_concat(provider: MimoTTSProvider, voices: list[str] | None = None):
    print("\n" + "=" * 60)
    print("FULL CONCATENATED TEXT (voice × emotion sweep)")
    print("=" * 60)

    segments = [SAMPLE_TEXTS[k] for k in _CONCAT_ORDER]
    full_text = "\n\n".join(segments)
    print(f"  total chars: {len(full_text)}")

    voices = voices or _VOICE_POOL
    emotions = ("neutral", "energetic", "warm")

    results = {}
    for voice in voices:
        provider.voice = voice
        for emotion in emotions:
            output_path = str(_OUTPUT_DIR / f"full_{voice}_{emotion}.mp3")
            label = f"voice={voice} emotion={emotion}"
            ok = test_one(provider, full_text, output_path, emotion=emotion, label=label)
            results[(voice, emotion)] = ok

    print(f"\nFull concat summary: {sum(results.values())}/{len(results)} passed")
    for (voice, emotion), ok in results.items():
        print(f"  {voice} + {emotion}: {'OK' if ok else 'FAIL'}")


def test_temperatures(provider: MimoTTSProvider, text: str):
    print("\n" + "=" * 60)
    print("TEMPERATURE SWEEP")
    print("=" * 60)

    results = {}
    for temp in [0.0, 0.2, 0.5, 1.0]:
        provider.temperature = temp
        output_path = str(_OUTPUT_DIR / f"temp_{temp}.mp3")
        ok = test_one(provider, text, output_path, emotion="neutral", label=f"temperature={temp}")
        results[temp] = ok

    print(f"\nTemperature sweep summary: {sum(results.values())}/{len(results)} passed")
    for temp, ok in results.items():
        print(f"  t={temp}: {'OK' if ok else 'FAIL'}")


def main():
    args = parse_args()

    if args.list:
        list_options()
        return

    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    provider = MimoTTSProvider(
        config={
            "tts": {
                "voice": args.voice,
                "temperature": args.temperature,
            }
        },
        debug=True,
    )

    print("Provider: MimoTTSProvider")
    print(f"  base_url: {provider.base_url}")
    print(f"  model: {provider.model}")
    print(f"  voice: {provider.voice}")
    print(f"  temperature: {provider.temperature}")
    print(f"  sample_rate: {provider.sample_rate}")
    print(f"  output dir: {_OUTPUT_DIR}")

    text = SAMPLE_TEXTS[args.text]

    if args.emotion:
        output_path = str(_OUTPUT_DIR / f"single_{args.emotion}.mp3")
        ok = test_one(provider, text, output_path, emotion=args.emotion, label=f"emotion={args.emotion}")
        sys.exit(0 if ok else 1)
    else:
        # test_emotions(provider, text, args.keep_wav)
        # test_text_samples(provider, args.keep_wav)
        # test_temperatures(provider, text)
        test_full_concat(provider, voices=args.voices)
        print(f"\nAll output files in: {_OUTPUT_DIR}")


if __name__ == "__main__":
    main()

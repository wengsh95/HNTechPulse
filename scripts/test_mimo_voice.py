"""MIMO TTS 音色 × 情绪 组合测试脚本。

使用与项目一致的 prompt 生成音频，方便试听对比。

运行方式:
    uv run python scripts/test_mimo_voice.py
    uv run python scripts/test_mimo_voice.py --voices 茉莉,冰糖 --emotions warm,upbeat
    uv run python scripts/test_mimo_voice.py --text "自定义文本"
"""

import argparse
import base64
import os
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# ── 与项目一致的 prompt ──
_DEFAULT_TONE = "你是《HN TechPulse》中文科技播报主持人。声音清亮磁性，语速中等偏快，咬字清晰饱满，专业沉稳有亲和力。遇到英文专有名词（如 Claude、Anthropic、MCP、REST API 等）必须用标准英文发音读出，不要用中文语调拼读字母。"

_STYLE_TAG = "(咬字清晰 发音饱满 沉稳 专业 英文专有名词用标准英文发音)"

_EMOTION_MAP = {
    "warm": "用温暖亲切的语气播报，声音明亮温和。",
    "energetic": "用活力充沛的语调播报，语速稍快，声音明亮有劲。",
    "neutral": "用沉稳中性的语调播报，客观冷静，重音落在关键信息上。",
    "upbeat": "用轻快上扬的语调播报，对技术亮点带有兴奋感。",
    "calm": "用从容平和的语气播报，语速稍慢，娓娓道来。",
}

# ── 默认测试文本 ──
DEFAULT_TEXT = (
    "今天的技术圈格外热闹。OpenAI 发布了 Claude 4 系列模型，性能提升显著，但定价也水涨船高。"
    "与此同时，Anthropic 宣布 MCP 协议正式进入 1.0 阶段，REST API 接口全面重构。"
    "开源社区对此褒贬不一，Hacker News 上的讨论帖已经积累了超过 500 条评论。"
    "有人欢呼进步，认为 AGI 的到来又近了一步；也有人担忧 Big Tech 的垄断正在加剧。"
    "GitHub 的 Star 数显示，LangChain 项目本周新增了 3000 多个 Star，而 LlamaIndex 只增加了 800。"
    "Python 和 TypeScript 依然是最热门的 AI 开发语言，Rust 的增长势头也不容小觑。"
)

# 中文预置音色（女声）
VOICES = {
    "冰糖": "冰糖",
    "茉莉": "茉莉",
}

OUTPUT_DIR = Path("tmp/mimo_voice_test")


def get_client() -> OpenAI:
    api_key = os.environ.get("MIMO_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("错误: 请设置 MIMO_API_KEY 或 OPENAI_API_KEY 环境变量")
        sys.exit(1)
    return OpenAI(
        api_key=api_key,
        base_url="https://api.xiaomimimo.com/v1",
    )


def build_user_message(emotion: str) -> str:
    """构建与项目一致的 user message。"""
    emotion_hint = _EMOTION_MAP.get(emotion, "")
    if emotion_hint:
        return (
            _DEFAULT_TONE
            + "\n\n"
            + _STYLE_TAG
            + "\n\n本段播报的情绪要求："
            + emotion_hint
        )
    else:
        return _DEFAULT_TONE + "\n\n" + _STYLE_TAG


def synthesize(client: OpenAI, text: str, voice: str, emotion: str, output_path: Path):
    """合成单个音频文件。"""
    messages = [
        {"role": "user", "content": build_user_message(emotion)},
        {"role": "assistant", "content": text},
    ]

    completion = client.chat.completions.create(
        model="mimo-v2.5-tts",
        messages=messages,
        audio={"format": "pcm16", "voice": voice},
        stream=True,
        temperature=0.3,
    )

    collected: list[np.ndarray] = []
    for chunk in completion:
        if not chunk.choices:
            continue
        audio = getattr(chunk.choices[0].delta, "audio", None)
        if audio and isinstance(audio, dict):
            pcm_bytes = base64.b64decode(audio["data"])
            np_pcm = (
                np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            )
            collected.append(np_pcm)

    if not collected:
        print(f"  WARNING: 无音频数据: {voice} + {emotion}")
        return False

    full_audio = np.concatenate(collected)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output_path), full_audio, samplerate=24000)
    return True


def main():
    parser = argparse.ArgumentParser(description="MIMO TTS 音色×情绪组合测试")
    parser.add_argument("--text", default=DEFAULT_TEXT, help="测试文本")
    parser.add_argument("--voices", default=None, help="音色列表，逗号分隔 (冰糖,茉莉)")
    parser.add_argument(
        "--emotions",
        default=None,
        help="情绪列表，逗号分隔 (warm,energetic,neutral,upbeat,calm)",
    )
    args = parser.parse_args()

    voices = args.voices.split(",") if args.voices else list(VOICES.keys())
    emotions = args.emotions.split(",") if args.emotions else list(_EMOTION_MAP.keys())

    # 验证参数
    for v in voices:
        if v not in VOICES:
            print(f"错误: 未知音色 '{v}'，可选: {', '.join(VOICES.keys())}")
            sys.exit(1)
    for e in emotions:
        if e not in _EMOTION_MAP:
            print(f"错误: 未知情绪 '{e}'，可选: {', '.join(_EMOTION_MAP.keys())}")
            sys.exit(1)

    client = get_client()
    total = len(voices) * len(emotions)
    print(f"开始生成 {total} 个音频 ({len(voices)} 音色 x {len(emotions)} 情绪)")
    print(f"文本: {args.text[:50]}...")
    print(f"输出目录: {OUTPUT_DIR}")
    print()

    count = 0
    for voice in voices:
        for emotion in emotions:
            count += 1
            filename = f"{voice}_{emotion}.wav"
            output_path = OUTPUT_DIR / filename
            sys.stdout.write(f"[{count}/{total}] {voice} + {emotion} ... ")
            sys.stdout.flush()

            ok = synthesize(client, args.text, voice, emotion, output_path)
            if ok:
                sys.stdout.write(f"OK -> {output_path}\n")
                sys.stdout.flush()

    print()
    print(f"完成！共生成 {count} 个音频文件")
    print(f"目录: {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()

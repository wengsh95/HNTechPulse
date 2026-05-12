#!/usr/bin/env python3
"""
HN Fetcher 最小单元测试脚本

用于逐层验证爬虫各环节是否正常，快速定位问题。

用法:
  python test_fetcher.py                      # 运行全部测试
  python test_fetcher.py --step connect        # 仅测连通性
  python test_fetcher.py --step story          # 仅测 Story 详情
  python test_fetcher.py --step comments       # 仅测评论抓取
  python test_fetcher.py --step comments --id 47892074   # 测试指定 Story
  python test_fetcher.py --step all            # 全部（含评论）
  python test_fetcher.py --debug               # DEBUG 级别日志
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.config import load_config
from src.utils.logger import setup_logger


def step_connect(fetcher, args):
    print(f"\n{'='*60}")
    print("[1] 连通性测试 — 获取 Top Stories ID 列表")
    print(f"{'='*60}")

    has_proxy = fetcher._session.proxies if hasattr(fetcher, '_session') else None
    if not has_proxy:
        print(f"  ⚠ 未配置代理")
        print(f"  当前超时: {fetcher.request_timeout} (connect, read) 秒")
        print()

    t0 = time.monotonic()
    try:
        ids = fetcher._fetch_top_stories()
        elapsed = time.monotonic() - t0

        print(f"  ✓ 成功！获取到 {len(ids)} 个 ID")
        print(f"  前 5 个: {ids[:5]}")
        print(f"  耗时: {elapsed:.2f}s")

        if not args.id and len(ids) > 0:
            args.default_story_id = ids[0]

        return True, elapsed
    except KeyboardInterrupt:
        print(f"\n  ✗ 用户中断 (耗时 {time.monotonic() - t0:.1f}s)")
        return False, time.monotonic() - t0
    except Exception as e:
        elapsed = time.monotonic() - t0
        err_type = type(e).__name__
        if "Timeout" in err_type or "timeout" in str(e).lower():
            print(f"  ✗ 请求超时 ({elapsed:.1f}s): {err_type}")
            print("    → 尝试在 config.yaml 中启用代理 (hn.proxy)")
        elif "Connection" in err_type or "ssl" in str(e).lower():
            print(f"  ✗ 连接错误 ({elapsed:.1f}s): {err_type}: {e}")
            print("    → 建议配置代理")
        else:
            print(f"  ✗ 失败: {err_type}: {e}")
        return False, elapsed


def step_story(fetcher, args):
    print(f"\n{'='*60}")
    print("[2] Story 详情测试")
    print(f"{'='*60}")

    story_id = args.id or getattr(args, "default_story_id", None)
    if not story_id:
        print("  ✗ 无可用 story_id，请用 --id <id> 指定，或先运行 --step connect")
        return False, 0.0

    has_proxy = fetcher._session.proxies if hasattr(fetcher, '_session') else None
    if not has_proxy:
        print(f"  ⚠ 未配置代理，直连 hacker-news.firebaseio.com 可能较慢或超时")
        print(f"    当前超时设置: {fetcher.request_timeout} (connect, read) 秒")
        print(f"    如需代理，请在 config.yaml 中取消注释 hn.proxy")
        print()

    t0 = time.monotonic()
    try:
        stories = asyncio.run(
            fetcher._async_fetch_stories([story_id])
        )
        elapsed = time.monotonic() - t0

        if not stories:
            print(f"  ⚠ id={story_id} 返回 None (可能已删除/非 story 类型)")
            return False, elapsed

        story = stories[0]
        from src.providers.fetcher.models import HNStory
        assert isinstance(story, HNStory)

        print(f"  ✓ id={story.id}")
        print(f"  标题: {story.title[:80]}{'...' if len(story.title) > 80 else ''}")
        print(f"  URL: {story.url or '(Text-only post)'}")
        print(f"  score={story.score}  comments={story.descendants}")
        print(f"  by={story.by or '?'}")
        print(f"  耗时: {elapsed:.3f}s")

        return True, elapsed
    except KeyboardInterrupt:
        print(f"\n  ✗ 用户中断 (耗时 {time.monotonic() - t0:.1f}s)")
        print("    提示: 如果经常卡住，请检查网络或配置代理")
        return False, time.monotonic() - t0
    except Exception as e:
        elapsed = time.monotonic() - t0
        err_type = type(e).__name__
        if "Timeout" in err_type or "timeout" in str(e).lower():
            print(f"  ✗ 请求超时 ({elapsed:.1f}s): {err_type}: {e}")
            print("    → 尝试: 1) 在 config.yaml 中启用代理  2) 增大 request_timeout")
        elif "Connection" in err_type or "SSLError" in err_type or "ssl" in str(e).lower():
            print(f"  ✗ 连接/SSL 错误 ({elapsed:.1f}s): {err_type}: {e}")
            print("    → 建议: 在 config.yaml 中配置代理 (hn.proxy)")
        else:
            print(f"  ✗ 失败 ({elapsed:.1f}s): {err_type}: {e}")
        return False, elapsed


def step_comments(fetcher, args):
    print(f"\n{'='*60}")
    print("[3] 评论抓取测试")
    print(f"{'='*60}")

    story_id = args.id or getattr(args, "default_story_id", None)
    if not story_id:
        print("  ✗ 无可用 story_id，请用 --id <id> 指定，或先运行 --step connect")
        return False, 0.0

    try:
        stories = asyncio.run(
            fetcher._async_fetch_stories([story_id])
        )
        expected = stories[0].descendants if stories else 0
    except Exception:
        expected = 0

    print(f"  目标: story_id={story_id}  预期评论数≈{expected}")
    print(f"  日志间隔: 每 {fetcher.comment_log_interval} 条输出一次进度")
    print(f"  最大深度: {fetcher.max_comment_depth}")
    print(f"  并发数: {fetcher.max_concurrent_requests}")
    print()

    t0 = time.monotonic()
    try:
        comments = asyncio.run(
            fetcher._async_fetch_all_story_comments_standalone(story_id, expected)
        )
        elapsed = time.monotonic() - t0

        rate = len(comments) / elapsed if elapsed > 0 else 0

        print()
        print(f"  ✓ 完成！实际获取 {len(comments)} 条评论")
        if expected > 0:
            print(f"  预期≈{expected}  达成率={len(comments)/expected*100:.1f}%")
        print(f"  总耗时: {elapsed:.1f}s  平均速率: {rate:.1f}条/s")

        if comments:
            print(f"\n  --- 前 3 条评论预览 ---")
            for i, c in enumerate(comments[:3], start=1):
                text_preview = c.text[:80].replace("\n", " ")
                if len(c.text) > 80:
                    text_preview += "..."
                print(f"  [{i}] by={c.author or '?'}  text={text_preview}")

        return True, elapsed
    except KeyboardInterrupt:
        print(f"\n  ✗ 用户中断 (已运行 {time.monotonic() - t0:.1f}s)")
        return False, time.monotonic() - t0
    except Exception as e:
        elapsed = time.monotonic() - t0
        err_type = type(e).__name__
        if "Timeout" in err_type or "timeout" in str(e).lower():
            print(f"\n  ✗ 请求超时 ({elapsed:.1f}s): {err_type}: {e}")
            print("    → 评论抓取需要大量 API 调用，建议配置代理以加速")
        elif "Connection" in err_type or "ssl" in str(e).lower():
            print(f"\n  ✗ 连接/SSL 错误 ({elapsed:.1f}s): {err_type}: {e}")
            print("    → 建议在 config.yaml 中启用代理 (hn.proxy)")
        else:
            print(f"\n  ✗ 失败: {err_type}: {e}")
        print(f"  已运行时间: {elapsed:.1f}s")
        return False, time.monotonic() - t0


def main():
    parser = argparse.ArgumentParser(description="HN Fetcher 最小单元测试")
    parser.add_argument(
        "--step",
        type=str,
        default="all",
        choices=["all", "connect", "story", "comments"],
        help="测试哪个环节"
    )
    parser.add_argument("--id", type=int, default=None, help="指定 story ID (story/comments)")
    parser.add_argument("--config", type=str, default="config/", help="配置文件目录或路径")
    parser.add_argument("--debug", action="store_true", help="DEBUG 日志级别")
    args = parser.parse_args()

    config = load_config(args.config)

    log_level = "DEBUG" if args.debug else "INFO"
    logger = setup_logger("test_fetcher", level=log_level)
    logger.info(f"[test] 配置文件: {args.config}")
    logger.info(f"[test] 测试环节: {args.step}")
    logger.info(f"[test] 日志级别: {log_level}")

    from src.providers.fetcher.hn_fetcher import HNFetcher
    fetcher = HNFetcher(config, debug=args.debug, log_level=log_level)

    hn_cfg = config.get("hn", {})
    print("\n┌─ 当前爬虫配置 ───────────────────────────┐")
    print(f"│ base_url      : {hn_cfg.get('base_url', '(default)')}")
    print(f"│ timeout       : {fetcher.request_timeout}")
    print(f"│ proxy         : {hn_cfg.get('proxy', '未配置')}")
    print(f"│ log_interval  : {fetcher.comment_log_interval}")
    print(f"│ top_count     : {hn_cfg.get('top_stories_count', 100)}")
    print(f"│ target_count  : {hn_cfg.get('target_stories_count', 10)}")
    print(f"│ max_depth     : {fetcher.max_comment_depth}")
    print(f"│ concurrency   : {fetcher.max_concurrent_requests}")
    print(f"│ max_retries   : {fetcher.max_retries}")
    print(f"│ granular_cache: {fetcher.granular_cache}")
    print("└──────────────────────────────────────────┘")

    results = {}
    total_t0 = time.monotonic()

    steps_to_run = []
    if args.step == "all":
        steps_to_run = ["connect", "story", "comments"]
    else:
        steps_to_run = [args.step]

    for step_name in steps_to_run:
        if step_name == "connect":
            ok, elapsed = step_connect(fetcher, args)
        elif step_name == "story":
            ok, elapsed = step_story(fetcher, args)
        elif step_name == "comments":
            ok, elapsed = step_comments(fetcher, args)
        else:
            continue
        results[step_name] = (ok, elapsed)

    total_elapsed = time.monotonic() - total_t0

    print(f"\n{'='*60}")
    print("汇总:")
    print(f"{'='*60}")
    all_ok = True
    for name, (ok, elapsed) in results.items():
        status = "✓ PASS" if ok else "✗ FAIL"
        print(f"  [{status}] {name:<12s}  {elapsed:.2f}s")
        if not ok:
            all_ok = False

    print(f"  {'':12s}  ─────────")
    print(f"  {'TOTAL':12s}  {total_elapsed:.2f}s")
    print()

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())

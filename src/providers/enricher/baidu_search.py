import logging

import aiohttp

from src.utils.config import get_env


class BaiduSearchProvider:
    """百度 AI 搜索 —— 调用千帆平台 Web Search API 获取全网信息。"""

    BASE_URL = "https://qianfan.baidubce.com/v2/ai_search/web_search"

    def __init__(self, config: dict):
        self.logger = logging.getLogger("hn_techpulse.baidu_search")
        cfg = config.get("enrich", {}).get("baidu_search", {})

        self.enabled = cfg.get("enabled", False)
        self.top_k = cfg.get("top_k", 5)
        self.search_recency_filter = cfg.get("search_recency_filter")
        self.request_timeout = cfg.get("request_timeout", 15)

        self.api_key = get_env("BAIDU_API_KEY")
        if self.enabled and not self.api_key:
            self.logger.warning(
                "Baidu search enabled but BAIDU_API_KEY not set, disabling"
            )
            self.enabled = False

    async def search(self, query: str) -> list[dict]:
        """搜索并返回结果列表，每项包含 title/url/content。失败返回空列表。"""
        if not self.enabled or not self.api_key:
            return []

        payload = {
            "messages": [{"content": query, "role": "user"}],
            "search_source": "baidu_search_v2",
            "resource_type_filter": [{"type": "web", "top_k": self.top_k}],
        }
        if self.search_recency_filter:
            payload["search_recency_filter"] = self.search_recency_filter

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        try:
            timeout = aiohttp.ClientTimeout(total=self.request_timeout)
            async with aiohttp.ClientSession(
                headers=headers, timeout=timeout, trust_env=True
            ) as session:
                async with session.post(self.BASE_URL, json=payload) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        self.logger.warning(
                            f"Baidu search returned {resp.status}: {text[:200]}"
                        )
                        return []
                    data = await resp.json()
        except aiohttp.ClientError as e:
            self.logger.warning(f"Baidu search request failed: {e}")
            return []
        except Exception as e:
            self.logger.warning(f"Baidu search error: {e}")
            return []

        references = data.get("references", [])
        if not references:
            return []

        results = []
        for ref in references:
            results.append(
                {
                    "title": ref.get("title", ""),
                    "url": ref.get("url", ""),
                    "content": ref.get("content", ""),
                }
            )
        self.logger.debug(
            f"Baidu search returned {len(results)} results for: {query[:60]}"
        )
        for i, r in enumerate(results, 1):
            self.logger.debug(
                f"  [{i}] {r['title'][:80]}\n"
                f"      url: {r['url']}\n"
                f"      content: {r['content'][:200]}"
            )
        return results

    @staticmethod
    def format_results(results: list[dict]) -> str:
        """将搜索结果格式化为 prompt 文本。"""
        if not results:
            return ""
        lines = ["## 网络搜索补充信息", ""]
        for i, r in enumerate(results, 1):
            title = r.get("title", "")
            content = r.get("content", "")
            url = r.get("url", "")
            lines.append(f"### 搜索结果 {i}")
            lines.append(f"标题：{title}")
            lines.append(f"摘要：{content}")
            if url:
                lines.append(f"来源：{url}")
            lines.append("")
        return "\n".join(lines)

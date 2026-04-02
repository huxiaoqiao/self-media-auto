import os
import json
from typing import List, Dict

def get_latest_context(topic_title, raw_content):
    """
    1. Extract new tech keywords from title and content
    2. Search using Tavily API for those keywords
    3. Return a combined summary of latest context string
    """
    try:
        import openai
    except ImportError:
        print("⚠️ 未安装 openai，跳过搜索增强。")
        return ""

    client = openai.OpenAI(
        api_key=os.getenv("OPENAI_API_KEY", ""),
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    )

    if not client.api_key:
        print("⚠️ 缺少 OPENAI_API_KEY，跳过搜索增强。")
        return ""

    prompt = f"""请从以下文章内容中，提取出可能是最新发布的 AI 工具、新技术名词、专有名词（例如：OpenClaude，DeepSeek-V3 等）。
你的任务仅仅是发现"可能会被大模型旧知识库搞错的新名词"。
如果没有这类新名词，请直接回复 "NONE"。
如果发现有，请以逗号分隔的形式仅仅返回这些名词（最多返回 2 个最重要的核心词）。
不要输出任何其他内容。

标题：{topic_title}
内容前 1000 字：{raw_content[:1000]}"""
    try:
        resp = client.chat.completions.create(
             model=os.getenv("LLM_MODEL_ID", "deepseek-chat"),
             messages=[{"role": "user", "content": prompt}],
             temperature=0.1,
             max_tokens=50
        )
        keywords_text = resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"⚠️ 提取关键词失败：{e}")
        return ""

    if not keywords_text or "NONE" in keywords_text.upper() or len(keywords_text) > 100:
        return ""

    keywords = [k.strip() for k in keywords_text.split(',') if k.strip()]
    if not keywords:
        return ""

    context_results = []
    print(f"🔍 识别到可能的新术语：{keywords}，正在执行全网搜索 (Tavily RAG)...")

    # 尝试使用 Tavily API
    tavily_api_key = os.getenv("TAVILY_API_KEY")
    if tavily_api_key:
        try:
            from tavily import TavilyClient
            tavily_client = TavilyClient(tavily_api_key)

            for kw in keywords[:2]:
                try:
                    response = tavily_client.search(query=f"{kw} 最新进展", search_depth="advanced")
                    results = response.get('results', [])
                    if results:
                        snippets = []
                        for r in results[:3]:
                            snippet = f"- {r.get('title', '')}: {r.get('content', '')} (来源：{r.get('source', '未知')})"
                            snippets.append(snippet)
                        context_results.append(f"有关【{kw}】的最新网络检索信息：\n" + "\n".join(snippets))
                except Exception as e:
                    print(f"⚠️ Tavily 搜索【{kw}】时出错：{e}")
        except ImportError:
            print("⚠️ 未安装 tavily 库，降级使用 DuckDuckGo 搜索...")
            _search_duckduckgo(keywords, context_results)
        except Exception as e:
            print(f"⚠️ Tavily 搜索失败：{e}，降级使用 DuckDuckGo 搜索...")
            _search_duckduckgo(keywords, context_results)
    else:
        print("⚠️ 未配置 TAVILY_API_KEY，使用 DuckDuckGo 搜索...")
        _search_duckduckgo(keywords, context_results)

    if context_results:
         return "\n\n".join(context_results)
    return ""


def _search_duckduckgo(keywords: List[str], context_results: List[str]):
    """降级搜索：使用 DuckDuckGo"""
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            for kw in keywords[:2]:
                try:
                    results = list(ddgs.text(kw + " 最新进展", max_results=3))
                    if results:
                        snippets = [r.get('body', '') for r in results]
                        context_results.append(f"有关【{kw}】的最新网络检索信息：\n" + "\n".join(snippets))
                except Exception as e:
                    print(f"⚠️ 搜索【{kw}】时出错：{e}")
    except Exception as e:
        print(f"⚠️ DuckDuckGo 搜索组件启动失败：{e}")


if __name__ == "__main__":
    test_title = "OpenClaude 终于发布了，震撼全场"
    test_content = "昨天硅谷发布了一款名为 OpenClaude 的全新推理模型，它比之前的模型更强大……"
    print("测试结果:")
    print(get_latest_context(test_title, test_content))

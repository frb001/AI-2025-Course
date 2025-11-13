from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import TextMentionTermination
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_core.memory import ListMemory
from autogen_agentchat.ui import Console
from autogen_core.tools import FunctionTool
import asyncio
import json

def common_search(query: str, num_results: int = 2, max_chars: int = 500) -> list:  # type: ignore[type-arg]
    import os
    import time

    import requests
    from bs4 import BeautifulSoup
    from dotenv import load_dotenv

    load_dotenv()

    api_key = os.getenv("Task_API_KEY")
    # search_engine_id = os.getenv("GOOGLE_SEARCH_ENGINE_ID")

    '''if not api_key or not search_engine_id:
        raise ValueError("API key or Search Engine ID not found in environment variables")'''

    url = "https://api.bochaai.com/v1/web-search"

    # 构建请求数据
    payload = json.dumps({
        "query": query,
    })

    # 设置请求头
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }

    # 发送请求
    response = requests.post(url, headers=headers, data=payload)

    # 检查响应状态
    if response.status_code != 200:
        raise Exception(f"搜索请求失败: {response.status_code} - {response.text}")

    results = response.json()['data']["webPages"]["value"]

    def get_page_content(url: str) -> str:
        try:
            response = requests.get(url, timeout=10)
            soup = BeautifulSoup(response.content, "html.parser")
            text = soup.get_text(separator=" ", strip=True)
            words = text.split()
            content = ""
            for word in words:
                if len(content) + len(word) + 1 > max_chars:
                    break
                content += " " + word
            return content.strip()
        except Exception as e:
            print(f"Error fetching {url}: {str(e)}")
            return ""

    enriched_results = []
    for item in results:
        body = get_page_content(item["url"])
        enriched_results.append(
            {"title": item["name"], "link": item["url"], "snippet": item["snippet"], "body": body}
        )
        time.sleep(1)  # Be respectful to the servers

    return enriched_results


def create_analysis_agent(model_client: OpenAIChatCompletionClient, memory: ListMemory):
    # model_client = OpenAIChatCompletionClient(model="deepseek-chat", api_key="sk-d9820c8127c8428e9ee59a01fcd8e116", base_url="https://api.deepseek.com/v1")
    common_search_tool = FunctionTool(
        common_search, description="Search Google for information, returns results with a snippet and body content"
    )

    search_agent = AssistantAgent(
        name="Task_Analysis_Agent",
        model_client=model_client,
        tools=[common_search_tool],
        memory=[memory],
        description="搜索符合用户所描述的特征的股票名称",
        system_message="你是一个任务解析智能体，你需要根据用户所描述的股票特征，搜索出符合的股票名称，不需要其他信息和文字。",
    )
    return search_agent


async def main():  # 1. 包成异步函数
    '''search_result = common_search("123")
    print(search_result)'''
    search_agent = create_analysis_agent()
    result = await search_agent.run(task="搜索今天a股股价最高的白酒企业的股票")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())

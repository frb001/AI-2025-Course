from autogen_agentchat.ui import Console
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_core.memory import ListMemory
from autogen_core.models import ModelFamily
from autogen_agentchat.base import TaskResult
import os
from dotenv import load_dotenv
import asyncio
import taskanalysis_agent
import output_agent
import search_agent
import plotting_agent
import report_agent


# 异步运行团队测试
async def test_team():
    load_dotenv()
    #代理设置，检索股票信息时必须使用魔法上网，端口根据各自的设备设置，在.env中修改。
    proxy = f"http://127.0.0.1:{os.getenv('Proxy_Port')}" 
    os.environ['HTTP_PROXY'] = proxy
    os.environ['HTTPS_PROXY'] = proxy
    # Define a model client. You can use other model client that implements
    # the `ChatCompletionClient` interface.
    model_client = OpenAIChatCompletionClient(
        model="deepseek-chat",
        base_url="https://api.deepseek.com",
        api_key=os.getenv("Deepseek_API_KEY"),
        model_info={
            "vision": False,
            "function_calling": True,
            "json_output": True,
            "family": ModelFamily.R1,
            "structured_output": True
        }
    )
    # 创建团队记忆体，用于保持上下文
    team_memory = ListMemory()
    #创建各个智能体
    TaskAnalysisAgent = taskanalysis_agent.create_analysis_agent(model_client, team_memory)
    SearchAgent = search_agent.create_search_agent(model_client, team_memory)
    PlottingAgent = plotting_agent.create_plotting_agent(model_client, team_memory)
    ReportAgent = report_agent.create_report_agent(model_client, team_memory)
    OutputAgent = output_agent.create_output_agent(model_client, team_memory)
    # 创建团队
    agent_team = RoundRobinGroupChat([TaskAnalysisAgent, SearchAgent, PlottingAgent, ReportAgent, OutputAgent], max_turns=5)
    eg_task = "搜索港股昨天市值最高的科技类股票的名称，并进行分析"
    """    
    stream = agent_team.run_stream(task=eg_task)
    await Console(stream=stream)
    await model_client.close()"""
    async for message in agent_team.run_stream(task=eg_task):
        if isinstance(message, TaskResult):
            print(f"流程终止，终止原因：{message.stop_reason}")
        else:
            print(message)
            print(f"信息来源：{message.source}")
            print(f"信息类型：{message.type}")
            print()
#异步正式运行函数
async def main():
    print("启动多智能体股票分析系统……初始化中")
    load_dotenv()
    #代理设置，检索股票信息时必须使用魔法上网，端口根据各自的设备设置，在.env中修改。
    proxy = f"http://127.0.0.1:{os.getenv('Proxy_Port')}" 
    os.environ['HTTP_PROXY'] = proxy
    os.environ['HTTPS_PROXY'] = proxy
    # Define a model client. You can use other model client that implements
    # the `ChatCompletionClient` interface.
    model_client = OpenAIChatCompletionClient(
        model="deepseek-chat",
        base_url="https://api.deepseek.com",
        api_key=os.getenv("Deepseek_API_KEY"),
        model_info={
            "vision": False,
            "function_calling": True,
            "json_output": True,
            "family": ModelFamily.R1,
            "structured_output": True
        }
    )
    # 创建团队记忆体，用于保持上下文
    team_memory = ListMemory()
    # 创建各个智能体
    TaskAnalysisAgent = taskanalysis_agent.create_analysis_agent(model_client, team_memory)
    SearchAgent = search_agent.create_search_agent(model_client, team_memory)
    PlottingAgent = plotting_agent.create_plotting_agent(model_client, team_memory)
    ReportAgent = report_agent.create_report_agent(model_client, team_memory)
    OutputAgent = output_agent.create_output_agent(model_client, team_memory)
    # 创建团队
    agent_team = RoundRobinGroupChat([TaskAnalysisAgent, SearchAgent, PlottingAgent, ReportAgent, OutputAgent], max_turns=5)
    print("初始化完成……请输入需要执行的指令")
    command = input()
    stream = agent_team.run_stream(task=command)
    await Console(stream=stream)
    await model_client.close()


if __name__ == "__main__":
    # asyncio.run(test_team())
    asyncio.run(main())
# 顶部导入区域
import json
import uuid
import time
from typing import Dict, Any, Generator

from flask import Flask, request, jsonify, Response, stream_with_context, send_file
import os
import queue
import threading
import asyncio
from dotenv import load_dotenv
import taskanalysis_agent
import search_agent
import plotting_agent
import report_agent
import output_agent
from autogen_agentchat.ui import Console
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_core.memory import ListMemory
from autogen_core.models import ModelFamily
from autogen_agentchat.base import TaskResult
from flask import send_from_directory

app = Flask(__name__)

# 简易内存任务表（占位）
TASKS: Dict[str, Dict[str, Any]] = {}

# massage queue 使用队列库
# 任务队列
MSG_QUEUES: Dict[str, queue.Queue] = {}


def sse_event(event_name: str, data: Dict[str, Any]) -> str:
    """格式化 SSE 事件"""
    return f"event: {event_name}\n" + f"data: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@app.route("/api/tasks", methods=["POST"])
def create_task():
    """创建任务（不实现具体业务，仅返回 taskId）"""
    try:
        payload = request.get_json(force=True, silent=False) or {}
    except Exception:
        return jsonify({"error": "invalid request body"}), 400

    task_text = (payload.get("task") or "").strip()
    if not task_text:
        return jsonify({"error": "task is required"}), 400

    task_id = str(uuid.uuid4())
    TASKS[task_id] = {
        "id": task_id,
        "task": task_text,
        "status": "created",
        "created_at": int(time.time()),
        # 可在此扩展：agents 队列、上下文、用户信息等
    }
    return jsonify({"taskId": task_id}), 200


@app.route("/", methods=["GET"])
def index():
    return send_file(os.path.join(os.path.dirname(__file__), "front.html"))


@app.route("/api/tasks/<task_id>/stream", methods=["GET"])
def stream_task(task_id: str):
    """任务 SSE 流"""
    if task_id not in TASKS:
        return jsonify({"error": "task not found"}), 404

    # 任务消息队列与工作线程
    MSG_QUEUES[task_id] = queue.Queue()
    work_thread = threading.Thread(target=run_agent_worker, args=(task_id,), daemon=True)
    work_thread.start()

    # 将后端 agent 源名称映射到前端事件名
    SOURCE_TO_EVENT = {
        "Task_Analysis_Agent": "taskAgent",
        "Search_Agent": "searchAgent",
        "Plotting_Agent": "chartAgent",
        "Report_Agent": "commentAgent",
        "Output_Agent": "commentAgent",
        "OutputAgent": "commentAgent",  # 兼容你日志中的来源名
    }
    @stream_with_context
    def generate() -> Generator[str, None, None]:
        print(f"start stream task {task_id}")
        while True:
            message = MSG_QUEUES[task_id].get()
            if message is None:
                break  # 正确结束流
            src = getattr(message, "source", "")
            content = getattr(message, "content", None)
            print(f"get message {src}")

            event_name = SOURCE_TO_EVENT.get(src)

            # 专门处理 Plotting_Agent 返回的结构体：优先使用 plot_file_path
            if event_name == "chartAgent" and isinstance(content, dict):
                path_val = content.get("plot_file_path") or content.get("plot_path")
                if path_val:
                    try:
                        # 规范化为绝对路径
                        abs_path = path_val
                        if not os.path.isabs(abs_path):
                            abs_path = os.path.normpath(os.path.join(os.path.dirname(__file__), abs_path))
                        # 计算相对 output 的子路径，并统一为 URL 斜杠
                        base_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "output"))
                        subpath = os.path.relpath(abs_path, base_dir).replace("\\", "/")
                        image_url = f"/files/{subpath}"
                        yield sse_event("chartAgent", {"status": "运行中", "result": image_url})
                        continue  # 已推送图片 URL，不再重复推送原始内容
                    except Exception as e:
                        print(f"failed to build image url: {e}")

            # 常规分发
            if event_name:
                yield sse_event(event_name, {"status": "运行中", "result": content})
            else:
                yield sse_event("log", {"status": "运行中", "result": str(content)})

        # 收尾事件
        yield sse_event("done", {"message": "所有智能体已完成"})
    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return Response(generate(), headers=headers)

def run_agent_worker(task_id: str):
    # 在线程中运行异步agent
    asyncio.run(agent_work(task_id))

async def agent_work(task_id: str):
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
    try:
        async for message in agent_team.run_stream(task=eg_task):
            if isinstance(message, TaskResult):
                print(f"流程终止，终止原因：{message.stop_reason}")
            else:
                MSG_QUEUES[task_id].put(message)
    finally:
        # 通知SSE生成器结束
        queue_obj = MSG_QUEUES.get(task_id)
        if queue_obj:
            queue_obj.put(None)
        # 可选：清理队列
        # MSG_QUEUES.pop(task_id, None)


@app.route("/files/<path:subpath>", methods=["GET"])
def serve_output_file(subpath: str):
    base_dir = os.path.join(os.path.dirname(__file__), "output")
    return send_from_directory(base_dir, subpath)

if __name__ == "__main__":
    # 可根据需要调整 host/port/debug
    app.run(host="127.0.0.1", port=5000, debug=True)
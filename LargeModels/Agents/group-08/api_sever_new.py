import json
import uuid
import time
import asyncio
import threading
from typing import Dict, Any, Generator
from datetime import datetime
import logging

from flask import Flask, request, jsonify, Response, stream_with_context, send_file
import os
from dotenv import load_dotenv

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__)

# 全局变量
TASKS: Dict[str, Dict[str, Any]] = {}
agent_team = None
model_client = None

# 导入AutoGen相关模块
from autogen_agentchat.ui import Console
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_core.memory import ListMemory
from autogen_core.models import ModelFamily
from autogen_agentchat.base import TaskResult

# 导入智能体模块
import taskanalysis_agent
import output_agent
import search_agent
import plotting_agent
import report_agent


def setup_agents():
    """初始化AutoGen智能体团队"""
    global agent_team, model_client

    try:
        # 代理设置，检索股票信息时必须使用魔法上网，端口根据各自的设备设置，在.env中修改。
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
        agent_team = RoundRobinGroupChat([TaskAnalysisAgent, SearchAgent, PlottingAgent, ReportAgent, OutputAgent],
                                         max_turns=5)
        logger.info("AutoGen智能体团队初始化完成")

    except Exception as e:
        logger.error(f"智能体初始化失败: {e}")
        raise


def sse_event(event_name: str, data: Dict[str, Any]) -> str:
    """格式化 SSE 事件"""
    return f"event: {event_name}\n" + f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.route("/api/tasks", methods=["POST"])
def create_task():
    """创建任务"""
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
        "progress": 0.0,
        "agents_output": [],
        "results": {},
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }

    logger.info(f"创建新任务: {task_id} - {task_text}")

    # 在后台线程中执行任务
    thread = threading.Thread(target=run_analysis_task, args=(task_id, task_text))
    thread.daemon = True
    thread.start()

    return jsonify({"taskId": task_id}), 200


@app.route("/api/tasks/<task_id>", methods=["GET"])
def get_task_status(task_id: str):
    """获取任务状态"""
    if task_id not in TASKS:
        return jsonify({"error": "task not found"}), 404

    return jsonify(TASKS[task_id])


@app.route("/api/tasks/<task_id>/results", methods=["GET"])
def get_task_results(task_id: str):
    """获取任务结果"""
    if task_id not in TASKS:
        return jsonify({"error": "task not found"}), 404

    task = TASKS[task_id]
    if task["status"] != "completed":
        return jsonify({"error": "task not completed"}), 400

    return jsonify(task["results"])


@app.route("/", methods=["GET"])
def index():
    return send_file(os.path.join(os.path.dirname(__file__), "front.html"))


@app.route("/api/tasks/<task_id>/stream", methods=["GET"])
def stream_task(task_id: str):
    """任务 SSE 流（使用真实智能体数据）"""
    if task_id not in TASKS:
        return jsonify({"error": "task not found"}), 404

    @stream_with_context
    def generate() -> Generator[str, None, None]:
        # 连接建立提示
        yield sse_event("progress", {"message": "SSE已连接，等待智能体输出..."})

        # 等待任务开始执行
        start_time = time.time()
        while TASKS[task_id]["status"] == "created" and time.time() - start_time < 30:
            time.sleep(0.5)

        if TASKS[task_id]["status"] == "created":
            yield sse_event("error", {"message": "任务启动超时"})
            return

        # 监听任务进度和智能体输出
        last_agent_count = 0
        last_progress = 0.0

        while TASKS[task_id]["status"] in ["running", "created"]:
            current_task = TASKS[task_id]
            current_progress = current_task.get("progress", 0.0)
            current_agents_output = current_task.get("agents_output", [])

            # 发送进度更新
            if current_progress != last_progress:
                yield sse_event("progress", {
                    "message": f"任务执行中... {current_progress * 100:.1f}%"
                })
                last_progress = current_progress

            # 发送新的智能体输出
            if len(current_agents_output) > last_agent_count:
                new_outputs = current_agents_output[last_agent_count:]
                for output in new_outputs:
                    agent_name = output.get("agent", "Unknown")
                    message = output.get("action", "")
                    message_content = output.get("content", "")

                    # 根据智能体类型发送对应的事件（保持与front.html兼容）
                    if agent_name == "TaskAnalysisAgent":
                        yield sse_event("taskAgent", {
                            "status": "running",
                            "result": message
                        })
                        time.sleep(0.8)
                        if message == "TollCallSummaryMessage":
                            yield sse_event("taskAgent", {
                                "status": "completed",
                                "result": "任务解析完成"
                            })
                    elif agent_name == "SearchAgent":
                        yield sse_event("searchAgent", {
                            "status": "running",
                            "result": message
                        })
                        time.sleep(0.8)
                        if message == "TollCallSummaryMessage":
                            yield sse_event("searchAgent", {
                                "status": "completed",
                                "result": "找到相关股票数据"
                            })
                    elif agent_name == "PlottingAgent":
                        yield sse_event("chartAgent", {
                            "status": "running",
                            "result": message
                        })
                        time.sleep(0.8)
                        if message == "TollCallSummaryMessage":
                            yield sse_event("chartAgent", {
                                "status": "completed",
                                "result": "图表生成完成",
                                "imageUrl": "./frontend_figure.png"
                            })
                    elif agent_name == "ReportAgent" and message == "TextMessage":
                        yield sse_event("commentAgent", {
                            "status": "completed",
                            "fullComment": message_content.content #获取评论智能体的输出评论
                        })
                    elif agent_name == "OutputAgent" and message == "TollCallSummaryMessage":
                        yield sse_event("commentAgent", {
                            "status": "completed"
                        })
                last_agent_count = len(current_agents_output)

            time.sleep(0.5)

        # 任务完成
        if TASKS[task_id]["status"] == "completed":
            yield sse_event("done", {"message": "所有智能体已完成"})
        else:
            yield sse_event("error", {
                "message": f"任务失败: {TASKS[task_id].get('error', 'Unknown error')}"
            })

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return Response(generate(), headers=headers)


def add_agent_output(task_id: str, agent_name: str, message_type: str, message):
    """添加智能体输出到任务记录"""
    if task_id in TASKS:
        output_data = {
            "agent": agent_name,
            "action": message_type,
            "content": message,
            "timestamp": datetime.now().isoformat()
        }
        TASKS[task_id]["agents_output"].append(output_data)
        TASKS[task_id]["updated_at"] = datetime.now().isoformat()


def update_task_progress(task_id: str, progress: float):
    """更新任务进度"""
    if task_id in TASKS:
        TASKS[task_id]["progress"] = progress
        TASKS[task_id]["updated_at"] = datetime.now().isoformat()


def run_analysis_task(task_id: str, task_description: str):
    """在后台线程中运行分析任务"""
    try:
        # 更新任务状态
        TASKS[task_id]["status"] = "running"
        update_task_progress(task_id, 0.1)

        logger.info(f"开始执行任务: {task_id}")

        # 使用真实的AutoGen智能体
        asyncio.run(execute_autogen_team(task_id, task_description))

    except Exception as e:
        logger.error(f"任务 {task_id} 执行失败: {e}")
        TASKS[task_id]["status"] = "failed"
        TASKS[task_id]["error"] = str(e)
        TASKS[task_id]["updated_at"] = datetime.now().isoformat()


async def execute_autogen_team(task_id: str, task_description: str):
    """执行AutoGen团队任务"""
    if agent_team is None:
        raise Exception("智能体团队未初始化")

    try:
        # 初始化任务结果
        final_results = {
            "task_id": task_id,
            "task_description": task_description,
            "agents_output": [],
            "final_result": "",
            "stop_reason": "",
            "completed_at": datetime.now().isoformat()
        }

        # 运行AutoGen团队
        agent_count = 0
        async for message in agent_team.run_stream(task=task_description):
            agent_count += 1

            # 处理消息并记录
            await process_autogen_message(task_id, message, final_results)

            # 更新进度（基于消息数量）
            progress = min(0.9, 0.1 + (agent_count * 0.2))
            update_task_progress(task_id, progress)

            if isinstance(message, TaskResult):
                update_task_progress(task_id, 1.0)
                final_results["final_result"] = str(message)
                final_results["stop_reason"] = message.stop_reason
                break

        # 保存最终结果
        TASKS[task_id]["status"] = "completed"
        TASKS[task_id]["results"] = final_results
        TASKS[task_id]["updated_at"] = datetime.now().isoformat()

        logger.info(f"AutoGen任务 {task_id} 完成")

    except Exception as e:
        logger.error(f"AutoGen任务执行失败: {e}")
        raise


async def process_autogen_message(task_id: str, message, final_results: Dict[str, Any]):
    """处理AutoGen消息"""

    # 确定智能体名称
    agent_name = "Unknown"
    if message.source == "TaskAnalysisAgent" :
        agent_name = "TaskAnalysisAgent"
    elif message.source == "SearchAgent":
        agent_name = "SearchAgent"
    elif message.source == "PlottingAgent":
        agent_name = "PlottingAgent"
    elif message.source == "ReportAgent":
        agent_name = "ReportAgent"
    elif message.source == "OutputAgent":
        agent_name = "OutputAgent"

    message_type = message.type
    # 记录消息
    message_data = {
        "agent": agent_name,
        "message": message,
        "type": message_type,
        "timestamp": datetime.now().isoformat()
    }
    final_results["agents_output"].append(message_data)

    # 添加到任务输出中（用于SSE流）
    add_agent_output(task_id, agent_name, message_type, message)

    logger.info(f"🤖 {agent_name}: {message_type}...")

    # 模拟处理时间
    await asyncio.sleep(0.5)


@app.route("/api/health", methods=["GET"])
def health_check():
    """健康检查端点"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "agent_team_initialized": agent_team is not None,
        "active_tasks": len(TASKS),
        "version": "1.0.0"
    })


# 应用启动时初始化
@app.before_first_request
def initialize():
    """应用启动时初始化智能体"""
    logger.info("初始化AutoGen智能体系统...")
    setup_agents()


if __name__ == "__main__":
    # 初始化智能体
    initialize()

    # 启动Flask应用
    logger.info("启动Flask服务器...")
    app.run(host="127.0.0.1", port=5500, debug=True)

from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_core.memory import ListMemory

def create_report_agent(model_client: OpenAIChatCompletionClient, memory: ListMemory):
    report_agent = AssistantAgent(
        name="Report_Agent",
        model_client=model_client,
        memory=[memory],
        description="Generate a report based the search and results of stock analysis",
        system_message="""你是一个专业的报告整合智能体。
            你的任务是收集来自上游智能体的所有输出，并将它们整合为一份结构清晰、内容全面的最终报告。

            请严格按照以下结构和顺序组织你的报告内容：

            --- 报告开始 ---

            # 股票分析综合报告 - [股票代码，例如 600519.SS]

            ## 1. 任务概述与分析范围
            *   **用户任务:** [原始用户输入任务]
            *   **解析股票:** [Task_Parsing_Agent 解析出的股票代码/名称]
            *   **分析时间范围:** [Task_Parsing_Agent 解析出的时间范围]

            ## 2. 核心数据分析概览
            *   **当前价格:** [Plotting_Agent 输出的 current_price]
            *   **52周高/低点:** [Plotting_Agent 输出的 52_week_high / 52_week_low]
            *   **50日移动平均线:** [Plotting_Agent 输出的 50_day_ma]
            *   **200日移动平均线:** [Plotting_Agent 输出的 200_day_ma]
            *   **年初至今涨跌幅:** [Plotting_Agent 输出的 ytd_percent_change]
            *   **当前趋势:** [Plotting_Agent 输出的 trend]
            *   **年化波动率:** [Plotting_Agent 输出的 volatility]

            ## 3. 市场新闻与相关信息
            *   [Search_Agent 输出的搜索结果摘要，例如：根据搜索，近期市场对白酒行业复苏预期增强，公司三季度业绩预告积极。请简洁总结，不要直接粘贴原始JSON。]
            *   [如果有多条搜索结果，请简洁总结]

            ## 4. 股价走势图
            *   **图表已生成并保存至:** [Plotting_Agent 输出的 plot_file_path]
            *   [可以简要描述图表显示的主要特征，例如：图表显示，该股票在过去一年呈现稳步上涨态势，尤其在九月下旬突破前期阻力位后加速上行。]

            ## 5. 金融评论报告
            [Financial_Comment_Agent 提供的完整格式化评论报告内容]

            ## 6. 免责声明与总结
            *   本报告基于公开数据和技术分析，仅供参考，不构成任何投资建议。
            *   股市有风险，投资需谨慎。
            *   报告生成时间：[当前时间，例如 2023-10-27 10:30:00]

            --- 报告结束 ---

            请确保报告内容准确、专业，并且所有信息都来自上游智能体的输出。
            在生成最终报告后，请回复 TERMINATE。""",
    )
    return report_agent

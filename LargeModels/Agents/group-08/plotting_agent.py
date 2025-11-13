import os
import json
from datetime import datetime, timedelta
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
import numpy as np
import pandas as pd
import yfinance as yf
from pytz import timezone


def analyze_stock(ticker: str) -> dict:
    """
    分析股票数据并生成图表
    
    Args:
        ticker: 股票代码，例如 'AAPL', '0700.HK', '600519.SS'
    
    Returns:
        dict: 包含股票分析结果和图表路径的字典
    """
    try:
        print(f"开始分析股票: {ticker}")
        stock = yf.Ticker(ticker)

        # 获取历史数据（1年的数据以确保有足够数据计算200日移动平均线）
        end_date = datetime.now(timezone("UTC"))
        start_date = end_date - timedelta(days=365)
        hist = stock.history(start=start_date, end=end_date)

        # 确保有数据
        if hist.empty:
            return {"error": f"无法获取股票代码 {ticker} 的历史数据"}

        print(f"获取到 {len(hist)} 天的历史数据")

        # 计算基本统计数据和额外指标
        current_price = stock.info.get("currentPrice", hist["Close"].iloc[-1])
        year_high = stock.info.get("fiftyTwoWeekHigh", hist["High"].max())
        year_low = stock.info.get("fiftyTwoWeekLow", hist["Low"].min())

        # 计算50日和200日移动平均线
        ma_50 = hist["Close"].rolling(window=50).mean().iloc[-1] if len(hist) >= 50 else None
        ma_200 = hist["Close"].rolling(window=200).mean().iloc[-1] if len(hist) >= 200 else None

        # 计算年初至今的涨跌幅
        ytd_start = datetime(end_date.year, 1, 1, tzinfo=timezone("UTC"))
        ytd_data = hist[hist.index >= ytd_start]
        if not ytd_data.empty:
            ytd_start_price = ytd_data["Close"].iloc[0]
            ytd_percent_change = ((current_price - ytd_start_price) / ytd_start_price) * 100
        else:
            ytd_percent_change = 0

        # 计算波动率（年化）
        daily_returns = hist["Close"].pct_change().dropna()
        volatility = daily_returns.std() * np.sqrt(252) * 100  # 年化波动率

        # 确定趋势
        if ma_50 and ma_200:
            if ma_50 > ma_200 and current_price > ma_50:
                trend = "上涨趋势"
            elif ma_50 < ma_200 and current_price < ma_50:
                trend = "下跌趋势"
            else:
                trend = "横盘整理"
        else:
            # 简单趋势判断：比较当前价格与30日前价格
            if len(hist) >= 30:
                price_30_days_ago = hist["Close"].iloc[-30]
                if current_price > price_30_days_ago * 1.05:
                    trend = "上涨趋势"
                elif current_price < price_30_days_ago * 0.95:
                    trend = "下跌趋势"
                else:
                    trend = "横盘整理"
            else:
                trend = "数据不足"

        print("开始生成图表...")

        # 设置中文字体支持
        plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans', 'Arial Unicode MS']
        plt.rcParams['axes.unicode_minus'] = False

        # 创建图表
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
        
        # 绘制价格线
        ax1.plot(hist.index, hist["Close"], label="收盘价", linewidth=2, color='blue')
        
        # 绘制移动平均线
        if ma_50:
            ma_50_series = hist["Close"].rolling(window=50).mean()
            ax1.plot(hist.index, ma_50_series, label="50日移动平均", alpha=0.7, color='orange')
        
        if ma_200:
            ma_200_series = hist["Close"].rolling(window=200).mean()
            ax1.plot(hist.index, ma_200_series, label="200日移动平均", alpha=0.7, color='red')

        ax1.set_title(f"{ticker} 股价走势图", fontsize=16, fontweight='bold')
        ax1.set_ylabel("价格", fontsize=12)
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # 绘制成交量
        ax2.bar(hist.index, hist["Volume"], alpha=0.7, color='gray')
        ax2.set_title("成交量", fontsize=14)
        ax2.set_ylabel("成交量", fontsize=12)
        ax2.set_xlabel("日期", fontsize=12)
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()

        # 保存图表
        output_dir = "./output/charts"
        os.makedirs(output_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        plot_filename = f"{ticker.replace('.', '_')}_{timestamp}.png"
        plot_path = os.path.join(output_dir, plot_filename)
        
        plt.savefig(plot_path, dpi=300, bbox_inches='tight')
        plt.savefig('frontend_figure.png', dpi=300, bbox_inches='tight')
        plt.close()

        print(f"图表已保存到: {plot_path}")

        # 获取公司信息
        try:
            company_name = stock.info.get("longName", ticker)
            sector = stock.info.get("sector", "未知")
            market_cap = stock.info.get("marketCap", "未知")
        except:
            company_name = ticker
            sector = "未知"
            market_cap = "未知"

        # 计算期间涨跌幅（最近3个月）
        three_months_ago = end_date - timedelta(days=90)
        period_data = hist[hist.index >= three_months_ago]
        if not period_data.empty:
            period_start_price = period_data["Close"].iloc[0]
            price_change_percent_period = ((current_price - period_start_price) / period_start_price) * 100
            
            # 计算成交量变化
            recent_volume = period_data["Volume"].tail(30).mean()
            earlier_volume = period_data["Volume"].head(30).mean()
            volume_change_percent = ((recent_volume - earlier_volume) / earlier_volume) * 100 if earlier_volume > 0 else 0
        else:
            price_change_percent_period = 0
            volume_change_percent = 0

        # 计算PE和EPS（如果可用）
        try:
            pe_ratio = stock.info.get("trailingPE", None)
            eps = stock.info.get("trailingEps", None)
        except:
            pe_ratio = None
            eps = None

        # 生成技术分析描述
        chart_description = f"股价走势图显示，{ticker}在过去一年中"
        if trend == "上涨趋势":
            chart_description += "呈现上涨态势，价格在移动平均线上方运行，显示多头力量占据主导。"
        elif trend == "下跌趋势":
            chart_description += "呈现下跌态势，价格在移动平均线下方运行，空头力量较强。"
        else:
            chart_description += "呈现横盘整理态势，价格在移动平均线附近震荡。"

        # 分析日期范围
        date_range = f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"

        # 潜在驱动因素和风险（基于技术分析）
        potential_drivers = []
        potential_risks = []
        
        if trend == "上涨趋势":
            potential_drivers = ["技术指标显示多头趋势", "价格突破关键阻力位", "成交量配合上涨"]
            potential_risks = ["获利回吐压力", "技术指标超买", "市场整体波动"]
        elif trend == "下跌趋势":
            potential_drivers = ["超跌反弹机会", "技术指标接近超卖", "支撑位附近"]
            potential_risks = ["下跌趋势延续", "技术面疲弱", "市场情绪悲观"]
        else:
            potential_drivers = ["整理后方向选择", "技术指标修复", "市场观望情绪"]
            potential_risks = ["方向不明确", "成交量萎缩", "市场缺乏催化剂"]

        # 按照新格式返回分析结果
        result = {
            "company_name": company_name,
            "stock_code": ticker,
            "date_range": date_range,
            "analysis_summary": {
                "price_trend": f"过去一年股价{trend}，当前价格为{current_price}。" + 
                             (f"相比三个月前{'上涨' if price_change_percent_period > 0 else '下跌'}{abs(price_change_percent_period):.1f}%。" 
                              if price_change_percent_period != 0 else ""),
                "key_metrics": {
                    "current_price": round(current_price, 2),
                    "price_change_percent_period": f"{'+' if price_change_percent_period >= 0 else ''}{price_change_percent_period:.1f}%",
                    "volume_change_percent_period": f"{'+' if volume_change_percent >= 0 else ''}{volume_change_percent:.1f}%",
                    "PE_ratio": round(pe_ratio, 1) if pe_ratio else "N/A",
                    "EPS": round(eps, 2) if eps else "N/A",
                    "52_week_high": round(year_high, 2),
                    "52_week_low": round(year_low, 2),
                    "50_day_ma": round(ma_50, 2) if ma_50 else "数据不足",
                    "200_day_ma": round(ma_200, 2) if ma_200 else "数据不足",
                    "volatility": f"{volatility:.1f}%"
                },
                "chart_description": chart_description,
                "potential_drivers": potential_drivers,
                "potential_risks": potential_risks
            },
            "recommendation_from_analyst": f"基于技术分析，当前{trend}，建议{'持有或适量增持' if trend == '上涨趋势' else '谨慎观望' if trend == '横盘整理' else '规避风险'}。",
            "plot_file_path": plot_path,
            "analysis_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data_points": len(hist)
        }

        print("股票分析完成!")
        return result

    except Exception as e:
        error_msg = f"分析股票 {ticker} 时发生错误: {str(e)}"
        print(error_msg)
        return {"error": error_msg, "stock": ticker}



from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_core.memory import ListMemory
from autogen_core.tools import FunctionTool


def create_plotting_agent(model_client=None, memory=None):
    """
    创建制图智能体
    
    Args:
        model_client: 语言模型客户端（如果AutoGen可用）
        memory: 团队记忆实例（如果AutoGen可用）
    
    Returns:
        AssistantAgent实例或简化的字典配置
    """
    if model_client and memory:
        # 创建股票分析工具
        analyze_stock_tool = FunctionTool(
            analyze_stock, 
            description="分析指定股票的价格数据，计算技术指标，并生成包含价格走势和成交量的图表"
        )

        plotting_agent = AssistantAgent(
            name="Plotting_Agent",
            model_client=model_client,
            tools=[analyze_stock_tool],
            memory=[memory],
            description="专业的股票数据分析和图表制作智能体，能够获取股票历史数据、计算技术指标并生成可视化图表",
            system_message="""你是一个专业的股票数据分析和制图智能体。你的主要职责是：

1. **数据分析**: 使用analyze_stock工具获取和分析股票的历史价格数据
2. **技术指标计算**: 计算关键技术指标，包括：
   - 当前价格、52周高低点
   - 50日和200日移动平均线
   - 年初至今涨跌幅
   - 年化波动率
   - 趋势判断

3. **图表生成**: 创建专业的股票分析图表，包含：
   - 价格走势线图
   - 移动平均线
   - 成交量柱状图

4. **结果输出**: 提供结构化的分析结果，包含所有关键数据和图表文件路径

**工作流程**:
- 接收股票代码（如AAPL、0700.HK、600519.SS等）
- 调用analyze_stock工具进行数据分析
- 返回完整的分析结果，包括图表路径和所有计算出的指标

**重要提示**:
- 确保股票代码格式正确（港股加.HK，A股加.SS或.SZ）
- 如果数据获取失败，请提供清晰的错误信息
- 生成的图表文件会保存在./output/charts/目录下
- 所有数值结果保留2位小数

请根据输入的股票代码进行专业的数据分析。""",
        )
        
        return plotting_agent
    else:
        # 返回简化配置
        return {
            "name": "Plotting_Agent",
            "function": analyze_stock,
            "description": "专业的股票数据分析和图表制作智能体",
            "system_message": "进行数据分析。"
        }
from flask import Flask, request, jsonify, send_from_directory, Response
import pywencai
import pandas as pd
import json
import math
from openai import OpenAI

app = Flask(__name__)

DEEPSEEK_KEY = "sk-e9b309fc5854489db866aa27c7bdcb07"
ds_client = OpenAI(api_key=DEEPSEEK_KEY, base_url="https://api.deepseek.com")


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/api/screen", methods=["POST"])
def screen():
    data = request.json
    conditions = []

    # === 盈利指标 ===
    if data.get("revenue_enabled"):
        op = data.get("revenue_op", "大于")
        val = data.get("revenue_val", "50")
        unit = data.get("revenue_unit", "亿")
        conditions.append(f"营业总收入{op}{val}{unit}")

    if data.get("revenue_growth_enabled"):
        op = data.get("revenue_growth_op", "大于")
        val = data.get("revenue_growth_val", "10")
        conditions.append(f"营业总收入同比增长率{op}{val}%")

    if data.get("profit_enabled"):
        op = data.get("profit_op", "大于")
        val = data.get("profit_val", "5")
        unit = data.get("profit_unit", "亿")
        conditions.append(f"扣非净利润{op}{val}{unit}")

    if data.get("profit_growth_enabled"):
        op = data.get("profit_growth_op", "大于")
        val = data.get("profit_growth_val", "10")
        conditions.append(f"扣非净利润同比增长率{op}{val}%")

    if data.get("gross_margin_enabled"):
        gm_min = data.get("gross_margin_min", "30")
        gm_max = data.get("gross_margin_max", "100")
        conditions.append(f"销售毛利率大于{gm_min}%且销售毛利率小于{gm_max}%")

    if data.get("net_margin_enabled"):
        nm_min = data.get("net_margin_min", "10")
        nm_max = data.get("net_margin_max", "100")
        conditions.append(f"销售净利率大于{nm_min}%且销售净利率小于{nm_max}%")

    if data.get("roe_enabled"):
        roe_min = data.get("roe_min", "10")
        roe_max = data.get("roe_max", "100")
        conditions.append(f"净资产收益率大于{roe_min}%且净资产收益率小于{roe_max}%")

    if data.get("eps_enabled"):
        op = data.get("eps_op", "大于")
        val = data.get("eps_val", "1")
        conditions.append(f"每股收益{op}{val}元")

    # === 现金流 ===
    if data.get("cashflow_enabled"):
        cashflow_type = data.get("cashflow_type", "为正")
        conditions.append(f"经营现金流{cashflow_type}")

    # === 估值指标 ===
    if data.get("pe_enabled"):
        pe_min = data.get("pe_min", "0")
        pe_max = data.get("pe_max", "25")
        conditions.append(f"市盈率大于{pe_min}且市盈率小于{pe_max}")

    if data.get("pb_enabled"):
        pb_min = data.get("pb_min", "0")
        pb_max = data.get("pb_max", "3")
        conditions.append(f"市净率大于{pb_min}且市净率小于{pb_max}")

    if data.get("ps_enabled"):
        ps_min = data.get("ps_min", "0")
        ps_max = data.get("ps_max", "10")
        conditions.append(f"市销率大于{ps_min}且市销率小于{ps_max}")

    if data.get("dividend_enabled"):
        op = data.get("dividend_op", "大于")
        val = data.get("dividend_val", "3")
        conditions.append(f"股息率{op}{val}%")

    if data.get("mcap_enabled"):
        mcap_min = data.get("mcap_min", "100")
        mcap_max = data.get("mcap_max", "5000")
        unit = data.get("mcap_unit", "亿")
        conditions.append(f"总市值大于{mcap_min}{unit}且总市值小于{mcap_max}{unit}")

    # === 财务健康 ===
    if data.get("goodwill_enabled"):
        op = data.get("goodwill_op", "小于")
        val = data.get("goodwill_val", "10")
        unit = data.get("goodwill_unit", "亿")
        conditions.append(f"商誉{op}{val}{unit}")

    if data.get("debt_ratio_enabled"):
        dr_min = data.get("debt_ratio_min", "0")
        dr_max = data.get("debt_ratio_max", "60")
        conditions.append(f"资产负债率大于{dr_min}%且资产负债率小于{dr_max}%")

    if data.get("current_ratio_enabled"):
        op = data.get("current_ratio_op", "大于")
        val = data.get("current_ratio_val", "1.5")
        conditions.append(f"流动比率{op}{val}")

    # === 市场表现 ===
    if data.get("industry_enabled"):
        val = data.get("industry_val", "")
        if val:
            conditions.append(f"所属行业为{val}")

    if data.get("listing_years_enabled"):
        op = data.get("listing_years_op", "大于")
        val = data.get("listing_years_val", "3")
        conditions.append(f"上市天数{op}{int(float(val)*365)}")

    if data.get("pct_change_enabled"):
        period = data.get("pct_change_period", "近一个月")
        op = data.get("pct_change_op", "大于")
        val = data.get("pct_change_val", "5")
        conditions.append(f"{period}涨跌幅{op}{val}%")

    if data.get("turnover_enabled"):
        op = data.get("turnover_op", "大于")
        val = data.get("turnover_val", "1")
        conditions.append(f"换手率{op}{val}%")

    # 自定义条件
    if data.get("custom"):
        conditions.append(data["custom"])

    if not conditions:
        return jsonify({"error": "请至少选择一个筛选条件"}), 400

    query = " 且 ".join(conditions)

    # 先用筛选条件查，再单独查显示字段
    try:
        result = pywencai.get(query=query)
    except Exception as e:
        return jsonify({"error": f"查询失败: {str(e)}"}), 500

    if result is None:
        return jsonify({"query": query, "data": [], "total": 0})

    df = result
    if isinstance(result, dict):
        for v in result.values():
            if isinstance(v, pd.DataFrame):
                df = v
                break
        else:
            return jsonify({"query": query, "data": [], "total": 0})

    if not isinstance(df, pd.DataFrame) or df.empty:
        return jsonify({"query": query, "data": [], "total": 0})

    # 尝试追加更多显示字段（第二次查询）
    extra_query = (
        query + "，显示最新价，最新涨跌幅，营业总收入，扣非净利润，"
        "经营现金流，市盈率，市净率，商誉，市销率，每股净资产，"
        "营业收入同比增长率，经营现金流除以营业收入，非经常性损益，"
        "归母净利润，现金净增加额，投资现金流，筹资现金流，"
        "预测市盈率2026，预测市盈率2027，预测市盈率2028，"
        "总市值，基本每股收益"
    )
    try:
        extra_result = pywencai.get(query=extra_query)
        if extra_result is not None:
            extra_df = extra_result
            if isinstance(extra_result, dict):
                for v in extra_result.values():
                    if isinstance(v, pd.DataFrame):
                        extra_df = v
                        break
            if isinstance(extra_df, pd.DataFrame) and not extra_df.empty:
                df = extra_df
    except Exception:
        pass  # 追加字段失败就用原始结果

    df = df.reset_index(drop=True)

    # 简化列名
    col_rename = {}
    for c in df.columns:
        short = c
        # 去掉日期后缀 [20251231] [20260414] 等
        import re
        short = re.sub(r'\[\d{8}\]', '', short).strip()
        # 常见长名缩短
        replacements = {
            '扣除非经常性损益后的净利润': '扣非净利润',
            '经营活动产生的现金流量净额': '经营现金流',
            '投资活动产生的现金流量净额': '投资现金流',
            '筹资活动产生的现金流量净额': '筹资现金流',
            '经营活动产生的现金流量净额／营业收入': '现金流/营收',
            '归属于母公司所有者的净利润': '归母净利润',
            '现金及现金等价物净增加额': '现金净增加',
            '营业收入(同比增长率)': '营收同比增长',
            '营业收入同比增长率': '营收同比增长',
            '市盈率(pe)': 'PE',
            '市净率(pb)': 'PB',
            '市销率(ps)': 'PS',
            '每股净资产bps': '每股净资产',
            '基本每股收益': 'EPS',
            '营业总收入': '营业总收入',
            '非经常性损益': '非经常损益',
            '最新涨跌幅': '涨跌幅',
            '股票代码': '代码',
            '股票简称': '名称',
            '预测市盈率(pe,最新预测)': '预测PE',
        }
        for long, s in replacements.items():
            if long in short.lower() or long in short:
                short = short.replace(long, s)
                break
            if long.lower() in short.lower():
                short = s
                break
        col_rename[c] = short
    df = df.rename(columns=col_rename)

    def clean_value(v):
        if v is None:
            return None
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        # 浮点数保留2位
        if isinstance(v, float):
            return round(v, 2)
        return v

    clean_data = [[clean_value(cell) for cell in row] for row in df.values.tolist()]

    result_json = json.dumps({
        "query": query,
        "columns": df.columns.tolist(),
        "data": clean_data,
        "total": len(df),
    }, ensure_ascii=False)

    return Response(result_json, content_type="application/json; charset=utf-8")


@app.route("/api/recommend", methods=["GET"])
def recommend():
    """AI 每日推荐：用问财拿今日数据，DeepSeek 分析出12只"""
    # 第一步：从问财获取今日市场数据
    queries = [
        "今日涨幅前30且市盈率大于0且市盈率小于50且扣非净利润大于0，显示最新价、涨跌幅、成交额、换手率、市盈率、市净率、营收同比增长率、净利率、毛利率",
        "今日成交额前30且市盈率大于0且市盈率小于50且扣非净利润大于0，显示最新价、涨跌幅、成交额、换手率、市盈率、市净率、营收同比增长率、净利率、毛利率",
    ]
    all_rows = []
    for q in queries:
        try:
            result = pywencai.get(query=q)
            if result is None:
                continue
            df = result
            if isinstance(result, dict):
                for v in result.values():
                    if isinstance(v, pd.DataFrame):
                        df = v
                        break
            if isinstance(df, pd.DataFrame) and not df.empty:
                all_rows.append(df.head(30).to_string())
        except Exception:
            continue

    if not all_rows:
        return jsonify({"error": "无法获取今日市场数据"}), 500

    market_data = "\n\n".join(all_rows)

    # 第二步：DeepSeek 分析
    prompt = f"""你是一个专业的A股短线交易分析师。根据以下今日A股市场数据，选出最值得关注的12只股票。

要求：
1. 综合考虑涨幅趋势、成交量、估值合理性、基本面
2. 偏好：有资金流入、估值不贵、业绩有支撑的股票
3. 避免：纯炒作无业绩支撑的、涨幅已经过高的
4. 每只股票的推荐理由必须具体充分（30-50字），要说明具体的财务数据亮点，例如"PE仅12倍低于行业均值，净利率18.5%持续改善，营收同比增长25%成长性好，成交额放大资金关注度高"
5. price和change字段必须是数字，不能缺失。如果数据中找不到准确数字就根据数据合理估算
6. 必须严格返回JSON格式，不要返回其他内容

返回格式（严格JSON数组，12个元素）：
[
  {{
    "code": "股票代码",
    "name": "股票名称",
    "price": 最新价数字,
    "change": 涨跌幅数字,
    "reason": "具体充分的推荐理由（30-50字，包含具体数据）",
    "signal": "看多/观望/谨慎"
  }}
]

今日市场数据：
{market_data[:8000]}
"""

    try:
        resp = ds_client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=4000,
        )
        content = resp.choices[0].message.content.strip()
        # 提取JSON部分
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()
        stocks = json.loads(content)
        # 过滤掉数据缺失的（price或change为空/None/非数字）
        valid = []
        for s in stocks:
            try:
                p = float(s.get("price", 0))
                c = float(s.get("change", 0))
                if p > 0:
                    s["price"] = round(p, 2)
                    s["change"] = round(c, 2)
                    valid.append(s)
            except (TypeError, ValueError):
                continue
        return jsonify({"stocks": valid[:12]})
    except Exception as e:
        return jsonify({"error": f"AI分析失败: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3010, debug=True)

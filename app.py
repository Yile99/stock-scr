from flask import Flask, request, jsonify, send_from_directory, Response
import pywencai
import pandas as pd
import json
import math
import re
from openai import OpenAI

app = Flask(__name__)

DEEPSEEK_KEY = "sk-e9b309fc5854489db866aa27c7bdcb07"
ds_client = OpenAI(api_key=DEEPSEEK_KEY, base_url="https://api.deepseek.com")


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/favicon.svg")
def favicon():
    return send_from_directory(".", "favicon.svg", mimetype="image/svg+xml")


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
        period = data.get("revenue_growth_period", "")
        op = data.get("revenue_growth_op", "大于")
        val = data.get("revenue_growth_val", "10")
        if period:
            conditions.append(f"{period}营业总收入同比增长率{op}{val}%")
        else:
            conditions.append(f"营业总收入同比增长率{op}{val}%")

    if data.get("profit_enabled"):
        op = data.get("profit_op", "大于")
        val = data.get("profit_val", "5")
        unit = data.get("profit_unit", "亿")
        conditions.append(f"扣非净利润{op}{val}{unit}")

    if data.get("profit_growth_enabled"):
        period = data.get("profit_growth_period", "")
        op = data.get("profit_growth_op", "大于")
        val = data.get("profit_growth_val", "10")
        if period:
            conditions.append(f"{period}扣非净利润同比增长率{op}{val}%")
        else:
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

    if data.get("cashflow_consecutive_enabled"):
        years = data.get("cashflow_consecutive_years", "5")
        cf_type = data.get("cashflow_consecutive_type", "为正")
        conditions.append(f"连续{years}年经营现金流{cf_type}")

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
        div_min = data.get("dividend_min", "3")
        div_max = data.get("dividend_max", "100")
        conditions.append(f"股息率大于{div_min}%且股息率小于{div_max}%")

    if data.get("mcap_enabled"):
        mcap_min = data.get("mcap_min", "100")
        mcap_max = data.get("mcap_max", "5000")
        unit = data.get("mcap_unit", "亿")
        conditions.append(f"总市值大于{mcap_min}{unit}且总市值小于{mcap_max}{unit}")

    # === 财务健康 ===
    if data.get("goodwill_enabled"):
        mode = data.get("goodwill_mode", "abs")
        op = data.get("goodwill_op", "小于")
        val = data.get("goodwill_val", "10")
        if mode == "pct":
            conditions.append(f"商誉占总市值比例{op}{val}%")
        else:
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
        period = data.get("turnover_period", "今日")
        op = data.get("turnover_op", "大于")
        val = data.get("turnover_val", "1")
        if period == "今日":
            conditions.append(f"换手率{op}{val}%")
        else:
            conditions.append(f"{period}换手率{op}{val}%")

    # === 新增：成长质量 ===
    if data.get("net_profit_enabled"):
        op = data.get("net_profit_op", "大于")
        val = data.get("net_profit_val", "5")
        unit = data.get("net_profit_unit", "亿")
        conditions.append(f"归母净利润{op}{val}{unit}")

    if data.get("net_profit_growth_enabled"):
        op = data.get("net_profit_growth_op", "大于")
        val = data.get("net_profit_growth_val", "10")
        conditions.append(f"归母净利润同比增长率{op}{val}%")

    if data.get("cont_growth_enabled"):
        val = data.get("cont_growth_val", "3")
        conditions.append(f"连续{val}年扣非净利润增长")

    if data.get("roa_enabled"):
        roa_min = data.get("roa_min", "5")
        roa_max = data.get("roa_max", "100")
        conditions.append(f"总资产报酬率大于{roa_min}%且总资产报酬率小于{roa_max}%")

    if data.get("rd_ratio_enabled"):
        op = data.get("rd_ratio_op", "大于")
        val = data.get("rd_ratio_val", "5")
        conditions.append(f"研发费用占营收比例{op}{val}%")

    # === 新增：估值进阶 ===
    if data.get("peg_enabled"):
        peg_min = data.get("peg_min", "0")
        peg_max = data.get("peg_max", "1.5")
        conditions.append(f"PEG大于{peg_min}且PEG小于{peg_max}")

    if data.get("pcf_enabled"):
        pcf_min = data.get("pcf_min", "0")
        pcf_max = data.get("pcf_max", "20")
        conditions.append(f"市现率大于{pcf_min}且市现率小于{pcf_max}")

    if data.get("float_mcap_enabled"):
        fm_min = data.get("float_mcap_min", "50")
        fm_max = data.get("float_mcap_max", "2000")
        unit = data.get("float_mcap_unit", "亿")
        conditions.append(f"流通市值大于{fm_min}{unit}且流通市值小于{fm_max}{unit}")

    # === 新增：资金与筹码 ===
    if data.get("holders_change_enabled"):
        htype = data.get("holders_change_type", "减少")
        conditions.append(f"最新一期股东人数{htype}")

    if data.get("north_fund_enabled"):
        op = data.get("north_fund_op", "大于")
        val = data.get("north_fund_val", "0")
        conditions.append(f"北向资金持股比例{op}{val}%")

    if data.get("fund_hold_enabled"):
        op = data.get("fund_hold_op", "大于")
        val = data.get("fund_hold_val", "5")
        conditions.append(f"基金持仓占比{op}{val}%")

    if data.get("main_fund_enabled"):
        mtype = data.get("main_fund_type", "净流入")
        conditions.append(f"今日主力资金{mtype}")

    if data.get("volume_ratio_enabled"):
        op = data.get("volume_ratio_op", "大于")
        val = data.get("volume_ratio_val", "1.5")
        conditions.append(f"量比{op}{val}")

    # === 新增：风险筛选 ===
    if data.get("pledge_enabled"):
        op = data.get("pledge_op", "小于")
        val = data.get("pledge_val", "30")
        conditions.append(f"质押比例{op}{val}%")

    if data.get("board_enabled"):
        val = data.get("board_val", "主板")
        conditions.append(f"上市板块为{val}")

    if data.get("no_st_enabled"):
        conditions.append("非ST")

    # === 新增：技术面 ===
    if data.get("above_ma_enabled"):
        val = data.get("above_ma_val", "20")
        conditions.append(f"股价站上{val}日均线")

    if data.get("amplitude_enabled"):
        op = data.get("amplitude_op", "小于")
        val = data.get("amplitude_val", "5")
        conditions.append(f"今日振幅{op}{val}%")

    if data.get("concept_enabled"):
        val = data.get("concept_val", "")
        if val:
            conditions.append(f"所属概念包含{val}")

    # === 盈利质量 ===
    if data.get("cash_content_enabled"):
        op = data.get("cash_content_op", "大于")
        val = data.get("cash_content_val", "80")
        conditions.append(f"净利润现金含量{op}{val}%")

    if data.get("ar_turnover_enabled"):
        op = data.get("ar_turnover_op", "大于")
        val = data.get("ar_turnover_val", "5")
        conditions.append(f"应收账款周转率{op}{val}")

    if data.get("inv_turnover_enabled"):
        op = data.get("inv_turnover_op", "大于")
        val = data.get("inv_turnover_val", "3")
        conditions.append(f"存货周转率{op}{val}")

    if data.get("sell_expense_enabled"):
        op = data.get("sell_expense_op", "小于")
        val = data.get("sell_expense_val", "20")
        conditions.append(f"销售费用率{op}{val}%")

    if data.get("fin_expense_enabled"):
        op = data.get("fin_expense_op", "小于")
        val = data.get("fin_expense_val", "5")
        conditions.append(f"财务费用率{op}{val}%")

    # === 价值投资 ===
    if data.get("fcf_enabled"):
        fcf_type = data.get("fcf_type", "为正")
        conditions.append(f"自由现金流{fcf_type}")

    if data.get("ev_ebitda_enabled"):
        ev_min = data.get("ev_ebitda_min", "0")
        ev_max = data.get("ev_ebitda_max", "15")
        conditions.append(f"EV/EBITDA大于{ev_min}且EV/EBITDA小于{ev_max}")

    if data.get("roic_enabled"):
        op = data.get("roic_op", "大于")
        val = data.get("roic_val", "10")
        conditions.append(f"ROIC{op}{val}%")

    if data.get("payout_enabled"):
        op = data.get("payout_op", "大于")
        val = data.get("payout_val", "30")
        conditions.append(f"分红率{op}{val}%")

    if data.get("cont_dividend_enabled"):
        val = data.get("cont_dividend_val", "5")
        conditions.append(f"连续{val}年分红")

    # === 分析师预期 ===
    if data.get("consensus_growth_enabled"):
        op = data.get("consensus_growth_op", "大于")
        val = data.get("consensus_growth_val", "20")
        conditions.append(f"机构预测净利增速{op}{val}%")

    if data.get("research_count_enabled"):
        op = data.get("research_count_op", "大于")
        val = data.get("research_count_val", "5")
        conditions.append(f"近三个月机构调研次数{op}{val}")

    if data.get("analyst_rating_enabled"):
        val = data.get("analyst_rating_val", "买入")
        conditions.append(f"最新评级为{val}")

    if data.get("forecast_type_enabled"):
        val = data.get("forecast_type_val", "预增")
        conditions.append(f"业绩预告类型为{val}")

    # === 资金进阶 ===
    if data.get("margin_enabled"):
        mtype = data.get("margin_type", "融资净买入")
        conditions.append(f"今日{mtype}")

    if data.get("shareholder_reduce_enabled"):
        conditions.append("近三个月无大股东减持")

    if data.get("unlock_enabled"):
        op = data.get("unlock_op", "小于")
        val = data.get("unlock_val", "5")
        conditions.append(f"未来一个月解禁比例{op}{val}%")

    if data.get("buyback_enabled"):
        conditions.append("有回购计划")

    if data.get("index_member_enabled"):
        val = data.get("index_member_val", "沪深300")
        conditions.append(f"属于{val}成分股")

    # === 技术面进阶 ===
    if data.get("macd_enabled"):
        val = data.get("macd_val", "金叉")
        period = data.get("macd_period", "日线")
        conditions.append(f"{period}MACD{val}")

    if data.get("rsi_enabled"):
        rsi_min = data.get("rsi_min", "30")
        rsi_max = data.get("rsi_max", "70")
        conditions.append(f"RSI大于{rsi_min}且RSI小于{rsi_max}")

    if data.get("new_high_enabled"):
        val = data.get("new_high_val", "60")
        conditions.append(f"创{val}日新高")

    if data.get("drawdown_enabled"):
        op = data.get("drawdown_op", "大于")
        val = data.get("drawdown_val", "30")
        conditions.append(f"距离250日高点回撤{op}{val}%")

    if data.get("vol_break_enabled"):
        val = data.get("vol_break_val", "2")
        conditions.append(f"今日成交量大于5日均量的{val}倍")

    # === 风险进阶 ===
    if data.get("audit_enabled"):
        conditions.append("审计意见为标准无保留意见")

    if data.get("controller_enabled"):
        val = data.get("controller_val", "国企")
        conditions.append(f"实际控制人性质为{val}")

    if data.get("interest_debt_enabled"):
        op = data.get("interest_debt_op", "小于")
        val = data.get("interest_debt_val", "40")
        conditions.append(f"有息负债率{op}{val}%")

    if data.get("single_q_revenue_enabled"):
        op = data.get("single_q_revenue_op", "大于")
        val = data.get("single_q_revenue_val", "20")
        conditions.append(f"单季度营收同比增速{op}{val}%")

    if data.get("single_q_profit_enabled"):
        op = data.get("single_q_profit_op", "大于")
        val = data.get("single_q_profit_val", "20")
        conditions.append(f"单季度扣非净利同比增速{op}{val}%")

    # 自定义条件
    if data.get("custom"):
        conditions.append(data["custom"])

    if not conditions:
        return jsonify({"error": "请至少选择一个筛选条件"}), 400

    query = "，".join(conditions)

    # 从 pywencai 结果中提取 DataFrame
    def extract_df(result):
        if result is None:
            return None
        if isinstance(result, pd.DataFrame):
            return result if not result.empty else None
        if isinstance(result, dict):
            for v in result.values():
                if isinstance(v, pd.DataFrame) and not v.empty:
                    return v
        return None

    # 先用筛选条件查，带重试
    df = None
    last_err = None
    for attempt in range(2):
        try:
            result = pywencai.get(query=query)
            df = extract_df(result)
            if df is not None:
                break
        except Exception as e:
            last_err = str(e)
            continue

    if df is None:
        if last_err:
            return jsonify({"error": f"问财查询暂时不可用，请稍后再试（{last_err}）"}), 500
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
        extra_df = extract_df(extra_result)
        if extra_df is not None:
            df = extra_df
    except Exception:
        pass  # 追加字段失败就用原始结果

    df = df.reset_index(drop=True)

    # 简化列名
    col_rename = {}
    for c in df.columns:
        short = c
        # 去掉日期后缀 [20251231] [20260414] 等
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

    # 删除无用列
    drop_cols = [c for c in df.columns if c.lower() in ('market_code', 'code', 'market_code')]
    if drop_cols:
        df = df.drop(columns=drop_cols, errors='ignore')

    def clean_value(v):
        if v is None:
            return None
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        # 浮点数保留2位
        if isinstance(v, float):
            return round(v, 2)
        # 字符串数字也转成float并round
        if isinstance(v, str):
            try:
                f = float(v)
                if math.isnan(f) or math.isinf(f):
                    return None
                return round(f, 2)
            except (ValueError, TypeError):
                pass
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
    import os
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=3010, debug=debug)

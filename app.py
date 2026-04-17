from flask import Flask, request, jsonify, send_from_directory, Response
import pywencai
import pandas as pd
import json
import math
import re
import threading
from datetime import datetime, date
from openai import OpenAI

app = Flask(__name__)

DEEPSEEK_KEY = "sk-e9b309fc5854489db866aa27c7bdcb07"
ds_client = OpenAI(api_key=DEEPSEEK_KEY, base_url="https://api.deepseek.com")

# ===== 每日推荐缓存 =====
_recommend_cache = {"date": None, "data": None, "generating": False}


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

    # === 股权结构 ===
    if data.get("inst_hold_enabled"):
        op = data.get("inst_hold_op", "大于")
        val = data.get("inst_hold_val", "20")
        conditions.append(f"机构持股比例{op}{val}%")

    if data.get("top10_hold_enabled"):
        op = data.get("top10_hold_op", "大于")
        val = data.get("top10_hold_val", "50")
        conditions.append(f"前十大股东持股比例合计{op}{val}%")

    if data.get("mgmt_hold_enabled"):
        op = data.get("mgmt_hold_op", "大于")
        val = data.get("mgmt_hold_val", "5")
        conditions.append(f"高管持股比例{op}{val}%")

    # === 行业对比 ===
    if data.get("pe_pct_enabled"):
        val = data.get("pe_pct_val", "30")
        conditions.append(f"市盈率行业排名前{val}%")

    if data.get("roe_above_avg_enabled"):
        conditions.append("净资产收益率高于行业平均")

    if data.get("revenue_rank_enabled"):
        val = data.get("revenue_rank_val", "10")
        conditions.append(f"营业总收入行业排名前{val}名")

    # === 特殊事件 ===
    if data.get("equity_incentive_enabled"):
        conditions.append("有股权激励计划")

    if data.get("holder_increase_enabled"):
        conditions.append("近三个月有大股东增持")

    if data.get("private_placement_enabled"):
        conditions.append("有定增预案")

    if data.get("merger_enabled"):
        conditions.append("有并购重组")

    # === 财务趋势 ===
    if data.get("cont_rev_growth_enabled"):
        val = data.get("cont_rev_growth_val", "3")
        conditions.append(f"连续{val}个季度营收同比增长")

    if data.get("gm_improve_enabled"):
        conditions.append("最新一期毛利率高于上期")

    if data.get("nm_improve_enabled"):
        conditions.append("最新一期净利率高于上期")

    if data.get("roe_improve_enabled"):
        val = data.get("roe_improve_val", "2")
        conditions.append(f"连续{val}个季度ROE提升")

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


def _generate_recommend():
    """内部函数：从问财拿数据 + DeepSeek 分析，返回 dict"""
    show_fields = "，显示最新价、涨跌幅、成交额、换手率、市盈率、市净率、营收同比增长率、净利率、毛利率"
    query_sets = [
        [f"今日涨幅前30且市盈率大于0且市盈率小于50且扣非净利润大于0{show_fields}",
         f"今日成交额前30且市盈率大于0且市盈率小于50且扣非净利润大于0{show_fields}"],
        [f"最近一个交易日涨幅前30且市盈率大于0且市盈率小于50且扣非净利润大于0{show_fields}",
         f"最近一个交易日成交额前30且市盈率大于0且市盈率小于50且扣非净利润大于0{show_fields}"],
    ]
    all_rows = []
    for queries in query_sets:
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
        if all_rows:
            break

    if not all_rows:
        return {"error": "无法获取今日市场数据"}

    market_data = "\n\n".join(all_rows)
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
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()
        stocks = json.loads(content)
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
        return {"stocks": valid[:12]}
    except Exception as e:
        return {"error": f"AI分析失败: {str(e)}"}


def _refresh_cache():
    """后台生成推荐并写入缓存"""
    _recommend_cache["generating"] = True
    try:
        result = _generate_recommend()
        if "stocks" in result:
            _recommend_cache["data"] = result
            _recommend_cache["date"] = date.today().isoformat()
    finally:
        _recommend_cache["generating"] = False


@app.route("/api/recommend", methods=["GET"])
def recommend():
    """返回缓存的每日推荐，如果缓存过期则后台刷新"""
    force = request.args.get("force") == "1"
    today = date.today().isoformat()

    # 缓存命中且非强制刷新 → 直接返回
    if _recommend_cache["date"] == today and _recommend_cache["data"] and not force:
        return jsonify(_recommend_cache["data"])

    # 正在生成中 → 如果有旧数据先返回旧的，否则提示等待
    if _recommend_cache["generating"]:
        if _recommend_cache["data"]:
            return jsonify(_recommend_cache["data"])
        return jsonify({"generating": True, "error": "AI正在分析中，请稍后刷新..."})

    # 强制刷新 或 当天首次 → 后台生成，先返回旧数据或等待提示
    threading.Thread(target=_refresh_cache, daemon=True).start()
    if _recommend_cache["data"]:
        return jsonify(_recommend_cache["data"])
    return jsonify({"generating": True, "error": "AI正在分析中，首次加载约需15秒，请稍后自动刷新..."})


@app.route("/api/news", methods=["GET"])
def news():
    """抓取东方财富7x24快讯"""
    import urllib.request
    import time

    from datetime import datetime, timedelta
    trace = str(int(time.time() * 1000))
    url = (
        "https://np-listapi.eastmoney.com/comm/web/getFastNewsList"
        f"?client=web&biz=web_724&fastColumn=102&sortEnd=&pageSize=30&channel=1&req_trace={trace}"
    )
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.eastmoney.com/"
        })
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        items = []
        cutoff = datetime.now() - timedelta(hours=6)
        for item in (data.get("data") or {}).get("fastNewsList", []):
            # showTime 是字符串 "2026-04-14 23:51:42"
            time_str = item.get("showTime", "")
            try:
                item_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                if item_time < cutoff:
                    continue
            except (ValueError, TypeError):
                pass
            title = item.get("title", "").strip()
            digest = item.get("digest", "").strip()
            summary = item.get("summary", "").strip()
            content_text = digest or summary or title
            content_text = re.sub(r'<[^>]+>', '', content_text)
            display_time = time_str[11:16] if len(time_str) >= 16 else time_str
            is_important = bool(item.get("titleColor", 0))
            items.append({
                "title": title,
                "content": content_text[:500],
                "time": display_time,
                "important": is_important,
            })

        return jsonify({"news": items[:20]})
    except Exception as e:
        return jsonify({"error": f"获取新闻失败: {str(e)}", "news": []}), 200


# ===== 大盘情绪温度计 =====
_sentiment_cache = {"ts": 0, "data": None}

@app.route("/api/sentiment")
def sentiment():
    """大盘情绪温度计"""
    import urllib.request
    import time as _time

    now = _time.time()
    if _sentiment_cache["data"] and now - _sentiment_cache["ts"] < 120:
        return jsonify(_sentiment_cache["data"])

    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    HDR = {"User-Agent": UA, "Referer": "https://www.eastmoney.com/"}
    result = {"indices": [], "advance": 0, "decline": 0, "flat": 0,
              "limit_up": 0, "limit_down": 0, "score": 50, "label": "中性"}

    # 1. 主要指数 + 涨跌家数（从上证+深证指数的 f104/f105/f106 汇总）
    try:
        url = ("https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&"
               "secids=1.000001,0.399001,0.399006&fields=f2,f3,f4,f6,f12,f14,f104,f105,f106")
        req = urllib.request.Request(url, headers=HDR)
        with urllib.request.urlopen(req, timeout=8) as resp:
            j = json.loads(resp.read().decode())
        adv_total = dec_total = flat_total = 0
        for d in j.get("data", {}).get("diff", []):
            result["indices"].append({
                "name": d.get("f14", ""), "code": d.get("f12", ""),
                "price": d.get("f2", 0), "pct": d.get("f3", 0),
                "change": d.get("f4", 0), "amount": d.get("f6", 0)
            })
            code = d.get("f12", "")
            # 只取上证指数和深证成指的涨跌家数（创业板已包含在深证中）
            if code in ("000001", "399001"):
                adv_total += int(d.get("f104", 0) or 0)
                dec_total += int(d.get("f105", 0) or 0)
                flat_total += int(d.get("f106", 0) or 0)
        result.update(advance=adv_total, decline=dec_total, flat=flat_total)
    except Exception:
        pass

    # 2. 涨停跌停数 — 问财查询（封板涨停，非曾涨停）
    def _wencai_count(query):
        try:
            r = pywencai.get(query=query)
            if isinstance(r, pd.DataFrame) and not r.empty:
                return len(r)
            if isinstance(r, dict):
                for v in r.values():
                    if isinstance(v, pd.DataFrame) and not v.empty:
                        return len(v)
        except Exception:
            pass
        return 0

    result["limit_up"] = _wencai_count("今日涨停封板的A股股票")
    result["limit_down"] = _wencai_count("今日跌停的A股股票")

    # 计算情绪分
    adv, dec = result["advance"], result["decline"]
    lu, ld = result["limit_up"], result["limit_down"]
    idx_pct = result["indices"][0]["pct"] if result["indices"] else 0
    idx_score = max(0, min(100, (idx_pct + 3) / 6 * 100))
    lt_total = lu + ld or 1
    lt_score = lu / lt_total * 100

    if adv + dec > 0:
        ad_score = adv / (adv + dec) * 100
        score = round(ad_score * 0.4 + lt_score * 0.3 + idx_score * 0.3)
    else:
        # 涨跌家数不可用时，用涨停跌停+指数算
        score = round(lt_score * 0.5 + idx_score * 0.5)
    score = max(0, min(100, score))
    result["score"] = score
    if score >= 80: result["label"] = "极度贪婪"
    elif score >= 60: result["label"] = "贪婪"
    elif score >= 40: result["label"] = "中性"
    elif score >= 20: result["label"] = "恐惧"
    else: result["label"] = "极度恐惧"

    _sentiment_cache.update(ts=now, data=result)
    return jsonify(result)


# ===== 文件缓存工具 =====
import os

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
os.makedirs(CACHE_DIR, exist_ok=True)


def _save_cache(name, data):
    """写缓存到文件，带日期标记"""
    try:
        payload = {"date": date.today().isoformat(), "data": data}
        with open(os.path.join(CACHE_DIR, f"{name}.json"), "w") as f:
            json.dump(payload, f, ensure_ascii=False)
    except Exception:
        pass


def _load_cache(name):
    """读缓存文件，只返回当天的数据"""
    try:
        with open(os.path.join(CACHE_DIR, f"{name}.json")) as f:
            payload = json.load(f)
        if payload.get("date") == date.today().isoformat():
            return payload["data"]
    except Exception:
        pass
    return None


# ===== 板块热力图 =====
@app.route("/api/sectors")
def sectors():
    """行业板块涨跌"""
    import urllib.request
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    # 1. 尝试东方财富实时接口
    try:
        url = ("https://push2.eastmoney.com/api/qt/clist/get?"
               "pn=1&pz=100&po=1&np=1&fltt=2&invt=2&fid=f3&fs=m:90+t:2&"
               "fields=f3,f12,f14,f104,f105,f20,f6")
        req = urllib.request.Request(url, headers={
            "User-Agent": UA, "Referer": "https://www.eastmoney.com/"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            j = json.loads(resp.read().decode())
        items = []
        for d in (j.get("data") or {}).get("diff", []):
            c = d.get("f3", 0)
            if not isinstance(c, (int, float)):
                continue
            items.append({
                "name": d.get("f14", ""), "pct": c,
                "mcap": d.get("f20", 0), "amount": d.get("f6", 0),
                "adv": d.get("f104", 0), "dec": d.get("f105", 0),
            })
        if items:
            _save_cache("sectors", {"sectors": items})
            return jsonify({"sectors": items})
    except Exception:
        pass
    # 2. 返回文件缓存
    cached = _load_cache("sectors")
    if cached:
        return jsonify(cached)
    # 3. 缓存也没有时，用问财获取行业板块数据
    try:
        r = pywencai.get(query="行业板块涨跌幅排名", query_type="zhishu")
        df = None
        if isinstance(r, pd.DataFrame) and not r.empty:
            df = r
        elif isinstance(r, dict):
            for v in r.values():
                if isinstance(v, pd.DataFrame) and not v.empty:
                    df = v
                    break
        if df is not None and len(df) > 0:
            items = []
            for _, row in df.iterrows():
                name = row.get("指数简称", "")
                pct_col = [c for c in df.columns if "涨跌幅" in c and "排名" not in c]
                pct = float(row[pct_col[0]]) if pct_col else 0
                amt_col = [c for c in df.columns if "成交额" in c]
                amt = float(row[amt_col[0]]) if amt_col else 0
                items.append({
                    "name": name, "pct": round(pct, 2),
                    "mcap": amt,  # 用成交额代替市值做面积
                    "amount": amt, "adv": 0, "dec": 0,
                })
            items = [x for x in items if x["mcap"] > 0]
            items.sort(key=lambda x: x["mcap"], reverse=True)
            items = items[:50]
            if items:
                _save_cache("sectors", {"sectors": items})
                return jsonify({"sectors": items})
    except Exception:
        pass
    return jsonify({"sectors": []})


# ===== 南向资金（港股通）流向 =====
@app.route("/api/southbound")
def southbound():
    """南向资金近20个交易日净买入趋势"""
    import urllib.request
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    HDR = {"User-Agent": UA, "Referer": "https://data.eastmoney.com/"}
    result = {"days": [], "sh": 0, "sz": 0, "total": 0}
    try:
        # 分别获取港股通(沪)002、港股通(深)004、合计006
        sh_map, sz_map, total_map = {}, {}, {}
        for code, target in [("002", sh_map), ("004", sz_map), ("006", total_map)]:
            url = (
                "https://datacenter-web.eastmoney.com/api/data/v1/get?"
                "sortColumns=TRADE_DATE&sortTypes=-1&pageSize=20&pageNumber=1&"
                "reportName=RPT_MUTUAL_DEAL_HISTORY&"
                "columns=TRADE_DATE,NET_DEAL_AMT,BUY_AMT,SELL_AMT&"
                f"filter=(MUTUAL_TYPE=%22{code}%22)"
            )
            req = urllib.request.Request(url, headers=HDR)
            with urllib.request.urlopen(req, timeout=10) as resp:
                j = json.loads(resp.read().decode())
            for row in (j.get("result") or {}).get("data", []):
                dt = row["TRADE_DATE"][:10]
                target[dt] = round((row.get("NET_DEAL_AMT") or 0) / 100, 2)  # 百万→亿

        # 合并为时间序列
        dates = sorted(total_map.keys())
        for dt in dates:
            short = dt[5:]  # MM-DD
            result["days"].append({
                "date": short,
                "sh": sh_map.get(dt, 0),
                "sz": sz_map.get(dt, 0),
                "total": total_map.get(dt, 0),
            })
        if result["days"]:
            last = result["days"][-1]
            result["sh"] = last["sh"]
            result["sz"] = last["sz"]
            result["total"] = last["total"]
            _save_cache("southbound", result)
        return jsonify(result)
    except Exception:
        pass
    cached = _load_cache("southbound")
    if cached:
        return jsonify(cached)
    return jsonify(result)


# ===== 个股查询 =====
@app.route("/api/stock_info", methods=["POST"])
def stock_info():
    """查询单只股票的详细信息 — pywencai识别+eastmoney财务数据"""
    data = request.json
    q = (data.get("q") or "").strip()
    if not q:
        return jsonify({"error": "请输入股票代码或名称"})

    def extract_df(result):
        if isinstance(result, pd.DataFrame) and not result.empty:
            return result
        if isinstance(result, dict):
            for v in result.values():
                if isinstance(v, pd.DataFrame) and not v.empty:
                    return v
        return None

    try:
        # Step 1: 用 pywencai 获取股票名称、代码、最新价、涨跌幅
        wc_query = f"{q}的最新价、最新涨跌幅"
        wc_result = pywencai.get(query=wc_query)
        df = extract_df(wc_result)
        if df is None or df.empty:
            return jsonify({"error": "未找到该股票"})
        df = df.head(1)

        name, code, price, pct = '', '', None, None
        for c in df.columns:
            val = df.iloc[0][c]
            if isinstance(val, pd.Series):
                val = val.iloc[0]
            if hasattr(val, 'item'):
                val = val.item()
            cl = c.lower()
            if '简称' in cl or '名称' in cl:
                name = str(val).strip() if val else ''
            elif '代码' in cl and 'market' not in cl:
                code = str(val).strip() if val else ''
            elif '最新价' in cl and price is None:
                try: price = round(float(val), 2)
                except: pass
            elif ('涨跌幅' in cl or '涨幅' in cl) and pct is None:
                try: pct = round(float(val), 2)
                except: pass

        if not code:
            return jsonify({"error": "未找到该股票代码"})

        # Step 2: 用 eastmoney datacenter API 获取财务数据
        import urllib.request, urllib.parse
        HDR = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        stock = {"名称": name or q, "代码": code, "最新价": price, "涨跌幅": pct}
        try:
            em_url = ("https://datacenter-web.eastmoney.com/api/data/v1/get"
                      "?reportName=RPT_LICO_FN_CPD&columns=ALL"
                      f"&filter=(SECURITY_CODE=%22{code}%22)&pageSize=1")
            req = urllib.request.Request(em_url, headers=HDR)
            with urllib.request.urlopen(req, timeout=8) as resp:
                em_resp = json.loads(resp.read().decode())
            if em_resp.get("success") and em_resp.get("result", {}).get("data"):
                d = em_resp["result"]["data"][0]
                eps = d.get("BASIC_EPS")
                bps = d.get("BPS")
                revenue = d.get("TOTAL_OPERATE_INCOME")
                # 从价格和每股指标计算估值
                if price and eps and eps > 0:
                    stock["PE"] = round(price / eps, 2)
                if price and bps and bps > 0:
                    stock["PB"] = round(price / bps, 2)
                if eps is not None:
                    stock["EPS"] = round(eps, 2)
                if d.get("WEIGHTAVG_ROE") is not None:
                    stock["ROE"] = round(d["WEIGHTAVG_ROE"], 2)
                if d.get("XSMLL") is not None:
                    stock["毛利率"] = round(d["XSMLL"], 2)
                if d.get("ZXGXL") is not None:
                    stock["股息率"] = round(d["ZXGXL"], 2)
                if d.get("YSTZ") is not None:
                    stock["营收增长"] = round(d["YSTZ"], 2)
                if revenue is not None:
                    stock["营收"] = round(revenue / 1e8, 2)  # 转为亿
                deduct_eps = d.get("DEDUCT_BASIC_EPS")
                if deduct_eps is not None:
                    stock["扣非EPS"] = round(deduct_eps, 2)
                net_profit = d.get("PARENT_NETPROFIT")
                if net_profit is not None:
                    stock["扣非利润"] = round(net_profit / 1e8, 2)  # 转为亿
                # 净利率 = 归母净利润 / 营收
                if net_profit and revenue and revenue > 0:
                    stock["净利率"] = round(net_profit / revenue * 100, 2)
                # PS = market_cap / revenue, 近似用 PE * 净利率
                if "PE" in stock and "净利率" in stock and stock["净利率"] > 0:
                    stock["PS"] = round(stock["PE"] * stock["净利率"] / 100, 2)
        except Exception:
            pass  # 财务数据获取失败仍返回基本信息

        # Step 3: 尝试 push2 API 补充实时估值（盘中可用）
        try:
            mkt = "1" if code.startswith("6") else "0"
            p2_url = (f"https://push2.eastmoney.com/api/qt/stock/get"
                      f"?secid={mkt}.{code}&fields=f43,f117,f162,f167,f170")
            req2 = urllib.request.Request(p2_url, headers=HDR)
            with urllib.request.urlopen(req2, timeout=3) as resp2:
                p2_resp = json.loads(resp2.read().decode())
            p2d = p2_resp.get("data", {})
            if p2d:
                if "PE" not in stock and p2d.get("f162"):
                    stock["PE"] = round(p2d["f162"] / 100, 2)
                if p2d.get("f167"):
                    stock["PB"] = round(p2d["f167"] / 100, 2)
                if p2d.get("f117"):
                    stock["总市值"] = round(p2d["f117"] / 1e8, 2)  # 转为亿
                if price is None and p2d.get("f43"):
                    stock["最新价"] = round(p2d["f43"] / 100, 2)
                if pct is None and p2d.get("f170"):
                    stock["涨跌幅"] = round(p2d["f170"] / 100, 2)
        except Exception:
            pass  # push2 盘后不可用，忽略

        # 如果还没有总市值，用 净利润/EPS 得到总股本，再乘价格
        if "总市值" not in stock and price and stock.get("EPS") and stock["EPS"] > 0:
            try:
                if stock.get("扣非利润"):
                    # 扣非利润 已转为亿
                    net_profit_yuan = stock["扣非利润"] * 1e8
                    total_shares = net_profit_yuan / stock["EPS"]
                    stock["总市值"] = round(price * total_shares / 1e8, 0)
            except Exception:
                pass

        return jsonify({"stock": stock})
    except Exception as e:
        return jsonify({"error": f"查询失败: {str(e)}"})


# ===== 个股AI点评 =====
@app.route("/api/stock_comment", methods=["POST"])
def stock_comment():
    """用 DeepSeek 对单只股票做简短点评"""
    data = request.json
    name = data.get("name", "")
    code = data.get("code", "")
    metrics = data.get("metrics", "")
    if not metrics:
        return jsonify({"comment": "缺少股票数据"})
    try:
        prompt = f"""你是一位专业的A股分析师。请根据以下{name}({code})的财务数据，给出一段简洁的投资点评（80-120字）。
要求：
1. 先给出一个标签：看好/中性/谨慎
2. 然后说明具体理由，引用关键数据
3. 提示主要风险
4. 语言精炼有信息量

数据：{metrics[:2000]}"""
        resp = ds_client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=300,
        )
        comment = resp.choices[0].message.content.strip()
        return jsonify({"comment": comment})
    except Exception as e:
        return jsonify({"comment": f"AI分析暂不可用: {str(e)}"})


if __name__ == "__main__":
    import os
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    # 启动时后台预生成今日推荐缓存
    threading.Thread(target=_refresh_cache, daemon=True).start()
    app.run(host="0.0.0.0", port=3010, debug=debug)

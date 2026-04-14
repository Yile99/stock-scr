from flask import Flask, request, jsonify, send_from_directory, Response
import pywencai
import pandas as pd
import json
import math

app = Flask(__name__)


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

    df = df.reset_index(drop=True)

    def clean_value(v):
        if v is None:
            return None
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        return v

    clean_data = [[clean_value(cell) for cell in row] for row in df.values.tolist()]

    result_json = json.dumps({
        "query": query,
        "columns": df.columns.tolist(),
        "data": clean_data,
        "total": len(df),
    }, ensure_ascii=False)

    return Response(result_json, content_type="application/json; charset=utf-8")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3010, debug=True)

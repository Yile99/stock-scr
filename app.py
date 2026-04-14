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

    # 营业总收入
    if data.get("revenue_enabled"):
        op = data.get("revenue_op", ">")
        val = data.get("revenue_val", "50")
        unit = data.get("revenue_unit", "亿")
        conditions.append(f"营业总收入{op}{val}{unit}")

    # 扣非净利润
    if data.get("profit_enabled"):
        op = data.get("profit_op", ">")
        val = data.get("profit_val", "5")
        unit = data.get("profit_unit", "亿")
        conditions.append(f"扣非净利润{op}{val}{unit}")

    # 经营现金流
    if data.get("cashflow_enabled"):
        cashflow_type = data.get("cashflow_type", "为正")
        conditions.append(f"经营现金流{cashflow_type}")

    # 市盈率
    if data.get("pe_enabled"):
        pe_min = data.get("pe_min", "0")
        pe_max = data.get("pe_max", "25")
        conditions.append(f"市盈率大于{pe_min}且市盈率小于{pe_max}")

    # 市净率
    if data.get("pb_enabled"):
        pb_min = data.get("pb_min", "0")
        pb_max = data.get("pb_max", "3")
        conditions.append(f"市净率大于{pb_min}且市净率小于{pb_max}")

    # 商誉
    if data.get("goodwill_enabled"):
        op = data.get("goodwill_op", "<")
        val = data.get("goodwill_val", "10")
        unit = data.get("goodwill_unit", "亿")
        conditions.append(f"商誉{op}{val}{unit}")

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

    # 清理数据：NaN/Inf 在 JSON 中不合法，全部替换为 None
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

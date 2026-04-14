"""
A股选股器 - 基于同花顺问财(pywencai)
支持指标：营业总收入、扣非净利润、经营现金流、市盈率、市净率、商誉
"""

import pywencai
import pandas as pd
import sys


def screen(query: str) -> pd.DataFrame:
    """执行问财查询，返回DataFrame"""
    print(f"正在查询：{query}\n")
    result = pywencai.get(query=query)
    if result is None:
        print("查询无结果")
        return pd.DataFrame()
    if isinstance(result, dict):
        # pywencai有时返回dict，取第一个值
        for v in result.values():
            if isinstance(v, pd.DataFrame):
                return v
        print("返回格式异常:", type(result))
        return pd.DataFrame()
    return result


def main():
    # ========== 筛选条件（按需修改） ==========
    conditions = [
        "营业总收入大于50亿",
        "扣非净利润大于5亿",
        "经营现金流为正",
        "市盈率大于0且市盈率小于25",
        "市净率大于0且市净率小于3",
        "商誉小于10亿",
    ]

    query = " 且 ".join(conditions)

    df = screen(query)

    if df.empty:
        print("没有符合条件的股票")
        sys.exit(0)

    print(f"共筛选出 {len(df)} 只股票\n")
    print(df.to_string(max_rows=50))

    # 保存到csv
    output = "result.csv"
    df.to_csv(output, index=False, encoding="utf-8-sig")
    print(f"\n结果已保存到 {output}")


if __name__ == "__main__":
    main()

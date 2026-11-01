"""
일별 종가 수집 — '단가 발표일 기준' 주가 반응 분석용.

삼성전자(005930.KS)·SK하이닉스(000660.KS) 분할조정 일별 종가를
data/raw/prices_daily.csv 로 저장한다. (월말 패널과 별개, 이벤트 분석 전용)
"""
import os
import sys

import pandas as pd
import yfinance as yf

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "data", "raw", "prices_daily.csv")

SERIES = {"삼성전자": "005930.KS", "SK하이닉스": "000660.KS"}
START = "2025-10-01"


def fetch_close(ticker: str) -> pd.Series:
    df = yf.download(ticker, start=START, auto_adjust=True, progress=False)
    if df.empty:
        raise RuntimeError(f"no data for {ticker}")
    close = df["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return close


def main() -> int:
    cols = {}
    for name, tkr in SERIES.items():
        s = fetch_close(tkr)
        cols[name] = s
        print(f"  {name:8} {tkr:10} {len(s):4} rows  {s.index.min().date()}~{s.index.max().date()}")
    daily = pd.DataFrame(cols).dropna(how="all")
    daily.index = pd.to_datetime(daily.index).tz_localize(None)
    daily.index.name = "date"
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    daily.round(1).to_csv(OUT, encoding="utf-8-sig")
    print(f"저장: {OUT}  ({len(daily)}거래일)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
Phase A 데이터 수집 — 20년 월간 패널 만들기.

수집 대상 (모두 무료, 2006~현재):
  타깃: 005930.KS 삼성전자, 000660.KS SK하이닉스  (분할조정 종가)
  시그널: ^SOX 필라델피아반도체지수, MU 마이크론, KRW=X 원달러

월말(month-end) 종가로 정렬해 data/processed/panel_monthly.csv 로 저장.
"""
import os
import pandas as pd
import yfinance as yf

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "data", "processed")
os.makedirs(OUT, exist_ok=True)

SERIES = {
    "삼성전자": "005930.KS",
    "SK하이닉스": "000660.KS",
    "SOX": "^SOX",
    "마이크론": "MU",
    "USDKRW": "KRW=X",
}
START = "2006-01-01"


def fetch_close(ticker: str) -> pd.Series:
    df = yf.download(ticker, start=START, auto_adjust=True, progress=False)
    if df.empty:
        raise RuntimeError(f"no data for {ticker}")
    close = df["Close"]
    if isinstance(close, pd.DataFrame):  # yfinance MultiIndex for single ticker
        close = close.iloc[:, 0]
    return close


def main() -> None:
    cols = {}
    for name, tkr in SERIES.items():
        s = fetch_close(tkr)
        cols[name] = s
        print(f"  {name:10} {tkr:10} {len(s):5} rows  {s.index.min().date()}~{s.index.max().date()}")

    daily = pd.DataFrame(cols)
    # 월말 종가로 리샘플 (사이클은 월 단위로 충분 + 잡음 제거)
    monthly = daily.resample("ME").last()
    # 환율은 forward-fill 허용(주말/공휴일 결측), 그 외는 그대로
    monthly = monthly.ffill(limit=1)
    monthly.index.name = "date"

    raw_path = os.path.join(OUT, "panel_monthly.csv")
    monthly.to_csv(raw_path, encoding="utf-8-sig")
    print(f"\n저장: {raw_path}")
    print(f"기간: {monthly.index.min().date()} ~ {monthly.index.max().date()}  ({len(monthly)}개월)")
    print(monthly.tail(3).round(1).to_string())


if __name__ == "__main__":
    main()

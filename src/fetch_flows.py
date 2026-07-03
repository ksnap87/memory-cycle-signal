"""
투자자별 수급(순매수) 수집 — 삼성전자·SK하이닉스의 외국인·기관 월별 순매수(원) → 억원.

출처: KRX(pykrx). 로그인 불필요(공개 데이터). import 시 나오는 'KRX 로그인 실패' 경고는
프리미엄 기능용이라 이 조회에는 영향 없음.

핵심 함수:
  stock.get_market_trading_value_by_date(fromdate, todate, ticker, on='순매수', freq='m')
    → 컬럼: 기관합계 · 기타법인 · 개인 · 외국인합계 · 전체  (순매수 '거래대금', 단위 원)

사용:
  python3 src/fetch_flows.py            # 전체기간 수집 → data/raw/flows_investor.csv
  python3 src/fetch_flows.py --probe    # 최근 몇 달 원본 확인
"""
import os
import sys
import argparse
import pandas as pd

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(HERE, "data", "raw")
os.makedirs(RAW, exist_ok=True)

START_YYMMDD = "20100101"

# (종목명, 티커) — 패널 타깃과 동일
TICKERS = [("삼성전자", "005930"), ("SK하이닉스", "000660")]


def _pick(df: pd.DataFrame, *names: str) -> pd.Series:
    """여러 후보 컬럼명 중 실제 존재하는 것을 골라 반환(KRX 컬럼명 변형 방어)."""
    for n in names:
        if n in df.columns:
            return df[n]
    raise KeyError(f"기대 컬럼 없음 {names} — 실제 {list(df.columns)}")


def fetch_one(ticker: str, start: str, end: str) -> pd.DataFrame:
    """한 종목의 월별 외국인·기관 순매수(억원). index=월말."""
    from pykrx import stock
    raw = stock.get_market_trading_value_by_date(start, end, ticker, on="순매수", freq="m")
    if raw is None or raw.empty:
        return pd.DataFrame()
    foreign = _pick(raw, "외국인합계", "외국인")
    inst = _pick(raw, "기관합계", "기관")
    out = pd.DataFrame({"외국인_억": foreign / 1e8, "기관_억": inst / 1e8})
    out.index = pd.to_datetime(out.index) + pd.offsets.MonthEnd(0)   # 월말 정렬(패널과 동일)
    out.index.name = "date"
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true", help="최근 6개월만 찍어보기")
    args = ap.parse_args()

    end = pd.Timestamp.today().strftime("%Y%m%d")
    start = START_YYMMDD
    if args.probe:
        start = (pd.Timestamp.today() - pd.DateOffset(months=6)).strftime("%Y%m%d")

    frames = []
    for name, tk in TICKERS:
        df = fetch_one(tk, start, end)
        if df.empty:
            print(f"  ⚠ {name}({tk}): 빈 응답")
            continue
        df = df.rename(columns={c: f"{name}_{c}" for c in df.columns})
        frames.append(df)
        print(f"  {name}({tk}): {len(df)}개월")

    if not frames:
        sys.exit("수급 데이터 없음 — KRX 응답 비어있음")

    out = pd.concat(frames, axis=1).sort_index()

    if args.probe:
        print(out.tail(6).round(0).to_string())
        return

    out_path = os.path.join(RAW, "flows_investor.csv")
    out.to_csv(out_path, encoding="utf-8-sig")
    print(f"\n저장: {out_path}")
    print(f"기간: {out.index.min().date()} ~ {out.index.max().date()}  ({len(out)}개월)")
    print("최근 6개월(억원):")
    print(out.tail(6).round(0).to_string())


if __name__ == "__main__":
    main()

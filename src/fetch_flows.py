"""
투자자 수급(순매수) 수집 — 네이버 증권에서 삼성전자·SK하이닉스의 외국인·기관
'순매매량'(주)을 받아 월별 '추정 순매수 금액(억원, 순매매량×종가)'으로 집계.

왜 네이버인가: KRX/pykrx 는 해외(깃허브 액션) IP 에서 빈 응답을 준다(검증됨).

출처: 네이버 증권 모바일 JSON API (깃허브 액션에서 동작 확인, 2026-10)
  https://m.stock.naver.com/api/stock/{code}/trend?pageSize=60[&bizdate=YYYYMMDD]
  - pageSize 최대 60(100 이상은 HTTP 400). bizdate 를 주면 그 날짜 '이전' 거래일부터 돌려준다 → 커서 페이징.
  - 필드: bizdate · closePrice · foreignerPureBuyQuant · organPureBuyQuant (숫자는 "+1,234" 문자열)
  (예전 HTML 표 finance.naver.com/item/frgn.naver 는 2026-09 무렵 새 사이트로 리다이렉트되며 폐지됨
   → 표가 사라져 '빈 응답'으로 조용히 실패했었다.)

사용:
  python3 src/fetch_flows.py            # 수집 → data/raw/flows_investor.csv
  python3 src/fetch_flows.py --probe    # 최근 표 몇 줄만 확인
"""
import os
import sys
import time
import argparse
import pandas as pd
import requests

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(HERE, "data", "raw")
os.makedirs(RAW, exist_ok=True)

TICKERS = [("삼성전자", "005930"), ("SK하이닉스", "000660")]
API = "https://m.stock.naver.com/api/stock/{code}/trend"
PAGE_SIZE = 60                   # API 상한
MAX_CALLS = 8                    # 60×8 = 480거래일 ≈ 23개월 (월별 집계·기존 CSV 덮어쓰기엔 충분)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Referer": "https://m.stock.naver.com/",
}


def _num(s) -> float:
    try:
        return float(str(s).replace(",", "").replace("+", "").strip())
    except ValueError:
        return float("nan")


def parse_trend(items: list) -> pd.DataFrame:
    """API 응답 리스트 → [날짜, 종가, 기관주, 외국인주] (숫자화, 결측행 제거)."""
    rows = [{
        "날짜": pd.to_datetime(it.get("bizdate"), format="%Y%m%d", errors="coerce"),
        "종가": _num(it.get("closePrice")),
        "기관주": _num(it.get("organPureBuyQuant")),
        "외국인주": _num(it.get("foreignerPureBuyQuant")),
    } for it in items or []]
    out = pd.DataFrame(rows, columns=["날짜", "종가", "기관주", "외국인주"])
    return out.dropna(subset=["날짜", "종가"])


def fetch_daily(code: str, max_calls: int = MAX_CALLS) -> pd.DataFrame:
    """bizdate 커서로 과거로 넘겨 가며 일별 수급 수집. 실패는 이유를 남기고 멈춘다(조용한 실패 금지)."""
    frames, cursor = [], None
    for _ in range(max_calls):
        params = {"pageSize": PAGE_SIZE}
        if cursor:
            params["bizdate"] = cursor
        r = requests.get(API.format(code=code), params=params, headers=HEADERS, timeout=15)
        if r.status_code != 200 or "json" not in r.headers.get("content-type", ""):
            raise RuntimeError(f"HTTP {r.status_code} ({r.headers.get('content-type')}) {r.text[:120]!r}")
        part = parse_trend(r.json())
        if part.empty:
            break
        oldest = part["날짜"].min().strftime("%Y%m%d")
        if oldest == cursor:            # 커서가 안 넘어가면(같은 페이지 반복) 무한루프 방지
            break
        frames.append(part)
        cursor = oldest
        time.sleep(0.3)                 # 예의상 딜레이
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames).drop_duplicates("날짜").set_index("날짜").sort_index()


def fetch_one(code: str) -> pd.DataFrame:
    """한 종목 → 월별 {외국인_억, 기관_억}. 순매매량(주)×종가 → 원 → 억원.
    가장 오래된 달은 중간부터 받았을 수 있어(부분월) 버린다 → 그 달은 기존 CSV 값을 유지."""
    d = fetch_daily(code)
    if d.empty:
        return pd.DataFrame()
    # 일별 추정 순매수 금액(원) = 순매매량(주) × 종가(원)
    val = pd.DataFrame({
        "외국인_억": d["외국인주"] * d["종가"] / 1e8,
        "기관_억": d["기관주"] * d["종가"] / 1e8,
    })
    m = val.resample("ME").sum()          # 월별 합계(월말 인덱스 = 패널과 동일)
    m.index.name = "date"
    return m.iloc[1:] if len(m) > 1 else m


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true", help="첫 종목 최근 표 몇 줄 확인")
    args = ap.parse_args()

    if args.probe:
        print(fetch_daily(TICKERS[0][1], max_calls=1).tail(8).to_string())
        return

    frames = []
    for name, code in TICKERS:
        try:
            m = fetch_one(code)
        except Exception as e:
            print(f"  ⚠ {name}({code}): 수집 실패 — {e}")
            continue
        if m.empty:
            print(f"  ⚠ {name}({code}): 빈 응답")
            continue
        frames.append(m.rename(columns={c: f"{name}_{c}" for c in m.columns}))
        print(f"  {name}({code}): {len(m)}개월")

    if not frames:
        sys.exit("수급 데이터 없음 — 네이버 응답 비어있음")

    out = pd.concat(frames, axis=1).sort_index()
    out_path = os.path.join(RAW, "flows_investor.csv")
    # 기존 CSV 와 병합: 새로 받은 달은 덮어쓰고, 그보다 오래된 달은 그대로 보존
    if os.path.exists(out_path):
        old = pd.read_csv(out_path, index_col=0, parse_dates=True, encoding="utf-8-sig")
        if not old.empty:
            out = pd.concat([old[~old.index.isin(out.index)], out]).sort_index()
            out = out[[c for c in old.columns if c in out.columns] + [c for c in out.columns if c not in old.columns]]
    out.to_csv(out_path, encoding="utf-8-sig")
    print(f"\n저장: {out_path}")
    print(f"기간: {out.index.min().date()} ~ {out.index.max().date()}  ({len(out)}개월)")
    print("최근 6개월(억원):")
    print(out.tail(6).round(0).to_string())


if __name__ == "__main__":
    main()

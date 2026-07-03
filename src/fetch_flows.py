"""
투자자 수급(순매수) 수집 — 네이버 금융에서 삼성전자·SK하이닉스의 외국인·기관
'순매매량'(주)을 긁어 월별 '추정 순매수 금액(억원, 순매매량×종가)'으로 집계.

왜 네이버인가: KRX/pykrx 는 해외(깃허브 액션) IP 에서 빈 응답을 준다(검증됨).
네이버 금융 HTML 은 전역 접근이 되므로 CI 에서 동작할 가능성이 높다.

출처: https://finance.naver.com/item/frgn.naver?code={code}&page={n}
  표 헤더(2단): 날짜 · 종가 · 전일비 · 등락률 · 거래량 · 기관[순매매량] · 외국인[순매매량] · 외국인[보유주수] · 외국인[보유율]

사용:
  python3 src/fetch_flows.py            # 수집 → data/raw/flows_investor.csv
  python3 src/fetch_flows.py --probe    # 최근 표 몇 줄만 확인
"""
import os
import sys
import io
import argparse
import pandas as pd
import requests

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(HERE, "data", "raw")
os.makedirs(RAW, exist_ok=True)

TICKERS = [("삼성전자", "005930"), ("SK하이닉스", "000660")]
PAGES = 18                       # 1페이지≈10거래일 → ~18페이지≈9개월+ (월별 집계엔 충분)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Referer": "https://finance.naver.com/",
}


def _flatten(col) -> str:
    return "".join(str(x) for x in col) if isinstance(col, tuple) else str(col)


def parse_frgn_table(html: str) -> pd.DataFrame:
    """네이버 frgn 페이지 HTML → [날짜, 종가, 기관순매매량, 외국인순매매량] (숫자화, 결측행 제거).
    표 구조가 조금 달라도 '순매매량' 컬럼을 가진 표를 찾아 컬럼명 부분일치로 뽑는다."""
    tables = pd.read_html(io.StringIO(html))
    target = None
    for t in tables:
        flat = [_flatten(c) for c in t.columns]
        if any("순매매량" in f for f in flat) and any("날짜" in f for f in flat):
            target = t
            break
    if target is None:
        return pd.DataFrame()

    flat = {_flatten(c): c for c in target.columns}

    def pick(*keys):
        for want in keys:
            for f, c in flat.items():
                if all(k in f for k in want):
                    return target[c]
        return None

    date = pick(("날짜",))
    close = pick(("종가",))
    inst = pick(("기관", "순매매량"))
    frgn = pick(("외국인", "순매매량"))
    if any(x is None for x in (date, close, inst, frgn)):
        return pd.DataFrame()

    out = pd.DataFrame({"날짜": date, "종가": close, "기관주": inst, "외국인주": frgn})
    out = out.dropna(subset=["날짜"])
    for c in ("종가", "기관주", "외국인주"):
        out[c] = pd.to_numeric(
            out[c].astype(str).str.replace(",", "", regex=False).str.replace("+", "", regex=False),
            errors="coerce")
    out["날짜"] = pd.to_datetime(out["날짜"], format="%Y.%m.%d", errors="coerce")
    return out.dropna(subset=["날짜", "종가"])


def fetch_one(code: str, pages: int = PAGES) -> pd.DataFrame:
    """한 종목 → 월별 {외국인_억, 기관_억}. 순매매량(주)×종가 → 원 → 억원."""
    frames = []
    for p in range(1, pages + 1):
        url = f"https://finance.naver.com/item/frgn.naver?code={code}&page={p}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.encoding = "euc-kr"
            part = parse_frgn_table(r.text)
        except Exception:
            continue
        if not part.empty:
            frames.append(part)
    if not frames:
        return pd.DataFrame()

    d = pd.concat(frames).drop_duplicates("날짜").set_index("날짜").sort_index()
    # 일별 추정 순매수 금액(원) = 순매매량(주) × 종가(원)
    val = pd.DataFrame({
        "외국인_억": d["외국인주"] * d["종가"] / 1e8,
        "기관_억": d["기관주"] * d["종가"] / 1e8,
    })
    m = val.resample("ME").sum()          # 월별 합계(월말 인덱스 = 패널과 동일)
    m.index.name = "date"
    return m


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true", help="첫 종목 최근 표 몇 줄 확인")
    args = ap.parse_args()

    if args.probe:
        r = requests.get(f"https://finance.naver.com/item/frgn.naver?code={TICKERS[0][1]}&page=1",
                         headers=HEADERS, timeout=15)
        r.encoding = "euc-kr"
        print(parse_frgn_table(r.text).head(8).to_string())
        return

    frames = []
    for name, code in TICKERS:
        m = fetch_one(code)
        if m.empty:
            print(f"  ⚠ {name}({code}): 빈 응답")
            continue
        frames.append(m.rename(columns={c: f"{name}_{c}" for c in m.columns}))
        print(f"  {name}({code}): {len(m)}개월")

    if not frames:
        sys.exit("수급 데이터 없음 — 네이버 응답 비어있음")

    out = pd.concat(frames, axis=1).sort_index()
    out_path = os.path.join(RAW, "flows_investor.csv")
    out.to_csv(out_path, encoding="utf-8-sig")
    print(f"\n저장: {out_path}")
    print(f"기간: {out.index.min().date()} ~ {out.index.max().date()}  ({len(out)}개월)")
    print("최근 6개월(억원):")
    print(out.tail(6).round(0).to_string())


if __name__ == "__main__":
    main()

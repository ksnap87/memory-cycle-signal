"""
가설 검증: "전월比 단가 하락이 발표되면 매도 신호" — 발표일 기준 주가 반응.

월말 종가 비교는 '발표 전에 이미 빠진 몫'까지 섞인다. 여기서는 관세청 단가가
'발표된 날' 종가를 기준(매도 가정 시점)으로, 그 전·후 주가 변화를 나눠 본다.

발표일(두 가지로 계산, 둘 다 표시):
  rule     : 실적월 다음 달 15일(주말·휴일이면 다음 거래일) — 관세청 월간 확정치 관행
  observed : 이 저장소 파이프라인이 그 달 수출 데이터를 처음 받아온 날(data/history)
             → '늦어도 이 날엔 알 수 있었다'는 상한

구간:
  pre   : 실적월 다음 달 직전 월말 종가 → 발표일 종가   (신호 전, 피할 수 없던 몫)
  post5 / post10 / post20 : 발표일 종가 → N거래일 뒤 종가 (신호 보고 팔았으면 피한 몫)
  기준선: 분석기간 전체의 N거래일 수익률 평균 (아무 날이나 팔았을 때)

출력: data/processed/release_event_study.csv + 콘솔 요약(마크다운 표)
"""
import glob
import json
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPORTS = os.path.join(HERE, "data", "raw", "exports_semiconductor.csv")
DAILY = os.path.join(HERE, "data", "raw", "prices_daily.csv")
HIST = os.path.join(HERE, "data", "history")
OUT = os.path.join(HERE, "data", "processed", "release_event_study.csv")

FIRST_DATA_MONTH = "2025-12"   # 2026년에 발표된 첫 데이터(12월분)부터
STUDY_START = "2026-06-01"     # 분석 시작(저장소 첫 기록) — 이후 발표분이 '본 검증'
HORIZONS = (5, 10, 20)
PRODUCTS = {
    "메모리": ("메모리수출_854232_백만$", "메모리수출_854232_톤"),
    "디램": ("디램수출_백만$", "디램수출_톤"),
    "낸드": ("낸드수출_백만$", "낸드수출_톤"),
}
STOCKS = ("SK하이닉스", "삼성전자")


def unit_prices() -> pd.DataFrame:
    df = pd.read_csv(EXPORTS, parse_dates=["date"]).set_index("date")
    out = {}
    for name, (amt, ton) in PRODUCTS.items():
        p = df[amt] * 1e3 / df[ton].where(df[ton] > 0)
        out[f"{name}_MoM"] = p.pct_change() * 100
        out[f"{name}_YoY"] = p.pct_change(12) * 100
    res = pd.DataFrame(out)
    res.index = res.index.to_period("M")
    return res


def observed_release_dates() -> dict:
    """data/history 스냅샷에서 각 실적월이 처음 포착된 날짜."""
    first = {}
    files = sorted(glob.glob(os.path.join(HIST, "signals_*.json")))
    for f in files:
        day = pd.Timestamp(os.path.basename(f)[8:18])
        with open(f, encoding="utf-8") as fh:
            thru = json.load(fh).get("export_through")
        if not thru:
            continue
        last = pd.Period(thru, "M")
        for m in pd.period_range(FIRST_DATA_MONTH, last, freq="M"):
            first.setdefault(m, day)
    # 첫 스냅샷에 이미 있던 달은 '발표일'이 아니라 '기록 시작일'이라 제외
    if files:
        day0 = pd.Timestamp(os.path.basename(files[0])[8:18])
        first = {m: d for m, d in first.items() if d > day0}
    return first


def next_trading_day(idx: pd.DatetimeIndex, day: pd.Timestamp):
    pos = idx.searchsorted(day)
    return idx[pos] if pos < len(idx) else None


def ret(px: pd.Series, a, b):
    if a is None or b is None:
        return None
    return round((px.loc[b] / px.loc[a] - 1) * 100, 1)


def main() -> int:
    if not os.path.exists(DAILY):
        print(f"일별 주가 없음: {DAILY} — 먼저 src/fetch_prices_daily.py 실행", file=sys.stderr)
        return 1
    px = pd.read_csv(DAILY, parse_dates=["date"]).set_index("date").sort_index()
    idx = px.index
    up = unit_prices()
    obs = observed_release_dates()

    rows = []
    for m in up.index[up.index >= pd.Period(FIRST_DATA_MONTH, "M")]:
        nxt = (m + 1).to_timestamp()
        cands = {"rule": next_trading_day(idx, nxt + pd.Timedelta(days=14))}
        if m in obs:
            cands["observed"] = next_trading_day(idx, obs[m])
        prev_me = idx[idx < nxt]
        prev_me = prev_me[-1] if len(prev_me) else None
        for basis, rel in cands.items():
            if rel is None:
                continue
            pos = idx.get_loc(rel)
            row = {"실적월": str(m), "발표일기준": basis, "발표일": rel.date().isoformat(),
                   "본검증": rel >= pd.Timestamp(STUDY_START)}
            for name in PRODUCTS:
                row[f"{name}_MoM"] = round(up.loc[m, f"{name}_MoM"], 1)
                yoy, yoy_prev = up.loc[m, f"{name}_YoY"], up.loc[m - 1, f"{name}_YoY"]
                row[f"{name}_YoY둔화"] = bool(yoy < yoy_prev)
            row["디램_신호"] = row["디램_MoM"] < 0
            row["디램_신호_YoY둔화"] = row["디램_신호"] and row["디램_YoY둔화"]
            row["아무품목_신호"] = any(row[f"{n}_MoM"] < 0 for n in PRODUCTS)
            for s in STOCKS:
                row[f"{s}_pre"] = ret(px[s], prev_me, rel)
                for h in HORIZONS:
                    end = idx[pos + h] if pos + h < len(idx) else None
                    row[f"{s}_post{h}"] = ret(px[s], rel, end)
                row[f"{s}_post_가용일"] = min(len(idx) - 1 - pos, max(HORIZONS))
            rows.append(row)

    res = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    res.to_csv(OUT, index=False, encoding="utf-8-sig")

    # 기준선: 분석기간 아무 날이나 N거래일 보유 수익률 평균
    base_from = px.index >= pd.Timestamp("2026-01-01")
    print("\n## 기준선 (2026-01 이후 아무 날 기준 N거래일 수익률 평균)")
    for s in STOCKS:
        sp = px[s]
        vals = []
        for h in HORIZONS:
            fwd = (sp.shift(-h) / sp - 1) * 100
            vals.append(f"{h}일 {fwd[base_from].mean():+.1f}%")
        print(f"- {s}: " + " · ".join(vals))

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    for basis in ("rule", "observed"):
        sub = res[res["발표일기준"] == basis]
        if sub.empty:
            continue
        cols = ["실적월", "발표일", "본검증", "디램_MoM", "낸드_MoM", "메모리_MoM",
                "디램_YoY둔화", "디램_신호"]
        for s in STOCKS:
            cols += [f"{s}_pre"] + [f"{s}_post{h}" for h in HORIZONS]
        print(f"\n## 발표일 기준 = {basis}")
        print(sub[cols].to_string(index=False))
    print(f"\n저장: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

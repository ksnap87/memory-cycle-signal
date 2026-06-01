"""
Phase A 분석 — 어떤 펀더멘털 시그널이 주가에 선행하는가 + 매수/매도 구간은 어디인가.
(차트분석/기술적 지표 배제. 펀더멘털 수급·업황 신호만.)

논리(평이하게):
 1) 시그널을 '정상성' 형태(YoY, 전년대비 %)로 변환.
 2) 선행성: 시그널(t)이 그 다음 h개월 주가수익률을 얼마나 예측하나 (h=1/3/6/12).
 3) 매수/매도 구간: 시그널을 5분위로 나눠 각 구간 다음 12개월 평균수익률·승률.
 4) 지금 위치: 최신 시그널 값이 5분위 중 어디인가 → 현재 신호.

발행지연(lookahead 방지): 수출액은 월말 시점엔 '전월치'까지만 공표됨 → 1개월 시차 적용.
"""
import os
import json
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(HERE, "data", "processed")
RAW = os.path.join(HERE, "data", "raw")

TARGETS = ["삼성전자", "SK하이닉스"]
HORIZONS = [1, 3, 6, 12]

# 시그널 방향(백테스트로 확인): 'low'=값이 낮을수록(=침체) 매수우호, 'high'=높을수록 매수우호.
# 원달러만 반대 — 약달러원(원화약세)=수출 채산성↑이라 '높을수록' 주가에 우호적.
FAVORABLE_WHEN = {
    "SOX YoY": "low",
    "마이크론 YoY": "low",
    "원달러 YoY": "high",
    "반도체수출 YoY": "low",
    "메모리수출 YoY": "low",
}


def load() -> pd.DataFrame:
    df = pd.read_csv(os.path.join(PROC, "panel_monthly.csv"), parse_dates=["date"], index_col="date")
    exp_path = os.path.join(RAW, "exports_semiconductor.csv")
    if os.path.exists(exp_path):
        ex = pd.read_csv(exp_path, parse_dates=["date"], index_col="date")
        df = df.join(ex, how="left")
    return df


def yoy(s: pd.Series) -> pd.Series:
    s = s.replace(0, np.nan)                       # 0 베이스(초기 메모리수출=0) → inf 방지
    out = s.pct_change(12, fill_method=None) * 100
    return out.replace([np.inf, -np.inf], np.nan)


def fwd_return(s: pd.Series, h: int) -> pd.Series:
    """t 시점에서 본 다음 h개월 누적수익률 (%). 미래값=예측대상이므로 OK."""
    return (s.shift(-h) / s - 1.0) * 100


def build_signals(df: pd.DataFrame) -> dict:
    """분석에 쓸 펀더멘털 시그널(이미 변환·시차 적용된 시계열) 딕셔너리."""
    sigs = {
        "SOX YoY": yoy(df["SOX"]),            # 반도체 산업 업황 프록시
        "마이크론 YoY": yoy(df["마이크론"]),    # 순수 메모리기업 업황 프록시
        "원달러 YoY": yoy(df["USDKRW"]),       # 수출 채산성(약달러원=수출주 우호)
    }
    if "반도체수출_8542_백만$" in df.columns:
        # 핵심 선행지표. 발행지연 1개월 반영.
        sigs["반도체수출 YoY"] = yoy(df["반도체수출_8542_백만$"]).shift(1)
    if "메모리수출_854232_백만$" in df.columns:
        # 메모리(DRAM/NAND)만 분리 — 삼성·하이닉스 매출에 더 직결. 동일 1개월 시차.
        sigs["메모리수출 YoY"] = yoy(df["메모리수출_854232_백만$"]).shift(1)
    return sigs


def lead_lag_table(df: pd.DataFrame, sigs: dict) -> pd.DataFrame:
    rows = []
    for tgt in TARGETS:
        for lab, sig in sigs.items():
            for h in HORIZONS:
                fr = fwd_return(df[tgt], h)
                pair = pd.concat([sig, fr], axis=1).dropna()
                if len(pair) < 24:
                    continue
                r = pair.iloc[:, 0].corr(pair.iloc[:, 1])
                ic = pair.iloc[:, 0].corr(pair.iloc[:, 1], method="spearman")
                rows.append({"타깃": tgt, "시그널": lab, "선행개월": h,
                             "상관": round(r, 3), "IC": round(ic, 3), "표본": len(pair)})
    return pd.DataFrame(rows)


def quintile_backtest(df: pd.DataFrame, signal_series: pd.Series, label: str) -> pd.DataFrame:
    out = []
    for tgt in TARGETS:
        fr12 = fwd_return(df[tgt], 12)
        pair = pd.concat([signal_series.rename("sig"), fr12.rename("fwd")], axis=1).dropna()
        if len(pair) < 40:
            continue
        pair["q"] = pd.qcut(pair["sig"], 5, labels=["Q1(가장낮음)", "Q2", "Q3", "Q4", "Q5(가장높음)"])
        g = pair.groupby("q", observed=True)["fwd"]
        tab = pd.DataFrame({
            "평균수익12M(%)": g.mean().round(1),
            "승률(%)": (g.apply(lambda x: (x > 0).mean() * 100)).round(0),
            "표본": g.size(),
        })
        tab.insert(0, "타깃", tgt)
        tab.insert(0, "시그널", label)
        out.append(tab.reset_index())
    return pd.concat(out) if out else pd.DataFrame()


def current_position(signal_series: pd.Series, label: str) -> dict:
    s = signal_series.dropna()
    latest = s.iloc[-1]
    pct = (s < latest).mean() * 100
    q = int(min(4, pct // 20)) + 1
    fav = FAVORABLE_WHEN.get(label, "low")
    buy_score = (100 - pct) if fav == "low" else pct   # 높을수록 매수우호
    if buy_score >= 60:
        interp = "침체→매수권" if fav == "low" else "채산성↑→우호"
    elif buy_score <= 40:
        interp = "과열→매도권" if fav == "low" else "채산성↓→비우호"
    else:
        interp = "중립"
    return {"시그널": label, "방향": fav, "최신값": round(float(latest), 1),
            "퍼센타일": round(float(pct), 0), "분위": f"Q{q}", "해석": interp}


def main(since: str | None = None, tag: str = "full") -> None:
    df = load()
    if since:
        # YoY(12)+발행지연(1) 리드인을 위해 시작점을 13개월 앞에서 자른다 → 분석 유효구간은 since부터.
        df = df[df.index >= (pd.Timestamp(since) - pd.DateOffset(months=13))]
    sigs = build_signals(df)
    win = since if since else str(df.index.min().date())
    print("=" * 70)
    print(f"[{tag}] 분석구간 {win}~ | 패널 {df.index.min().date()}~{df.index.max().date()} ({len(df)}개월) | 시그널 {list(sigs)}")
    print("=" * 70)

    ll = lead_lag_table(df, sigs).dropna(subset=["상관"])
    best_h = ll.loc[ll.groupby(["타깃", "시그널"])["상관"].idxmax()]
    print("\n[1] 선행성 — 펀더멘털 시그널이 다음 h개월 주가수익률 예측 (상관 최대 h):")
    print(best_h.sort_values("상관", ascending=False).to_string(index=False))

    print("\n[2] 5분위 백테스트 — 시그널 구간별 '다음 12개월' 평균수익률·승률:")
    bt_all = []
    for lab, ser in sigs.items():
        bt = quintile_backtest(df, ser, lab)
        if bt.empty:
            continue
        bt_all.append(bt)
        print(f"\n  ── {lab} ──")
        print(bt.to_string(index=False))

    print("\n[3] 현재 위치 (최신 시그널이 과거 분포상 어디인가):")
    cur = [current_position(ser, lab) for lab, ser in sigs.items()]
    print(pd.DataFrame(cur).to_string(index=False))

    res = {
        "tag": tag,
        "analysis_start": win,
        "panel_period": [str(df.index.min().date()), str(df.index.max().date())],
        "n_months": len(df),
        "lead_lag_best": best_h.to_dict("records"),
        "current_position": cur,
    }
    with open(os.path.join(PROC, f"analysis_summary_{tag}.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    if bt_all:
        pd.concat(bt_all).to_csv(os.path.join(PROC, f"quintile_backtest_{tag}.csv"), index=False, encoding="utf-8-sig")
    print(f"\n저장: data/processed/analysis_summary_{tag}.json, quintile_backtest_{tag}.csv")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="분석 시작 YYYY-MM-DD (구조변화 이후 부분구간). 예: 2013-01-01")
    ap.add_argument("--tag", default=None, help="저장 파일 접미사")
    args = ap.parse_args()
    tag = args.tag or ("since" + args.since[:4] if args.since else "full")
    main(since=args.since, tag=tag)

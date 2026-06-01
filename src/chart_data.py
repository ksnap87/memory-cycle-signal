"""
인터랙티브 차트용 데이터 추출 — matplotlib 없이 순수 데이터(JSON)만 뽑는다.

기존 make_report.py 는 matplotlib 로 PNG 이미지를 그렸다(폰에서 너무 작음).
여기서는 '그림' 대신 '숫자'만 뽑아서 → 리포트 HTML 의 Chart.js 가 브라우저에서
반응형(폰 화면에 꽉 차고, 손가락으로 값 확인·확대) 그래프로 직접 그린다.

분위(1~5번)·백테스트 수익률 계산 로직은 make_report.py 와 100% 동일하게
analyze.quintile_backtest / 동일한 분위 경계를 그대로 재사용한다(숫자 어긋남 방지).
클라우드(CI)에서 matplotlib·한글폰트가 필요 없어진다.
"""
import os
import numpy as np
import pandas as pd

from analyze import (build_signals, yoy, fwd_return, quintile_backtest,
                     FAVORABLE_WHEN, TARGETS, HERE)

REPORTS = os.path.join(HERE, "reports")
os.makedirs(REPORTS, exist_ok=True)
CALIB_SINCE = "2013-01-01"

# 비전문가용 — 'YoY' 대신 쉬운 이름
PLAIN_LABEL = {
    "반도체수출 YoY": "반도체 수출",
    "메모리수출 YoY": "메모리 수출",
    "SOX YoY": "미국 반도체지수(SOX)",
    "마이크론 YoY": "마이크론(美 메모리社)",
}


def windowed(df: pd.DataFrame, since: str | None):
    if not since:
        return df
    return df[df.index >= (pd.Timestamp(since) - pd.DateOffset(months=13))]


def quintile_edges(dw: pd.DataFrame, ser: pd.Series) -> np.ndarray:
    """백테스트와 동일한 풀드 분포로 5분위 경계값(작년比 %) 산출 → 6개 edge."""
    frames = []
    for tgt in TARGETS:
        fr = fwd_return(dw[tgt], 12)
        p = pd.concat([ser.rename("sig"), fr.rename("fwd")], axis=1).dropna()
        frames.append(p)
    pp = pd.concat(frames)
    return pd.qcut(pp["sig"], 5, retbins=True)[1]


def edge_ticklabels(e: np.ndarray) -> list:
    """분위 경계값을 'Q1·Q2' 대신 '구체적 숫자 구간'으로."""
    return [f"≤{e[1]:+.0f}%", f"{e[1]:+.0f}~{e[2]:+.0f}",
            f"{e[2]:+.0f}~{e[3]:+.0f}", f"{e[3]:+.0f}~{e[4]:+.0f}", f"≥{e[4]:+.0f}%"]


def _aligned(series: pd.Series, idx: pd.Index, nd: int = 2) -> list:
    """series 를 공통 x축(idx)에 맞추고, 결측은 None(그래프 끊김)으로."""
    s = series.reindex(idx)
    return [None if pd.isna(v) else round(float(v), nd) for v in s.values]


def _labels(idx: pd.Index) -> list:
    return [ts.strftime("%Y-%m") for ts in idx]


# ─────────────────────────────────────────────────────────────
# 1) 사이클 동행 (섹션 4) — 위:주가(시작100·로그) / 아래:수출 YoY
# ─────────────────────────────────────────────────────────────
def data_cycle(df: pd.DataFrame) -> dict:
    idx = df.index
    out = {"labels": _labels(idx), "prices": [], "yoy": []}
    for tgt, color in [("삼성전자", "#0071e3"), ("SK하이닉스", "#ff9500")]:
        if tgt not in df.columns:
            continue
        s = df[tgt].dropna()
        if s.empty:
            continue
        norm = s / s.iloc[0] * 100
        out["prices"].append({"label": tgt, "color": color, "data": _aligned(norm, idx, 1)})
    for col, lab, color in [("반도체수출_8542_백만$", "반도체 수출 증가율", "#1f77b4"),
                            ("메모리수출_854232_백만$", "메모리 수출 증가율", "#d62728")]:
        if col in df.columns:
            out["yoy"].append({"label": lab, "color": color, "data": _aligned(yoy(df[col]), idx, 1)})
    return out


# ─────────────────────────────────────────────────────────────
# 2-a) 수출 금액 추이 (섹션 2 첫 그래프) — 20년 전체(가로 스크롤)
# ─────────────────────────────────────────────────────────────
def data_recent_exports(df: pd.DataFrame) -> dict:
    cols = [("반도체수출_8542_백만$", "반도체 수출", "#0071e3"),
            ("메모리수출_854232_백만$", "메모리 수출", "#ff3b30")]
    idx = None
    for col, _, _ in cols:
        if col in df.columns:
            i = df[col].dropna().index
            idx = i if idx is None else idx.union(i)
    if idx is None:
        return {"labels": [], "series": []}
    idx = idx.sort_values()
    series = []
    for col, lab, color in cols:
        if col not in df.columns:
            continue
        s = df[col].dropna() / 100.0          # 백만$ → 억$
        series.append({"label": lab, "color": color, "data": _aligned(s, idx, 0),
                       "last": round(float(s.iloc[-1]), 0),
                       "lastMonth": s.index[-1].strftime("%Y-%m")})
    return {"labels": _labels(idx), "series": series,
            "span": f"{idx[0].strftime('%Y')}~{idx[-1].strftime('%Y')}", "n": len(idx)}


# ─────────────────────────────────────────────────────────────
# 2-b) 메모리 수출 분해 (섹션 2 둘째 그래프) — 금액 vs 단가 vs 물량 (최근 N개월, 시작=100)
# ─────────────────────────────────────────────────────────────
def data_export_decomp(df: pd.DataFrame, months: int = 24) -> dict:
    v = df["메모리수출_854232_백만$"].dropna()
    w = df["메모리수출_854232_톤"].dropna()
    idx = v.index.intersection(w.index)[-months:]
    v, w = v[idx], w[idx]
    p = (v * 1e6) / (w * 1e3)                  # 백만$·톤 → $/kg

    def ix(s):
        return [round(float(x / s.iloc[0] * 100), 1) for x in s.values]

    return {"labels": _labels(idx), "base": idx[0].strftime("%y년 %m월"),
            "amount": ix(v), "price": ix(p), "volume": ix(w)}


# ─────────────────────────────────────────────────────────────
# 3) 분위별 1년 뒤 수익 (섹션 3) — 4개 지표 × (삼성·하이닉스) 막대
# ─────────────────────────────────────────────────────────────
def _q_series(bt: pd.DataFrame, tgt: str) -> list:
    t = bt[bt["타깃"] == tgt].sort_values("q")   # q 는 범주형 Q1..Q5 순
    if len(t) < 5:
        return [None] * 5
    return [round(float(x), 1) for x in t["평균수익12M(%)"].values[:5]]


def data_quintile_grid(df: pd.DataFrame) -> list:
    order = [l for l in ["반도체수출 YoY", "메모리수출 YoY", "SOX YoY", "마이크론 YoY"]
             if FAVORABLE_WHEN.get(l) == "low"]
    dw = windowed(df, CALIB_SINCE)
    sigs = build_signals(dw)
    charts = []
    for lab in order:
        if lab not in sigs:
            continue
        bt = quintile_backtest(dw, sigs[lab], lab)
        if bt.empty:
            continue
        e = quintile_edges(dw, sigs[lab])
        charts.append({
            "title": PLAIN_LABEL.get(lab, lab),
            "binlabels": [f"{i}번" for i in range(1, 6)],
            "ranges": edge_ticklabels(e),
            # 낮을수록(쌀 때) 초록 … 높을수록(비쌀 때) 빨강 (low_is_buy 기준)
            "bincolors": ["#34c759", "#34c759", "#8e8e93", "#ff3b30", "#ff3b30"],
            "samsung": _q_series(bt, "삼성전자"),
            "hynix": _q_series(bt, "SK하이닉스"),
        })
    return charts

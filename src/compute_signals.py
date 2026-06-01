"""
Phase B 핵심 — 최신 데이터로 '현재 신호등'을 다시 계산한다.

Phase A(make_config.py)가 만든 signal_config.yaml 의 임계값·가중치는 그대로 쓰고,
'현재값/퍼센타일/존(매수·중립·매도)'만 매주 최신 패널로 재계산한다.
  → 결과를 docs/signals.json 으로 저장(대시보드가 읽음) + data/history/ 에 주간 스냅샷 누적.

차트분석 배제 — 펀더멘털(수출·업황 프록시·환율)만. 투자권유 아님.
"""
import os
import json
import datetime as dt
import pandas as pd
import yaml

from analyze import load, build_signals, FAVORABLE_WHEN, HERE, PROC

DOCS = os.path.join(HERE, "docs")
HIST = os.path.join(HERE, "data", "history")
os.makedirs(DOCS, exist_ok=True)
os.makedirs(HIST, exist_ok=True)

# 라벨별 표시명·신뢰도(별)·한줄설명 — 대시보드 표기용(판단 포함이라 코드에 명시)
META = {
    "반도체수출 YoY": ("반도체 수출", "★★★", "실제 통관된 실물 금액 — 가장 믿을만"),
    "메모리수출 YoY": ("메모리 수출", "★★★", "D램·낸드만 — 삼성·하이닉스 매출 직결"),
    "SOX YoY": ("미국 반도체지수", "★★", "업황 잘 맞지만 '주가'라 보조"),
    "마이크론 YoY": ("마이크론(美 메모리)", "★★", "메모리 업황 프록시 — '주가'라 보조"),
    "원달러 YoY": ("원/달러 환율", "★", "약달러원=수출 우호 · 거드는 정도"),
}
SPARK_MONTHS = 24


def calib_start(cfg: dict) -> pd.Timestamp:
    """config meta 의 calibration_window 시작일 파싱(없으면 2013-01-01)."""
    win = cfg.get("meta", {}).get("calibration_window", "2013-01-01 ~")
    return pd.Timestamp(win.split("~")[0].strip())


def zone_of(yoy_val: float, thr: dict, direction: str) -> str:
    """config 임계값으로 현재 존 판정. low_is_buy=낮을수록 매수, 원달러는 반대."""
    if direction == "low_is_buy":
        if yoy_val <= thr["buy_below"]:
            return "매수권"
        if yoy_val >= thr["sell_above"]:
            return "매도권"
    else:  # high_is_buy
        if yoy_val >= thr["buy_above"]:
            return "매수권"
        if yoy_val <= thr["sell_below"]:
            return "매도권"
    return "중립"


def main() -> None:
    df = load()
    sigs = build_signals(df)
    with open(os.path.join(HERE, "signal_config.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    sig_cfg = cfg.get("signals", {})
    since = calib_start(cfg)

    out_signals = []
    score = 0.0
    for lab, c in sig_cfg.items():
        ser = sigs.get(lab)
        if ser is None:
            continue
        s = ser.dropna()
        if s.empty:
            continue
        latest = float(s.iloc[-1])
        calib = s[s.index >= since]
        pct = round(float((calib < latest).mean() * 100), 0)
        direction = c["direction"]
        zone = zone_of(latest, c["thresholds"], direction)
        # 분위(Q): low_is_buy는 낮을수록 Q1, high_is_buy(원달러)는 높을수록 Q1(=매수쪽)
        q_raw = int(min(4, pct // 20)) + 1
        q = q_raw if direction == "low_is_buy" else (6 - q_raw)
        weight = c.get("weight", 0.0)
        if zone == "매수권":
            score += weight
        elif zone == "매도권":
            score -= weight

        name, stars, trust = META.get(lab, (lab, "", ""))
        spark = [round(float(v), 1) for v in s.iloc[-SPARK_MONTHS:].tolist()]
        # 20년 칸(1~5번)별 '그때 샀으면 1년 뒤 평균수익%' — Phase A 백테스트 결과(고정).
        # 대시보드 '칸별 성적표' 막대그래프용. 매주 재계산 안 함(보정창 고정값).
        bt_q = [None] * 5
        for item in c.get("backtest_quintiles", []):
            qi = int(item.get("q", 0))
            if 1 <= qi <= 5:
                bt_q[qi - 1] = round(float(item.get("fwd12_mean", 0.0)), 1)
        qb = c.get("quintile_boundaries", {}) or {}
        bins_pct = [qb.get("P20"), qb.get("P40"), qb.get("P60"), qb.get("P80")]
        out_signals.append({
            "label": lab, "name": name, "stars": stars, "trust": trust,
            "direction": direction, "yoy": round(latest, 1), "percentile": pct,
            "q": q, "zone": zone, "weight": weight,
            "thresholds": c["thresholds"],
            "asof": s.index[-1].strftime("%Y-%m"),
            "spark": spark,
            "bt_q": bt_q,
            "bins_pct": bins_pct,
        })

    score = round(score, 3)
    if score <= -0.6:
        verdict, color = "강한 과열 — 차익실현(매도) 구간", "#ff3b30"
    elif score <= -0.2:
        verdict, color = "과열 쪽 — 신규매수 비추천", "#ff9500"
    elif score < 0.2:
        verdict, color = "중립", "#8e8e93"
    elif score < 0.6:
        verdict, color = "바닥 쪽 — 분할매수 고려", "#34c759"
    else:
        verdict, color = "강한 침체 — 매수 구간", "#34c759"

    # 데이터 신선도: 수출은 발행지연 1개월이라 패널 최신월보다 늦음
    price_through = df[["삼성전자", "SK하이닉스"]].dropna(how="all").index[-1].strftime("%Y-%m")
    exp_col = "반도체수출_8542_백만$"
    exp_through = (df[exp_col].dropna().index[-1].strftime("%Y-%m")
                   if exp_col in df.columns and df[exp_col].notna().any() else None)

    result = {
        "updated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "price_through": price_through,
        "export_through": exp_through,
        "composite": {"score": score, "verdict": verdict, "color": color},
        "calibration": cfg.get("meta", {}).get("calibration_window", ""),
        "signals": out_signals,
        "notes": cfg.get("meta", {}).get("notes", []),
    }

    out_path = os.path.join(DOCS, "signals.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 주간 스냅샷 누적(추세 추적용) — 같은 날 재실행은 덮어씀
    snap = os.path.join(HIST, f"signals_{dt.date.today().isoformat()}.json")
    with open(snap, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"저장: {out_path}")
    print(f"  종합점수 {score:+.2f} → {verdict}")
    print(f"  주가 {price_through} / 수출 {exp_through}")
    for s in out_signals:
        print(f"  {s['name']:14s} {s['stars']:3s} | {s['zone']:4s} | "
              f"YoY {s['yoy']:+7.1f}% (상위 {100 - s['percentile']:.0f}%) {s['q']}번")


if __name__ == "__main__":
    main()

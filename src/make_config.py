"""
Phase A 최종 산출 ① — signal_config.yaml 생성.

각 펀더멘털 시그널의 (1) 방향 (2) 분위 경계값 (3) 분위별 다음12개월 성과
(4) 매수/매도 임계값 (5) 가중치 를 데이터에서 직접 산출해 기록한다.
Phase B(주간 클라우드 모니터)가 이 파일을 읽어 '현재 신호등'을 계산한다.

캘리브레이션 구간 = 2013-01 이후(엘피다·키몬다 파산 후 3사 과점 확립).
  → 현재 시장구조와 동일한 구간에서 임계값을 잡는 게 타당.
임계값 규칙(분위 기반):
  - low=buy 시그널: YoY ≤ P40 → 매수권,  YoY ≥ P60 → 매도권
  - high=buy 시그널(원달러): 반대.
가중치: 분위 양끝 수익률 격차(Q1−Q5, 방향보정)에 비례 → 잘 갈리는 신호일수록 큰 가중.
"""
import os
import datetime as dt
import numpy as np
import pandas as pd
import yaml

from analyze import load, build_signals, fwd_return, FAVORABLE_WHEN, TARGETS, PROC, HERE

CALIB_SINCE = "2013-01-01"
PCTS = [20, 40, 60, 80]


def pooled_pairs(df: pd.DataFrame, sig: pd.Series) -> pd.DataFrame:
    """두 종목의 (시그널, 다음12M수익률) 쌍을 한 데 모아 분위 통계를 안정화."""
    frames = []
    for tgt in TARGETS:
        fr = fwd_return(df[tgt], 12)
        p = pd.concat([sig.rename("sig"), fr.rename("fwd")], axis=1)
        p = p[p.index >= CALIB_SINCE].dropna()
        frames.append(p)
    return pd.concat(frames) if frames else pd.DataFrame(columns=["sig", "fwd"])


def quintile_table(pairs: pd.DataFrame) -> list:
    q = pd.qcut(pairs["sig"], 5, labels=[1, 2, 3, 4, 5])
    g = pairs.groupby(q, observed=True)["fwd"]
    out = []
    for qi, mean, win, n in zip(g.groups.keys(), g.mean(), g.apply(lambda x: (x > 0).mean() * 100), g.size()):
        out.append({"q": int(qi), "fwd12_mean": round(float(mean), 1),
                    "win_rate": round(float(win), 0), "n": int(n)})
    return out


def main() -> None:
    df = load()
    sigs = build_signals(df)

    signals_cfg = {}
    spreads = {}
    for lab, ser in sigs.items():
        fav = FAVORABLE_WHEN.get(lab, "low")
        calib = ser[ser.index >= CALIB_SINCE].dropna()
        if len(calib) < 40:
            continue
        cuts = {f"P{p}": round(float(np.percentile(calib, p)), 1) for p in PCTS}
        qt = quintile_table(pooled_pairs(df, ser))
        qmap = {r["q"]: r for r in qt}

        # 방향보정 격차 → 가중치 근거. 수익격차(크기)+승률격차(신뢰도)를 함께 반영.
        lo, hi = (1, 5) if fav == "low" else (5, 1)   # lo=매수존 분위, hi=매도존 분위
        spread = (qmap[lo]["fwd12_mean"] - qmap[hi]["fwd12_mean"]) \
            + (qmap[lo]["win_rate"] - qmap[hi]["win_rate"])
        if fav == "low":
            thresholds = {"buy_below": cuts["P40"], "sell_above": cuts["P60"]}
        else:
            thresholds = {"buy_above": cuts["P60"], "sell_below": cuts["P40"]}
        spreads[lab] = max(spread, 0.0)

        latest = float(ser.dropna().iloc[-1])
        pct = round(float((calib < latest).mean() * 100), 0)
        zone = ("매수권" if (latest <= cuts["P40"]) else "매도권" if (latest >= cuts["P60"]) else "중립") \
            if fav == "low" else \
            ("매수권" if (latest >= cuts["P60"]) else "매도권" if (latest <= cuts["P40"]) else "중립")

        signals_cfg[lab] = {
            "direction": "low_is_buy" if fav == "low" else "high_is_buy",
            "lead_months": 1,
            "quintile_boundaries": cuts,
            "thresholds": thresholds,
            "backtest_quintiles": qt,
            "current": {"yoy": round(latest, 1), "percentile": pct, "zone": zone},
        }

    # 가중치 = 격차 비례, 합 1.0
    tot = sum(spreads.values()) or 1.0
    for lab in signals_cfg:
        signals_cfg[lab]["weight"] = round(spreads.get(lab, 0.0) / tot, 3)

    cfg = {
        "meta": {
            "generated_at": dt.date.today().isoformat(),
            "calibration_window": f"{CALIB_SINCE} ~ {df.index.max().date()}",
            "panel_period": f"{df.index.min().date()} ~ {df.index.max().date()}",
            "targets": {"삼성전자": "005930.KS", "SK하이닉스": "000660.KS"},
            "transform": "YoY(전년대비%), 수출은 발행지연 1개월 시차",
            "method": "5분위 백테스트(다음 12개월 수익률·승률) → P40/P60 임계값",
            "notes": [
                "상관≠인과. 분석용이며 투자권유 아님.",
                "현재 시그널은 20년 중 최고 과열(99~100퍼센타일) — 학습범위 밖 외삽 주의(AI/HBM 구조변화 가능).",
                "정밀 타이밍 아님 — '사이클 체온계'(바닥권/천장권 판별).",
            ],
        },
        "composite_rule": {
            "buy_signal_score": ">= 0.6",
            "sell_signal_score": "<= -0.6",
            "desc": "신호별 매수=+1·중립=0·매도=−1 에 weight 가중합 → [-1,+1]. 음수=과열/매도권.",
        },
        "signals": signals_cfg,
    }

    out_path = os.path.join(HERE, "signal_config.yaml")
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    print("저장:", out_path)
    print("=" * 60)
    for lab, c in signals_cfg.items():
        t = c["thresholds"]
        print(f"{lab:12s} | dir={c['direction']:11s} w={c['weight']:.3f} | "
              f"임계 {t} | 현재 {c['current']}")


if __name__ == "__main__":
    main()

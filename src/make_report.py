"""
Phase A 최종 산출 ② — reports/백테스트_리포트_v1.html 생성.

20년 펀더멘털 시그널 검증 결과를 비전문가도 읽을 수 있게 한 장으로 정리.
차트(사이클 동행성 · 분위별 수익)는 base64로 HTML에 내장 → 파일 하나로 자체완결.
파일 버전관리: _v1 고정. 다음 갱신은 _v2 새 파일(덮어쓰기 금지).
"""
import os
import io
import base64
import html
import datetime as dt
import numpy as np
import pandas as pd
import yaml
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

from analyze import (load, build_signals, yoy, fwd_return, lead_lag_table, quintile_backtest,
                     current_position, FAVORABLE_WHEN, TARGETS, HERE, PROC)

REPORTS = os.path.join(HERE, "reports")
os.makedirs(REPORTS, exist_ok=True)
CALIB_SINCE = "2013-01-01"

for _cand in ["AppleGothic", "Apple SD Gothic Neo", "NanumGothic", "Malgun Gothic"]:
    try:
        font_manager.findfont(_cand, fallback_to_default=False)
        plt.rcParams["font.family"] = _cand
        break
    except Exception:
        continue
plt.rcParams["axes.unicode_minus"] = False


def fig_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def windowed(df: pd.DataFrame, since: str | None):
    if not since:
        return df
    return df[df.index >= (pd.Timestamp(since) - pd.DateOffset(months=13))]


def chart_cycle(df: pd.DataFrame) -> str:
    """위: 주가(정규화·로그). 아래: 반도체·메모리 수출 YoY. 사이클 동행/현재 극단을 시각화."""
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True,
                                 gridspec_kw={"height_ratios": [1.3, 1]})
    for tgt in TARGETS:
        s = df[tgt].dropna()
        a1.plot(s.index, s / s.iloc[0] * 100, label=tgt, lw=1.4)
    a1.set_yscale("log")
    a1.set_title("삼성전자 · SK하이닉스 주가 (시작=100, 로그축)")
    a1.legend(loc="upper left", fontsize=9)
    a1.grid(True, alpha=0.3)

    for col, lab, c in [("반도체수출_8542_백만$", "반도체수출 YoY", "#1f77b4"),
                        ("메모리수출_854232_백만$", "메모리수출 YoY", "#d62728")]:
        if col in df.columns:
            y = yoy(df[col])
            a2.plot(y.index, y, label=lab, lw=1.2, color=c)
    a2.axhline(0, color="k", lw=0.8)
    a2.set_title("반도체 수출 YoY (%) — 바닥=업황침체(매수권), 급등=과열(매도권)")
    a2.legend(loc="upper left", fontsize=9)
    a2.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig_b64(fig)


# 비전문가용 — 'YoY' 같은 용어 대신 쉬운 이름으로 범례 표기
PLAIN_LABEL = {
    "반도체수출 YoY": "반도체 수출",
    "메모리수출 YoY": "메모리 수출",
    "SOX YoY": "미국 반도체지수(SOX)",
    "마이크론 YoY": "마이크론(美 메모리社)",
}
SIG_COLORS = ["#0071e3", "#34c759", "#ff9500", "#af52de"]


def chart_quintile(df: pd.DataFrame) -> str:
    """과거를 시그널 크기로 5등분(Q1~Q5) → 각 구간에서 산 뒤 다음12M 평균수익률.
    삼성전자·SK하이닉스 둘 다, 막대 위 숫자 표시, 쉬운 범례."""
    order = [l for l in ["반도체수출 YoY", "메모리수출 YoY", "SOX YoY", "마이크론 YoY"]
             if FAVORABLE_WHEN.get(l) == "low"]
    dw = windowed(df, CALIB_SINCE)
    sigs = build_signals(dw)

    fig, axes = plt.subplots(2, 1, figsize=(12, 9), sharex=True)
    x = np.arange(5)
    w = 0.2
    for ax, tgt in zip(axes, TARGETS):
        for i, lab in enumerate(order):
            bt = quintile_backtest(dw, sigs[lab], lab)
            if bt.empty:
                continue
            sam = bt[bt["타깃"] == tgt].sort_values("q")
            bars = ax.bar(x + (i - 1.5) * w, sam["평균수익12M(%)"].values, width=w,
                          label=PLAIN_LABEL.get(lab, lab), color=SIG_COLORS[i % len(SIG_COLORS)])
            ax.bar_label(bars, fmt="%+.0f", fontsize=7.5, padding=2, color="#3a3a3c")
        ax.axhline(0, color="#1d1d1f", lw=1.0)
        ax.set_title(tgt, fontsize=13, fontweight="bold", loc="left", color="#1d1d1f")
        ax.set_ylabel("1년 뒤 평균수익률 (%)", fontsize=10.5)
        ax.grid(True, axis="y", alpha=0.25)
        ax.margins(y=0.18)

    axes[-1].set_xticks(x)
    axes[-1].set_xticklabels(["Q1\n바닥(쌀 때)", "Q2", "Q3", "Q4", "Q5\n천장(비쌀 때)"], fontsize=11)

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=4, fontsize=10.5,
               frameon=True, fancybox=True, framealpha=0.96, edgecolor="#d2d2d7",
               handlelength=1.2, columnspacing=1.6, bbox_to_anchor=(0.5, 0.99))
    fig.suptitle("바닥(Q1)에서 사면 1년 뒤 많이 오르고, 천장(Q5)에서 사면 손해 — 2013년 이후",
                 fontsize=13.5, y=1.045, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    return fig_b64(fig)


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


def chart_quintile_grid(df: pd.DataFrame) -> str:
    """비전문가용 — 4개 지표 × 삼성·하이닉스 = 8개 계열을 2×2 작은그림으로.
    'Q1~Q5' 대신 각 지표의 '작년比 실제 숫자 구간'을 x축에 표기.
    막대 높이 = 그때 샀으면 1년 뒤 주가 수익률(지표 변화가 아님)."""
    order = [l for l in ["반도체수출 YoY", "메모리수출 YoY", "SOX YoY", "마이크론 YoY"]
             if FAVORABLE_WHEN.get(l) == "low"]
    dw = windowed(df, CALIB_SINCE)
    sigs = build_signals(dw)
    fig, axes = plt.subplots(2, 2, figsize=(13, 9.2))
    palette = {"삼성전자": "#0071e3", "SK하이닉스": "#ff9500"}
    x = np.arange(5)
    w = 0.38
    for ax, lab in zip(axes.flat, order):
        bt = quintile_backtest(dw, sigs[lab], lab)
        e = quintile_edges(dw, sigs[lab])
        for j, tgt in enumerate(TARGETS):
            t = bt[bt["타깃"] == tgt].sort_values("q")
            if t.empty:
                continue
            bars = ax.bar(x + (j - 0.5) * w, t["평균수익12M(%)"].values, width=w,
                          label=tgt, color=palette[tgt])
            ax.bar_label(bars, fmt="%+.0f", fontsize=8.5, padding=2,
                         fontweight="bold", color="#1d1d1f")
        ax.axhline(0, color="#1d1d1f", lw=0.9)
        ax.set_xticks(x)
        ax.set_xticklabels(edge_ticklabels(e), fontsize=8.4)
        ax.set_title(PLAIN_LABEL.get(lab, lab) + " — 작년比 변화율 구간",
                     fontsize=11, fontweight="bold", loc="left", color="#1d1d1f")
        ax.set_xlabel("← 침체(쌀 때) ······ 과열(비쌀 때) →", fontsize=8.6, color="#8e8e93")
        ax.set_ylabel("1년 뒤 수익률(%)", fontsize=9.5)
        ax.grid(True, axis="y", alpha=0.22)
        ax.margins(y=0.22)
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=2, fontsize=12.5,
               frameon=True, fancybox=True, framealpha=0.96, edgecolor="#d2d2d7",
               bbox_to_anchor=(0.5, 0.997))
    fig.suptitle("막대 높이 = 그때 샀으면 '1년 뒤 주가 수익률(%)'  ·  파랑 삼성전자 / 주황 SK하이닉스",
                 fontsize=12.5, y=1.035, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    return fig_b64(fig)


def chart_recent_exports(df: pd.DataFrame, months: int = 24) -> str:
    """최근 N개월 '실제 수출 금액($)' 추이 — 지금 늘고 있나/꺾였나를 눈으로 확인."""
    cols = [("반도체수출_8542_백만$", "반도체 수출", "#0071e3"),
            ("메모리수출_854232_백만$", "메모리 수출", "#ff3b30")]
    fig, ax = plt.subplots(figsize=(11, 5))
    for col, lab, c in cols:
        if col not in df.columns:
            continue
        s = (df[col].dropna() / 100.0).iloc[-months:]   # 백만$ → 억$
        ax.plot(s.index, s.values, marker="o", ms=4, lw=2, color=c, label=lab)
        ax.scatter([s.index[-1]], [s.values[-1]], s=90, color=c, zorder=5,
                   edgecolor="white", linewidth=1.5)
        ax.annotate(f"{s.values[-1]:.0f}억$", (s.index[-1], s.values[-1]),
                    textcoords="offset points", xytext=(8, 6), fontsize=10.5,
                    fontweight="bold", color=c)
    ax.set_ylabel("월 수출 금액 (억 달러)", fontsize=11.5)
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=11.5, loc="upper left", frameon=True, fancybox=True, edgecolor="#d2d2d7")
    ax.set_title(f"최근 {months}개월 반도체·메모리 수출 금액 — 사상 최고 수준, 최근 1~2달은 상승세 주춤(횡보)",
                 fontsize=12.5, fontweight="bold", pad=12)
    ax.text(0.5, -0.26,
            "※ '금액(달러)' 기준 — 수량(개수) 아님. 아래 그림에서 '물량 vs 단가'로 분해해 봅니다.",
            transform=ax.transAxes, ha="center", fontsize=9, color="#8e8e93")
    fig.autofmt_xdate(rotation=30)
    fig.tight_layout()
    return fig_b64(fig)


def chart_export_decomp(df: pd.DataFrame, months: int = 24) -> str:
    """메모리 수출의 금액 vs 물량(톤) vs 평균단가($/kg) — 시작점=100 지수.
    '늘어난 건 가격(단가)이지 물량이 아니다'를 눈으로 확인."""
    v = df["메모리수출_854232_백만$"].dropna()
    w = df["메모리수출_854232_톤"].dropna()
    idx = v.index.intersection(w.index)[-months:]
    v, w = v[idx], w[idx]
    p = (v * 1e6) / (w * 1e3)            # 백만$·톤 → $/kg
    base = idx[0].strftime("%y년 %m월")

    def ix(s):
        return s / s.iloc[0] * 100

    fig, ax = plt.subplots(figsize=(11, 5.2))
    ax.plot(idx, ix(v), marker="o", ms=3.5, lw=2.6, color="#ff3b30", label="수출액(금액·달러)")
    ax.plot(idx, ix(p), marker="o", ms=3.5, lw=2.6, color="#af52de", label="평균단가($/kg)")
    ax.plot(idx, ix(w), marker="o", ms=3.0, lw=2.0, color="#34c759", label="물량(톤·무게)")
    ax.axhline(100, color="#c7c7cc", lw=1.0, ls="--")
    for s, c in [(v, "#ff3b30"), (p, "#af52de"), (w, "#34c759")]:
        ax.annotate(f"{ix(s).iloc[-1]:.0f}", (idx[-1], ix(s).iloc[-1]),
                    textcoords="offset points", xytext=(8, 0), fontsize=10,
                    fontweight="bold", color=c, va="center")
    ax.set_ylabel(f"{base} = 100 기준 지수", fontsize=11)
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=11, loc="upper left", frameon=True, fancybox=True, edgecolor="#d2d2d7")
    ax.set_title("메모리 수출이 늘어난 건 '단가(가격)'이지 '물량'이 아니다",
                 fontsize=12.5, fontweight="bold", pad=12)
    ax.text(0.5, -0.27,
            "※ 빨강(금액)과 보라(단가)는 같이 치솟고, 초록(물량)은 거의 제자리 → 'AI·HBM 가격 폭등'의 전형.",
            transform=ax.transAxes, ha="center", fontsize=9, color="#8e8e93")
    fig.autofmt_xdate(rotation=30)
    fig.tight_layout()
    return fig_b64(fig)


def df_to_html(d: pd.DataFrame) -> str:
    return d.to_html(index=False, border=0, classes="tbl", justify="center")


def section_tables(df: pd.DataFrame, since: str | None):
    dw = windowed(df, since)
    sigs = build_signals(dw)
    ll = lead_lag_table(dw, sigs).dropna(subset=["상관"])
    best = ll.loc[ll.groupby(["타깃", "시그널"])["상관"].idxmax()].sort_values("상관", ascending=False)
    qparts = []
    for lab, ser in sigs.items():
        bt = quintile_backtest(dw, ser, lab)
        if not bt.empty:
            qparts.append(bt)
    qt = pd.concat(qparts) if qparts else pd.DataFrame()
    cur = pd.DataFrame([current_position(s, l) for l, s in sigs.items()])
    return best, qt, cur


def main() -> None:
    df = load()
    cfg = {}
    cfg_path = os.path.join(HERE, "signal_config.yaml")
    if os.path.exists(cfg_path):
        with open(cfg_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

    cycle_png = chart_cycle(df)
    quint_png = chart_quintile(df)

    best_full, qt_full, cur_full = section_tables(df, None)
    best_13, qt_13, _ = section_tables(df, CALIB_SINCE)

    # 채택 시그널 가중치 요약
    wrows = []
    for lab, c in (cfg.get("signals") or {}).items():
        t = c["thresholds"]
        thr = (f"≤{t['buy_below']} 매수 / ≥{t['sell_above']} 매도" if c["direction"] == "low_is_buy"
               else f"≥{t['buy_above']} 매수 / ≤{t['sell_below']} 매도")
        wrows.append({"시그널": lab, "방향": c["direction"], "가중치": c["weight"],
                      "임계값(YoY%)": thr, "현재": f"{c['current']['yoy']} ({c['current']['zone']})"})
    wtab = pd.DataFrame(wrows)

    period = f"{df.index.min().date()} ~ {df.index.max().date()} ({len(df)}개월)"
    today = dt.date.today().isoformat()

    style = """
    <style>
      body{font-family:-apple-system,'Apple SD Gothic Neo',sans-serif;max-width:980px;margin:24px auto;
           padding:0 16px;color:#1d1d1f;line-height:1.65}
      h1{font-size:1.7rem} h2{margin-top:2em;border-bottom:2px solid #0071e3;padding-bottom:.3em}
      h3{margin-top:1.4em;color:#0071e3}
      .tbl{border-collapse:collapse;width:100%;font-size:.86rem;margin:.6em 0}
      .tbl th,.tbl td{border:1px solid #d2d2d7;padding:5px 8px;text-align:center}
      .tbl th{background:#f5f5f7}
      .box{background:#f5f5f7;border-radius:12px;padding:14px 18px;margin:1em 0}
      .warn{background:#fff4e5;border-left:4px solid #ff9500;border-radius:8px;padding:12px 16px;margin:1em 0}
      .key{background:#e8f3ff;border-left:4px solid #0071e3;border-radius:8px;padding:12px 16px;margin:1em 0}
      img{max-width:100%;border-radius:10px;border:1px solid #e5e5ea;margin:.5em 0}
      .muted{color:#6e6e73;font-size:.85rem}
      code{background:#f5f5f7;padding:1px 5px;border-radius:4px}
    </style>"""

    body = f"""
    <h1>메모리 사이클 시그널 — 20년 백테스트 리포트 <span class="muted">v1</span></h1>
    <p class="muted">생성일 {today} · 분석기간 {period} · 대상: 삼성전자(005930)·SK하이닉스(000660)</p>

    <div class="key"><b>한 줄 요약.</b> 차트분석 없이 펀더멘털 시그널(반도체·메모리 수출, SOX, 마이크론, 환율)만으로
    "지금 사이클이 바닥권이냐 천장권이냐"를 판별한다. 20년 검증 결과 <b>침체 구간(Q1)에서 사면 다음 12개월
    승률 93~100%</b>로 깨끗하게 갈렸다. <b>다만 현재는 20년 만의 최고 과열(99~100퍼센타일)</b>이라 역사 기준 매도권이되,
    전례 없는 영역(AI/HBM)이라 해석에 주의가 필요하다.</div>

    <h2>1. 이 도구가 하는 일 (로직)</h2>
    <div class="box">
      ① 시그널을 <b>YoY(전년대비 %)</b>로 변환 (수출은 발행지연 1개월 시차 → 미래 엿보기 방지).<br>
      ② <b>선행성</b>: 시그널(t)이 다음 1·3·6·12개월 주가수익률을 얼마나 예측하나(상관·IC).<br>
      ③ <b>5분위 백테스트</b>: 과거를 시그널 크기로 5등분 → 각 구간에서 산 뒤 <b>다음 12개월</b> 평균수익률·승률.<br>
      ④ <b>현재 위치</b>: 최신 시그널이 과거 분포상 어디인가 → 매수권/중립/매도권.
    </div>

    <h2>2. 사이클 동행성 (눈으로 확인)</h2>
    <img src="data:image/png;base64,{cycle_png}">
    <p class="muted">수출 YoY가 깊게 꺾일 때(2009·2012·2019·2023 침체) 주가도 바닥, 급등할 때 천장.
    맨 오른쪽 — 현재 수출 YoY는 20년 내 최고 수준.</p>

    <h2>3. 핵심 결과 — 분위별 12개월 수익</h2>
    <div class="box"><b>막대 4개가 뭔가요?</b> 우리가 쓰는 <b>4개 지표</b>입니다 —
    <b>반도체 수출 · 메모리 수출 · 미국 반도체지수(SOX) · 마이크론(미국 메모리회사 주가)</b>.
    네 지표 모두 <b>'작년 같은 달 대비 몇 % 늘었나(YoY)'</b>로 계산합니다 (예: 올해 100, 작년 80 → +25%).
    <b>어느 지표로 5등분해도 결론이 같다</b>는 걸 보여주려고 4개를 나란히 그렸습니다.</div>
    <img src="data:image/png;base64,{quint_png}">
    <p class="muted">왼쪽(Q1=바닥, 쌀 때)일수록 이후 1년 수익이 높고, 오른쪽(Q5=천장, 비쌀 때)일수록 낮다 =
    "쌀 때 사라"가 데이터로 확인. 위=삼성전자, 아래=SK하이닉스(둘 다). 2013년 이후 기준.</p>

    <h3>3-1. 선행성 (전체 20년)</h3>
    {df_to_html(best_full.round(3))}
    <p class="muted">단순 상관은 0.05~0.28로 약함 → 정밀 '몇 월에 사라'는 못함. 아래 분위 백테스트가 핵심 신호.</p>

    <h3>3-2. 5분위 백테스트 (전체 20년)</h3>
    {df_to_html(qt_full)}

    <h3>3-3. 5분위 백테스트 (2013년 이후 = 3사 과점 확립)</h3>
    {df_to_html(qt_13)}
    <div class="key">과점 시대엔 신호가 <b>더 선명</b>: 바닥권(Q1) 승률 93~100%, 그리고 <b>천장권(Q5)에서 사면 실제로 마이너스</b>가 됐다
    (전체 20년에선 '안 오를 뿐'이었음). 단 분위당 표본 30개로 양 끝만 신뢰.</div>

    <h2>4. 현재 위치</h2>
    {df_to_html(cur_full)}
    <div class="warn"><b>지금 읽기.</b> 4개 시그널 중 3개(SOX·마이크론·반도체수출)가 <b>퍼센타일 99~100 = 20년 최고 과열</b>.
    환율만 수출채산성 우호. 역사 기준 = 차익실현(매도)권. <b>그러나 이 수치는 모델이 경험한 적 없는 범위 밖</b>이라,
    AI/HBM이 구조적 신수요라면 '이번엔 다를' 가능성도 함께 봐야 한다.</div>

    <h2>5. 채택 시그널 & 임계값 (→ <code>signal_config.yaml</code>)</h2>
    {df_to_html(wtab)}
    <p class="muted">가중치 = 분위 양끝(매수존−매도존)의 수익·승률 격차 비례. 복합점수 = Σ(신호 ±1 × 가중치),
    ≥+0.6 매수 / ≤−0.6 매도. 이 설정을 Phase B(주간 모니터)가 읽어 신호등을 만든다.</p>

    <h2>6. 한계 / 주의</h2>
    <div class="warn">
      · <b>상관 ≠ 인과</b>. 본 리포트는 분석용이며 <b>투자권유가 아니다</b>.<br>
      · 정밀 타이밍 시계가 아니라 <b>'사이클 체온계'</b>(바닥권/천장권 판별).<br>
      · 현재는 학습범위 밖 극단 — <b>AI/HBM 구조변화</b> 시 과거 패턴이 안 맞을 수 있음.<br>
      · 2013년 이후 부분구간은 표본이 작다(분위당 30) → 중간 분위는 들쭉날쭉, 양 끝만 신뢰.<br>
      · 메모리(854232)는 2007년부터 / 주가·SOX·마이크론·환율은 2006년부터.
    </div>
    <p class="muted">데이터: 주가·SOX·마이크론·환율 = yfinance / 반도체·메모리 수출 = 관세청 품목별 수출입실적 API(HS 8542·854232).</p>
    """

    out = f"<!doctype html><html lang='ko'><head><meta charset='utf-8'>" \
          f"<meta name='viewport' content='width=device-width,initial-scale=1'>" \
          f"<title>메모리 사이클 시그널 백테스트 v1</title>{style}</head><body>{body}</body></html>"

    out_path = os.path.join(REPORTS, "백테스트_리포트_v1.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(out)
    print("저장:", out_path)
    print("크기:", round(len(out) / 1024, 1), "KB")


if __name__ == "__main__":
    main()

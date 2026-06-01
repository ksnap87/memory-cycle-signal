"""
Phase A 산출 ②-쉬운판 — reports/백테스트_리포트_v2.html 생성.

v1이 전문용어(상관계수·IC·선행성)를 앞세워 비전문가가 읽기 어려웠음.
v2 = 용어 제거, "어떤 지표가 / 지금 어떤지 / 왜 그렇게 보는지"만 그림과 평이한 말로.
차트는 v1과 동일(사이클 동행 + 분위별 수익)을 재사용.
"""
import os
import datetime as dt
import pandas as pd
import yaml

from analyze import load, build_signals, quintile_backtest, TARGETS, HERE
from make_report import (chart_cycle, chart_quintile_grid, chart_recent_exports,
                         chart_export_decomp, windowed, REPORTS, CALIB_SINCE)

# 신뢰도/설명은 판단이 들어가므로 라벨별로 명시
META = {
    "반도체수출 YoY": ("한국 반도체 수출액(작년 대비). 실제 통관된 실물 금액", "별3", "실물 — 가장 믿을만"),
    "메모리수출 YoY": ("그중 메모리(D램·낸드)만 떼어낸 것", "별3", "실물 — 가장 믿을만"),
    "SOX YoY": ("미국 반도체 회사들 주가지수(작년 대비)", "별2", "잘 맞지만 '주가'라 보조"),
    "마이크론 YoY": ("미국 메모리회사 마이크론 주가(작년 대비)", "별2", "잘 맞지만 '주가'라 보조"),
    "원달러 YoY": ("원/달러 환율(작년 대비). 오르면 원화 약세=수출 유리", "별1", "방향 반대 · 거드는 정도"),
}
STARS = {"별3": "★★★", "별2": "★★", "별1": "★"}

def q_from_pct(pct: float) -> int:
    """현재값의 퍼센타일(과거 분포상 위치)을 Q1~Q5로 환산."""
    return min(5, int(pct // 20) + 1)


def sig_pill(zone: str) -> str:
    """현재 신호를 색 배지(pill)로 — 한 칸 한 항목."""
    c, t = {"매수권": ("#34c759", "🟢 매수"), "매도권": ("#ff3b30", "🔴 매도"),
            "중립": ("#8e8e93", "⚪ 중립")}.get(zone, ("#8e8e93", "⚪ 중립"))
    return f'<span class="pill" style="background:{c}">{t}</span>'


def q_dots(q: int, zone: str) -> str:
    """20년 분포상 현재 위치 — 5점 중 현재 Q만 색칠(왼쪽=바닥, 오른쪽=천장)."""
    c = {"매수권": "#34c759", "매도권": "#ff3b30", "중립": "#8e8e93"}.get(zone, "#8e8e93")
    dots = "".join(
        f'<span class="dot" style="background:{c if i == q else "#d2d2d7"}"></span>'
        for i in range(1, 6))
    return f'<span class="qdots">{dots}</span><b>Q{q}</b>'


def yoy_cell(yv: float) -> str:
    """작년 같은 달 대비 증감 — 한국식 색(빨강=늘었다, 파랑=줄었다)."""
    if yv >= 0:
        return f'<b style="color:#d70015">▲ {yv:.0f}%</b>'
    return f'<b style="color:#0071e3">▼ {abs(yv):.0f}%</b>'


def both_q15(df: pd.DataFrame) -> dict:
    """시그널별 Q1(바닥)·Q5(천장) 다음12M 성과 — 삼성·하이닉스 둘 다."""
    dw = windowed(df, CALIB_SINCE)
    sigs = build_signals(dw)
    out = {}
    for lab, ser in sigs.items():
        bt = quintile_backtest(dw, ser, lab)
        per = {}
        for tgt in ("삼성전자", "SK하이닉스"):
            t = bt[bt["타깃"] == tgt].sort_values("q")
            if len(t) < 5:
                continue
            r = t.to_dict("records")
            per[tgt] = {"q1_ret": r[0]["평균수익12M(%)"], "q1_win": r[0]["승률(%)"],
                        "q5_ret": r[4]["평균수익12M(%)"], "q5_win": r[4]["승률(%)"]}
        if per:
            out[lab] = per
    return out


def main() -> None:
    df = load()
    with open(os.path.join(HERE, "signal_config.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    sig_cfg = cfg.get("signals", {})

    cycle_png = chart_cycle(df)
    quint_png = chart_quintile_grid(df)          # 4개 지표 × 삼성·하이닉스 = 8개 계열
    recent_png = chart_recent_exports(df)        # 최근 24개월 실제 수출 금액
    decomp_png = chart_export_decomp(df)         # 메모리 수출 금액 vs 물량 vs 단가
    q15 = both_q15(df)

    # '지금 수출 어떻게 가나' 문장용 실데이터 — 금액·물량·단가로 분해
    from analyze import yoy as _yoy
    def _exp(amt_col, wgt_col):
        a = df[amt_col].dropna()
        w = df[wgt_col].dropna()
        idx = a.index.intersection(w.index)
        a2, w2 = a[idx], w[idx]
        price = (a2 * 1e6) / (w2 * 1e3)          # 백만$·톤 → $/kg
        return {
            "eok": a.iloc[-1] / 100.0,           # 억달러
            "yoy": _yoy(a).iloc[-1],             # 금액 작년比 (dropna 시리즈 기준 → nan 방지)
            "vol_yoy": _yoy(w2).iloc[-1],        # 물량 작년比
            "price_yoy": _yoy(price).iloc[-1],   # 단가 작년比
            "price": price.iloc[-1],             # 현재 단가 $/kg
            "month": a.index[-1].strftime("%Y년 %m월"),
            "is_high": a.iloc[-1] >= a.max(),
            "mom": (a.iloc[-1] / a.iloc[-2] - 1) * 100,
        }
    semi = _exp("반도체수출_8542_백만$", "반도체수출_8542_톤")
    mem = _exp("메모리수출_854232_백만$", "메모리수출_854232_톤")
    dram = _exp("디램수출_백만$", "디램수출_톤")

    # 종합 신호등 점수: 매수권 +가중치 / 매도권 -가중치
    score = 0.0
    for lab, c in sig_cfg.items():
        z = c["current"]["zone"]
        if z == "매수권":
            score += c["weight"]
        elif z == "매도권":
            score -= c["weight"]
    if score <= -0.6:
        verdict, vcolor = "강한 과열 — 차익실현(매도) 구간", "#ff3b30"
    elif score <= -0.2:
        verdict, vcolor = "과열 쪽 — 신규매수 비추천", "#ff9500"
    elif score < 0.2:
        verdict, vcolor = "중립", "#8e8e93"
    elif score < 0.6:
        verdict, vcolor = "바닥 쪽 — 분할매수 고려", "#34c759"
    else:
        verdict, vcolor = "강한 침체 — 매수 구간", "#34c759"

    # 지표 표 (신뢰도순) — 한 칸에 하나의 항목만
    order = ["반도체수출 YoY", "메모리수출 YoY", "SOX YoY", "마이크론 YoY", "원달러 YoY"]
    rows = ""
    for lab in order:
        if lab not in sig_cfg:
            continue
        desc, star, trust = META[lab]
        cur = sig_cfg[lab]["current"]
        q = q_from_pct(cur.get("percentile", 50))
        if lab in q15 and lab != "원달러 YoY":
            s = q15[lab].get("삼성전자")
            h = q15[lab].get("SK하이닉스")
            sam = (f'<b>+{s["q1_ret"]:.0f}%</b><br><span class="muted">승률 {s["q1_win"]:.0f}%</span>'
                   if s else "—")
            hyn = (f'<b>+{h["q1_ret"]:.0f}%</b><br><span class="muted">승률 {h["q1_win"]:.0f}%</span>'
                   if h else "—")
        else:
            sam = hyn = '<span class="muted">방향 반대¹</span>'
        rows += f"""<tr>
          <td class="name"><b>{lab.replace(' YoY','')}</b><br><span class="muted">{desc}</span></td>
          <td><span class="stars">{STARS[star]}</span><br><span class="muted">{trust}</span></td>
          <td>{sig_pill(cur['zone'])}</td>
          <td>{q_dots(q, cur['zone'])}</td>
          <td>{yoy_cell(cur['yoy'])}</td>
          <td>{sam}</td>
          <td>{hyn}</td></tr>"""

    today = dt.date.today().isoformat()
    style = """
    <style>
      body{font-family:-apple-system,'Apple SD Gothic Neo',sans-serif;max-width:860px;margin:20px auto;
           padding:0 16px;color:#1d1d1f;line-height:1.7}
      h1{font-size:1.6rem;margin-bottom:.2em} h2{margin-top:1.8em}
      .lead{font-size:1.05rem;color:#3a3a3c}
      .verdict{border-radius:14px;padding:18px 20px;margin:1.2em 0;color:#fff;font-size:1.15rem;font-weight:600}
      .tblwrap{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:.8em 0;
               border:1px solid #e5e5ea;border-radius:14px}
      table.rt{border-collapse:collapse;width:100%;min-width:660px;font-size:.9rem;
               font-variant-numeric:tabular-nums}
      table.rt thead th{background:#f5f5f7;color:#1d1d1f;font-weight:600;font-size:.8rem;
               padding:9px 10px;border-bottom:1px solid #e0e0e5;text-align:center;line-height:1.35}
      table.rt thead tr:first-child th{border-bottom:1px solid #ededf0}
      table.rt thead th.sub{font-weight:500;color:#6e6e73;font-size:.76rem;background:#fafafa}
      .th-sub{font-weight:400;color:#8e8e93;font-size:.72rem}
      table.rt tbody td{padding:13px 10px;border-bottom:1px solid #f0f0f2;text-align:center;vertical-align:middle}
      table.rt tbody tr:last-child td{border-bottom:none}
      table.rt tbody tr:hover{background:#fbfbfd}
      table.rt td.name{text-align:left;min-width:148px}
      table.rt td.name b{font-size:.95rem}
      .pill{display:inline-block;color:#fff;font-weight:600;font-size:.8rem;
            padding:3px 11px;border-radius:999px;white-space:nowrap}
      .qdots{display:inline-flex;gap:3px;align-items:center;margin-right:6px;vertical-align:middle}
      .dot{width:7px;height:7px;border-radius:50%;display:inline-block}
      .stars{color:#ff9f0a;letter-spacing:1px;white-space:nowrap;font-size:.95rem}
      .step{background:#f5f5f7;border-radius:12px;padding:16px 20px;margin:1em 0}
      .step b{color:#0071e3}
      .warn{background:#fff4e5;border-left:4px solid #ff9500;border-radius:8px;padding:14px 18px;margin:1.2em 0}
      .muted{color:#8e8e93;font-size:.82rem}
      img{max-width:100%;border-radius:10px;border:1px solid #e5e5ea;margin:.4em 0}
      .big{font-size:1.1rem}
    </style>"""

    body = f"""
    <h1>반도체 사이클 — 지금 사야 할 때? 팔아야 할 때?</h1>
    <p class="muted">쉬운 설명판 v2 · {today} · 삼성전자·SK하이닉스</p>
    <p class="lead">이 도구는 딱 한 가지를 알려줍니다 — <b>지금 반도체 주식이 '바닥권(쌀 때)'이냐 '천장권(비쌀 때)'이냐.</b>
    주가 차트는 안 봅니다. 실제 반도체 수출·업황 같은 <b>펀더멘털(실물 지표)</b>만 씁니다.</p>

    <div class="verdict" style="background:{vcolor}">지금 종합 판정 : {verdict}
      <div style="font-size:.85rem;font-weight:400;margin-top:6px">종합점수 {score:+.2f} (−1=완전 과열 … +1=완전 침체)</div>
    </div>

    <h2>1. 어떤 지표가 쓸모있나 (신뢰도순)</h2>
    <div class="tblwrap"><table class="rt">
      <thead>
        <tr>
          <th rowspan="2" class="lh">지표<br><span class="th-sub">무엇을 보나</span></th>
          <th rowspan="2">신뢰도</th>
          <th rowspan="2">현재<br>신호</th>
          <th rowspan="2">지금 위치<br><span class="th-sub">◀바닥 … 천장▶</span></th>
          <th rowspan="2">작년 같은<br>달 대비</th>
          <th colspan="2">바닥(Q1)에 샀다면 1년 뒤 수익</th>
        </tr>
        <tr><th class="sub">삼성전자</th><th class="sub">SK하이닉스</th></tr>
      </thead>
      <tbody>{rows}</tbody>
    </table></div>
    <div class="warn"><b>표 읽는 법 (왼쪽 칸부터).</b><br>
      · <b>신뢰도</b> — ★★★ 반도체·메모리 수출은 <b>실제 통관된 실물 금액</b>이라 가장 믿을만.
        ★★ SOX·마이크론은 미국 '<b>주가</b>'라 주가로 주가를 맞히는 셈이어서 보조. ★ 환율은 거드는 정도.<br>
      · <b>현재 신호</b> — 🟢매수(쌀 때) / ⚪중립 / 🔴매도(비쌀 때).<br>
      · <b>지금 위치</b> — 20년 줄세우기에서 어느 칸(Q). 점이 <b>왼쪽(Q1)=바닥, 오른쪽(Q5)=천장.</b><br>
      · <b>작년 같은 달 대비</b> — 1년 전 같은 달보다 그 지표가 몇 % 변했나 (▲빨강=늘었다, ▼파랑=줄었다).<br>
      · <b>바닥(Q1)에 샀다면</b> — 과거에 그 지표가 가장 쌀 때(Q1) 사서 1년 묵혔으면 주가가 평균 몇 % 올랐나.<br>
      <span class="muted">¹ 원달러는 '높을수록 수출 유리'라 방향이 반대 — 바닥이 좋은 게 아니어서 같은 칸으로 비교 못 합니다.</span></div>

    <h2>2. 지금 수출이 실제로 어떻게 가고 있나</h2>
    <img src="data:image/png;base64,{recent_png}">
    <p class="big">가장 최근 <b>{semi['month']}</b> 기준 — 반도체 수출 <b>{semi['eok']:.0f}억 달러</b>{'(사상 최고치)' if semi['is_high'] else ''},
    작년 같은 달보다 <b>+{semi['yoy']:.0f}%</b>. 메모리 수출 <b>{mem['eok']:.0f}억 달러</b>{'(사상 최고치)' if mem['is_high'] else ''},
    작년比 <b>+{mem['yoy']:.0f}%</b>. 다만 <b>최근 1~2달은 더 안 오르고 옆걸음(횡보)</b> 중입니다
    (메모리 전달比 {mem['mom']:+.1f}%) — 사상 최고 수준이긴 해도 <b>상승 속도는 한풀 꺾였습니다.</b></p>

    <div class="step"><b>"수출이 늘었다" — 물량이 늘었나, 비싸게 판 건가?</b><br>
      수출 금액은 <b>물량(몇 톤 팔았나) × 단가(kg당 얼마)</b>로 쪼갤 수 있습니다.
      그래야 "진짜 많이 판 건지, 비싸서 금액만 커 보이는 건지"가 드러납니다.</div>
    <img src="data:image/png;base64,{decomp_png}">
    <p class="big"><b>지금의 수출 급증은 거의 다 '가격(단가)' 때문입니다 — 물량이 아니라.</b><br>
    메모리 금액 <b>+{mem['yoy']:.0f}%</b> = 물량 <b>+{mem['vol_yoy']:.0f}%</b> × 단가 <b>+{mem['price_yoy']:.0f}%</b>.
    특히 <b>D램</b>은 물량은 거의 그대로(+{dram['vol_yoy']:.0f}%)인데 <b>단가가 +{dram['price_yoy']:.0f}%</b> 뛰어 금액이 +{dram['yoy']:.0f}%가 됐습니다.
    = <b>AI·HBM발 D램 값 폭등</b>의 전형적인 모습입니다.</p>
    <div class="warn"><b>"수출이 늘었다"의 정확한 뜻 (오해 주의).</b><br>
      · 이 숫자는 <b>금액(달러)</b> 기준 — 몇 '개/톤' 팔렸나(물량)가 아니라 얼마치 팔았나입니다.<br>
      · 종류는 <b>메모리 전체(D램+낸드 합산, 관세청 코드 854232)</b> — <b>HBM만 따로는 못 가립니다.</b><br>
      · 즉 지금 금액 급증의 본질은 <b>'물량 폭발'이 아니라 '단가 폭등'</b> — 가격이 꺾이면 금액도 빠르게 식을 수 있습니다.</div>

    <h2>3. 어떻게 판단하나 (이 그림이 핵심)</h2>
    <div class="step">
      <b>5칸(구간)으로 줄 세우기 — 무엇을 기준으로?</b><br>
      각 지표의 <b>'작년 같은 달 대비 몇 %'(= 금액·달러 기준 증가율)</b>를 지난 20년(2013년~) 치 전부 모아
      <b>크기순으로 줄 세운 뒤 20%씩 5칸</b>으로 나눕니다.
      <span class="muted">※ 수량(개수)이 아니라 <b>금액(달러)</b> 기준입니다.</span><br>
      예로 <b>반도체 수출</b>은 이렇게 갈립니다 (아래 그림 왼쪽 위 칸 x축 숫자와 동일):<br>
      · <b>가장 쌀 때(침체)</b> = 작년比 <b>≤ −9%</b> (수출 줄던 2009·2019·2023 불황기)<br>
      · <b>한가운데(보통)</b> = 작년比 <b>+5 ~ +15%</b><br>
      · <b>가장 비쌀 때(과열)</b> = 작년比 <b>≥ +37%</b><br>
      <b>지금은?</b> 반도체 수출이 작년比 <b>+{semi['yoy']:.0f}%</b> — +37% 선을 한참 넘어 <b>20년 중 상위 1%, 가장 비싼 칸(과열)</b>입니다.
    </div>
    <div class="warn"><b>막대 높이가 헷갈리지 않게 — 꼭 읽으세요.</b>
      아래 막대 높이는 <b>지표 숫자가 아니라 '그때 샀으면 삼성·하이닉스 주가가 1년 뒤 얼마 올랐나(주가 수익률)'</b>입니다
      (막대 위 숫자가 그 수익률). <b>파랑=삼성전자, 주황=SK하이닉스.</b>
      그림 4개는 가장 믿을만한 지표 4개(반도체수출·메모리수출·SOX·마이크론),
      각 그림 <b>x축 숫자는 그 지표의 '작년比 구간'</b> — 왼쪽일수록 쌀 때, 오른쪽일수록 비쌀 때입니다.</div>
    <img src="data:image/png;base64,{quint_png}">
    <p class="big"><b>읽는 법:</b> 네 지표 모두 <b>왼쪽(쌀 때)에서 사면 1년 뒤 수익이 크고, 오른쪽(비쌀 때)으로 갈수록 막대가 낮아집니다</b>
    — 비쌀 때 산 칸은 수익이 0 근처거나 손해. = <b>쌀 때 사고 비쌀 때 팔라</b>를 20년 데이터가 한목소리로 보여줍니다.
    그리고 <b>지금은 네 지표 모두 맨 오른쪽 칸(과열)</b>에 들어가 있습니다.</p>

    <h2>4. 20년 그림으로 보기</h2>
    <img src="data:image/png;base64,{cycle_png}">
    <p class="big">아래 칸(수출 증가율)이 <b>바닥을 칠 때마다</b> 위 칸(주가)도 바닥이었고, <b>치솟을 때</b> 주가도 천장이었습니다.
    그리고 <b>맨 오른쪽 = 지금</b> — 수출 증가율이 20년 중 가장 높이 치솟아 있습니다(과열).</p>

    <h2>5. 꼭 기억할 점</h2>
    <div class="warn">
      · 이건 <b>'사이클 체온계'</b>입니다 — "지금 뜨겁다/차갑다"는 알려주지만 <b>'며칠에 사라'까지는 못 맞힙니다.</b><br>
      · <b>지금은 20년 만의 최고 과열</b>이라 역사 기준으론 '파는 자리'. 단 <b>AI/HBM 때문에 사상 처음 보는 영역</b>이라
      "이번엔 다를" 가능성도 함께 봐야 합니다(과거에 없던 상황이라 100% 장담 불가).<br>
      · <b>투자 권유가 아니라 참고용 분석</b>입니다.
    </div>
    <p class="muted">자료: 주가·SOX·마이크론·환율 = yfinance / 반도체·메모리 수출 = 관세청 수출입실적. 어려운 통계표(상관계수·선행성)는 전문가용이라 v1 리포트에 따로 있습니다.</p>
    """
    out = f"<!doctype html><html lang='ko'><head><meta charset='utf-8'>" \
          f"<meta name='viewport' content='width=device-width,initial-scale=1'>" \
          f"<title>반도체 사이클 쉬운 리포트 v2</title>{style}</head><body>{body}</body></html>"
    out_path = os.path.join(REPORTS, "백테스트_리포트_v2.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(out)
    print("저장:", out_path, "|", round(len(out) / 1024, 1), "KB | 종합점수", round(score, 2), verdict)


if __name__ == "__main__":
    main()

"""
Phase A 산출 ②-쉬운판 — reports/백테스트_리포트_v3.html 생성.

v1이 전문용어(상관계수·IC·선행성)를 앞세워 비전문가가 읽기 어려웠음.
v2 = 용어 제거, "어떤 지표가 / 지금 어떤지 / 왜 그렇게 보는지"만 그림과 평이한 말로.
v3 = 3번 섹션에 '지금 어느 칸(분위)인지 + 올해(2026) 월별 칸 이동' 표 추가.
차트는 v1과 동일(사이클 동행 + 분위별 수익)을 재사용.
"""
import os
import json
import datetime as dt
import pandas as pd
import yaml

from analyze import load, build_signals, quintile_backtest, fwd_return, HORIZONS, TARGETS, HERE
from chart_data import (data_cycle, data_quintile_grid, data_recent_exports,
                        data_export_decomp, windowed, quintile_edges, REPORTS, CALIB_SINCE)

SRC = os.path.dirname(os.path.abspath(__file__))


def _read_chartjs() -> str:
    """동봉한 Chart.js 를 통째로 HTML 에 인라인 — 외부 CDN 의존 0,
    비번(StatiCrypt) 페이지·오프라인에서도 그래프가 확실히 그려지게."""
    with open(os.path.join(SRC, "vendor", "chart.umd.min.js"), encoding="utf-8") as f:
        return f.read().replace("</script", "<\\/script")


# 브라우저에서 실행될 차트 초기화 코드(반응형). window.__CHARTDATA__ 의 숫자로 그림.
# f-string 아님 — JS 의 중괄호를 그대로 둠.
INIT_JS = r"""
(function(){
  if(typeof Chart==='undefined' || !window.__CHARTDATA__) return;
  var D = window.__CHARTDATA__;
  Chart.defaults.font.family = "-apple-system,'Apple SD Gothic Neo','Segoe UI',sans-serif";
  Chart.defaults.color = "#3a3a3c";
  Chart.defaults.animation = false;

  function baseOpts(o){
    o = o || {};
    return {
      responsive:true, maintainAspectRatio:false,
      interaction:{mode:'index', intersect:false},
      plugins:{
        legend:{position:'top', labels:{boxWidth:12, font:{size:12}, padding:10}},
        title: o.title ? {display:true, text:o.title, font:{size:13, weight:'bold'}, color:'#1d1d1f', padding:{bottom:6}} : {display:false},
        tooltip:{backgroundColor:'rgba(0,0,0,.82)', padding:9, titleFont:{size:12}, bodyFont:{size:12}}
      },
      scales:{
        x:{ticks:{maxTicksLimit:o.xmax||8, autoSkip:true, maxRotation:0, font:{size:10}, color:'#8e8e93'}, grid:{display:false}},
        y:{ticks:{font:{size:10}, color:'#8e8e93'}, grid:{color:'#eef0f2'},
           title: o.ytitle ? {display:true, text:o.ytitle, font:{size:10}, color:'#8e8e93'} : {display:false}}
      }
    };
  }
  function line(d, color, w){
    return {label:d.label, data:d.data, borderColor:color||d.color, backgroundColor:color||d.color,
            borderWidth:w||2, pointRadius:0, pointHoverRadius:4, tension:.15, spanGaps:true};
  }

  // 2-a) 수출 금액 20년 (가로 스크롤)
  var ex = D.exports, elE = document.getElementById('cExports');
  if(ex && elE){
    new Chart(elE, {type:'line',
      data:{labels:ex.labels, datasets: ex.series.map(function(s){return line(s);})},
      options: baseOpts({ytitle:'월 수출액 (억$)', xmax:16})});
  }
  // 2-b) 메모리 수출 분해 (시작=100)
  var dc = D.decomp, elD = document.getElementById('cDecomp');
  if(dc && elD){
    new Chart(elD, {type:'line',
      data:{labels:dc.labels, datasets:[
        {label:'수출액(금액)', data:dc.amount, borderColor:'#ff3b30', backgroundColor:'#ff3b30', borderWidth:2.6, pointRadius:0, pointHoverRadius:4, tension:.15},
        {label:'평균단가($/kg)', data:dc.price, borderColor:'#af52de', backgroundColor:'#af52de', borderWidth:2.6, pointRadius:0, pointHoverRadius:4, tension:.15},
        {label:'물량(톤)', data:dc.volume, borderColor:'#34c759', backgroundColor:'#34c759', borderWidth:2, pointRadius:0, pointHoverRadius:4, tension:.15},
        {label:'기준 100', data:dc.labels.map(function(){return 100;}), borderColor:'#c7c7cc', borderWidth:1, borderDash:[5,4], pointRadius:0}
      ]},
      options: baseOpts({ytitle:(dc.base+' = 100'), xmax:8})});
  }
  // 3) 분위 막대 (지표별)
  (D.quint||[]).forEach(function(q, i){
    var el = document.getElementById('cQ'+i); if(!el) return;
    var binc = q.bincolors;
    var opt = baseOpts({title:q.title});
    opt.scales = {
      x:{ticks:{font:{size:9}, color:function(c){return binc[c.index]||'#8e8e93';}}, grid:{display:false}},
      y:{ticks:{font:{size:9}, color:'#8e8e93'}, grid:{color:'#eef0f2'}, title:{display:true, text:'1년 뒤 수익률(%)', font:{size:9}, color:'#8e8e93'}}
    };
    new Chart(el, {type:'bar',
      data:{labels:q.binlabels.map(function(b,k){return [b, q.ranges[k]];}), datasets:[
        {label:'삼성전자', data:q.samsung, backgroundColor:'#0071e3', borderRadius:3, maxBarThickness:36},
        {label:'SK하이닉스', data:q.hynix, backgroundColor:'#ff9500', borderRadius:3, maxBarThickness:36}
      ]},
      options: opt});
  });
  // 4) 사이클 — 주가(로그) + 수출 증가율
  var cy = D.cycle;
  if(cy && document.getElementById('cPrice')){
    var po = baseOpts({title:'삼성·SK하이닉스 주가 (시작=100, 로그축)', xmax:8});
    po.scales.y = {type:'logarithmic', ticks:{font:{size:9}, color:'#8e8e93'}, grid:{color:'#eef0f2'}};
    new Chart(document.getElementById('cPrice'), {type:'line',
      data:{labels:cy.labels, datasets: cy.prices.map(function(s){return line(s, s.color, 1.8);})},
      options: po});
  }
  if(cy && document.getElementById('cYoY')){
    var ds = cy.yoy.map(function(s){return line(s, s.color, 1.8);});
    ds.push({label:'0%', data:cy.labels.map(function(){return 0;}), borderColor:'#c7c7cc', borderWidth:1, borderDash:[5,4], pointRadius:0});
    new Chart(document.getElementById('cYoY'), {type:'line',
      data:{labels:cy.labels, datasets: ds},
      options: baseOpts({title:'반도체·메모리 수출 증가율 (작년比 %)', ytitle:'%', xmax:8})});
  }
})();
"""

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
    """20년 분포상 현재 위치 — 5칸 중 현재 칸만 색칠(왼쪽=1번 바닥, 오른쪽=5번 천장)."""
    c = {"매수권": "#34c759", "매도권": "#ff3b30", "중립": "#8e8e93"}.get(zone, "#8e8e93")
    dots = "".join(
        f'<span class="dot" style="background:{c if i == q else "#d2d2d7"}"></span>'
        for i in range(1, 6))
    return f'<span class="qdots">{dots}</span><b>{q}번</b>'


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


def _bin_color(q: int) -> str:
    """분위 칸 색 — 낮을수록(쌀 때) 초록, 높을수록(비쌀 때) 빨강. (low_is_buy 지표 기준)"""
    if q <= 2:
        return "#34c759"
    if q >= 4:
        return "#ff3b30"
    return "#8e8e93"


def yearly_quintile_path(df: pd.DataFrame, year: int) -> dict:
    """각 지표의 해당 연도 '월별 분위(Q1~Q5)'. 기준 분포 = 보정창(2013년~).
    퍼센타일→Q 환산은 섹션1 '지금 위치'와 동일(q_from_pct) → 표끼리 어긋나지 않음.
    반환: {label: {월(int): (q, yoy값)}}"""
    sigs = build_signals(df)
    cstart = pd.Timestamp(CALIB_SINCE)
    out = {}
    for lab, ser in sigs.items():
        s = ser.dropna()
        calib = s[s.index >= cstart]
        if len(calib) < 20:
            continue
        path = {}
        for ts, v in s[s.index.year == year].items():
            pct = (calib < v).mean() * 100
            path[ts.month] = (q_from_pct(pct), round(float(v), 0))
        if path:
            out[lab] = path
    return out


def describe_path(path: dict) -> str:
    """월별 분위 경로를 '올해 내내 5번' / '올해 4번→5번' 식으로 요약."""
    if not path:
        return ""
    qs = [path[m][0] for m in sorted(path)]
    if len(set(qs)) == 1:
        return f"올해 내내 {qs[0]}번"
    return f"올해 {qs[0]}번→{qs[-1]}번"


def load_live_current() -> dict:
    """매주 compute_signals.py 가 새로 쓴 docs/signals.json 의 '현재값'을 라벨별로.
    {label: {yoy, percentile, zone}}. 없으면 빈 dict → config 의 고정 스냅샷으로 폴백.
    (이게 있어야 매주 자동 갱신 때 1번 표·종합점수가 최신값으로 같이 움직임)"""
    sj = os.path.join(HERE, "docs", "signals.json")
    if not os.path.exists(sj):
        return {}
    try:
        with open(sj, encoding="utf-8") as f:
            data = json.load(f)
        return {s["label"]: {"yoy": s.get("yoy"), "percentile": s.get("percentile"),
                             "zone": s.get("zone")}
                for s in data.get("signals", []) if "label" in s}
    except Exception:
        return {}


def leadlag_summary(df: pd.DataFrame) -> dict:
    """수출이 주가를 '몇 개월' 앞서나 + '얼마나 맞나(상관)' — 전체 20년 vs 2013년 이후.
    각 (종목,시그널)에서 상관(피어슨)이 최대가 되는 선행개월 h(1/3/6/12) 채택
    → {window: {(종목,시그널): {h,corr}}}.
    analyze.lead_lag_table 의 '피어슨 상관' 계산을 그대로 재현(숫자 동일)하되,
    대시보드에서 안 쓰는 스피어만 IC 는 빼서 클라우드(CI)에 scipy 의존을 없앤다."""
    def best(sub: pd.DataFrame) -> dict:
        sigs = build_signals(sub)
        out: dict = {}
        for tgt in TARGETS:
            for lab, sig in sigs.items():
                bh, br = None, None
                for h in HORIZONS:
                    pair = pd.concat([sig, fwd_return(sub[tgt], h)], axis=1).dropna()
                    if len(pair) < 24:
                        continue
                    r = round(pair.iloc[:, 0].corr(pair.iloc[:, 1]), 3)  # 피어슨(기본) — scipy 불필요
                    if pd.isna(r):
                        continue
                    if br is None or r > br:        # 동률이면 더 짧은 h(먼저 만난 값) 유지 = idxmax 와 동일
                        bh, br = h, r
                if bh is not None:
                    out[(tgt, lab)] = {"h": int(bh), "corr": float(br)}
        return out
    return {"full": best(df), "c2013": best(windowed(df, CALIB_SINCE))}


def main() -> None:
    df = load()
    with open(os.path.join(HERE, "signal_config.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    sig_cfg = cfg.get("signals", {})
    live_cur = load_live_current()   # 최신 현재값(있으면 우선) ← 매주 자동 갱신 핵심

    # 그림(PNG) 대신 '숫자'만 뽑는다 → 브라우저의 Chart.js 가 반응형 그래프로 직접 그림
    chart_payload = {
        "cycle": data_cycle(df),                 # 섹션4: 주가 + 수출 증가율 (20년)
        "quint": data_quintile_grid(df),         # 섹션3: 4개 지표 × 삼성·하이닉스 막대
        "exports": data_recent_exports(df),      # 섹션2: 20년 전체 수출 금액(가로 스크롤)
        "decomp": data_export_decomp(df),        # 섹션2: 메모리 수출 금액 vs 물량 vs 단가
    }
    n_q = len(chart_payload["quint"])
    ex_span = chart_payload["exports"].get("span", "")
    q_canvases = "".join(f'<div class="chartbox"><canvas id="cQ{i}"></canvas></div>'
                         for i in range(n_q))
    q15 = both_q15(df)

    # 3번 섹션 그림 x축과 '똑같은' 칸 경계(작년比 %) — 설명 문장에 그대로 주입(숫자 어긋남 방지)
    _dwe = windowed(df, CALIB_SINCE)
    _e = quintile_edges(_dwe, build_signals(_dwe)["반도체수출 YoY"])  # 6개 edge
    b1, mid_lo, mid_hi, b5 = _e[1], _e[2], _e[3], _e[4]

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
        z = (live_cur.get(lab) or c.get("current", {})).get("zone")
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
        cur = live_cur.get(lab) or sig_cfg[lab]["current"]
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

    # 3번 섹션용 — 올해 월별 분위(칸) 이동 표. 원달러는 방향 반대라 제외(섹션1에서 따로).
    traj_all = yearly_quintile_path(df, dt.date.today().year)
    traj = {k: traj_all[k] for k in ("반도체수출 YoY", "메모리수출 YoY", "SOX YoY", "마이크론 YoY") if k in traj_all}
    traj_table_html = ""
    if traj:
        exp_last = [max(traj[l]) for l in ("반도체수출 YoY", "메모리수출 YoY") if l in traj]
        all_m = {m for p in traj.values() for m in p}
        frontier = max(exp_last) if exp_last else max(all_m)
        months = sorted(m for m in all_m if m <= frontier)
        head_m = "".join(f"<th>{m}월</th>" for m in months)

        def _path_to(lab):
            return {m: traj[lab][m] for m in months if m in traj.get(lab, {})}

        traj_rows = ""
        for lab in traj:
            p = _path_to(lab)
            cells = "".join(
                (f'<td><span class="qbin" style="background:{_bin_color(p[m][0])}">{p[m][0]}</span></td>'
                 if m in p else '<td><span class="muted">·</span></td>')
                for m in months)
            qs = [p[m][0] for m in months if m in p]
            last_q = qs[-1] if qs else 3
            tag = "천장권(비쌀 때)" if last_q >= 4 else ("바닥권(쌀 때)" if last_q <= 2 else "중간")
            move = describe_path(p).replace("올해 ", "")
            traj_rows += (f'<tr><td class="name"><b>{lab.replace(" YoY", "")}</b></td>{cells}'
                          f'<td><b>{move}</b><br><span class="muted">{tag}</span></td></tr>')

        semi_p, mem_p = _path_to("반도체수출 YoY"), _path_to("메모리수출 YoY")
        sq = semi_p[max(semi_p)][0] if semi_p else "—"
        mq = mem_p[max(mem_p)][0] if mem_p else "—"
        both_top = isinstance(sq, int) and sq >= 4 and isinstance(mq, int) and mq >= 4
        closing = ("<b>올해 줄곧 역사적 최고가 구간(천장권)</b>에 머물러 있습니다."
                   if both_top else "위 칸 이동을 그대로 참고하세요.")
        traj_table_html = f"""
    <div class="step"><b>지금 어느 칸에 있나 — 올해 어떻게 움직였나.</b><br>
      위 그림 x축의 <b>1~5번을 그대로</b> 써서, 가장 믿을만한 네 지표가 <b>올해 매달 몇 번 칸</b>에 있었는지입니다
      (<b>1번 = 가장 쌀 때 … 5번 = 가장 비쌀 때</b> · 그림 막대 번호와 동일).
      <span class="muted">초록 = 쌀 때(1·2) · 회색 = 보통(3) · 빨강 = 비쌀 때(4·5).</span></div>
    <div class="tblwrap"><table class="rt">
      <thead><tr><th style="text-align:left">지표</th>{head_m}<th>올해 이동</th></tr></thead>
      <tbody>{traj_rows}</tbody>
    </table></div>
    <p class="big"><b>지금 위치:</b> 반도체 수출 <b>{sq}번 칸</b> · 메모리 수출 <b>{mq}번 칸</b>
      (5칸 중 5번이 가장 비쌀 때 = 과열). 반도체 수출은 {describe_path(semi_p)}, 메모리 수출은 {describe_path(mem_p)} 칸에 머물러 —
      {closing}
      <span class="muted">※ 원/달러는 방향이 반대인 보조지표라 위 1번 표에서 따로 봅니다.</span></p>"""

    # 5번 섹션 — 수출이 주가를 '몇 개월 앞서나'(선행성). analyze.lead_lag_table 재사용.
    lls = leadlag_summary(df)

    def _ll_row(sig: str, tgt: str, name: str) -> str:
        a = lls["c2013"].get((tgt, sig))
        if not a:
            return ""
        b = lls["full"].get((tgt, sig))
        h, c2 = a["h"], a["corr"]
        cf = b["corr"] if b else None
        barw = max(6, min(100, c2 / 0.5 * 100))     # 0.5 만점 환산(과대표현 방지)
        return (f'<tr><td class="name"><b>{name}</b></td>'
                f'<td><b>{h}개월</b></td>'
                f'<td><b>{c2:.2f}</b><div class="mbar"><span style="width:{barw:.0f}%"></span></div></td>'
                f'<td>{("%.2f" % cf) if cf is not None else "—"}</td></tr>')

    ll_rows = "".join([
        _ll_row("메모리수출 YoY", "SK하이닉스", "메모리수출 → 하이닉스"),
        _ll_row("반도체수출 YoY", "SK하이닉스", "반도체수출 → 하이닉스"),
        _ll_row("메모리수출 YoY", "삼성전자", "메모리수출 → 삼성"),
        _ll_row("반도체수출 YoY", "삼성전자", "반도체수출 → 삼성"),
    ])
    leadlag_section = ""
    if ll_rows.strip():
        leadlag_section = f"""
    <h2>5. 수출이 주가를 '얼마나 앞서' 가나? (선행성)</h2>
    <div class="step"><b>한 줄 답 — 수출은 주가를 1~3개월 앞서지만, 그 힘은 약합니다.</b><br>
      수출이 오르면 1~3개월 뒤 주가도 오르는 경향이 있지만 '같이 움직이는 정도(상관)'가 <b>0.3을 거의 못 넘습니다</b>
      (1.0=완벽히 일치 · 0=무관). 즉 <b>수출 보고 '몇 달 뒤 주가'를 콕 맞히는 용도로는 약해요.</b>
      대신 3번의 <b>"수출 증가율이 바닥일 때 = 사이클 저점"</b> 신호로는 강력합니다(그때 사면 1년 뒤 승률 90%+).</div>
    <div class="tblwrap"><table class="rt">
      <thead><tr>
        <th style="text-align:left">수출 → 종목</th>
        <th>몇 개월<br>앞서나</th>
        <th>맞는 정도<br><span class="th-sub">2013년~ · 0~1, 높을수록 강함</span></th>
        <th>전체<br>20년</th>
      </tr></thead>
      <tbody>{ll_rows}</tbody>
    </table></div>
    <p class="big"><b>표에서 세 가지가 더 드러납니다.</b><br>
      · <b>하이닉스 &gt; 삼성</b> — 순수 메모리주(하이닉스)에 훨씬 잘 맞습니다. 삼성은 폰·파운드리가 섞여 신호가 희석돼요.<br>
      · <b>메모리수출 &gt; 반도체수출 전체</b> — D램·낸드만 떼어 보는 게 더 정확(삼성·하이닉스 매출에 직결).<br>
      · <b>2013년 이후 더 또렷</b> — 3사 과점(삼성·하이닉스·마이크론)이 자리잡은 뒤 신호가 약 2배로 강해졌습니다.</p>
    <div class="warn"><b>그래서 '체온계'입니다.</b>
      짧게(1~3개월)는 수출과 주가가 같이 가고, 길게(12개월)는 거꾸로 — <b>수출이 폭락한 바닥에서 산 게 1년 뒤 가장 크게 올랐습니다</b>(3번 표).
      이 도구가 '며칠에 사라'는 정밀 시계가 아니라 <b>지금이 바닥권이냐 천장권이냐를 재는 체온계</b>인 이유입니다.</div>"""

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
      .qbin{display:inline-block;min-width:24px;height:24px;line-height:24px;border-radius:6px;
            color:#fff;font-weight:700;font-size:.85rem;text-align:center;padding:0 4px}
      .stars{color:#ff9f0a;letter-spacing:1px;white-space:nowrap;font-size:.95rem}
      .step{background:#f5f5f7;border-radius:12px;padding:16px 20px;margin:1em 0}
      .step b{color:#0071e3}
      .warn{background:#fff4e5;border-left:4px solid #ff9500;border-radius:8px;padding:14px 18px;margin:1.2em 0}
      .muted{color:#8e8e93;font-size:.82rem}
      img{max-width:100%;border-radius:10px;border:1px solid #e5e5ea;margin:.4em 0}
      .big{font-size:1.1rem}
      .mbar{height:6px;background:#eef0f2;border-radius:3px;margin-top:5px;overflow:hidden;min-width:54px}
      .mbar span{display:block;height:100%;background:#0071e3;border-radius:3px}
      /* 인터랙티브 차트(반응형) — 화면 폭에 맞게 또렷하게, 손가락으로 값 확인 */
      .charthint{color:#8e8e93;font-size:.82rem;margin:.4em 0 .1em}
      .chartbox{position:relative;height:330px;margin:.6em 0;border:1px solid #e5e5ea;
                border-radius:12px;background:#fff;padding:10px 8px 6px}
      .scrollx{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid #e5e5ea;
               border-radius:12px;margin:.4em 0}
      .scrollx .chartbox{border:none;min-width:1180px;height:350px;margin:0}
      .qgrid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:.6em 0}
      .qgrid .chartbox{height:300px;margin:0}
      @media(max-width:680px){.qgrid{grid-template-columns:1fr}.chartbox{height:300px}}
    </style>"""

    body = f"""
    <h1>반도체 사이클 — 지금 사야 할 때? 팔아야 할 때?</h1>
    <p class="muted">쉬운 설명판 v3 · {today} · 삼성전자·SK하이닉스</p>
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
          <th rowspan="2">지금 위치<br><span class="th-sub">◀1번 바닥 … 천장 5번▶</span></th>
          <th rowspan="2">작년 같은<br>달 대비</th>
          <th colspan="2">1번(바닥)에 샀다면 1년 뒤 수익</th>
        </tr>
        <tr><th class="sub">삼성전자</th><th class="sub">SK하이닉스</th></tr>
      </thead>
      <tbody>{rows}</tbody>
    </table></div>
    <div class="warn"><b>표 읽는 법 (왼쪽 칸부터).</b><br>
      · <b>신뢰도</b> — ★★★ 반도체·메모리 수출은 <b>실제 통관된 실물 금액</b>이라 가장 믿을만.
        ★★ SOX·마이크론은 미국 '<b>주가</b>'라 주가로 주가를 맞히는 셈이어서 보조. ★ 환율은 거드는 정도.<br>
      · <b>현재 신호</b> — 🟢매수(쌀 때) / ⚪중립 / 🔴매도(비쌀 때).<br>
      · <b>지금 위치</b> — 20년 줄세우기에서 몇 번 칸. 점이 <b>왼쪽=1번(바닥), 오른쪽=5번(천장)</b> — <b>3번 섹션 그림·표의 번호와 똑같습니다.</b><br>
      · <b>작년 같은 달 대비</b> — 1년 전 같은 달보다 그 지표가 몇 % 변했나 (▲빨강=늘었다, ▼파랑=줄었다).<br>
      · <b>1번(바닥)에 샀다면</b> — 과거에 그 지표가 가장 쌀 때(1번 칸) 사서 1년 묵혔으면 주가가 평균 몇 % 올랐나.<br>
      <span class="muted">¹ 원달러는 '높을수록 수출 유리'라 방향이 반대 — 바닥이 좋은 게 아니어서 같은 칸으로 비교 못 합니다.</span></div>

    <h2>2. 지금 수출이 실제로 어떻게 가고 있나</h2>
    <p class="charthint">← 좌우로 밀어서 20년 전체({ex_span})를 볼 수 있어요 · 점을 누르면 그달 값 표시 →</p>
    <div class="scrollx"><div class="chartbox"><canvas id="cExports"></canvas></div></div>
    <p class="big">가장 최근 <b>{semi['month']}</b> 기준 — 반도체 수출 <b>{semi['eok']:.0f}억 달러</b>{'(사상 최고치)' if semi['is_high'] else ''},
    작년 같은 달보다 <b>+{semi['yoy']:.0f}%</b>. 메모리 수출 <b>{mem['eok']:.0f}억 달러</b>{'(사상 최고치)' if mem['is_high'] else ''},
    작년比 <b>+{mem['yoy']:.0f}%</b>. 다만 <b>최근 1~2달은 더 안 오르고 옆걸음(횡보)</b> 중입니다
    (메모리 전달比 {mem['mom']:+.1f}%) — 사상 최고 수준이긴 해도 <b>상승 속도는 한풀 꺾였습니다.</b></p>

    <div class="step"><b>"수출이 늘었다" — 물량이 늘었나, 비싸게 판 건가?</b><br>
      수출 금액은 <b>물량(몇 톤 팔았나) × 단가(kg당 얼마)</b>로 쪼갤 수 있습니다.
      그래야 "진짜 많이 판 건지, 비싸서 금액만 커 보이는 건지"가 드러납니다.</div>
    <div class="chartbox"><canvas id="cDecomp"></canvas></div>
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
      <b>5칸으로 줄 세우고 1~5번 번호 붙이기 — 무엇을 기준으로?</b><br>
      각 지표의 <b>'작년 같은 달 대비 몇 %'(= 금액·달러 기준 증가율)</b>를 2013년 이후 전부 모아
      <b>크기순으로 줄 세운 뒤 20%씩 5칸</b>으로 나누고, 싼 쪽부터 <b>1번~5번</b>을 붙입니다.
      <b>이 1~5번이 아래 그림 x축에도, 맨 아래 표에도 똑같이 쓰입니다.</b>
      <span class="muted">※ 수량(개수)이 아니라 금액(달러) 기준.</span><br>
      예로 <b>반도체 수출</b>은 이렇게 갈립니다 (아래 그림 왼쪽 위 칸 x축과 동일한 숫자):<br>
      · <b style="color:#34c759">1번 칸 = 가장 쌀 때(침체)</b> = 작년比 <b>≤ {b1:+.0f}%</b> (수출 줄던 불황기)<br>
      · <b style="color:#8e8e93">3번 칸 = 한가운데(보통)</b> = 작년比 <b>{mid_lo:+.0f} ~ {mid_hi:+.0f}%</b><br>
      · <b style="color:#ff3b30">5번 칸 = 가장 비쌀 때(과열)</b> = 작년比 <b>≥ {b5:+.0f}%</b><br>
      <b>지금은?</b> 반도체 수출이 작년比 <b>+{semi['yoy']:.0f}%</b> — {b5:+.0f}% 선을 한참 넘어 <b>5번 칸(가장 비쌈·과열)</b>입니다.
    </div>
    <div class="warn"><b>막대 높이가 헷갈리지 않게 — 꼭 읽으세요.</b>
      아래 막대 높이는 <b>지표 숫자가 아니라 '그때 샀으면 삼성·하이닉스 주가가 1년 뒤 얼마 올랐나(주가 수익률)'</b>입니다
      (막대 위 숫자가 그 수익률). <b>파랑=삼성전자, 주황=SK하이닉스.</b>
      그림 4개는 가장 믿을만한 지표 4개(반도체수출·메모리수출·SOX·마이크론),
      각 그림 <b>x축의 1번~5번</b>이 그 지표의 작년比 구간 — <b>1번=가장 쌀 때 … 5번=가장 비쌀 때</b>입니다
      (초록 1·2번 / 회색 3번 / 빨강 4·5번 — <b>맨 아래 표와 똑같은 번호·색</b>).</div>
    <p class="charthint">막대를 누르면 정확한 수익률이 표시됩니다 · 파랑 삼성전자 / 주황 SK하이닉스</p>
    <div class="qgrid">{q_canvases}</div>
    <p class="big"><b>읽는 법:</b> 네 지표 모두 <b>1번(쌀 때)에서 사면 1년 뒤 수익이 크고, 5번 쪽(비쌀 때)으로 갈수록 막대가 낮아집니다</b>
    — 비쌀 때(4·5번) 산 칸은 수익이 0 근처거나 손해. = <b>쌀 때(1번) 사고 비쌀 때(5번) 팔라</b>를 20년 데이터가 한목소리로 보여줍니다.
    그리고 <b>지금은 네 지표 모두 5번 칸(과열)</b>입니다 — 바로 아래 표가 그 5번을 올해 월별로 보여줍니다.</p>
    {traj_table_html}
    <h2>4. 20년 그림으로 보기</h2>
    <div class="chartbox"><canvas id="cPrice"></canvas></div>
    <div class="chartbox"><canvas id="cYoY"></canvas></div>
    <p class="big">아래 칸(수출 증가율)이 <b>바닥을 칠 때마다</b> 위 칸(주가)도 바닥이었고, <b>치솟을 때</b> 주가도 천장이었습니다.
    그리고 <b>맨 오른쪽 = 지금</b> — 수출 증가율이 20년 중 가장 높이 치솟아 있습니다(과열).</p>
    {leadlag_section}
    <h2>6. 꼭 기억할 점</h2>
    <div class="warn">
      · 이건 <b>'사이클 체온계'</b>입니다 — "지금 뜨겁다/차갑다"는 알려주지만 <b>'며칠에 사라'까지는 못 맞힙니다.</b><br>
      · <b>지금은 20년 만의 최고 과열</b>이라 역사 기준으론 '파는 자리'. 단 <b>AI/HBM 때문에 사상 처음 보는 영역</b>이라
      "이번엔 다를" 가능성도 함께 봐야 합니다(과거에 없던 상황이라 100% 장담 불가).<br>
      · <b>투자 권유가 아니라 참고용 분석</b>입니다.
    </div>
    <p class="muted">자료: 주가·SOX·마이크론·환율 = yfinance / 반도체·메모리 수출 = 관세청 수출입실적. 더 자세한 통계표(전체 선행성·IC 등)는 전문가용 v1 리포트에 있습니다.</p>
    """
    # Chart.js 라이브러리(인라인) + 데이터(JSON) + 초기화 스크립트를 body 끝에 주입
    chart_json = json.dumps(chart_payload, ensure_ascii=False)
    scripts = ("<script>" + _read_chartjs() + "</script>\n"
               "<script>window.__CHARTDATA__=" + chart_json + ";\n" + INIT_JS + "</script>")

    out = f"<!doctype html><html lang='ko'><head><meta charset='utf-8'>" \
          f"<meta name='viewport' content='width=device-width,initial-scale=1'>" \
          f"<title>반도체 사이클 쉬운 리포트 v3</title>{style}</head><body>{body}{scripts}</body></html>"
    out_path = os.path.join(REPORTS, "백테스트_리포트_v3.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(out)
    print("저장:", out_path, "|", round(len(out) / 1024, 1), "KB | 종합점수", round(score, 2), verdict)


if __name__ == "__main__":
    main()

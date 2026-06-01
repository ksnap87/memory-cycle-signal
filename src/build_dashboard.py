"""
Phase B 대시보드 — docs/signals.json 을 읽어 docs/index.html(폰 친화) 생성.

외부 JS/CDN 없이 순수 HTML+CSS+인라인 SVG로 그린다(스파크라인 포함).
  → StatiCrypt로 통째 암호화해도 깨지지 않는 단일 파일.
값은 Python에서 직접 박아 넣음(JS 데이터주입 없음). 투자권유 아님 — '사이클 체온계'.
"""
import os
import json
import html

from analyze import HERE

DOCS = os.path.join(HERE, "docs")
ZONE_COLOR = {"매수권": "#34c759", "중립": "#8e8e93", "매도권": "#ff3b30"}
ZONE_TEXT = {"매수권": "🟢 매수", "중립": "⚪ 중립", "매도권": "🔴 매도"}


def sparkline(vals: list, color: str, w: int = 132, h: int = 34) -> str:
    """24개월 추세 인라인 SVG. 자체 min~max로 정규화(값 스케일이 시그널마다 달라서)."""
    if not vals or len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    n = len(vals)
    pts = [(i / (n - 1) * (w - 4) + 2, h - 3 - (v - lo) / rng * (h - 6))
           for i, v in enumerate(vals)]
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    cx, cy = pts[-1]
    # 0선이 범위 안에 있으면 점선으로 표시
    zero = ""
    if lo < 0 < hi:
        zy = h - 3 - (0 - lo) / rng * (h - 6)
        zero = f'<line x1="2" y1="{zy:.1f}" x2="{w - 2}" y2="{zy:.1f}" stroke="#d2d2d7" stroke-width="1" stroke-dasharray="3,2"/>'
    return (f'<svg class="spark" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'{zero}<polyline fill="none" stroke="{color}" stroke-width="2" '
            f'stroke-linejoin="round" stroke-linecap="round" points="{poly}"/>'
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="2.8" fill="{color}"/></svg>')


def pos_gauge(percentile: float, zone: str, direction: str) -> str:
    """20년 분포상 현재 위치 — ◀바닥(매수우호) … 천장(매도우호)▶ 트랙 + 존색 마커.
    원달러(high_is_buy)는 '높을수록 매수우호'라 축이 반대 → 위치를 뒤집어
    왼쪽(바닥/매수)·오른쪽(천장/매도)의 색·의미를 다른 지표와 일치시킨다."""
    c = ZONE_COLOR.get(zone, "#8e8e93")
    pos = percentile if direction == "low_is_buy" else 100 - percentile
    left = max(0, min(100, pos))
    return (
        '<div class="gauge">'
        '<div class="track"><div class="seg g"></div><div class="seg n"></div><div class="seg r"></div>'
        f'<div class="mark" style="left:{left:.0f}%;background:{c}"></div></div>'
        '<div class="gax"><span>◀ 바닥(쌀 때)</span><span>천장(비쌀 때) ▶</span></div>'
        '</div>')


def thr_text(s: dict) -> str:
    """임계값 안내(작년比 기준) — 어디부터 매수/매도인지."""
    t = s["thresholds"]
    if s["direction"] == "low_is_buy":
        return f'작년比 ≤ {t["buy_below"]:+.0f}% 면 매수권 · ≥ {t["sell_above"]:+.0f}% 면 매도권'
    return f'작년比 ≥ {t["buy_above"]:+.0f}% 면 매수권 · ≤ {t["sell_below"]:+.0f}% 면 매도권'


def yoy_badge(yv: float) -> str:
    if yv >= 0:
        return f'<b style="color:#d70015">▲ {yv:+.0f}%</b>'
    return f'<b style="color:#0071e3">▼ {yv:+.0f}%</b>'


def score_gauge(score: float) -> str:
    """종합점수 −1(과열/매도) … +1(침체/매수). 마커 위치 = (score+1)/2."""
    left = max(0, min(100, (score + 1) / 2 * 100))
    return (
        '<div class="sgauge">'
        '<div class="strack"><div class="sseg r"></div><div class="sseg n"></div><div class="sseg g"></div>'
        f'<div class="smark" style="left:{left:.1f}%"></div></div>'
        '<div class="sax"><span>−1 과열(팔자)</span><span>0 중립</span><span>침체(사자) +1</span></div>'
        '</div>')


def _bin_color(q: int) -> str:
    """칸 색 — 낮을수록(쌀 때) 초록, 가운데 회색, 높을수록(비쌀 때) 빨강. 리포트와 동일."""
    if q <= 2:
        return "#34c759"
    if q >= 4:
        return "#ff3b30"
    return "#8e8e93"


def qbar_chart(bt_q: list, cur_q: int) -> str:
    """한 지표의 '칸별 1년 성적표' 미니 막대그래프(인라인 SVG).
    x축 = 1~5번 칸(1=가장 쌀 때 … 5=가장 비쌀 때), 막대높이 = 그 칸일 때 사서 1년 뒤 평균수익%.
    색은 _bin_color(쌀 때 초록·보통 회색·비쌀 때 빨강), '지금' 칸은 진하게+번호칩 강조."""
    vals = [(v if isinstance(v, (int, float)) else 0.0) for v in (bt_q or [0] * 5)]
    mx = max(vals + [1.0])
    W, H = 156, 106
    x0, x1, base, top = 12, 148, 76, 24
    maxh = base - top
    slot = (x1 - x0) / 5
    bw = slot * 0.6
    parts = [f'<line x1="{x0}" y1="{base}" x2="{x1}" y2="{base}" stroke="#d2d2d7" stroke-width="1"/>']
    for i, v in enumerate(vals):
        q = i + 1
        col = _bin_color(q)
        h = max(2.0, (v / mx) * maxh) if v > 0 else 2.0
        bx = x0 + slot * i + (slot - bw) / 2
        by = base - h
        cx = bx + bw / 2
        cur = (q == cur_q)
        op = "1" if cur else "0.4"
        if cur:
            parts.append(f'<rect x="{bx - 4:.1f}" y="{top - 8:.1f}" width="{bw + 8:.1f}" '
                         f'height="{base - top + 30:.1f}" rx="6" fill="#0071e3" fill-opacity="0.07"/>')
        parts.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw:.1f}" height="{h:.1f}" '
                     f'rx="3" fill="{col}" opacity="{op}"/>')
        parts.append(f'<text x="{cx:.1f}" y="{by - 3:.1f}" text-anchor="middle" font-size="8.5" '
                     f'fill="{col}" opacity="{op}" font-weight="700">{v:.0f}%</text>')
        if cur:
            parts.append(f'<rect x="{cx - 9:.1f}" y="{base + 6:.1f}" width="18" height="15" rx="4" fill="{col}"/>')
            parts.append(f'<text x="{cx:.1f}" y="{base + 17:.1f}" text-anchor="middle" font-size="9.5" '
                         f'fill="#fff" font-weight="700">{q}</text>')
        else:
            parts.append(f'<text x="{cx:.1f}" y="{base + 17:.1f}" text-anchor="middle" font-size="9.5" '
                         f'fill="#8e8e93">{q}</text>')
    return (f'<svg viewBox="0 0 {W} {H}" class="qbar" width="100%" '
            f'preserveAspectRatio="xMidYMid meet">{"".join(parts)}</svg>')


# 사이클 지표(작년比 낮을수록 쌀 때) — 원달러는 방향 반대라 이 그래프에서 제외(카드에서 따로).
CYCLE_LABELS = ["반도체수출 YoY", "메모리수출 YoY", "SOX YoY", "마이크론 YoY"]


def cycle_block(d: dict) -> str:
    """'칸별 1년 성적표' 그래프 4개 + 밑에 1~5번 설명 — 리포트 3번 섹션과 같은 말로 동기화."""
    by_label = {s["label"]: s for s in d["signals"]}
    cells = ""
    for lab in CYCLE_LABELS:
        s = by_label.get(lab)
        if not s or not s.get("bt_q") or all(v is None for v in s["bt_q"]):
            continue
        q = int(s["q"])
        chart = qbar_chart(s["bt_q"], q)
        cells += (f'<div class="qcell"><div class="qcap">{html.escape(s["name"])} '
                  f'<span class="stars">{s["stars"]}</span></div>{chart}'
                  f'<div class="qnow">지금 <b style="color:{_bin_color(q)}">{q}번 칸</b></div></div>')
    if not cells:
        return ""
    head = by_label.get("반도체수출 YoY", {})
    bp = head.get("bins_pct") or [None, None, None, None]
    p20, p80 = bp[0], bp[3]
    rng = ""
    if isinstance(p20, (int, float)) and isinstance(p80, (int, float)):
        rng = (f' 가장 믿을만한 <b>반도체 수출</b>은 작년比 <b>≤{p20:+.0f}%</b>면 1번(쌀 때), '
               f'<b>≥{p80:+.0f}%</b>면 5번(비쌀 때)인데 — 지금은 한참 위입니다.')
    return f"""
      <div class="sec">
        <div class="sech">지금 사이클 어느 칸? — 20년 칸별 성적표</div>
        <div class="qgrid">{cells}</div>
        <div class="qexp">
          각 지표의 <b>작년 같은 달 대비 증가율</b>을 2013년 이후 줄세워 <b>5칸(1번~5번)</b>으로 나눈 것입니다.
          막대 = 그 칸일 때 사서 <b>1년 묵혔으면 평균 몇 % 올랐나</b>(20년 백테스트).
          <b style="color:#34c759">1번(가장 쌀 때)</b>에 살수록 수익이 크고
          <b style="color:#ff3b30">5번(가장 비쌀 때)</b>일수록 0에 가깝거나 손해 —
          <span class="muted">초록=쌀 때(1·2) · 회색=보통(3) · 빨강=비쌀 때(4·5).</span><br>
          <b>지금은 네 지표 모두 5번 칸</b>입니다.{rng}
          역사적으로 5번은 <b>사는 자리가 아니라 파는 자리</b>였습니다.
          <span class="muted">※ 원/달러는 방향이 반대인 보조지표라 아래 카드에서 따로 봅니다.</span>
        </div>
      </div>"""


def main() -> None:
    with open(os.path.join(DOCS, "signals.json"), encoding="utf-8") as f:
        d = json.load(f)
    comp = d["composite"]

    cards = ""
    for s in d["signals"]:
        spark = sparkline(s["spark"], ZONE_COLOR.get(s["zone"], "#8e8e93"))
        cards += f"""
        <div class="card">
          <div class="chead">
            <div><span class="nm">{html.escape(s['name'])}</span>
                 <span class="stars">{s['stars']}</span></div>
            <span class="pill" style="background:{ZONE_COLOR[s['zone']]}">{ZONE_TEXT[s['zone']]}</span>
          </div>
          <div class="crow">
            <div class="kv"><span class="k">작년 같은 달 대비</span>{yoy_badge(s['yoy'])}</div>
            <div class="kv"><span class="k">20년 중 위치</span><b>상위 {100 - s['percentile']:.0f}%</b> · {s['q']}번 칸</div>
            <div class="sp">{spark}<span class="splab">최근 24개월</span></div>
          </div>
          {pos_gauge(s['percentile'], s['zone'], s['direction'])}
          <div class="thr">{thr_text(s)}</div>
          <div class="trust">{html.escape(s['trust'])} · 기준월 {s['asof']}</div>
        </div>"""

    notes = "".join(f"<li>{html.escape(n)}</li>" for n in d.get("notes", []))
    exp_through = d.get("export_through") or "—"

    style = """
    <style>
      :root{color-scheme:light dark}
      *{box-sizing:border-box}
      body{font-family:-apple-system,'Apple SD Gothic Neo',sans-serif;margin:0;
           background:#f5f5f7;color:#1d1d1f;line-height:1.6}
      .wrap{max-width:680px;margin:0 auto;padding:18px 14px 40px}
      h1{font-size:1.35rem;margin:.2em 0}
      .sub{color:#8e8e93;font-size:.82rem;margin-bottom:1em}
      .verdict{border-radius:16px;padding:18px 18px;color:#fff;margin:.4em 0 .2em}
      .verdict .vt{font-size:1.2rem;font-weight:700}
      .verdict .vs{font-size:.85rem;opacity:.95;margin-top:3px}
      .sgauge{margin:14px 2px 2px}
      .strack{position:relative;height:9px;border-radius:6px;overflow:hidden;display:flex}
      .sseg{height:100%} .sseg.r{flex:2;background:#ffb3ad} .sseg.n{flex:1;background:#e5e5ea} .sseg.g{flex:2;background:#a7e8bd}
      .smark{position:absolute;top:-4px;width:4px;height:17px;border-radius:3px;background:#1d1d1f;transform:translateX(-2px);box-shadow:0 0 0 2px #fff}
      .sax{display:flex;justify-content:space-between;color:#8e8e93;font-size:.7rem;margin-top:4px}
      .card{background:#fff;border:1px solid #e5e5ea;border-radius:16px;padding:15px 16px;margin:12px 0;
            box-shadow:0 1px 3px rgba(0,0,0,.04)}
      .chead{display:flex;justify-content:space-between;align-items:center;gap:8px}
      .nm{font-weight:700;font-size:1.05rem} .stars{color:#ff9f0a;font-size:.85rem;margin-left:5px}
      .pill{color:#fff;font-weight:600;font-size:.82rem;padding:4px 12px;border-radius:999px;white-space:nowrap}
      .crow{display:flex;flex-wrap:wrap;gap:10px 18px;align-items:center;margin:11px 0 4px}
      .kv{display:flex;flex-direction:column} .kv .k{color:#8e8e93;font-size:.72rem}
      .kv b{font-size:1.05rem;font-variant-numeric:tabular-nums}
      .sp{margin-left:auto;text-align:center} .spark{display:block}
      .splab{color:#8e8e93;font-size:.66rem}
      .gauge{margin:9px 0 4px}
      .track{position:relative;height:8px;border-radius:5px;overflow:hidden;display:flex}
      .seg{height:100%} .seg.g{flex:2;background:#a7e8bd} .seg.n{flex:1;background:#e5e5ea} .seg.r{flex:2;background:#ffb3ad}
      .mark{position:absolute;top:-3px;width:14px;height:14px;border-radius:50%;transform:translateX(-7px);border:2px solid #fff;box-shadow:0 1px 2px rgba(0,0,0,.25)}
      .gax{display:flex;justify-content:space-between;color:#8e8e93;font-size:.68rem;margin-top:3px}
      .thr{color:#3a3a3c;font-size:.78rem;margin-top:8px;padding-top:8px;border-top:1px solid #f0f0f2}
      .trust{color:#8e8e93;font-size:.72rem;margin-top:3px}
      .foot{background:#fff4e5;border-left:4px solid #ff9500;border-radius:10px;padding:13px 16px;margin-top:18px;font-size:.82rem}
      .foot ul{margin:.4em 0;padding-left:1.1em} .foot li{margin:.25em 0}
      .src{color:#8e8e93;font-size:.72rem;margin-top:14px;text-align:center}
      .sec{background:#fff;border:1px solid #e5e5ea;border-radius:16px;padding:15px 16px;margin:14px 0;
           box-shadow:0 1px 3px rgba(0,0,0,.04)}
      .sech{font-weight:700;font-size:1.02rem;margin-bottom:10px}
      .qgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(148px,1fr));gap:8px 6px}
      .qcell{text-align:center;padding:4px 2px}
      .qcap{font-size:.8rem;font-weight:600;line-height:1.3}
      .qcap .stars{color:#ff9f0a;font-size:.72rem;margin-left:2px}
      .qbar{display:block;margin:1px auto 0}
      .qnow{font-size:.74rem;color:#8e8e93;margin-top:1px}
      .qexp{font-size:.82rem;color:#3a3a3c;margin-top:11px;padding-top:11px;border-top:1px solid #f0f0f2;line-height:1.65}
      @media(prefers-color-scheme:dark){
        body{background:#000;color:#f5f5f7} .card,.sec{background:#1c1c1e;border-color:#2c2c2e}
        .thr{color:#c7c7cc;border-top-color:#2c2c2e} .sub,.trust,.gax,.sax,.splab,.src,.kv .k,.qnow{color:#8e8e93}
        .qexp{color:#c7c7cc;border-top-color:#2c2c2e}
        .foot{background:#2a2113;color:#f5f5f7}}
    </style>"""

    body = f"""
    <div class="wrap">
      <h1>반도체 사이클 신호등</h1>
      <div class="sub">삼성전자 · SK하이닉스 &nbsp;|&nbsp; 갱신 {d['updated_at']}
        &nbsp;|&nbsp; 주가 {d['price_through']} · 수출 {exp_through} 기준</div>

      <div class="verdict" style="background:{comp['color']}">
        <div class="vt">{comp['verdict']}</div>
        <div class="vs">종합점수 {comp['score']:+.2f} · 5개 지표를 신뢰도(가중치)로 합산</div>
      </div>
      {score_gauge(comp['score'])}

      {cycle_block(d)}

      {cards}

      <div class="foot">
        <b>꼭 기억할 점</b>
        <ul>{notes}</ul>
        <b>이건 '사이클 체온계'</b>입니다 — 지금 뜨겁다/차갑다는 알려주지만 '며칠에 사라'까지는 못 맞힙니다.
        <b>투자권유가 아니라 참고용 분석</b>입니다.
      </div>
      <div class="src">자료: 주가·SOX·마이크론·환율 = yfinance / 반도체·메모리 수출 = 관세청 수출입실적<br>
        매수/매도 임계값은 2013년 이후 20년 백테스트로 산출(고정), 현재값은 매주 자동 갱신.</div>
    </div>"""

    out = ("<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
           "<meta name='viewport' content='width=device-width,initial-scale=1'>"
           "<meta name='robots' content='noindex,nofollow'>"
           f"<title>반도체 사이클 신호등</title>{style}</head><body>{body}</body></html>")
    out_path = os.path.join(DOCS, "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"저장: {out_path} | {round(len(out) / 1024, 1)} KB")


if __name__ == "__main__":
    main()

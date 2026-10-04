"""
관세청 품목별 수출입실적 API — 반도체(HS 8542) 월별 수출액 수집.

엔드포인트: http://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList
키: 환경변수 CUSTOMS_API_KEY  또는  secrets.local.yaml 의 customs_api_key
    (secrets.local.yaml 은 .gitignore 처리됨 — 절대 커밋 안 됨)

사용:
  python3 src/fetch_exports.py --probe 202504   # 한 달치 원본 응답 구조 확인(첫 실행용)
  python3 src/fetch_exports.py                   # 전체기간 수집 → data/raw/exports_8542.csv
"""
import os
import sys
import argparse
import xml.etree.ElementTree as ET
from urllib.parse import unquote
import time
import requests
import pandas as pd

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(HERE, "data", "raw")
os.makedirs(RAW, exist_ok=True)

ENDPOINT = "https://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList"
# data.go.kr 은 해외(GitHub Actions 러너) 접속이 간헐적으로 타임아웃 난다(2026-08·09 월간 실행 실패).
# → 같은 요청을 백오프 재시도하고, https 연결이 안 되면 공식 문서상 주소인 http 로도 시도한다.
ENDPOINT_FALLBACK = ENDPOINT.replace("https://", "http://", 1)
RETRY_WAITS = (5, 15, 45)          # 실패 시 대기(초) — 최대 4회 시도
TIMEOUT = (20, 60)                 # (연결, 응답) 초
HS_SEMICONDUCTOR = "8542"   # 전자집적회로(반도체 핵심). 메모리만 보려면 854232
START_YYMM = "200601"


def load_key() -> str:
    key = os.environ.get("CUSTOMS_API_KEY")
    if not key:
        sp = os.path.join(HERE, "secrets.local.yaml")
        if os.path.exists(sp):
            import yaml
            with open(sp, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            key = data.get("customs_api_key")
    if not key:
        sys.exit("키 없음. 환경변수 CUSTOMS_API_KEY 설정 또는 secrets.local.yaml 에 customs_api_key 작성")
    # data.go.kr 은 같은 키를 'Encoding'(%2B·%2F 등 이미 퍼센트인코딩됨)과
    # 'Decoding'(+·/ 등 원문) 두 형태로 제공한다. requests 는 params 를 다시 인코딩하므로
    # Encoding 키를 그대로 넣으면 '%2B'→'%252B' 이중 인코딩되어 403(권한없음)이 난다.
    # unquote 로 항상 Decoding 형태로 통일 → requests 가 정확히 한 번만 인코딩하게 한다.
    return unquote(key.strip())


def call(key: str, strt: str, end: str, hs: str = HS_SEMICONDUCTOR) -> requests.Response:
    params = {
        "serviceKey": key,
        "strtYymm": strt,
        "endYymm": end,
        "hsSgn": hs,
    }
    last_err: Exception | None = None
    for attempt in range(len(RETRY_WAITS) + 1):
        for url in (ENDPOINT, ENDPOINT_FALLBACK):
            try:
                r = requests.get(url, params=params, timeout=TIMEOUT)
                if r.status_code < 500:      # 4xx 는 키/권한 문제 → 재시도해도 같으므로 바로 반환
                    return r
                last_err = RuntimeError(f"HTTP {r.status_code}")
            except requests.RequestException as e:
                last_err = e
        if attempt < len(RETRY_WAITS):
            wait = RETRY_WAITS[attempt]
            print(f"  … 관세청 접속 실패({type(last_err).__name__}) — {wait}초 후 재시도 ({attempt + 1}/{len(RETRY_WAITS)})")
            time.sleep(wait)
    raise RuntimeError(f"관세청 API 접속 실패(재시도 {len(RETRY_WAITS)}회 소진): {last_err}")


def probe(key: str, yymm: str) -> None:
    """첫 실행용: 원본 응답 그대로 출력해서 실제 필드명/월별 여부 확인."""
    r = call(key, yymm, yymm)
    print("HTTP", r.status_code, "| URL:", r.url.replace(key, "***KEY***"))
    print("-" * 60)
    print(r.text[:3000])


FIELDS = ("total_8542", "memory_854232", "dram", "nand",
          "wgt_8542", "wgt_854232", "wgt_dram", "wgt_nand")

# getNitemtradeList 는 '조회한 hsSgn 단위' 실적만 돌려준다(하위코드로 자동 분해해 주지 않음).
# 따라서 반도체·메모리·디램·낸드를 각각 따로 호출해 채워야 한다.
# (금액필드, 중량필드, 조회할 HS코드)
HS_TARGETS = (
    ("total_8542",    "wgt_8542",   "8542"),        # 반도체(전자집적회로) 전체
    ("memory_854232", "wgt_854232", "854232"),      # 메모리(D램·플래시 등)
    ("dram",          "wgt_dram",   "8542321010"),  # 디램(DRAM)
    ("nand",          "wgt_nand",   "8542321030"),  # 낸드(플래시 메모리)
)


def sum_months(xml_text: str) -> dict:
    """단일 hsSgn 조회 응답 XML → {YYYY-MM: (금액USD합, 중량kg합)}. '총계' 행은 제외.
    금액=expDlr(USD), 중량=expWgt(kg). 중량도 같이 모아 평균단가($/kg)=금액/중량 분해에 쓴다."""
    root = ET.fromstring(xml_text)
    code = root.findtext(".//resultCode")
    if code not in (None, "00"):
        raise RuntimeError(f"API 오류 resultCode={code} msg={root.findtext('.//resultMsg')}")
    out: dict = {}
    for it in root.iter("item"):
        ym = (it.findtext("year") or "").strip()
        if "." not in ym:            # '총계' 같은 합계행 제외
            continue
        exp = float(it.findtext("expDlr") or 0)
        wgt = float(it.findtext("expWgt") or 0)
        key = ym.replace(".", "-")   # "2025.04" -> "2025-04"
        e, w = out.get(key, (0.0, 0.0))
        out[key] = (e + exp, w + wgt)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", metavar="YYYYMM", help="한 달치 원본 응답 확인")
    ap.add_argument("--full", action="store_true", help="2006년부터 전체 재수집(기본: 최근 2년만 받아 기존 CSV에 덮어쓰기)")
    args, _ = ap.parse_known_args()

    key = load_key()
    if args.probe:
        probe(key, args.probe)
        return

    out_path = os.path.join(RAW, "exports_semiconductor.csv")
    old = None
    if not args.full and os.path.exists(out_path):
        old = pd.read_csv(out_path, index_col=0, parse_dates=True, encoding="utf-8-sig")
        if old.empty:
            old = None

    # HS코드별 × 연도별로 끊어 호출(응답 과대·캡 방지).
    # 기본은 '증분' — 작년·올해만 받아 기존 CSV의 같은 달을 덮어쓴다(관세청 잠정→확정치 수정 반영).
    # HS 4종 × 2년 = 8콜이라 접속 불안정에 덜 노출된다. CSV가 없거나 --full 이면 2006년부터 전체.
    end = pd.Timestamp.today()
    start_year = end.year - 1 if old is not None else int(START_YYMM[:4])
    rows: dict = {}
    for val_f, wgt_f, hs in HS_TARGETS:
        got = set()
        for yr in range(start_year, end.year + 1):
            strt = f"{yr}01"
            last = f"{yr}{end.month:02d}" if yr == end.year else f"{yr}12"
            r = call(key, strt, last, hs)
            if r.status_code != 200:
                # data.go.kr 은 사유를 본문에 담아 준다(예: SERVICE_KEY_IS_NOT_REGISTERED_ERROR,
                # 등록되지 않은 서비스키, 활용중지 등) → 상태코드만 보지 말고 본문을 그대로 노출.
                body = r.text.strip().replace("\n", " ")[:300]
                raise RuntimeError(f"HTTP {r.status_code} — 관세청 응답: {body}")
            for month, (e, w) in sum_months(r.text).items():
                rec = rows.setdefault(month, {f: 0.0 for f in FIELDS})
                rec[val_f] += e
                rec[wgt_f] += w
                got.add(month)
        print(f"  HS {hs}: {len(got)}개월 수집")

    df = pd.DataFrame(rows).T.sort_index()
    df.index = pd.to_datetime(df.index) + pd.offsets.MonthEnd(0)  # 월말로 정렬
    df.index.name = "date"
    # 금액: USD → 백만$ , 중량: kg → 톤 (읽기 편하게)
    val_cols = ["total_8542", "memory_854232", "dram", "nand"]
    wgt_cols = ["wgt_8542", "wgt_854232", "wgt_dram", "wgt_nand"]
    df[val_cols] = df[val_cols] / 1e6
    df[wgt_cols] = df[wgt_cols] / 1e3
    df = df.rename(columns={
        "total_8542": "반도체수출_8542_백만$", "memory_854232": "메모리수출_854232_백만$",
        "dram": "디램수출_백만$", "nand": "낸드수출_백만$",
        "wgt_8542": "반도체수출_8542_톤", "wgt_854232": "메모리수출_854232_톤",
        "wgt_dram": "디램수출_톤", "wgt_nand": "낸드수출_톤",
    })
    df = df[["반도체수출_8542_백만$", "메모리수출_854232_백만$", "디램수출_백만$", "낸드수출_백만$",
             "반도체수출_8542_톤", "메모리수출_854232_톤", "디램수출_톤", "낸드수출_톤"]]

    if old is not None:
        prev_last = old.index.max()
        df = pd.concat([old[~old.index.isin(df.index)], df]).sort_index()[old.columns]
        new_months = [d.strftime("%Y-%m") for d in df.index if d > prev_last]
        print(f"  기존 마지막 달 {prev_last:%Y-%m} → 새로 추가: {', '.join(new_months) or '없음(아직 미발표)'}")

    df.to_csv(out_path, encoding="utf-8-sig")
    print(f"\n저장: {out_path}")
    print(f"기간: {df.index.min().date()} ~ {df.index.max().date()}  ({len(df)}개월)")
    print(df.head(2).round(0).to_string())
    print("...")
    print(df.tail(3).round(0).to_string())


if __name__ == "__main__":
    main()

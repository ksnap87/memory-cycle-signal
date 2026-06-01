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
import requests
import pandas as pd

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(HERE, "data", "raw")
os.makedirs(RAW, exist_ok=True)

ENDPOINT = "https://apis.data.go.kr/1220000/Itemtrade/getItemtradeList"
HS_SEMICONDUCTOR = "8542"   # 전자집적회로(반도체 핵심). 메모리만 보려면 854232
START_YYMM = "200601"


def load_key() -> str:
    key = os.environ.get("CUSTOMS_API_KEY")
    if key:
        return key
    sp = os.path.join(HERE, "secrets.local.yaml")
    if os.path.exists(sp):
        import yaml
        with open(sp, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if data.get("customs_api_key"):
            return data["customs_api_key"]
    sys.exit("키 없음. 환경변수 CUSTOMS_API_KEY 설정 또는 secrets.local.yaml 에 customs_api_key 작성")


def call(key: str, strt: str, end: str, hs: str = HS_SEMICONDUCTOR) -> requests.Response:
    params = {
        "serviceKey": key,
        "strtYymm": strt,
        "endYymm": end,
        "hsSgn": hs,
    }
    return requests.get(ENDPOINT, params=params, timeout=30)


def probe(key: str, yymm: str) -> None:
    """첫 실행용: 원본 응답 그대로 출력해서 실제 필드명/월별 여부 확인."""
    r = call(key, yymm, yymm)
    print("HTTP", r.status_code, "| URL:", r.url.replace(key, "***KEY***"))
    print("-" * 60)
    print(r.text[:3000])


FIELDS = ("total_8542", "memory_854232", "dram", "nand",
          "wgt_8542", "wgt_854232", "wgt_dram", "wgt_nand")


def parse_month_sums(xml_text: str) -> dict:
    """응답 XML → {YYYY-MM: {금액·중량 합계}}. '총계' 행은 제외.
    금액=expDlr(USD), 중량=expWgt(kg). 디램=8542321010, 낸드(플래시)=8542321030.
    → 평균단가($/kg)=금액/중량 으로 '물량 vs 가격'을 분해할 수 있게 중량도 같이 수집."""
    root = ET.fromstring(xml_text)
    code = root.findtext(".//resultCode")
    if code not in (None, "00"):
        raise RuntimeError(f"API 오류 resultCode={code} msg={root.findtext('.//resultMsg')}")
    out: dict = {}
    for it in root.iter("item"):
        ym = (it.findtext("year") or "").strip()
        if "." not in ym:            # '총계' 같은 합계행 제외
            continue
        hs = (it.findtext("hsCode") or "").strip()
        exp = float(it.findtext("expDlr") or 0)
        wgt = float(it.findtext("expWgt") or 0)
        key = ym.replace(".", "-")   # "2025.04" -> "2025-04"
        rec = out.setdefault(key, {f: 0.0 for f in FIELDS})
        rec["total_8542"] += exp
        rec["wgt_8542"] += wgt
        if hs.startswith("854232"):
            rec["memory_854232"] += exp
            rec["wgt_854232"] += wgt
        if hs == "8542321010":       # 디램(DRAM)
            rec["dram"] += exp
            rec["wgt_dram"] += wgt
        elif hs == "8542321030":     # 낸드(플래시 메모리)
            rec["nand"] += exp
            rec["wgt_nand"] += wgt
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", metavar="YYYYMM", help="한 달치 원본 응답 확인")
    ap.add_argument("--hs", default=HS_SEMICONDUCTOR)
    args = ap.parse_args()

    key = load_key()
    if args.probe:
        probe(key, args.probe)
        return

    # 전체기간 수집 — 연도별로 끊어 호출(응답 과대·캡 방지). 20여 콜 << 일 10,000.
    end = pd.Timestamp.today()
    rows: dict = {}
    for yr in range(int(START_YYMM[:4]), end.year + 1):
        strt = f"{yr}01"
        last = f"{yr}{end.month:02d}" if yr == end.year else f"{yr}12"
        r = call(key, strt, last, args.hs)
        r.raise_for_status()
        part = parse_month_sums(r.text)
        rows.update(part)
        print(f"  {yr}: {len(part)}개월 수집")

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

    out_path = os.path.join(RAW, "exports_semiconductor.csv")
    df.to_csv(out_path, encoding="utf-8-sig")
    print(f"\n저장: {out_path}")
    print(f"기간: {df.index.min().date()} ~ {df.index.max().date()}  ({len(df)}개월)")
    print(df.head(2).round(0).to_string())
    print("...")
    print(df.tail(3).round(0).to_string())


if __name__ == "__main__":
    main()

"""
Phase B 주간 갱신 ① — 최신 데이터를 새로 받아 패널을 업데이트한다.

주가·SOX·마이크론·환율(yfinance)은 매번 갱신.
반도체·메모리 수출(관세청)은 API 키가 있을 때만 갱신 — 키가 없으면(예: CI에 시크릿
미설정) 경고만 남기고 기존 CSV를 그대로 둔다(파이프라인이 멈추지 않게).

흐름:  fetch_current.py → compute_signals.py → build_dashboard.py
"""
import sys

import fetch_data
import fetch_exports
import fetch_flows


def main() -> None:
    print("[1/3] 주가·SOX·마이크론·환율 갱신 (yfinance) …")
    fetch_data.main()

    print("\n[2/3] 반도체·메모리 수출 갱신 (관세청) …")
    try:
        fetch_exports.main()
    except SystemExit as e:
        # load_key()가 키 없을 때 sys.exit(메시지) 함 → CI에서 죽지 않게 흡수
        print(f"  ⚠ 수출 데이터 건너뜀(키 없음/오류): {e}\n    → 기존 exports CSV를 그대로 사용합니다.")
    except Exception as e:  # 네트워크/파싱 오류도 비치명적으로 처리
        print(f"  ⚠ 수출 데이터 갱신 실패: {e}\n    → 기존 exports CSV를 그대로 사용합니다.")

    print("\n[3/3] 투자자 수급(외국인·기관 순매수) 갱신 (KRX) …")
    try:
        fetch_flows.main()
    except SystemExit as e:
        print(f"  ⚠ 수급 데이터 건너뜀: {e}\n    → 기존 flows CSV를 그대로 사용합니다.")
    except Exception as e:  # KRX 응답/네트워크 오류도 비치명적으로 처리
        print(f"  ⚠ 수급 데이터 갱신 실패: {e}\n    → 기존 flows CSV를 그대로 사용합니다.")

    print("\n갱신 완료. 다음: python3 src/compute_signals.py → python3 src/build_dashboard.py")


if __name__ == "__main__":
    sys.exit(main())

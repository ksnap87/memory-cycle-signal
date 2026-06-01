# 반도체 사이클 신호등

삼성전자·SK하이닉스 메모리 사이클을 **펀더멘털 데이터**(수출·업황 프록시·환율)로 읽는 '사이클 체온계'.
지금이 사이클상 **뜨거운지(과열) / 차가운지(침체)** 를 신호등으로 보여줍니다.

> ⚠️ **투자권유가 아니라 참고용 분석**입니다. 차트분석·기술적 지표는 쓰지 않습니다(펀더멘털만).
> '며칠에 사라/팔아라'를 맞히는 도구가 아니라, 사이클 위치를 알려주는 온도계입니다.

## 어떻게 동작하나

```
[Phase A · 1회 백테스트]  20년치 데이터로 "잘 맞는 지표 + 매수/매도 임계값" 산출
        → signal_config.yaml (임계값·가중치 고정)
                    │
                    ▼
[Phase B · 매주 자동]  최신 데이터 수집 → 임계값과 비교 → 신호등 계산 → 대시보드 재생성
        fetch_current.py → compute_signals.py → build_dashboard.py
                    │
                    ▼
        docs/index.html (StatiCrypt 비번 암호화) → GitHub Pages 게시 → 폰에서 열람
```

지표 5종: 반도체 수출 YoY(★★★) · 메모리 수출 YoY(★★★) · 미국 반도체지수 SOX(★★) · 마이크론(★★) · 원/달러(★).
별(★)은 **데이터 신뢰도**(실물 통관금액 > 주가 프록시)이고, 매수/매도 판정은 2013년 이후 20년 백테스트로 고정한 임계값으로 합니다.

## 자동 갱신 켜는 법 (GitHub Secrets)

`.github/workflows/weekly.yml` 이 매주 월요일 08:00(KST) 자동 실행됩니다. 단, **대시보드 암호 비번**이 있어야 게시합니다.

저장소 **Settings → Secrets and variables → Actions** 에서 추가:

| 시크릿 이름 | 필수? | 설명 |
|---|---|---|
| `STATICRYPT_PASSWORD` | **필수** | 대시보드 잠금 비밀번호. 미설정이면 평문 노출 방지를 위해 게시를 건너뜁니다. |
| `CUSTOMS_API_KEY` | 선택 | 관세청 수출 데이터까지 클라우드에서 자동 갱신하려면. 없으면 주가만 갱신하고 수출은 저장된 CSV를 사용. |

> 보안상 비밀번호·API키는 **저장소 소유자가 직접** 입력합니다(코드/대화에 남기지 않음).

## 로컬 실행

```bash
pip install -r requirements.txt
# 수출 데이터까지 받으려면: secrets.local.yaml 에 customs_api_key 작성 (gitignore 처리됨)
python3 src/fetch_current.py        # 최신 데이터 수집
python3 src/compute_signals.py      # 신호등 계산 → docs/signals.json
python3 src/build_dashboard.py      # 대시보드 생성 → docs/index.html
```

## 한계/주의

- **상관 ≠ 인과.** 분석용 도구이며 투자권유가 아닙니다.
- 관세청 품목별 수출 실적은 발행지연으로 매달 중순에 전월치가 채워집니다(주가보다 1개월 늦음).
- 공개 저장소이지만 대시보드는 StatiCrypt 비밀번호로 보호하며, 보유종목 등 **개인정보는 대시보드에 넣지 않습니다**(공개 시장지표만).

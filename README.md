# Nuclear Regulation Update Tracker — NRC MVP

NRC Regulatory Guide 표를 주기적으로 읽고 이전 실행 상태와 비교해 변경을 Markdown 보고서로 남기는 최소 기능 제품(MVP)입니다.

## 현재 구현된 것

- NRC Division 1 페이지에서 `Guide Number / Title / Revision / Issue Date / Additional Information / document URL` 수집
- 이전 실행 결과를 `data/state.json`에 저장
- `NEW / MODIFIED / REMOVED` 자동 판정
- 어떤 필드가 바뀌었는지 diff 생성
- Revision/문서 링크 변경을 HIGH, 제목/발행일 변경을 MEDIUM 등으로 1차 중요도 분류
- 결과를 `reports/*.md`로 저장
- 네트워크 없이 검증할 수 있는 샘플 HTML 및 단위 테스트 포함

## 설치

Python 3.10+ 기준입니다.

```bash
python -m venv .venv
# Windows
.venv\\Scripts\\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## 첫 실행

첫 실행에서는 현재 상태를 기준선으로만 저장하는 것을 권장합니다.

```bash
python tracker.py --bootstrap
```

이후 실행:

```bash
python tracker.py
```

종료 코드는 다음 의미입니다.

- `0`: 변경 없음
- `1`: 실행 오류
- `2`: 변경 감지됨

따라서 향후 GitHub Actions, Windows Task Scheduler, cron 등에서 종료 코드 2를 이용해 알림을 연결할 수 있습니다.

## 오프라인 데모

```bash
python tracker.py --html-file tests/sample_v1.html --state data/demo_state.json --reports reports --bootstrap
python tracker.py --html-file tests/sample_v2.html --state data/demo_state.json --reports reports
```

두 번째 실행에서 `1.261 MODIFIED`, `1.263 NEW`가 감지되어야 합니다.

## 테스트

프로젝트 루트에서:

```bash
python -m unittest discover -s tests -v
```

## 이번 버전의 한계

이 MVP는 **NRC 목록 페이지의 메타데이터 변경**을 검출합니다. 즉 Revision이 바뀌었다는 사실은 잡지만, 이전 PDF와 신규 PDF 본문의 조항별 의미 차이까지 자동 비교하지는 않습니다.

다음 버전의 우선순위는 다음과 같습니다.

1. 변경된 PDF 자동 다운로드 및 버전별 보관
2. PDF 텍스트 추출
3. 이전/신규 본문의 section-aware diff
4. LLM을 통한 `무엇이 바뀌었나 / 기술적 의미 / 사업자 영향 / 중요도` 분석
5. 이메일·Slack·Discord 등 알림 연결
6. NRC 외 원안위 고시, 법령정보센터, IAEA Safety Standards로 소스 확대

## 감시 범위 변경

기본값은 최신 구간인 Division 1 `1.261–1.271` 페이지입니다. 다른 NRC 구간도 같은 표 구조라면 `--url`로 교체할 수 있습니다.

```bash
python tracker.py --url "https://www.nrc.gov/reading-rm/doc-collections/reg-guides/power-reactors/rg/division-1/division-1-241"
```

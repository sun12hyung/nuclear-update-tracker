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

## NRC 403 오류와 자동 실행

NRC는 일부 지역·클라우드 IP를 Akamai에서 차단하여 같은 공식 URL도 HTTP 403을 반환할 수 있습니다. 이 오류는 Python이나 패키지 설치 문제가 아닙니다.

- 로컬에서 접속되면 기존 명령을 그대로 사용합니다.
- 로컬에서 403이면 브라우저로 페이지를 HTML로 저장한 뒤 python tracker.py --html-file 저장파일.html로 처리할 수 있습니다.
- `.github/workflows/nrc-tracker.yml`은 매일 오전 10시(KST)에 자동 실행되며, Actions 탭에서 수동으로도 실행할 수 있습니다.
- 이전 수집 상태와 PDF 보관본은 GitHub Actions 캐시에 이어서 저장하므로, 다음 실행부터 실제 변경 여부를 비교합니다.
- 실행 결과는 `nrc-tracker-result` artifact로 내려받을 수 있습니다.
- GitHub Actions 구성요소는 Node.js 24 호환 버전을 사용합니다.

## PDF 본문 수집과 비교

```bash
python tracker.py --bootstrap --pdf-archive pdf_archive
```

각 Regulatory Guide PDF를 `pdf_archive/<문서번호>/`에 버전별로 보관하고, `pypdf`로 추출한 본문을 함께 저장합니다. 이후 PDF 링크가 바뀌면 이전 텍스트와 새 텍스트의 unified diff를 생성합니다. GitHub Actions 결과물에도 PDF, 추출 텍스트, 비교 파일이 포함됩니다.

추출된 본문은 장·절 제목을 기준으로 다시 나누어 `*.sections.json`에 저장합니다. 새 버전에서는 절별로 `ADDED / REMOVED / MODIFIED`를 판정하므로, 긴 PDF 전체 diff보다 실제로 검토해야 할 부분을 빠르게 찾을 수 있습니다.

매 실행마다 PDF를 다시 내려받아 SHA-256을 확인하므로 NRC가 같은 주소의 파일을 교체해도 변경을 감지합니다. `reports/nrc_summary_*.md`에는 변경된 문서와 장·절을 `추가 / 삭제 / 수정`으로 바꾼 간단한 한국어 요약이 생성됩니다.

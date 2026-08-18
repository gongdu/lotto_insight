# Lotto Insight 3.0 — GitHub Actions + GitHub Pages

Android 로또/연금복권 조회·통계·추천 앱입니다. 별도 FastAPI/VPS 서버를 운영하지 않고 **GitHub Actions가 동행복권 공식 데이터를 주기적으로 확인하고 GitHub Pages에 회차별 JSON을 배포**합니다. Android 앱은 Pages의 `manifest.json`을 확인한 뒤 자신에게 없는 회차만 다운로드해 로컬 SQLite에 반영합니다.

## 구조

```text
동행복권 공식 사이트
        ↓
GitHub Actions (목/토 자동 + 수동 실행)
        ↓
automation/updater.py
        ↓
임시 SQLite (.runtime/lotto_app.db)
        ↓
회차별 JSON 생성
        ↓
GitHub Pages (HTTPS)
        ↓
Android WorkManager / 수동 동기화
        ↓
휴대폰 내부 lotto_app.db
```

SQLite 바이너리 전체를 매주 Git에 커밋하지 않습니다. `data/seed/lotto_app.db`는 최초 기준 DB로 한 번만 저장하고, 이후 변경분은 `public/data/<dataset>/<round>.json`처럼 작은 회차 파일만 커밋합니다. Action은 매 실행마다 seed DB + 기존 JSON을 합쳐 현재 DB를 복원한 뒤 신규 회차를 수집합니다.

## 1. GitHub에 올리기

1. GitHub에서 **Public repository** 하나를 만듭니다. 예: `lotto-insight`.
2. 이 프로젝트의 **내용 전체**를 저장소 루트에 올립니다. `.github/` 폴더도 반드시 포함해야 합니다.
3. 저장소에서 **Settings → Pages → Build and deployment → Source → GitHub Actions**를 선택합니다.
4. **Actions** 탭에서 `Update lottery data and deploy Pages`를 열고 **Run workflow**를 한 번 실행합니다.
5. 성공하면 Pages 주소는 보통 아래 형태입니다.

```text
https://GITHUB_ID.github.io/REPOSITORY_NAME
```

예:

```text
https://honggildong.github.io/lotto-insight
```

브라우저에서 위 주소를 열어 최신 회차가 표시되는지 확인합니다. `manifest.json`, `health.json`, 최신 `lotto_app.db`도 같은 Pages에서 제공됩니다.

## 2. 자동 업데이트 시간

`.github/workflows/update-pages.yml`에 UTC cron이 설정되어 있습니다. 한국시간 기준:

- 목요일 20:17, 21:17 — 연금복권 결과/판매점 확인
- 토요일 21:17, 22:17, 23:17 — 로또 결과/판매점 확인
- 일요일 09:17 — 누락 복구용 재확인
- Actions 화면의 `Run workflow` — 언제든 수동 실행

수집은 멱등성 있게 작성되어 이미 저장된 회차를 중복 삽입하지 않습니다. 한 종류의 데이터 수집이 실패해도 기존 정상 데이터는 보존됩니다.

> GitHub의 예약 실행은 정확한 초 단위 스케줄러가 아니며 서비스 부하에 따라 지연될 수 있습니다. 앱의 `지금 동기화`는 Pages에 이미 배포된 데이터를 즉시 확인합니다.

## 3. Android 앱 연결

Android Studio에서 `android/` 폴더를 엽니다. 홈 화면의 **GitHub Pages 데이터 주소**에 Pages URL을 입력하고 `저장` → `지금 동기화`를 누르면 됩니다.

```text
https://GITHUB_ID.github.io/REPOSITORY_NAME
```

앱은 다음 파일만 사용합니다.

```text
/manifest.json
/data/lotto/{회차}.json
/data/lotto-stores/{회차}.json
/data/pension/{회차}.json
/data/pension-stores/{회차}.json
```

예를 들어 앱 DB가 로또 1237회까지이고 Pages manifest가 1238회라면 앱은 `data/lotto/1238.json` 하나만 받습니다.

### 앱에 URL을 미리 박아 넣고 싶을 때

`android/app/build.gradle.kts`의 아래 값을 Pages 주소로 바꾸면 사용자가 주소를 입력하지 않아도 됩니다.

```kotlin
buildConfigField("String", "PAGES_BASE_URL", "\"https://GITHUB_ID.github.io/REPOSITORY_NAME\"")
```

기본값은 빈 문자열이며 홈 화면에서 입력한 주소가 있으면 그 값을 우선 사용합니다.

## 4. 데이터 파일

- `android/app/src/main/assets/databases/lotto_app.db` — Android 최초 설치용 DB
- `data/seed/lotto_app.db` — GitHub Action 복원용 기준 DB
- `public/manifest.json` — 앱이 가장 먼저 확인하는 최신 상태
- `public/latest.json` — 최신 로또 결과
- `public/health.json` — 데이터 최신 회차 상태
- `public/data/...` — seed 이후 신규 회차 JSON
- `public/downloads/lotto_app.db` — Action 실행 시 만들어져 Pages에만 배포되는 최신 통합 DB

현재 seed 상태:

```text
lotto          1237
lotto_stores   1236
pension        328
pension_stores 328
```

## 5. 자동화 코드

- `automation/updater.py` — 동행복권 공식 결과/판매점 증분 수집
- `automation/apply_site_updates.py` — seed DB에 기존 Pages JSON을 재적용
- `automation/export_pages.py` — 현재 DB를 manifest + 회차별 JSON으로 변환
- `automation/test_updater.py` — 파서 fixture 테스트
- `automation/test_static_sync.py` — DB → JSON → DB 왕복 무결성 테스트

Action은 대략 아래 순서로 실행합니다.

```text
checkout
  ↓
seed DB 복사
  ↓
기존 public/data JSON 재적용
  ↓
동행복권 신규 회차 수집
  ↓
파서/정적동기화 테스트
  ↓
회차별 JSON export
  ↓
SQLite integrity_check
  ↓
새 JSON을 저장소에 commit/push
  ↓
GitHub Pages 배포
```

## 6. 로컬 검증

프로젝트 루트:

```bash
python verify.py
```

정적 동기화 테스트:

```bash
cd automation
python test_static_sync.py
```

파서 테스트는 의존성 설치 후 실행합니다.

```bash
python -m pip install -r automation/requirements.txt
cd automation
python test_updater.py
```

## 7. 앱 기능

- 로또 6/45 최신/과거 회차 조회
- 번호별 전체/최근 출현 통계
- 최근 N회 빈도 차트
- 미출현 간격
- 조건 기반 통계 추천 5게임
- 추천번호/수동번호 저장
- 저장번호 과거 회차 1~5등 자동 판정
- 로또 당첨 판매점 검색
- 연금복권720+ 조회
- WorkManager 12시간 주기 데이터 확인
- 수동 `지금 동기화`

추천 점수는 과거 데이터에 대한 통계적 균형 지표이며 당첨 확률 상승을 보장하지 않습니다.

## 8. 주의사항

동행복권 사이트가 응답 필드나 HTML 구조를 변경하면 `automation/updater.py`의 파서를 수정해야 할 수 있습니다. 수집기가 데이터를 완전하게 검증하지 못하면 해당 회차를 기존 DB에 반영하지 않고 실패 로그만 남기도록 구성했습니다.

GitHub 예약 Actions는 저장소 상태/정책에 따라 비활성화될 수 있으므로 가끔 Actions 탭에서 최근 실행 여부를 확인하는 것이 좋습니다. `workflow_dispatch`가 있어 언제든 수동 실행할 수 있습니다.

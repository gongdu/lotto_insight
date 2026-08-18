# GitHub 무료 배포 — 5분 체크리스트

1. GitHub에서 Public 저장소 생성
2. 프로젝트 전체 업로드 (`.github` 포함)
3. Settings → Pages → Source → **GitHub Actions**
4. Actions → **Update lottery data and deploy Pages** → Run workflow
5. 성공 후 `https://아이디.github.io/저장소명` 접속
6. Android 앱 홈 → **GitHub Pages 데이터 주소**에 위 URL 저장
7. **지금 동기화** 실행

정상이라면 Pages의 `manifest.json`에 다음과 비슷하게 표시됩니다.

```json
{
  "schema_version": 1,
  "datasets": {
    "lotto": {"latest_round": 1237},
    "lotto_stores": {"latest_round": 1236},
    "pension": {"latest_round": 328},
    "pension_stores": {"latest_round": 328}
  }
}
```

문제가 생기면 GitHub의 Actions 실행 화면에서 실패한 step 이름과 로그를 복사해 확인하면 됩니다.

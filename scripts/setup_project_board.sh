#!/usr/bin/env bash
# GitHub Projects v2 칸반 보드를 만들고 모든 이슈를 올린다.
#
# 선행 조건 — gh 토큰에 project 권한이 필요합니다. 한 번만 실행하면 됩니다.
#     gh auth refresh -s project,read:project
#
# 사용법
#     ./scripts/setup_project_board.sh
set -euo pipefail

OWNER="${OWNER:-kennykimtang}"
REPO="${REPO:-shepherdron}"
TITLE="${TITLE:-Shepherdron 작업 보드}"

if ! gh project list --owner "$OWNER" --limit 1 >/dev/null 2>&1; then
  cat <<'MSG'
gh 토큰에 project 권한이 없습니다. 먼저 아래를 실행하세요 (브라우저 인증 1회):

    gh auth refresh -s project,read:project

끝나면 이 스크립트를 다시 실행하면 됩니다.
MSG
  exit 1
fi

# ── 이미 있으면 재사용 ─────────────────────────────────────────
NUM="$(gh project list --owner "$OWNER" --format json \
        --jq ".projects[] | select(.title == \"$TITLE\") | .number" 2>/dev/null | head -1)"

if [[ -z "$NUM" ]]; then
  echo "▶ 보드 생성: $TITLE"
  NUM="$(gh project create --owner "$OWNER" --title "$TITLE" --format json --jq '.number')"
else
  echo "▶ 기존 보드 재사용 (#$NUM)"
fi

PROJECT_URL="https://github.com/users/$OWNER/projects/$NUM"
echo "  $PROJECT_URL"

# ── 열린 이슈 전부 올리기 ──────────────────────────────────────
echo "▶ 이슈 추가"
ADDED=0
while read -r url; do
  [[ -z "$url" ]] && continue
  if gh project item-add "$NUM" --owner "$OWNER" --url "$url" >/dev/null 2>&1; then
    ADDED=$((ADDED + 1))
    printf '  + %s\n' "$url"
  fi
done < <(gh issue list -R "$OWNER/$REPO" --state open --limit 100 --json url --jq '.[].url')
echo "  총 $ADDED 건 추가"

# ── 전부 Todo 로 세팅 ──────────────────────────────────────────
# 기본 Status 필드는 Todo / In Progress / Done 세 칸을 제공합니다.
FIELD_JSON="$(gh project field-list "$NUM" --owner "$OWNER" --format json 2>/dev/null || echo '{}')"
STATUS_ID="$(jq -r '.fields[]? | select(.name=="Status") | .id' <<<"$FIELD_JSON" | head -1)"
TODO_ID="$(jq -r '.fields[]? | select(.name=="Status") | .options[]? | select(.name=="Todo") | .id' <<<"$FIELD_JSON" | head -1)"

if [[ -n "$STATUS_ID" && -n "$TODO_ID" ]]; then
  echo "▶ Status 를 Todo 로 초기화"
  PROJECT_ID="$(gh project view "$NUM" --owner "$OWNER" --format json --jq '.id')"
  while read -r item_id; do
    [[ -z "$item_id" ]] && continue
    gh project item-edit --id "$item_id" --project-id "$PROJECT_ID" \
      --field-id "$STATUS_ID" --single-select-option-id "$TODO_ID" >/dev/null 2>&1 || true
  done < <(gh project item-list "$NUM" --owner "$OWNER" --limit 100 --format json --jq '.items[].id')
fi

cat <<MSG

완료했습니다.

  보드      $PROJECT_URL
  이슈      https://github.com/$OWNER/$REPO/issues
  마일스톤  https://github.com/$OWNER/$REPO/milestones

다음으로 할 일
  1. 보드에서 Status 칼럼을 팀에 맞게 바꿉니다
     (기본 Todo / In Progress / Done → Backlog / In Progress / Review / Done)
  2. Settings → Manage access 에서 팀원을 Collaborator 로 초대합니다
     또는:  gh repo add-collaborator $OWNER/$REPO <github-id> --permission push
  3. 보드 우상단 ⋯ → Settings → Workflows 에서 자동화를 켭니다
     - Item closed        → Done
     - Pull request merged → Done
MSG

# Codex 인계: PyFlow Workbench

## 현재 상태

- 인계 기준: 2026-09-22, 앱 버전 0.3.0.
- 이 프로젝트는 새 폴더에서 시작한 Python-native Node-RED 스타일 비주얼 파이프라인 도구다.
- 사용자는 실제 테스트와 수정·안정화를 반복하면서 기능을 증분하기를 원한다. 특히 async를 처음부터 고려하라고 요청했다.
- v0.3 구현은 완료했다. 다음 v0.4의 범위는 합의할 수 있도록 제안한 상태이며 아직 구현하지 않았다.
- 이 문서는 대화의 개발 맥락을 인계한다. 채팅 세션 자체를 자동 이관하는 파일은 아니다.

## 구현된 기능

Python 함수 등록과 타입 기반 포트, DAG 검증, 독립 노드 병렬 실행, React Flow 편집기, JSON import/export, 브라우저 draft 저장, NDJSON 실행 이벤트, Inject/Switch/Change/Debug, Merge, Split/Join, 재사용 Subflow, Map Subflow.

17개 노드가 등록된다. Merge는 모든 부모가 종료된 뒤 활성 입력을 left/right 순서로 선택한다. null과 비활성을 구분한다. Split/Map/Join은 유한 배치이며 Node-RED의 장기 실행 메시지 스트림은 아니다.

## 코드 위치

| 파일 | 역할 |
| --- | --- |
| `backend/pyflow/models.py` | 그래프·포트·실행 결과 모델 |
| `backend/pyflow/registry.py` | 함수 등록, 타입 정보와 호환성 |
| `backend/pyflow/executor.py` | DAG 스케줄링, Merge, Subflow/Map, 취소 |
| `backend/pyflow/batch.py` | 인덱스 배치 검증, Split/Join |
| `backend/pyflow/nodes.py` | 내장 노드 |
| `backend/pyflow/api.py` | FastAPI, 검증·실행·NDJSON 스트림 |
| `frontend/src/App.tsx` | 편집기, 실행 상태, Subflow 편집 |
| `frontend/src/graph.ts` | 직렬화, 복원, 예제 그래프 |
| `frontend/src/types.ts` | 프론트 데이터 계약 |
| `scripts/smoke_http.py` | 실제 Uvicorn/Vite HTTP 검증 |

## async 계약과 제한

async 함수는 await하고 동기 함수는 thread에서 실행한다. 한 root run의 모든 중첩 leaf가 동일한 semaphore를 공유하며 기본 동시성은 8이다. Subflow/Map 부모는 자식 대기 중 슬롯을 점유하지 않는다. 동시성 1에서도 중첩 실행이 가능하다.

중첩 async 취소 정리가 구현돼 있다. 실행 중인 동기 thread를 강제 종료할 수는 없다. 배치는 1000개, 전체 중첩 노드 스케줄링은 5000개, Subflow 깊이는 8까지다. 재귀 참조는 거부한다. 현재 Map은 아이템 하나라도 실패하거나 비활성 출력이면 전체 실패한다.

child 이벤트는 `scope` 배열로 구분하고 완료된 자식 결과는 `child_runs`에 남긴다. 부모/자식에 동일한 node ID가 있어도 UI 상태가 충돌하지 않아야 한다.

## 검증 기록과 남은 확인

v0.3 당시 backend 61개, frontend 20개 테스트, TypeScript/Vite build, 실제 HTTP smoke를 통과했다. 기록은 `TESTING.md`에 있다. 새 환경에서는 의존성을 설치한 뒤 다시 실행해야 한다.

실제 브라우저 드래그·시각 QA는 이전 환경의 localhost 차단 때문에 미검증이다. 컴포넌트 테스트는 canvas를 mock한다. 대상 PC에서 포트 연결, 해제, 화면 크기 변경, 파일 import/export, Save 후 reload를 확인해야 한다.

## 다음 작업

`V0.4_SCOPE.md`를 기준으로 Timeout → Retry → Catch → UI/관찰성 순서로 구현한다. 실행 정책/오류 상태 계약을 먼저 정리하고 회귀 테스트를 추가한다. 세부 미결정 사항은 그 문서에 명시했다. 기존 코드를 유지하면서 확장하며 영속화·스케줄러·외부 서비스 노드까지 이번 범위를 넓히지 않는다.

## 로컬에서 이어받기

공개 저장소: https://github.com/ithing-goon/pyflow-workbench

저장소를 clone한 후 `pyflow-workbench` 폴더를 로컬 프로젝트로 열고 `README.md`의 Windows 또는 Linux/macOS 설치 명령을 실행한다. 의존성/가상환경/빌드 결과는 저장소에 포함하지 않았다.

```bash
git clone https://github.com/ithing-goon/pyflow-workbench.git
cd pyflow-workbench
```

웹 Codex에서는 이 저장소에 대한 접근을 연결하고 해당 저장소의 환경을 선택한다. 다음 프롬프트로 대화의 개발 맥락을 이어받을 수 있다. 채팅 이력이 자동으로 복원되는 것은 아니다. 사용자 Git 작성자 정보는 설정하지 않았으므로 이후 로컬 커밋에는 자신의 설정을 사용한다.

## 새 Codex 대화에 붙여넣을 프롬프트

```text
이 저장소는 PyFlow Workbench v0.3이다. AGENTS.md, docs/CODEX_HANDOFF.md,
docs/ARCHITECTURE.md, docs/V0.4_SCOPE.md, docs/TESTING.md를 읽고 이어서 작업해줘.
새 프로젝트를 만들지 말고 기존 구현을 유지하면서 v0.4를 구현해줘.
범위는 async Timeout, 일반 실행 노드의 opt-in Retry, 최종 실패의 Catch 분기,
시도별 추적과 편집기 설정이다. 실행 계약을 먼저 정리하고 구현·테스트·수정을 반복해줘.
공유 동시성 제한, 취소 정리, 재시도 비중첩, null/비활성 구분을 보존해줘.
기존 81개 테스트와 새 회귀 테스트, build, 실제 HTTP smoke를 검증하고
브라우저에서 확인하지 못한 항목은 분명하게 알려줘. 결과는 한국어로 설명해줘.
```

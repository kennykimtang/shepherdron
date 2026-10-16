Shepherdron 작업 보드

갱신 : 2026-10-16

이 파일은 큰 그림입니다. 실제 작업 추적은 GitHub에서 합니다.

| 용도 | 위치 |
|---|---|
| 작업 추적 | [Issues](https://github.com/kennykimtang/shepherdron/issues) |
| 단계별 마감 | [Milestones](https://github.com/kennykimtang/shepherdron/milestones) |
| CI 상태 | [Actions](https://github.com/kennykimtang/shepherdron/actions) |

---

확정된 전제

| 항목 | 내용 | 영향 |
|---|---|---|
| **시연 장소** | 실내 계단식 강당, 천장 4.22~4.43 m | GPS 불가 → 옵티컬 플로우 필요. 고도 상한 3.4 m |
| **동력계** | 4S 14.8 V + AirGear 355 (AIR2213 920KV + T9545) | T/W 2.32, 체공 12.1분 |
| **비행제어기** | KoA H743 | 핀맵 제조사 매뉴얼 확인 필요 |
| **연산 위치** | 노트북이 YOLO, 기체가 판단·구동 | 링크는 관측만 전달 |
| **카메라 각도** | 45도 하향 | 수직은 사람이 6.5 px라 검출 불가 |

상세 : [INDOOR.md](INDOOR.md), [HARDWARE_SPEC.md](HARDWARE_SPEC.md) 0절, [ARCHITECTURE.md](ARCHITECTURE.md)

---

현재 상태

| 파트 | 상태 | 다음 할 일 |
|---|---|---|
| 비전 | 코어 완료 | 현장 임계치 튜닝 [#1](https://github.com/kennykimtang/shepherdron/issues/1), CSI 스트리밍 [#2](https://github.com/kennykimtang/shepherdron/issues/2) |
| 항법 | 코어 완료 (실내 포함) | 옵티컬 플로우 [#23](https://github.com/kennykimtang/shepherdron/issues/23), SITL [#4](https://github.com/kennykimtang/shepherdron/issues/4), 실기 통신 [#5](https://github.com/kennykimtang/shepherdron/issues/5) |
| 하드웨어 | 동력계 확보, 조립 전 | 전원 배선 [#7](https://github.com/kennykimtang/shepherdron/issues/7), **기구 방식 결정 [#9](https://github.com/kennykimtang/shepherdron/issues/9)** |
| 문서 | 설계 문서 완료 | 발표 자료 [#14](https://github.com/kennykimtang/shepherdron/issues/14) |

테스트 298건이 하드웨어 없이 돌아갑니다. `pytest tests/`

---

완료

비전 (Phase 1)
- YOLOv8n + ByteTrack 검출·추적, 프레임 간 동일 인물 ID 유지
- 지상 평면 호모그래피 기반 persons/m2 판정
- 경보 히스테리시스 : 단발 오검출이 비행 명령이 되지 않도록
- 카메라 45도 기울임, 검출 범위 밖 구역은 UNKNOWN 처리

항법 (Phase 2)
- 기체 기준 오프셋 ↔ 위경도 변환, 반경·고도 제한
- 임무 상태기계 IDLE → NAVIGATING → HOVERING → RETRACTING → RETURNING
- 조종사 수동 전환 시 STANDBY : 조종권을 되찾아가지 않음
- **실내 프로파일** : GPS 없이 기수 기준 상대 이동으로 비행
- 설정 정합성 점검, 세션 로그 (JSONL)

통합 (Phase 4)
- 지상/기체 역할 분리, 링크는 관측만 전달
- 링크 끊겨도 기체 단독으로 안전 복귀 (실측 40초 유지 후 타임아웃 RTL)
- 페이로드 추상화 : 기구 방식과 무관하게 전개/수축 제어

문서
- 부품 검증 9건 교정, 질량·추력·전력 예산
- 결선 명세, 현장 운용 절차, 실내 제약, 구매 목록

---

진행 중 / 대기

| # | 작업 | 파트 | 우선순위 |
|---|---|---|---|
| [#23](https://github.com/kennykimtang/shepherdron/issues/23) | **옵티컬 플로우 + 거리계** (실내 필수) | 하드웨어·항법 | 높음 |
| [#9](https://github.com/kennykimtang/shepherdron/issues/9) | **기구 방식 결정 + 실내용 길이** | 하드웨어 | 높음 |
| [#1](https://github.com/kennykimtang/shepherdron/issues/1) | 현장 임계치 튜닝 (앉은 사람 대응 포함) | 비전 | 높음 |
| [#2](https://github.com/kennykimtang/shepherdron/issues/2) | CSI 카메라 MJPEG 스트리밍 | 비전 | 높음 |
| [#4](https://github.com/kennykimtang/shepherdron/issues/4) | SITL 완주 확인 | 항법 | 높음 |
| [#5](https://github.com/kennykimtang/shepherdron/issues/5) | KoA H743 시리얼 통신 | 항법 | 높음 |
| [#7](https://github.com/kennykimtang/shepherdron/issues/7) | 4S 전원 분배 구축 | 하드웨어 | 높음 |
| [#12](https://github.com/kennykimtang/shepherdron/issues/12) | 배터리 추가 구매 | 하드웨어 | 높음 |
| [#8](https://github.com/kennykimtang/shepherdron/issues/8) | 페이로드 구동부 제어 | 하드웨어 | 보통 |
| [#10](https://github.com/kennykimtang/shepherdron/issues/10) | WS2812B LED 패턴 | 하드웨어 | 보통 |
| [#11](https://github.com/kennykimtang/shepherdron/issues/11) | MAX98357A 음성 안내 | 하드웨어 | 보통 |
| [#3](https://github.com/kennykimtang/shepherdron/issues/3) | Pi NCNN FPS 실측 (폴백용) | 비전 | 낮음 |
| [#13](https://github.com/kennykimtang/shepherdron/issues/13) | 페이로드 연동, systemd | 인프라 | 보통 |
| [#14](https://github.com/kennykimtang/shepherdron/issues/14) | 발표 자료, 시연 영상 | 문서 | 보통 |

---

팀 결정이 필요한 사항

| # | 내용 | 막고 있는 것 |
|---|---|---|
| 1 | **기구 방식** : 텔레스코픽 마스트 vs Kresling, 윈치 구동 방식 | Phase 3 전체 |
| 2 | **구조물 길이** : 실내 천장 4.22 m라 600 mm는 사람 머리에 닿음. 300 mm 권장 | 기구 설계 |
| 3 | **전개 방향** : 아래면 중력이 펴주고, 옆·위면 스프링 필요 | 기구 설계 |
| 4 | **시연 단계** : 비전만 / 수동비행+자동전개 / 자율이동 중 어디까지 | 시연 준비 |

4번은 [INDOOR.md](INDOOR.md) 5절 참조. 사람이 있는 실내에서 1.5 kg 기체를
자율비행시키는 것은 위험하므로 단계를 나눌 것을 권합니다.

---

작업 규칙

1. 시작 전 : Issue를 자신에게 할당하고 `feat/<파트>-<작업>` 브랜치를 만듭니다.
2. PR : 본문에 `Resolves #<번호>`를 적으면 머지 시 Issue가 자동으로 닫힙니다.
3. 테스트 : 푸시 전 `pytest tests/` 통과 확인. CI가 모든 PR에서 다시 돌립니다.
4. main 직접 푸시 금지 : 반드시 PR로 올립니다.

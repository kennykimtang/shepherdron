부품 명세 (BOM)

갱신 : 2026-10-29  ·  모든 항목에 구매 링크 포함

---

구매 완료 (엑스캅터, 2026-10-14, 거래명세표 합계 312,800원)

| 품목 | 사양 | 질량 | 가격 | 링크 |
|---|---|---:|---:|---|
| T-MOTOR AirGear 355 | AIR2213 KV1000 ×4 + AIR 20A ESC ×4 + MF9545 접이식 ×4 | 295 g | 167,000 | [xcopter 34863](https://xcopter.com/product/detail.html?product_no=34863) |
| Xcopter F450 프레임 | PDB 일체형 하판 | 282 g | 32,000 | [xcopter 30221](https://xcopter.com/product/detail.html?product_no=30221) |
| Tarot F450/F550 랜딩 스키드 | White | 60 g | 4,800 | [xcopter 22992](https://xcopter.com/product/detail.html?product_no=22992) |
| RadioMaster Pocket | 모드2 · **CC2500** (멀티프로토콜) · 실물 확인됨 | 288 g | 109,000 | xcopter (아래 참조) |
| Raspberry Pi 4 | | 46 g | | (별도 확보) |

조종기 : CC2500 확정

실물이 **CC2500 (멀티프로토콜) 버전**임을 확인했습니다.
→ **발주 예정인 R86C V2 수신기와 호환됩니다** (FrSky D8/D16 지원).

> 링크 주의 : 공유해 주신 `product_no=37115` 는 **ELRS 버전(129,000원)** 페이지입니다.
> 실제 구매는 CC2500(109,000원)이며, 거래명세표 합계와도 맞습니다.
> 발주·정산 서류에 링크를 쓸 때는 CC2500 상품 페이지를 따로 확인하세요.
>
> ```
> AirGear 167,000 + F450 32,000 + 스키드 4,800 + CC2500 109,000 = 312,800  (명세표 합계 일치)
> ```

바인딩이 안 될 때 : 판매처 안내에 **"한국형 펌웨어가 업데이트되어 있어 조종기와
수신기가 한국형이어야 한다"** 는 문구가 있습니다. 이 점을 먼저 확인하세요.

---

발주 예정 (팰콘샵)

| 품목 | 사양 | 링크 |
|---|---|---|
| KoA FC H743 | KC 인증 · **예약판매** | [falconshop QA92258](https://www.falconshop.co.kr/shop/goods/goods_view.php?&goodsno=100092258) |
| PT-B2800N-FX50 | 4S1P 14.8 V 2800 mAh 50C · XT60 | [falconshop QA41869](https://www.falconshop.co.kr/shop/goods/goods_view.php?&goodsno=100041869) |
| iMax B6 + 5A 60W PSU | 6셀 밸런스 · KC | [falconshop QQ98187](https://www.falconshop.co.kr/shop/goods/goods_view.php?&goodsno=99998187) |
| RadioMaster R86C V2 | FrSky D8/D16/S-FHSS · PWM 6ch / **SBUS 8ch** | [falconshop](https://www.falconshop.co.kr/shop/goods/goods_view.php?&goodsno=100051589) |
| UBEC 5A 레귤레이터 | 입력 5~30 V / 출력 5 V 5 A · 10.4 g · 43×21×10 mm | [falconshop](https://www.falconshop.co.kr/shop/goods/goods_view.php?&goodsno=100004015) |
| XT60 연장 케이블 | 16 AWG 30 cm | [falconshop](https://www.falconshop.co.kr/shop/goods/goods_view.php?&goodsno=100091412) |
| XT60 전원 케이블 | AMASS XT60H · 12 AWG 10 cm | [falconshop](https://www.falconshop.co.kr/shop/goods/goods_view.php?&goodsno=100072742) |

**KoA FC 는 예약판매**입니다. 입고 예정일이 전체 일정을 좌우하므로 발주 전에
판매처에 확인하세요.

---

아직 구매처 미정 (필수)

| 품목 | 왜 필요한가 |
|---|---|
| **GPS + 나침반 모듈** | KoA FC 에 **나침반이 없습니다.** 실내에서도 EKF 의 yaw 추정에 필요 → 없으면 LOITER/GUIDED 진입 불가. 픽스호크 표준 GH1.25 6핀 |
| **옵티컬 플로우 + 거리계** | 실내는 GPS 가 안 잡힙니다. 없으면 자율비행 시연 자체가 불가능 (예: Matek 3901-L0X) |
| **프로펠러 가드** | 실내에서 사람 근처 비행. 접이식 프로펠러와 간섭하지 않는 제품으로 |
| **microSD 카드** | Raspberry Pi 용 32 GB 이상 A1/A2. (FC 용 8 GB 는 동봉) |
| **Camera Module 3 Wide** | 비전 입력 |
| **USB-TTL 케이블** | **3.3 V 로직**. Pi ↔ FC TELEM2 |
| **WS2812B 30 LED + 74AHCT125** | 방향 유도. Pi 3.3 V 는 LED 문턱 3.5 V 미달이라 시프터 필수 |
| **MAX98357A + 3 W 4 Ω 스피커** | 음성 안내 |
| **4S 2800 mAh 배터리 1개 추가** | 체공 11.5분 vs 충전 1시간. 리허설+시연 당일 부족 |
| **페이로드 구동부** | 기구 방식 결정 후 ([#9](https://github.com/kennykimtang/shepherdron/issues/9)) |

사지 않아도 되는 것

| 품목 | 이유 |
|---|---|
| 파워모듈 | KoA FC 가 VBAT 26 V 직접 입력 + 5 V 2.5 A BEC 내장. 전류 측정이 꼭 필요할 때만 |
| PDB | F450 하판이 PDB 겸용 |
| 텔레메트리 모듈 | Pi 가 Wi-Fi 로 MAVLink 중계 |
| Pi 쿨링 팬 | YOLO 가 지상으로 가서 히트싱크면 충분 |

---

호환성 점검 결과

| 조합 | 결과 |
|---|---|
| 4S ↔ AIR2213 / AIR 20A | OK (둘 다 3~4S 정격) |
| 4S ↔ KoA FC VBAT | OK (최대 26 V) |
| 4S ↔ UBEC | OK (입력 5~30 V) |
| UBEC 5 V 5 A ↔ Pi 4 | OK (Pi 권장 3 A) |
| KoA FC RC 포트 5 V ↔ R86C V2 | OK (SBUS 입력 제한 4.5~6.6 V 충족) |
| R86C V2 SBUS ↔ ArduPilot | OK (SERIAL6 = UART5) |
| **R86C V2 ↔ Pocket** | **OK** — CC2500 확정, FrSky D8/D16 지원 |
| iMax B6 ↔ 4S 2800 mAh | OK (6셀 밸런스, 1C 충전 47 W < 60 W) |
| F450 ↔ MF9545 (9.5인치) | OK (인접 모터 318 mm, 프로펠러 241 mm, 여유 77 mm) |
| AIR 20A ESC ↔ AIR2213 모터 | OK (모터 최대 15 A, ESC 연속 20 A) |

남은 확인 사항

1. **KoA FC 입고 예정일** — 예약판매라 전체 일정을 좌우합니다
2. 4S 만충 16.8 V vs T-MOTOR 표기 상한 16 V (표기 오류로 보이나 판매처 확인 권장)
3. 모터 마운트 홀 ↔ F450 암 (2213 급은 보통 M3 16/19 mm)

전기적 호환은 전부 확인됐습니다. 남은 것은 일정과 기구 치수뿐입니다.

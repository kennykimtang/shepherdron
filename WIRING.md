Shepherdron 결선 명세 (텍스트판, rev.B)

> KoA FC 공식 매뉴얼로 핀맵을 확정했습니다 (2026-10-29).
> 실내 시연 전제는 [INDOOR.md](INDOOR.md), 확정 부품은 [HARDWARE_SPEC.md](HARDWARE_SPEC.md) 0절.

KoA FC 커넥터 핀아웃 (공식)

| 커넥터 | 핀 배열 | 용도 |
|---|---|---|
| **POWER** 6핀 | 5V, 5V, Curr, Vbat, GND, GND | **VBAT 최대 26 V 직접 입력.** XT60 으로 PDB 직결 가능 |
| **PWM** 10핀 | GND, PWM8/BUZZER, PWM7~PWM1, 5V | 8채널, 전 채널 BDShot. 8번은 부저 |
| **RC** 4핀 | GND, RX5/SBUS IN, TX5, **5V** | SBUS 입력 + 수신기 급전 |
| **GPS** 6핀 | GND, SDA, SCL, RX1, TX1, 5V | UART + I2C(나침반) |
| TELEM1 / TELEM2 | 표준 MAVLink 시리얼 | TELEM2 를 라즈베리파이에 연결 |

UART 매핑 (ArduPilot)

| SERIAL | UART | 포트 |
|---|---|---|
| SERIAL 0 | USB | — |
| SERIAL 1 | UART 2 | TELEM1 |
| **SERIAL 2** | UART 4 | **TELEM2** → 라즈베리파이 |
| SERIAL 3 | UART 1 | GPS / 나침반 |
| SERIAL 4 | UART 3 | Digital FPV (여유) |
| SERIAL 5 | UART 7 | ESC 텔레메트리 (여유) |
| **SERIAL 6** | UART 5 | **RC** → R86C V2 SBUS |
| SERIAL 7 | UART 8 | DEBUG |

전원 구조 : **파워모듈 불필요**

KoA FC 는 VBAT 단자로 배터리를 직접 받고(최대 26 V) **5 V 2.5 A BEC 를 내장**해
FC·수신기·GPS/나침반·옵티컬플로우까지 공급합니다. 전류 측정이 꼭 필요할 때만
별도 파워모듈(Holybro PM02 V3 / PM06 / PM07 호환)을 답니다.

**라즈베리파이는 별도 UBEC 에서 급전**합니다. FC 의 5 V BEC 2.5 A 는 이미
수신기·나침반·플로우가 쓰고 있어 Pi 의 3 A 를 감당하지 못합니다.

주의 : **USB 는 BEC 회로와 분리**돼 있어 USB 만 연결하면 외부기기에 전원이
가지 않습니다. 벤치 테스트 때도 배터리를 함께 연결해야 합니다.

---

조립 설명서 도면

| 장 | 내용 |
|---|---|
| [1장 : 부품 식별](manual_1_parts.png) | 부품 12종의 그림·수량·장착 위치. 조립 전 재고 확인용 |
| [2장 : 전원 배선](manual_2_power.png) | 배터리 → 전원 분배 → ESC 4개 → 모터 4개, FC·UBEC·Pi 급전 |
| [3장 : 신호 배선](manual_3_signal.png) | KoA FC 커넥터 핀맵, PWM·RC·GPS·I2C·TELEM2 결선, ArduPilot 파라미터 |
| [4장 : 조립 순서와 점검](manual_4_assembly.png) | 조립 12단계, 비행 전 점검표 16항목, 첫 시동 순서 |

아래 텍스트는 같은 내용을 grep·diff 가능한 형태로 옮긴 것입니다.
> 부품 기호(BT1, U3 …)와 배선 번호(W01 …)는 도면과 1:1로 같습니다.
> 수치 근거는 [HARDWARE_SPEC.md](HARDWARE_SPEC.md) 참조.

---

1. 부품 목록 (Reference Designator)

| 기호 | 부품 | 핵심 사양 |
|---|---|---|
| `BT1` | PT-B2800N-FX50 4S LiPo | 14.8 V · 2800 mAh · 50C · XT60 · 약 300 g |
| `PDB1` | F450 하판 PDB | 14.8 V 분배 버스 · **★ 스타 그라운드 집결점** |
| `FC1` | KoA FC H743 | ArduCopter 4.x · Quad X · **VBAT 26 V 직결** · 5 V 2.5 A BEC 내장 · 나침반 없음 |
| `GPS1` | GPS + 나침반 모듈 | **FC 에 나침반이 없어 필수.** 실내에서는 나침반만 사용. 미구매 |
| `FLOW1` | 옵티컬 플로우 + 하향 거리계 | 실내 위치 유지. 인터페이스는 모델에 따라 다름(§4-3). 미구매 |
| `TM1` | 2.4 GHz 텔레메트리 | 지상 Mission Planner · 57 600 bps. **미구매** |
| `TX1` | RadioMaster Pocket | **CC2500 / D16** · 모드2 · 지상 장비 |
| `RX1` | RadioMaster R86C V2 수신기 | CC2500 / D16 · S.BUS 8채널 · 비상 수동 조종 |
| `ESC1~4` | AIR 20A BLHeli_S (AirGear 355) | 2–4S · 연속 20 A / 버스트 30 A · 개별 4개 |
| `M1~M4` | AIR2213 **KV1000** BLDC (AirGear 355) | DETAIL A 배치 참조 |
| `LG1` | Tarot F450/F550 랜딩 스키드 | White · 60 g |
| `PC1` | Raspberry Pi 4 Model B 2GB | 컴패니언 · MAVLink 수신 + 페이로드 구동 |
| `CAM1` | Camera Module 3 Wide | IMX708 · 102° H / 120° D · CSI-2 · **45° 하향 마운트** |
| `U1` | UBEC 5 V / 5 A | 스위칭 강압 · 피크 3.15 A |
| `U2` | PAM8403 | 아날로그 class-D 앰프 3 W×2 @ 4 Ω · Pi 3.5 mm 잭 입력 |
| `U3` | DMD-150 | H-브리지 · 6.5–40 V / 15 A · **5 V TTL 입력** |
| `U4` | 74AHCT125 | 쿼드 버퍼 · 3.3 V → 5 V · **필수** |
| `M5` | LMB2036U | 12 V · 120 N · **150 mm** · 2선 극성반전 |
| `LED1` | WS2812B 스트립 30 px | 470 Ω 직렬 · 1000 µF 벌크 · 밝기 50% 상한 |
| `LS1` | 스피커 3 W 4 Ω | 대피 안내 음성 |

---

2. 전원 계통도 (Power Tree)

```
BT1  PT-B2800N-FX50  4S LiPo 14.8 V 2800 mAh
 │
 └─[W01] 12 AWG / XT60
    │
    PDB1  F450 하판 PDB  ★ STAR GROUND
     │     470 µF / 25 V 저ESR 콘덴서 (입력 패드)
     │
     ├─[W02] 6핀 ───────→ FC1 POWER   (Vbat 직결, 최대 26 V)
     │                     └ FC1 내장 5 V 2.5 A BEC
     │                        └→ GPS1 / RX1 / FLOW1   ! PC1 금지
     │
     ├─[W04] ESC 동봉 리드 ×4 ─→ ESC1..ESC4 ─→ M1..M4
     │                             (호버 스로틀 30%)
     │
     ├─[W13] 16 AWG ────→ U1  UBEC 5 V / 5 A
     │                     │
     │                     ├─[W15] 18 AWG → PC1  J8-2 / J8-6
     │                     │                ! 인라인 3 A 퓨즈
     │                     ├─[W16] 18 AWG → U4 Vcc, LED1 Vcc
     │                     │                (LED1에 1000 µF)
     │                     └─[W17] 22 AWG → U2 Vin
     │
     └─[W14] 16 AWG ────→ U3 Vcc (DMD-150)
                           └─[W28]→ M5 액추에이터
                           ! 5 V 레일에서 절대 금지

파워모듈(PM1)은 쓰지 않습니다. KoA FC 가 VBAT 를 직접 받으므로
배터리 → PDB → FC POWER 로 바로 갑니다. 전류 측정이 필요해지면
그때 PDB 와 FC 사이에 외장 파워모듈을 끼웁니다.
```

**5 V 레일 부하 (U1 기준 5.00 A 중 3.25 A, 65%)**

```
PC1 + CAM1  (YOLO 부하)  1.50 A
LED1 30px @ 밝기 50%     0.90 A
U2 피크                  0.80 A
U4 외                    0.05 A
──────────────────────────────
합계 피크                3.25 A
```

---

3. 신호 계통도 (Signal Tree)

```
                     ┌─[W09] GPS  6핀  ─→ GPS1   (UART + I2C, 나침반 포함)
                     ├─[W11] RC   4핀  ─→ RX1    (S.BUS)  ← 비상 수동 조종
                     ├─[W05..08] PWM 10핀 ─→ ESC1..ESC4  (서보 3핀 하네스)
  FC1  KoA H743 ──┼─[W10] TELEM1 6핀 ─→ TM1    (57600)   ※ 미구매
                     ├─[W30] 여유 포트 ─→ FLOW1  (§4-3, 모델 확정 후)
                     └─[W12] TELEM2 6핀 ⇄ PC1 J8-8 / 10 / 6
                              GPIO UART 직결, 3.3 V, 921600 bps
                              ! 5 V 선은 연결하지 말 것 (역급전)

  CAM1 ─[W18] CSI-2 15p FPC 200 mm ─→ PC1

  PC1  J8 헤더
   ├─[W19] J8-19  GPIO10 SPI0 MOSI ─→ U4 A1 ─[W25]→ LED1 DIN   (470 Ω 직렬)
   ├─[W20] J8-33  GPIO13 PWM1      ─→ U4 A2 ─┐
   ├─[W21] J8-31  GPIO6  DIR       ─→ U4 A3 ─┴[W26-27]→ U3 PWM / DIR
   └─[W22] 3.5 mm 잭 ───────────────────────→ U2  (아날로그 라인 입력)
                                               └─[W29]→ LS1 스피커
```

---

4. 커넥터 핀맵

4-1. FC1 : KoA H743

| 포트 | 핀 | 배선 | 연결 대상 | 비고 |
|---|:-:|---|---|---|
| `POWER` | 6핀 | W02 | PDB1 패드 | **Vbat 직결** (최대 26 V). 파워모듈 불필요 |
| `PWM` 1 | 10핀 중 9번 | W05 | ESC1 → **M1 전방우측 CCW / MF9545 (역)** | 서보 3핀 하네스 |
| `PWM` 2 | 10핀 중 8번 | W06 | ESC2 → **M2 후방좌측 CCW / MF9545 (역)** | 〃 |
| `PWM` 3 | 10핀 중 7번 | W07 | ESC3 → **M3 전방좌측 CW / MF9545** | 〃 |
| `PWM` 4 | 10핀 중 6번 | W08 | ESC4 → **M4 후방우측 CW / MF9545** | 〃 |
| `GPS` | 6핀 | W09 | GPS1 (UART + I2C 나침반) | SERIAL3 = UART1 |
| `RC` | 4핀 | W11 | RX1 S.BUS | SERIAL6 = UART5. RC 포트 5 V 로 수신기 급전 |
| `TELEM1` | 6핀 | W10 | TM1 | SERIAL1 = UART2 · 57 600 bps. **미구매** |
| `TELEM2` | 6핀 | W12 | PC1 GPIO UART | SERIAL2 = UART4 · 3.3 V 직결 · 921 600 bps |
| `I2C` | 4핀 | — | (예비) | 외장 나침반·I2C 센서용 |

**ArduPilot 파라미터**

```
FRAME_CLASS       1      multicopter
FRAME_TYPE        1      quad X
SERIAL2_PROTOCOL  2      MAVLink2   (TELEM2 = UART4)
SERIAL2_BAUD      921    불안정 시 115
SERIAL6_PROTOCOL  23     RC Input   (RC 포트 = UART5)
BRD_SAFETYENABLE  1
BATT_MONITOR      4      전압 + 전류
MOT_BAT_VOLT_MAX  16.8   4S 만충 (4 x 4.2 V)
MOT_BAT_VOLT_MIN  13.2   4S 방전 (4 x 3.3 V)
```

위 SERIAL 번호는 KoA 공식 보드 정의(`hwdef.dat`)로 확인했습니다.
`SERIAL_ORDER = OTG1 USART2 UART4 USART1 USART3 UART7 UART5 UART8` 이므로
**SERIAL1=TELEM1 · SERIAL2=TELEM2 · SERIAL3=GPS1 · SERIAL6=RC** 가 맞습니다.

4-1-1. 펌웨어 : ArduCopter (PX4 아님)

이 저장소의 비행 코드는 전부 **ArduPilot** 기준입니다(GUIDED·RTL·위 파라미터 이름).
PX4 를 올리면 `flight/` 전체가 맞지 않습니다.

| 항목 | 값 |
|---|---|
| 공식 포크 | [github.com/koadrone/ardupilot](https://github.com/koadrone/ardupilot) (ArduPilot 본가의 포크) |
| 받을 파일 | 릴리스 `koafc-4.7.1` 의 **`arducopter.apj`** (CAN 안 쓰면 `-can` 아닌 쪽) |
| 확인한 내용 | ArduCopter **V4.7.1** · board_id **1013** · 보드명 `KoaFC` · 이미지 1 412 348 B (선언값 일치) |
| 보드 | STM32H743 · IMU BMI088 ×2 · 기압계 SPL06 |

설치는 QGroundControl 에서 **Firmware → Advanced settings → Custom firmware file** 로
이 `.apj` 를 고르면 됩니다(영상의 PX4 설치 절차와 같은 자리). 맥에서는 Mission Planner 가
사실상 안 돌아가므로 QGC 를 그대로 쓰면 됩니다.

> **나침반은 보드에 없습니다.** hwdef 에 `COMPASS` 줄이 없고 IMU·기압계만 있습니다.
> 판매처 영상의 "지자기 센서 내장" 설명은 이 보드에 해당하지 않습니다.
> 다만 `ALLOW_ARM_NO_COMPASS` 가 켜져 있어 **나침반 없이도 시동이 걸립니다.**
> Stabilize·AltHold 로 하는 1·2단계 시연에는 외장 나침반이 필요 없고,
> LOITER/GUIDED 를 쓰는 3단계에만 필요합니다.

4-2. PC1 : Raspberry Pi 4 · J8 40핀 헤더

```
 물리핀  BCM      기능              배선     연결 대상
 ──────────────────────────────────────────────────────────────
   2     —        5V IN             W15      U1 UBEC 출력
   6     —        GND               —        스타 그라운드
   8     GPIO14   UART TXD          W12      FC1 TELEM2 RX
  10     GPIO15   UART RXD          W12      FC1 TELEM2 TX
  19     GPIO10   SPI0 MOSI         W19      U4 A1 → LED1 DIN
  31     GPIO6    DIR               W21      U4 A3 → U3 DIR
  33     GPIO13   PWM1              W20      U4 A2 → U3 PWM
  39     —        GND               —        스타 그라운드
 ──────────────────────────────────────────────────────────────
 CSI 포트          camera            W18      CAM1
 3.5 mm 잭         아날로그 오디오     W22      U2 라인 입력
```

> **핀 선정 이유**
> - 앰프를 I2S(MAX98357A)에서 아날로그(PAM8403)로 바꾸면서 **`GPIO18`·`GPIO19`·
> `GPIO21`이 풀렸다.** rev.A 에 있던 "GPIO18은 I2S 고정이라 PWM 불가, GPIO12도
> PWM0 공유라 불가" 제약은 더 이상 없다. 핀이 모자라면 여기서 가져다 쓴다.
> - 액추에이터 → **GPIO13 (PWM1)** + **GPIO6 (DIR)**. LMB2036U는 2선 극성반전식이라
> PWM 1핀만으로는 수축이 불가능하므로 DIR이 반드시 필요하다.
> - LED → **GPIO10 (SPI0 MOSI)**. SPI 구동이라 root 권한도 필요 없다.
> - MAVLink → **GPIO14/15**. 기본 `/dev/serial0`은 mini-UART 라 921 600 bps 에서
> 바이트를 흘린다. `/boot/firmware/config.txt` 에 **`dtoverlay=disable-bt`** 를 넣어
> PL011(`ttyAMA0`)로 넘기고, raspi-config 에서 시리얼 로그인 셸을 끈다.

4-3. FLOW1 : 옵티컬 플로우 + 거리계 — **포트 미확정**

모델에 따라 인터페이스가 다릅니다. 구매 확정 전에는 포트를 못 박지 않습니다.

| 계열 | 인터페이스 | 연결 포트 | ArduPilot 설정 |
|---|---|---|---|
| Matek 3901-L0X 등 | **UART (MSP)** | 여유 UART (`SERIAL4` = Digital FPV 커넥터) | `SERIAL4_PROTOCOL 32` · `OPTFLOW_TYPE 5` · `RNGFND1_TYPE 32` |
| PX4FLOW 등 | **I2C** | `GPS` 6핀의 SDA/SCL 또는 `I2C` 4핀 | `OPTFLOW_TYPE 1` |

> PURCHASE.md B1 의 예시는 Matek 3901-L0X 이고 이 계열은 **UART** 입니다.
> I2C 로 가정하고 배선하면 인식되지 않습니다. 모델 확정 후 이 절을 못 박으세요.
> 공통 설정은 [INDOOR.md](INDOOR.md) 의 `EK3_SRC1_*` 를 따릅니다.

---

5. 배선 명세표 (Wire Schedule)

| ID | FROM | TO | NET | 전선 규격 | 비고 |
|---|---|---|---|---|---|
| W01 | BT1 XT60 | PDB1 입력 패드 | 14.8 V | 12 AWG 실리콘 | 메인 배터리 리드. 패드에 470 µF |
| W02 | PDB1 패드 | FC1 `POWER` 6핀 | 14.8 V (Vbat) | 동봉 6핀 | **파워모듈 없이 직결.** 역결선 시 FC 손상 |
| W03 | — | — | — | — | *삭제. 파워모듈 제거로 W01 에 통합* |
| W04 | PDB1 패드 | ESC1–4 입력 | 14.8 V | ESC 동봉 리드 (연장 시 16 AWG) | 호버 스로틀 30% |
| W05–08 | FC1 `PWM` 1–4 | ESC1–4 신호 | PWM | 10핀 → 서보 3핀 하네스 | 모터 순번은 §6 |
| W09 | GPS1 | FC1 `GPS` 6핀 | UART + I2C | 동봉 6핀 | 나침반 포함 |
| W10 | TM1 | FC1 `TELEM1` 6핀 | UART | 6핀 | 57 600 bps. **미구매** |
| W11 | RX1 | FC1 `RC` 4핀 | S.BUS | 동봉 4핀 | 수동 개입 경로. RC 포트 5 V 로 수신기 급전 |
| W12 | FC1 TELEM2 | PC1 J8-8 / 10 / 6 | MAVLink2 | JST-GH 6핀 → 듀폰 3선 | TX↔RX 교차. **5 V 선 제거** |
| W13 | PDB1 패드 | U1 입력 | 14.8 V | 16 AWG | |
| W14 | PDB1 패드 | U3 Vcc | 14.8 V | 16 AWG | 액추에이터 구동 전원 |
| W15 | U1 출력 | PC1 J8-2 / J8-6 | 5.0 V | 18 AWG | **인라인 3 A 퓨즈** |
| W16 | U1 출력 | U4 Vcc, LED1 Vcc | 5.0 V | 18 AWG | LED1에 1000 µF |
| W17 | 5 V 레일 | U2 Vin | 5.0 V | 22 AWG | |
| W18 | CAM1 | PC1 CSI-2 | MIPI | 15p FPC 200 mm | ESC 전력선과 이격. **45° 하향 고정** |
| W19 | PC1 J8-19 | U4 A1 | SPI0 MOSI | 22 AWG | 3.3 V in → 5 V out |
| W20 | PC1 J8-33 | U4 A2 | PWM1 | 22 AWG | 액추에이터 속도 |
| W21 | PC1 J8-31 | U4 A3 | DIR | 22 AWG | 전개 / 수축 |
| W22 | PC1 3.5 mm 잭 | U2 라인 입력 | 아날로그 | 3.5 mm 플러그 → 선 | 짧게. U2 옆에 100 µF + 0.1 µF |
| W25 | U4 Y1 | LED1 DIN | 5 V data | 22 AWG | 470 Ω 직렬 |
| W26–27 | U4 Y2, Y3 | U3 PWM, DIR | 5 V TTL | 22 AWG ×2 | |
| W28 | U3 출력 | M5 | 스위칭 14.8 V | 18 AWG 트위스트 | 극성 반전 |
| W29 | U2 출력 | LS1 | 오디오 | 스피커 페어 | |
| W30 | FLOW1 | FC1 여유 UART 또는 I2C | §4-3 | 모듈 동봉 | **포트 미확정.** 모델 확정 후 결정 |

---

6. DETAIL A : 모터 배치 (위에서 본 평면)

```
                          ▲ FWD (기수 방향)
                          │

        M3  CW                              M1  CCW
       MF9545  프로펠러                      MF9545 (역) 프로펠러
          ╲                                  ╱
           ╲                                ╱
            ╲                              ╱
             ╲────────  FC1  ────────────╱
             ╱                            ╲
            ╱                              ╲
           ╱                                ╲
          ╱                                  ╲
        M2  CCW                             M4  CW
       MF9545 (역) 프로펠러                       MF9545  프로펠러
```

| 모터 | 위치 | ESC | FC `PWM` 채널 | 회전 | 프로펠러 |
|:-:|---|:-:|:-:|:-:|:-:|
| M1 | 전방 우측 | ESC1 | PWM 1 | CCW | **MF9545 (역)** |
| M2 | 후방 좌측 | ESC2 | PWM 2 | CCW | **MF9545 (역)** |
| M3 | 전방 좌측 | ESC3 | PWM 3 | CW | **MF9545** |
| M4 | 후방 우측 | ESC4 | PWM 4 | CW | **MF9545** |

> 주의 `MF9545 (역)`은 역방향(푸셔) 블레이드입니다. 엉뚱한 모터에 끼우면 **이륙 즉시 전복**합니다.
> 프로펠러를 끼우기 전에 반드시 모터 회전 방향부터 확인하세요.

---

7. 조립 순서

1. **프레임·동력계 가조립** : F450 암 체결, 모터 4개 장착(프로펠러는 아직 끼우지 않음), ESC 4개 배치.
2. **전원 배선 (W01 / W04)** : BT1 → PDB1 → ESC. PDB 입력 패드에 470 µF 납땜. 파워모듈은 거치지 않습니다.
3. **접지 집결** : 모든 GND를 PDB1 한 점에 모음. 이 단계를 건너뛰면 이후 PWM 노이즈로 고생합니다.
4. **FC 계통 (W02 / W05–08 / W09–11)** : KoA FC `POWER` 직결, `PWM` 모터 신호, `GPS`, `TELEM1`, `RC`.
5. **1차 통전 시험** : 프로펠러 **없이** 전원 인가. Mission Planner로 모터 회전 방향 확인.
6. **프로펠러 장착** : §6 표대로 MF9545 / MF9545 (역) 구분해 체결.
7. **컴패니언 계통 (W13 / W15 / W18 / W12)** : UBEC → Pi J8-2/6(3 A 퓨즈), 카메라, TELEM2 → Pi J8-8/10/6.
8. **페이로드 계통 (W14 / W16 / W17 / W19–29)** : 레벨 시프터 → DMD-150 / LED / 앰프.
9. **액추에이터 시험** : **기체를 고정한 상태에서** 전개. 120 N 반력이 기체를 밀어냅니다.
10. **전체 통합 시험** : 비전 → 판단 → MAVLink → 전개 전 시퀀스를 지상에서 1회 완주.

---

8. 통전 전 필독 사항

1. 모든 GND를 **PDB1 스타 그라운드**에 접속. 접지가 갈라지면 스위칭 노이즈가 PWM 라인에 실립니다.
2. `FC1` 내장 BEC 의 5 V는 **2.5 A** 한계입니다. GPS1·RX1·FLOW1 전용이며 **PC1에는 절대 연결 금지**.
 PC1 은 `U1` UBEC 에서만 급전합니다.
3. `PC1`은 J8-2/6 급전이라 보드 폴리퓨즈를 **우회**합니다. **인라인 3 A 퓨즈**를 다세요.
4. 3.3 V GPIO는 WS2812B의 VIH(0.7 × VDD = **3.5 V**)와 DMD-150의 **5 V TTL** 문턱에 모두 미달합니다.
 → `U4` 74AHCT125는 W25·W26·W27에 **필수**입니다 (선택 아님).
5. `W12` 는 **TX↔RX 교차**입니다. FC TELEM2 의 TX 가 Pi 의 RXD(J8-10)로 갑니다.
 그리고 케이블의 **5 V 선을 반드시 뽑으세요.** Pi 는 `U1` 에서 급전되므로 전원이 충돌합니다.
6. 첫 시동은 **프로펠러 제거 상태**로. DETAIL A와 회전 방향 대조 후 블레이드 체결.
7. `M5` 스트로크 시험은 **기체 고정 후**. 120 N 반력이 고정되지 않은 기체를 움직입니다.
8. `LED1` 밝기는 코드에서 상한을 거세요. 30 px 전체 백색은 1.8 A를 끌어 PC1이 리부팅됩니다.

---

9. 설계 예산 요약

| 항목 | 값 | 판정 |
|---|---|---|
| 총 이륙 중량 (AUW) | **1,463 g** | : |
| 정지 추력 (MF9545 ×4 @ 16 V) | **4,932 g** (1,233 g × 4) | : |
| 추력 / 중량 | **3.37 : 1** | OK 권장 2.0 : 1 초과 |
| 호버 스로틀 | **30 %** | OK |
| 체공 : 2800 mAh (DoD 80%) | **11.5 분** | OK |
| ESC 전류 마진 | 모터 최대 15 A 대 ESC 연속 20 A | OK 33 % 여유 |
| 5 V 레일 부하 (U1 기준) | 3.15 A / 5.00 A (63 %) | OK |

> T/W 3.37 은 권장치를 크게 웃돕니다. 추력은 충분하지만 **조작이 민감**해지므로
> 실내 저속 비행에서는 `MOT_THST_EXPO` 와 스로틀 커브 조정이 필요할 수 있습니다.

> 페이로드 구조물 질량은 위 AUW 1,463 g 에 아직 포함돼 있지 않습니다. 산출 과정은 [HARDWARE_SPEC.md](HARDWARE_SPEC.md) §0 참조.

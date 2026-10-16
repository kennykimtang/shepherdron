Shepherdron 결선 명세 (텍스트판, rev.B)

> 주의 : 부품 표기는 2026-10-14 실구매분(4S + AirGear 355 + KoA H743)으로 갱신했습니다.
> 다만 **결선 구조와 핀 번호는 Pixhawk 2.4.8 기준으로 작성된 것**이라, KoA H743 의
> TELEM 포트 번호와 커넥터 규격은 **제조사 매뉴얼로 반드시 확인**해야 합니다.
> 실내 시연 전제는 [INDOOR.md](INDOOR.md), 확정 부품은 [HARDWARE_SPEC.md](HARDWARE_SPEC.md) 0절.

> [shepherdron_wiring_diagram.png](shepherdron_wiring_diagram.png)와 **동일한 내용**을 텍스트로 옮긴 것입니다.
> 부품 기호(BT1, U3 …)와 배선 번호(W01 …)는 도면과 1:1로 같습니다.
> 수치 근거는 [HARDWARE_SPEC.md](HARDWARE_SPEC.md) 참조.

---

1. 부품 목록 (Reference Designator)

| 기호 | 부품 | 핵심 사양 |
|---|---|---|
| `BT1` | 4S LiPo 배터리 | 14.8 V · 2800 mAh · 50C · XT60 · 약 300 g |
| `PM1` | 파워모듈 (3DR 타입) | 14.8 V 패스스루 + 5.3 V / **2.25 A** 레귤레이터 |
| `PDB1` | F450 PDB | 14.8 V 분배 버스 · **★ 스타 그라운드 집결점** |
| `FC1` | KoA H743 | ArduCopter 4.x · Quad X · 핀맵은 제조사 매뉴얼 확인 |
| `GPS1` | u-blox M8N | GPS + 나침반 |
| `TM1` | 2.4 GHz 텔레메트리 | 지상 Mission Planner · 57 600 bps |
| `RX1` | Microzone MC6C 수신기 | S.BUS · 비상 수동 조종 |
| `ESC1~4` | 35 A BLHeli_S | 2–4S · opto PWM 입력 |
| `M1~M4` | AIR2213 920KV BLDC (AirGear 355) | DETAIL A 배치 참조 |
| `PC1` | Raspberry Pi 4 Model B 2GB | 컴패니언 · YOLOv8n + MAVLink |
| `CAM1` | Camera Module 3 Wide | IMX708 · 102° H / 120° D · CSI-2 · **45° 하향 마운트** |
| `U1` | UBEC 5 V / 5 A | 스위칭 강압 · 피크 3.15 A |
| `U2` | MAX98357A | I2S class-D 앰프 · 3.3 V 로직 수용 |
| `U3` | DMD-150 | H-브리지 · 6.5–40 V / 15 A · **5 V TTL 입력** |
| `U4` | 74AHCT125 | 쿼드 버퍼 · 3.3 V → 5 V · **필수** |
| `M5` | LMB2036U | 12 V · 120 N · **150 mm** · 2선 극성반전 |
| `LED1` | WS2812B 스트립 30 px | 470 Ω 직렬 · 1000 µF 벌크 · 밝기 50% 상한 |
| `LS1` | 스피커 3 W 4 Ω | 대피 안내 음성 |

---

2. 전원 계통도 (Power Tree)

```
BT1  4S LiPo 14.8 V 2800 mAh
 │
 └─[W01] 12 AWG / XT60
    │
    PM1  Power Module
     ├─[W02] 6p molex ──→ FC1 POWER (5.3 V)
     │                     └ FC1 + GPS1 + TM1 + RX1 전용  ⚠ PC1 금지
     │
     └─[W03] 12 AWG ────→ PDB1  F450 PDB  ★ STAR GROUND
                           │     470 µF / 25 V 저ESR 콘덴서 (입력 패드)
                           │
                           ├─[W04] 14 AWG x4 ─→ ESC1..ESC4 ─→ M1..M4
                           │                     (호버 합계 19.8 A)
                           │
                           ├─[W13] 16 AWG ────→ U1  UBEC 5 V / 5 A
                           │                     │
                           │                     ├─[W15] 18 AWG → PC1  J8-2 / J8-6
                           │                     │                ⚠ 인라인 3 A 퓨즈
                           │                     ├─[W16] 18 AWG → U4 Vcc, LED1 Vcc
                           │                     │                (LED1에 1000 µF)
                           │                     └─[W17] 22 AWG → U2 Vin
                           │
                           └─[W14] 16 AWG ────→ U3 Vcc (DMD-150)
                                                 └─[W28]→ M5 액추에이터
                                                 ⚠ 5 V 레일에서 절대 금지
```

**5 V 레일 부하 (U1 기준 5.00 A 중 3.15 A, 63%)**

```
PC1 + CAM1  (YOLO 부하)  1.50 A
LED1 30px @ 밝기 50%     0.90 A
U2 피크                  0.70 A
U4 외                    0.05 A
──────────────────────────────
합계 피크                3.15 A
```

---

3. 신호 계통도 (Signal Tree)

```
                        ┌─[W09] GPS1  (UART + I2C, 6p + 4p)
                        ├─[W10] TM1   (UART, 6p, 57600)
  FC1  KoA H743 ───┼─[W11] RX1   (S.BUS, 3p)  ← 비상 수동 조종
                        ├─[W05..W08] MAIN OUT 1-4 ─→ ESC1..ESC4 (3p 서보선)
                        └─[W12] TELEM2 ⇄ PC1 USB-A
                                 USB-TTL, 3.3 V FTDI, 921600 bps
                                 ⚠ 5 V 선은 연결하지 말 것 (역급전)

  CAM1 ─[W18] CSI-2 15p FPC 200 mm ─→ PC1

  PC1  J8 헤더
   ├─[W19] J8-19  GPIO10 SPI0 MOSI ─→ U4 A1 ─[W25]→ LED1 DIN   (470 Ω 직렬)
   ├─[W20] J8-33  GPIO13 PWM1      ─→ U4 A2 ─┐
   ├─[W21] J8-31  GPIO6  DIR       ─→ U4 A3 ─┴[W26-27]→ U3 PWM / DIR
   └─[W22-24] J8-12 / 35 / 40  I2S ─────────→ U2  (3.3 V 직결, 시프터 불필요)
               GPIO18 BCLK / GPIO19 LRCLK / GPIO21 DIN
                                               └─[W29]→ LS1 스피커
```

---

4. 커넥터 핀맵

4-1. FC1 : KoA H743

| 포트 | 배선 | 연결 대상 | 규격 |
|---|---|---|---|
| `POWER` | W02 | PM1 | 6p 몰렉스 · 5.3 V + 전압/전류 센싱 |
| `MAIN OUT 1` | W05 | ESC1 → **M1 전방우측 CCW / T9545R** | 3p 서보선 |
| `MAIN OUT 2` | W06 | ESC2 → **M2 후방좌측 CCW / T9545R** | 3p 서보선 |
| `MAIN OUT 3` | W07 | ESC3 → **M3 전방좌측 CW / T9545** | 3p 서보선 |
| `MAIN OUT 4` | W08 | ESC4 → **M4 후방우측 CW / T9545** | 3p 서보선 |
| `GPS` + `I2C` | W09 | GPS1 | 6p + 4p |
| `TELEM 1` | W10 | TM1 | 6p · 57 600 bps |
| `TELEM 2` | W12 | PC1 USB-A | USB-TTL 3.3 V · 921 600 bps |
| `RC IN` | W11 | RX1 | 3p S.BUS |

**ArduPilot 파라미터**

```
FRAME_CLASS       1      multicopter
FRAME_TYPE        1      quad X
SERIAL2_PROTOCOL  2      MAVLink2
SERIAL2_BAUD      921    불안정 시 115
BRD_SAFETYENABLE  1
BATT_MONITOR      4      전압 + 전류
MOT_BAT_VOLT_MAX  12.6   3S
MOT_BAT_VOLT_MIN  9.9    3S
```

4-2. PC1 : Raspberry Pi 4 · J8 40핀 헤더

```
 물리핀  BCM      기능              배선     연결 대상
 ──────────────────────────────────────────────────────────────
   2     —        5V IN             W15      U1 UBEC 출력
   6     —        GND               —        스타 그라운드
  12     GPIO18   I2S BCLK      ┐
  35     GPIO19   I2S LRCLK     ├─ W22-24    U2 MAX98357A
  40     GPIO21   I2S DIN       ┘
  19     GPIO10   SPI0 MOSI         W19      U4 A1 → LED1 DIN
  31     GPIO6    DIR               W21      U4 A3 → U3 DIR
  33     GPIO13   PWM1              W20      U4 A2 → U3 PWM
  39     —        GND               —        스타 그라운드
 ──────────────────────────────────────────────────────────────
 CSI 포트          camera            W18      CAM1
 USB-A             MAVLink           W12      FC1 TELEM2
```

> **핀 선정 이유 (rev.A에서 바뀐 부분)**
> - `GPIO18`은 **I2S BCLK로 고정**이다. 액추에이터 PWM이나 LED에 쓸 수 없다.
> - `GPIO12`는 GPIO18과 **같은 PWM0 채널**이라 동시에 못 쓴다.
> - 액추에이터 → **GPIO13 (PWM1)** + **GPIO6 (DIR)**. LMB2036U는 2선 극성반전식이라
> PWM 1핀만으로는 수축이 불가능하므로 DIR이 반드시 필요하다.
> - LED → **GPIO10 (SPI0 MOSI)**. SPI 구동이라 root 권한도 필요 없다.

---

5. 배선 명세표 (Wire Schedule · 23 conductors)

| ID | FROM | TO | NET | 전선 규격 | 비고 |
|---|---|---|---|---|---|
| W01 | BT1 XT60 | PM1 입력 | 14.8 V | 12 AWG 실리콘 | 메인 배터리 리드 |
| W02 | PM1 6핀 | FC1 POWER | 5.3 V | 6p 몰렉스 | FC1·GPS1·TM1·RX1 전용 |
| W03 | PM1 출력 | PDB1 패드 | 14.8 V | 12 AWG 실리콘 | 패드에 470 µF |
| W04 | PDB1 패드 | ESC1–4 입력 | 14.8 V | 14 AWG ×4 | 호버 합계 19.8 A |
| W05–08 | FC1 MAIN 1–4 | ESC1–4 신호 | PWM | 3p 서보선 | 모터 순번은 §6 |
| W09 | GPS1 | FC1 GPS + I2C | UART, I2C | 6p + 4p | |
| W10 | TM1 | FC1 TELEM1 | UART | 6p | 57 600 bps |
| W11 | RX1 | FC1 RC IN | S.BUS | 3p 서보선 | 수동 개입 경로 |
| W12 | FC1 TELEM2 | PC1 USB-A | MAVLink2 | USB-TTL 3.3 V | **5 V 선 연결 금지** |
| W13 | PDB1 패드 | U1 입력 | 14.8 V | 16 AWG | |
| W14 | PDB1 패드 | U3 Vcc | 14.8 V | 16 AWG | 액추에이터 구동 전원 |
| W15 | U1 출력 | PC1 J8-2 / J8-6 | 5.0 V | 18 AWG | **인라인 3 A 퓨즈** |
| W16 | U1 출력 | U4 Vcc, LED1 Vcc | 5.0 V | 18 AWG | LED1에 1000 µF |
| W17 | 5 V 레일 | U2 Vin | 5.0 V | 22 AWG | |
| W18 | CAM1 | PC1 CSI-2 | MIPI | 15p FPC 200 mm | ESC 전력선과 이격. **45° 하향 고정** |
| W19 | PC1 J8-19 | U4 A1 | SPI0 MOSI | 22 AWG | 3.3 V in → 5 V out |
| W20 | PC1 J8-33 | U4 A2 | PWM1 | 22 AWG | 액추에이터 속도 |
| W21 | PC1 J8-31 | U4 A3 | DIR | 22 AWG | 전개 / 수축 |
| W22–24 | PC1 J8-12/35/40 | U2 I2S | I2S | 22 AWG ×3 | 3.3 V 직결 |
| W25 | U4 Y1 | LED1 DIN | 5 V data | 22 AWG | 470 Ω 직렬 |
| W26–27 | U4 Y2, Y3 | U3 PWM, DIR | 5 V TTL | 22 AWG ×2 | |
| W28 | U3 출력 | M5 | 스위칭 14.8 V | 18 AWG 트위스트 | 극성 반전 |
| W29 | U2 출력 | LS1 | 오디오 | 스피커 페어 | |

---

6. DETAIL A : 모터 배치 (위에서 본 평면)

```
                          ▲ FWD (기수 방향)
                          │

        M3  CW                              M1  CCW
       T9545  프로펠러                      T9545R 프로펠러
          ╲                                  ╱
           ╲                                ╱
            ╲                              ╱
             ╲────────  FC1  ────────────╱
             ╱                            ╲
            ╱                              ╲
           ╱                                ╲
          ╱                                  ╲
        M2  CCW                             M4  CW
       T9545R 프로펠러                       T9545  프로펠러
```

| 모터 | 위치 | ESC | FC 출력 | 회전 | 프로펠러 |
|:-:|---|:-:|:-:|:-:|:-:|
| M1 | 전방 우측 | ESC1 | MAIN OUT 1 | CCW | **T9545R** |
| M2 | 후방 좌측 | ESC2 | MAIN OUT 2 | CCW | **T9545R** |
| M3 | 전방 좌측 | ESC3 | MAIN OUT 3 | CW | **T9545** |
| M4 | 후방 우측 | ESC4 | MAIN OUT 4 | CW | **T9545** |

> 주의 `T9545R`은 역방향(푸셔) 블레이드입니다. 엉뚱한 모터에 끼우면 **이륙 즉시 전복**합니다.
> 프로펠러를 끼우기 전에 반드시 모터 회전 방향부터 확인하세요.

---

7. 조립 순서

1. **프레임·동력계 가조립** : F450 암 체결, 모터 4개 장착(프로펠러는 아직 끼우지 않음), ESC 4개 배치.
2. **전원 배선 (W01 / W03 / W04)** : BT1 → PM1 → PDB1 → ESC. PDB 입력 패드에 470 µF 납땜.
3. **접지 집결** : 모든 GND를 PDB1 한 점에 모음. 이 단계를 건너뛰면 이후 PWM 노이즈로 고생합니다.
4. **FC 계통 (W02 / W05–08 / W09–11)** : Pixhawk 전원·모터 신호·GPS·텔레메트리·수신기.
5. **1차 통전 시험** : 프로펠러 **없이** 전원 인가. Mission Planner로 모터 회전 방향 확인.
6. **프로펠러 장착** : §6 표대로 T9545 / T9545R 구분해 체결.
7. **컴패니언 계통 (W13 / W15 / W18 / W12)** : UBEC → Pi(3 A 퓨즈), 카메라, USB-TTL.
8. **페이로드 계통 (W14 / W16 / W17 / W19–29)** : 레벨 시프터 → DMD-150 / LED / 앰프.
9. **액추에이터 시험** : **기체를 고정한 상태에서** 전개. 120 N 반력이 기체를 밀어냅니다.
10. **전체 통합 시험** : 비전 → 판단 → MAVLink → 전개 전 시퀀스를 지상에서 1회 완주.

---

8. 통전 전 필독 사항

1. 모든 GND를 **PDB1 스타 그라운드**에 접속. 접지가 갈라지면 스위칭 노이즈가 PWM 라인에 실립니다.
2. `PM1`의 5.3 V는 **2.25 A** 한계입니다. FC1·GPS1·TM1·RX1 전용이며 **PC1에는 절대 연결 금지**.
3. `PC1`은 J8-2/6 급전이라 보드 폴리퓨즈를 **우회**합니다. **인라인 3 A 퓨즈**를 다세요.
4. 3.3 V GPIO는 WS2812B의 VIH(0.7 × VDD = **3.5 V**)와 DMD-150의 **5 V TTL** 문턱에 모두 미달합니다.
 → `U4` 74AHCT125는 W25·W26·W27에 **필수**입니다 (선택 아님).
5. `GPIO18`은 I2S 비트클럭입니다. LED나 액추에이터 PWM에 겸용 불가. `GPIO12`도 PWM0 공유라 불가.
6. 첫 시동은 **프로펠러 제거 상태**로. DETAIL A와 회전 방향 대조 후 블레이드 체결.
7. `M5` 스트로크 시험은 **기체 고정 후**. 120 N 반력이 고정되지 않은 기체를 움직입니다.
8. `LED1` 밝기는 코드에서 상한을 거세요. 30 px 전체 백색은 1.8 A를 끌어 PC1이 리부팅됩니다.

---

9. 설계 예산 요약

| 항목 | 값 | 판정 |
|---|---|---|
| 총 이륙 중량 (AUW) | 1 567 g | : |
| 정지 추력 (T9545 ×4 @ 14.8 V) | 2 800 g | : |
| 추력 / 중량 | **1.79 : 1** | 주의 권장 2.0 : 1 미달 |
| 호버 스로틀 / 호버 전류 | 56 % / 19.8 A | : |
| 체공 : 2200 mAh (DoD 80%) | **5.3 분** | NG 임무 수행 불가 |
| 체공 : 3300 mAh | **7.7 분** | OK 권장 |
| 5 V 레일 부하 | 3.15 A / 5.00 A (63 %) | OK |

> 오리가미 구조물을 **150 g 이하**로 묶어야 T/W 1.7대를 유지합니다. 산출 과정은 [HARDWARE_SPEC.md](HARDWARE_SPEC.md) §4.

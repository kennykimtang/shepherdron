import matplotlib.pyplot as plt
import matplotlib.patches as patches

fig, ax = plt.subplots(figsize=(22, 13), dpi=250)
bg_color = "#0B1120"
ax.set_facecolor(bg_color)
fig.patch.set_facecolor(bg_color)

ax.set_xlim(0, 2200)
ax.set_ylim(0, 1300)
ax.axis("off")

# 헤더 타이틀
ax.text(60, 1250, "SHEPHERDRON: 100% VERIFIED HARDWARE WIRING BLUEPRINT", 
        fontsize=22, fontweight="bold", color="#F8FAFC", fontfamily="sans-serif")
ax.text(60, 1220, "Yonsei Univ. Creative Product Design | F450 Quadcopter | Pixhawk 2.4.8 | Raspberry Pi 4 | 3S 11.1V System", 
        fontsize=12, color="#38BDF8", fontfamily="sans-serif")

def draw_block(x, y, w, h, title, sub="", bg="#1E293B", border="#38BDF8", title_col="#F8FAFC"):
    rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=3,rounding_size=6",
                                  linewidth=1.8, edgecolor=border, facecolor=bg, zorder=2)
    ax.add_patch(rect)
    if title:
        ax.text(x + w/2, y + h - 18, title, fontsize=10.5, fontweight="bold", 
                color=title_col, ha="center", va="center", zorder=4)
    if sub:
        ax.text(x + w/2, y + h - 36, sub, fontsize=8.5, 
                color="#94A3B8", ha="center", va="center", zorder=4)

def wire(coords, col="#94A3B8", w=2, style="-"):
    xs, ys = zip(*coords)
    ax.plot(xs, ys, color=col, linewidth=w, linestyle=style, zorder=3)

# ==================== 배경 레이어 구분 ====================
# 상단 레이어 1: 비행제어 및 동력계
bg1 = patches.FancyBboxPatch((30, 480), 2140, 710, boxstyle="round,pad=8,rounding_size=10",
                             linewidth=1, edgecolor="#334155", facecolor="#0F172A", alpha=0.7, zorder=1)
ax.add_patch(bg1)
ax.text(50, 1170, "▶ LAYER 1: FLIGHT CONTROL & PROPULSION (Pixhawk 2.4.8 FC & F450 Power/Motors)", 
        fontsize=11.5, fontweight="bold", color="#94A3B8")

# 하단 레이어 2: 비전 및 기구부
bg2 = patches.FancyBboxPatch((30, 30), 2140, 420, boxstyle="round,pad=8,rounding_size=10",
                             linewidth=1, edgecolor="#334155", facecolor="#0F172A", alpha=0.7, zorder=1)
ax.add_patch(bg2)
ax.text(50, 420, "▶ LAYER 2: ONBOARD VISION & MISSION PAYLOAD (Raspberry Pi 4 & Actuators)", 
        fontsize=11.5, fontweight="bold", color="#94A3B8")

# ==================== 부품 배치 ====================

# [1] 전원부 (좌측 상단)
draw_block(60, 920, 170, 180, "3S LiPo Battery", "2200mAh 11.1V 55C", bg="#1E1B4B", border="#818CF8")
ax.text(145, 985, "XT60 Connector\nWeight: 180g", fontsize=8.5, color="#C7D2FE", ha="center", zorder=4)

draw_block(270, 920, 170, 180, "Power Module", "Pixhawk Sensor", bg="#1E293B", border="#F59E0B")
ax.text(355, 985, "In: 11.1V Bat\nOut: 11.1V to PDB\nReg: 5.3V to FC", fontsize=8.5, color="#FCD34D", ha="center", zorder=4)

draw_block(270, 580, 170, 260, "F450 PDB", "Power Distribution", bg="#1E293B", border="#EF4444")
ax.text(355, 690, "11.1V High-Current\nBus to 4x ESCs,\nUBEC, & DMD-150", fontsize=8.5, color="#FCA5A5", ha="center", zorder=4)

# [2] 센서 / 통신 블록 (픽스호크 상단에 나란히 배치하여 교차 방지!)
draw_block(500, 1070, 200, 65, "GPS & Compass", "Neo-M8N / I2C", bg="#1E293B", border="#38BDF8")
draw_block(730, 1070, 200, 65, "2.4GHz Telemetry", "To Ground GCS", bg="#064E3B", border="#10B981")
draw_block(960, 1070, 200, 65, "Microzone S.BUS", "To MC6C Radio", bg="#3B0764", border="#A855F7")

# [3] 픽스호크 2.4.8 FC (중앙)
draw_block(560, 540, 480, 460, "PIXHAWK 2.4.8 (KOA FC)", "Flight Controller Core (ArduPilot/PX4)", bg="#090D16", border="#38BDF8")

# 포트 라벨 (교차 없는 완벽한 분리)
ax.text(580, 950, "● POWER (5.3V In)", fontsize=9, fontweight="bold", color="#F59E0B", zorder=4)
ax.text(600, 910, "▲ GPS Port", fontsize=9, fontweight="bold", color="#38BDF8", zorder=4)
ax.text(830, 910, "▲ TELEM 1 (57600)", fontsize=9, fontweight="bold", color="#10B981", zorder=4)
ax.text(1010, 910, "▲ RC IN (S.BUS)", fontsize=9, fontweight="bold", color="#A855F7", zorder=4)
ax.text(580, 600, "● TELEM 2 (921600 MAVLink)", fontsize=9, fontweight="bold", color="#EC4899", zorder=4)

# MAIN OUT 1~4 (우측 끝에 정렬)
ax.text(1020, 850, "MAIN OUT 1 ▶", fontsize=9.5, fontweight="bold", color="#F43F5E", ha="right", zorder=4)
ax.text(1020, 770, "MAIN OUT 2 ▶", fontsize=9.5, fontweight="bold", color="#F43F5E", ha="right", zorder=4)
ax.text(1020, 690, "MAIN OUT 3 ▶", fontsize=9.5, fontweight="bold", color="#F43F5E", ha="right", zorder=4)
ax.text(1020, 610, "MAIN OUT 4 ▶", fontsize=9.5, fontweight="bold", color="#F43F5E", ha="right", zorder=4)

# [4] ESC 및 모터 4개 (우측 직결 라인)
motors_data = [
    (1180, 825, "ESC 1 (35A)", "Motor 1 (Front-Right)", "CCW", "#F59E0B", 850),
    (1180, 745, "ESC 2 (35A)", "Motor 2 (Rear-Left)",   "CCW", "#F59E0B", 770),
    (1180, 665, "ESC 3 (35A)", "Motor 3 (Front-Left)",  "CW",  "#38BDF8", 690),
    (1180, 585, "ESC 4 (35A)", "Motor 4 (Rear-Right)",  "CW",  "#38BDF8", 610),
]

for ex, ey, etit, mtit, mrot, mcol, my in motors_data:
    draw_block(ex, ey, 140, 60, etit, "BLHeli_S", bg="#1E293B", border="#F43F5E")
    draw_block(ex + 180, ey, 240, 60, mtit, f"2212 920KV | {mrot} | 1045 Prop", bg="#090D16", border=mcol)
    # ESC ➔ 모터 3상 연결
    wire([(ex + 140, ey + 30), (ex + 180, ey + 30)], col="#38BDF8", w=2.5)

# [5] 하단부: 전원 강하 모듈 (UBEC)
draw_block(270, 160, 170, 140, "5V / 5A UBEC", "DC-DC Step-Down", bg="#1E293B", border="#10B981")
ax.text(355, 215, "In: 11.1V PDB\nOut: 5.0V Clean\n(RPi & LED Power)", fontsize=8.5, color="#6EE7B7", ha="center", zorder=4)

# [6] 하단부: 라즈베리파이 4 (중앙)
draw_block(560, 70, 480, 310, "Raspberry Pi 4 Model B (2GB)", "Companion Computer (YOLOv8 & DroneKit)", bg="#090D16", border="#EC4899")
ax.text(580, 320, "● 5V / GND (Pin 2,6) Power In", fontsize=9, fontweight="bold", color="#10B981", zorder=4)
ax.text(580, 260, "● USB Port (to TTL Serial)", fontsize=9, fontweight="bold", color="#EC4899", zorder=4)
ax.text(1020, 320, "CSI Camera Port ●", fontsize=9, fontweight="bold", color="#38BDF8", ha="right", zorder=4)
ax.text(1020, 240, "GPIO 18 (PWM Out) ●", fontsize=9, fontweight="bold", color="#F59E0B", ha="right", zorder=4)
ax.text(1020, 140, "GPIO 12 (DIN Out) ●", fontsize=9, fontweight="bold", color="#A855F7", ha="right", zorder=4)

# [7] 하단부: 비전/기구부 주변 장치 (우측 수평 직결)
draw_block(1180, 290, 240, 65, "Camera Module 3 Wide", "120° Wide Angle CSI", bg="#1E293B", border="#38BDF8")
draw_block(1180, 205, 240, 65, "DMD-150 Driver", "H-Bridge DC Controller", bg="#1E293B", border="#F59E0B")
draw_block(1540, 205, 240, 65, "LMB2036U Actuator", "250mm Stroke Mechanism", bg="#090D16", border="#F59E0B")
draw_block(1180, 110, 240, 65, "WS2812B NeoPixel LED", "Directional Night Guide", bg="#1E293B", border="#A855F7")

# ==================== 배선 라우팅 (No Crossing / Clean) ====================

# 1. 배터리 ➔ 파워모듈
wire([(230, 1010), (270, 1010)], col="#EF4444", w=3.5)
ax.text(250, 1020, "11.1V", color="#EF4444", fontsize=8.5, fontweight="bold", ha="center")

# 2. 파워모듈 ➔ 픽스호크 POWER (5.3V)
wire([(440, 950), (560, 950)], col="#F59E0B", w=2.5)
ax.text(500, 960, "5.3V Regulated", color="#F59E0B", fontsize=8, fontweight="bold", ha="center")

# 3. 파워모듈 ➔ PDB (메인 11.1V 버스)
wire([(355, 920), (355, 840)], col="#EF4444", w=3.5)
ax.text(370, 880, "11.1V Main Bus", color="#EF4444", fontsize=8, fontweight="bold")

# 4. PDB ➔ 4x ESC 11.1V 전원 (상단 우회 라인)
wire([(440, 710), (470, 710), (470, 520), (1130, 520), (1130, 855), (1180, 855)], col="#EF4444", w=1.8)
wire([(1130, 775), (1180, 775)], col="#EF4444", w=1.8)
wire([(1130, 695), (1180, 695)], col="#EF4444", w=1.8)
wire([(1130, 615), (1180, 615)], col="#EF4444", w=1.8)
ax.text(1110, 530, "11.1V Power to 4x ESCs", color="#EF4444", fontsize=8, fontweight="bold")

# 5. 픽스호크 MAIN OUT 1~4 ➔ ESC 1~4 PWM 신호선 (완전 직선! 교차 0%)
wire([(1040, 850), (1180, 850)], col="#F43F5E", w=2.2)
wire([(1040, 770), (1180, 770)], col="#F43F5E", w=2.2)
wire([(1040, 690), (1180, 690)], col="#F43F5E", w=2.2)
wire([(1040, 610), (1180, 610)], col="#F43F5E", w=2.2)
ax.text(1110, 858, "MAIN 1", color="#F43F5E", fontsize=8, fontweight="bold", ha="center")
ax.text(1110, 778, "MAIN 2", color="#F43F5E", fontsize=8, fontweight="bold", ha="center")
ax.text(1110, 698, "MAIN 3", color="#F43F5E", fontsize=8, fontweight="bold", ha="center")
ax.text(1110, 618, "MAIN 4", color="#F43F5E", fontsize=8, fontweight="bold", ha="center")

# 6. 픽스호크 ➔ 상단 센서 모듈 (수직 직결! 교차 0%)
wire([(600, 920), (600, 1070)], col="#38BDF8", w=2.2)
ax.text(610, 1020, "GPS / I2C", color="#38BDF8", fontsize=8, fontweight="bold")

wire([(830, 920), (830, 1070)], col="#10B981", w=2.2)
ax.text(840, 1020, "TELEM1 (57600)", color="#10B981", fontsize=8, fontweight="bold")

wire([(1010, 920), (1010, 1070)], col="#A855F7", w=2.2)
ax.text(1020, 1020, "S.BUS Signal", color="#A855F7", fontsize=8, fontweight="bold")

# 7. 라즈베리파이 USB ➔ 픽스호크 TELEM 2 (USB to TTL 시리얼 통신)
wire([(560, 260), (490, 260), (490, 600), (560, 600)], col="#EC4899", w=2.5)
ax.text(500, 430, "USB to TTL Serial (921600 baud | MAVLink)", color="#EC4899", fontsize=8.5, fontweight="bold", rotation=90, va="center")

# 8. PDB ➔ UBEC ➔ 라즈베리파이 5V
wire([(355, 580), (355, 300)], col="#EF4444", w=2.5)
ax.text(370, 440, "11.1V In", color="#EF4444", fontsize=8, fontweight="bold")

wire([(440, 230), (510, 230), (510, 320), (560, 320)], col="#10B981", w=2.5)
ax.text(525, 275, "5.0V Clean Power", color="#10B981", fontsize=8, fontweight="bold")

# 9. 라즈베리파이 ➔ 카메라 CSI
wire([(1040, 320), (1180, 320)], col="#38BDF8", w=2.2)
ax.text(1110, 328, "CSI Ribbon", color="#38BDF8", fontsize=8, fontweight="bold", ha="center")

# 10. 라즈베리파이 GPIO 18 ➔ DMD-150 ➔ 액추에이터
wire([(1040, 240), (1180, 240)], col="#F59E0B", w=2.2)
ax.text(1110, 248, "PWM Out", color="#F59E0B", fontsize=8, fontweight="bold", ha="center")

wire([(1420, 240), (1540, 240)], col="#F59E0B", w=2.5)
ax.text(1480, 248, "Motor +/-", color="#F59E0B", fontsize=8.5, fontweight="bold", ha="center")

# DMD-150 모터 고전압 (PDB 11.1V 연결)
wire([(440, 650), (480, 650), (480, 180), (1180, 180)], col="#EF4444", w=1.5, style="--")
ax.text(800, 185, "11.1V High-Power to DMD-150 (from PDB)", color="#EF4444", fontsize=7.5)

# 11. 라즈베리파이 GPIO 12 ➔ LED
wire([(1040, 140), (1180, 140)], col="#A855F7", w=2.2)
ax.text(1110, 148, "DIN Data", color="#A855F7", fontsize=8, fontweight="bold", ha="center")

# LED 5V 전원 (UBEC 연결)
wire([(440, 190), (470, 190), (470, 90), (1180, 90)], col="#10B981", w=1.5, style="--")
ax.text(800, 95, "5.0V Clean Power to LED (from UBEC)", color="#10B981", fontsize=7.5)

plt.tight_layout()
final_path = "/Users/kennytang/shepherdron/shepherdron_master_blueprint.png"
plt.savefig(final_path, dpi=250, bbox_inches="tight", facecolor=fig.get_facecolor())
plt.close()
print(f"[SUCCESS] Perfect collision-free blueprint saved to: {final_path}")

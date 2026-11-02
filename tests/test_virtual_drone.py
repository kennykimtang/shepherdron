"""가상 기체 위에서 실제 GuidanceMission 이 한 바퀴 도는지 검증한다."""
import pytest

from flight.mission import MissionState
from flight.virtual_drone import DemoMission, VirtualDrone

HOT = (2.0, 6.0)


def run(m, seconds, dt=0.1, t0=0.0, rising_at=None, hotspot=HOT, active=True):
    t = t0
    states = []
    while t < t0 + seconds:
        rising = rising_at is not None and abs(t - rising_at) < dt / 2
        m.update(rising, active, 12, hotspot, now=t)
        states.append(m.state)
        t += dt
    return t, states


def test_stays_idle_without_an_alert():
    m = DemoMission()
    _, states = run(m, 3.0)
    assert set(states) == {MissionState.IDLE}
    assert not m.drone.flying


def test_full_mission_cycle_runs_on_real_logic():
    m = DemoMission()
    t, states = run(m, 40.0, rising_at=0.0)
    seen = []
    for s in states:
        if not seen or seen[-1] != s:
            seen.append(s)
    # 경보 프레임에서 곧바로 출동하고, 착륙하면 대기로 돌아온다
    assert seen == [MissionState.NAVIGATING, MissionState.HOVERING,
                    MissionState.RETRACTING, MissionState.RETURNING,
                    MissionState.IDLE]
    assert m.mission.missions_completed == 1
    assert not m.drone.flying


def test_drone_reaches_the_hotspot_before_hovering():
    m = DemoMission()
    t = 0.0
    while m.state is not MissionState.HOVERING and t < 30:
        m.update(t == 0.0, True, 12, HOT, now=t)
        t = round(t + 0.1, 3)
    assert m.state is MissionState.HOVERING
    x, y = m.drone.position
    assert ((x - HOT[0]) ** 2 + (y - HOT[1]) ** 2) ** 0.5 <= 0.9


def test_manual_dispatch_launches_without_an_alert():
    m = DemoMission()
    m.dispatch()
    m.update(False, False, 3, HOT, now=0.0)
    assert m.state is MissionState.NAVIGATING


def test_cooldown_ignores_a_new_alert_right_after_landing():
    m = DemoMission()
    m.update(True, True, 12, HOT, now=0.0)
    t = 0.1
    while m.state is not MissionState.IDLE and t < 60:
        m.update(False, True, 12, HOT, now=t)
        t = round(t + 0.1, 3)
    assert m.state is MissionState.IDLE
    m.update(True, True, 12, HOT, now=t + 1.0)
    assert m.state is MissionState.IDLE          # 쿨다운 15초 안
    m.update(True, True, 12, HOT, now=t + 16.0)
    assert m.state is MissionState.NAVIGATING    # 쿨다운 뒤에는 다시 출동


def test_virtual_drone_lands_and_disarms_at_home():
    d = VirtualDrone(cruise_alt_m=2.0)
    d.goto_body_offset(3.0, 0.0)
    for _ in range(80):
        d.step(0.1)
    d.return_to_launch()
    for _ in range(200):
        d.step(0.1)
    assert not d.state.armed
    assert d.position == pytest.approx((0.0, 0.0), abs=0.2)

"""줄자 붐 드라이버 테스트 — 하드웨어 없이 돈다.

지켜야 할 것
    1. is_stowed 는 **수납 센서가 눌렸을 때만** 참이다. 시간으로 추정하지 않는다.
       거짓 참이면 구조물이 펼쳐진 채 착륙한다.
    2. 끝에 닿지 못하면 반드시 멈추고 FAULT 로 간다. 모터가 계속 돌면 안 된다.
    3. FAULT 에서도 수축은 받아야 한다. 원점으로 돌아가는 유일한 길이다.
"""
import pytest

from hardware.payload import Payload, PayloadState
from hardware.payload_tape import (FakeBackend, TapeBoomConfig, TapeBoomPayload)


class Clock:
    def __init__(self, t: float = 0.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


def build(position=0.0, travel_s=3.0, jam_at=None, **cfg_kw):
    clk = Clock()
    cfg = TapeBoomConfig(**cfg_kw)
    be = FakeBackend(travel_s=travel_s, clock=clk, position=position, jam_at=jam_at)
    return TapeBoomPayload(be, cfg, clock=clk), be, clk


def run(p, clk, seconds, step=0.02):
    """실제 벤치 루프처럼 주기적으로 update() 를 부르며 시간을 보낸다."""
    end = clk.t + seconds
    while clk.t < end - 1e-9:
        clk.t = min(end, clk.t + step)
        p.update()
    return p.state


class TestStartup:
    def test_stowed_switch_means_stowed_immediately(self):
        p, _, _ = build(position=0.0)
        assert p.state is PayloadState.STOWED
        assert p.is_stowed

    def test_deployed_switch_means_deployed(self):
        p, _, _ = build(position=1.0)
        assert p.state is PayloadState.DEPLOYED
        assert not p.is_stowed

    def test_unknown_position_is_a_fault_not_stowed(self):
        p, _, _ = build(position=0.5)
        assert p.state is PayloadState.FAULT
        assert not p.is_stowed          # 가장 중요한 한 줄
        assert p.fault_reason

    def test_it_satisfies_the_payload_protocol(self):
        p, _, _ = build()
        assert isinstance(p, Payload)


class TestTravel:
    def test_deploy_reaches_the_deployed_switch(self):
        p, _, clk = build()
        p.deploy()
        assert p.state is PayloadState.DEPLOYING
        assert run(p, clk, 4.0) is PayloadState.DEPLOYED

    def test_not_stowed_while_moving(self):
        p, _, clk = build()
        p.deploy()
        run(p, clk, 1.0)
        assert p.state is PayloadState.DEPLOYING
        assert not p.is_stowed

    def test_retract_comes_back_to_stowed(self):
        p, _, clk = build(position=1.0)
        p.retract()
        assert run(p, clk, 4.0) is PayloadState.STOWED
        assert p.is_stowed

    def test_motor_is_braked_once_stopped(self):
        p, be, clk = build()
        p.deploy()
        run(p, clk, 4.0)
        assert be._duty == 0.0
        assert p.snapshot()["duty"] == 0.0

    def test_soft_start_ramps_the_duty(self):
        p, be, clk = build(ramp_s=0.5, duty=0.8)
        p.deploy()
        run(p, clk, 0.1)
        mid = abs(be._duty)
        assert 0.0 < mid < 0.8
        run(p, clk, 0.6)
        assert abs(be._duty) == pytest.approx(0.8, abs=1e-6)

    def test_repeated_deploy_does_not_restart_the_clock(self):
        p, _, clk = build()
        p.deploy()
        run(p, clk, 2.0)
        p.deploy()                       # 무시돼야 한다 (램프·타이머가 다시 시작되면 안 된다)
        assert run(p, clk, 2.0) is PayloadState.DEPLOYED

    def test_deploy_when_already_deployed_is_a_no_op(self):
        p, be, _ = build(position=1.0)
        p.deploy()
        assert p.state is PayloadState.DEPLOYED
        assert be._duty == 0.0


class TestFaults:
    def test_a_jam_stops_the_motor_and_faults(self):
        p, be, clk = build(jam_at=0.6, deploy_timeout_s=2.0)
        p.deploy()
        assert run(p, clk, 3.0) is PayloadState.FAULT
        assert be._duty == 0.0           # 계속 돌면 안 된다
        assert "2 초" in p.fault_reason

    def test_both_switches_active_is_a_wiring_fault(self):
        p, be, clk = build()

        be.stowed = lambda: True
        be.deployed = lambda: True
        run(p, clk, 0.1)
        assert p.state is PayloadState.FAULT
        assert not p.is_stowed

    def test_stop_mid_travel_is_a_fault_because_position_is_unknown(self):
        p, be, clk = build()
        p.deploy()
        run(p, clk, 1.0)
        p.stop()
        assert p.state is PayloadState.FAULT
        assert be._duty == 0.0

    def test_stop_while_idle_does_not_invent_a_fault(self):
        p, _, _ = build(position=0.0)
        p.stop()
        assert p.state is PayloadState.STOWED

    def test_retract_still_works_from_a_fault(self):
        p, _, clk = build(position=0.5)
        assert p.state is PayloadState.FAULT
        p.retract()
        assert run(p, clk, 6.0) is PayloadState.STOWED

    def test_fault_recovery_uses_the_slower_creep_duty(self):
        p, be, clk = build(position=0.5, ramp_s=0.0, duty=0.9, creep_duty=0.4)
        p.retract()
        p.update()
        assert abs(be._duty) == pytest.approx(0.4)

    def test_losing_the_switch_while_idle_is_a_fault(self):
        p, be, clk = build(position=0.0)
        assert p.is_stowed
        be.stowed = lambda: False        # 자석이 떨어졌다
        run(p, clk, 0.2)
        assert p.state is PayloadState.FAULT
        assert not p.is_stowed


class TestWiring:
    def test_invert_flips_the_drive_direction(self):
        a, ba, ca = build(ramp_s=0.0)
        a.deploy(); a.update()
        b, bb, cb = build(ramp_s=0.0, invert=True)
        b.deploy(); b.update()
        assert ba._duty > 0 and bb._duty < 0

    def test_config_rejects_impossible_duty(self):
        with pytest.raises(ValueError):
            TapeBoomConfig(duty=0.0)
        with pytest.raises(ValueError):
            TapeBoomConfig(duty=1.5)

    def test_config_rejects_zero_timeout(self):
        with pytest.raises(ValueError):
            TapeBoomConfig(deploy_timeout_s=0.0)

    def test_snapshot_reports_the_switches(self):
        p, _, _ = build(position=0.0)
        s = p.snapshot()
        assert s["state"] == "STOWED"
        assert s["stowed_switch"] is True
        assert s["deployed_switch"] is False

    def test_close_brakes_the_motor(self):
        p, be, clk = build()
        p.deploy()
        run(p, clk, 1.0)
        p.close()
        assert be._duty == 0.0

from __future__ import annotations

from pathlib import Path

import pytest

from src.hardware import (
    HardwareBinding,
    HardwareBindingStore,
    build_default_registry,
    detect_hardware,
    doctor_hardware,
    hardware_binding_lock,
    hardware_lock_path,
    resolve_hardware,
)


def _base_config() -> dict:
    return {
        "experiment": {"seed": 7},
        "target": {"name": "STM32F303"},
        "hardware": {
            "mode": "auto",
            "adapter": "auto",
            "transport": "auto",
            "binding_file": "configs/local/hardware.yaml",
            "profile_dirs": [],
            "target": {"port": None, "baudrate": 115200, "timeout": 0.25},
            "serial": {
                "io_mode": "sync",
                "keep_open": True,
                "reconnect_attempts": 1,
                "reconnect_backoff_s": 0.0,
            },
            "discovery": {
                "enabled": True,
                "candidate_ports": ["/dev/ttyUSB_FAKE"],
                "port_globs": [],
                "probe_timeout_s": 0.25,
            },
        },
    }


def test_resolve_hardware_prefers_local_binding_even_when_default_mode_is_mock(
    tmp_path: Path,
) -> None:
    config = _base_config()
    config["hardware"]["mode"] = "mock"
    config["hardware"]["binding_file"] = str(tmp_path / "hardware.yaml")
    store = HardwareBindingStore(Path(config["hardware"]["binding_file"]))
    binding = HardwareBinding(
        adapter_id="serial-json-hardware",
        profile="serial-json-hardware",
        transport="serial",
        location="/dev/ttyUSB_BOUND",
        baudrate=115200,
        timeout_s=0.25,
        target="STM32F303",
    )
    store.save(binding, selected_from="unit-test", candidates=[])

    resolution = resolve_hardware(config=config, explicit_adapter=None, explicit_port=None, seed=7)

    assert resolution.source == "local-binding"
    assert resolution.selected.location == "/dev/ttyUSB_BOUND"


def test_detect_hardware_returns_typed_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _base_config()
    monkeypatch.setattr(
        "src.hardware.typed_serial_hardware.TypedSerialCommandHardware.probe",
        classmethod(
            lambda cls, *, port, baudrate, timeout, serial_factory=None: {  # noqa: ARG005
                "confidence": 0.99,
                "reason": "typed_protocol_handshake_ok",
                "protocol": "autoglitch.v1",
                "identity": {"port": port},
            }
        ),
    )
    monkeypatch.setattr(
        "src.hardware.serial_hardware.SerialCommandHardware.probe",
        classmethod(lambda cls, *, port, baudrate, timeout, serial_factory=None: None),  # noqa: ARG005
    )

    candidates = detect_hardware(config=config)

    assert len(candidates) == 1
    assert candidates[0].profile.adapter_id == "serial-json-hardware"
    assert candidates[0].binding.location == "/dev/ttyUSB_FAKE"


def test_resolve_hardware_rejects_ambiguous_high_confidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _base_config()
    config["hardware"]["discovery"]["candidate_ports"] = ["/dev/ttyUSB_A", "/dev/ttyUSB_B"]
    monkeypatch.setattr(
        "src.hardware.typed_serial_hardware.TypedSerialCommandHardware.probe",
        classmethod(
            lambda cls, *, port, baudrate, timeout, serial_factory=None: {  # noqa: ARG005
                "confidence": 0.99,
                "reason": "typed_protocol_handshake_ok",
                "identity": {"port": port},
            }
        ),
    )
    monkeypatch.setattr(
        "src.hardware.serial_hardware.SerialCommandHardware.probe",
        classmethod(lambda cls, *, port, baudrate, timeout, serial_factory=None: None),  # noqa: ARG005
    )

    with pytest.raises(RuntimeError, match="ambiguous hardware detection"):
        resolve_hardware(config=config, explicit_adapter=None, explicit_port=None, seed=7)


def test_doctor_hardware_reports_missing_binding_when_no_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _base_config()
    monkeypatch.setattr(
        "src.hardware.typed_serial_hardware.TypedSerialCommandHardware.probe",
        classmethod(lambda cls, *, port, baudrate, timeout, serial_factory=None: None),  # noqa: ARG005
    )
    monkeypatch.setattr(
        "src.hardware.serial_hardware.SerialCommandHardware.probe",
        classmethod(lambda cls, *, port, baudrate, timeout, serial_factory=None: None),  # noqa: ARG005
    )

    report = doctor_hardware(config=config, explicit_adapter=None, explicit_port=None)

    assert report["status"] == "degraded"
    codes = {item["code"] for item in report["findings"]}
    assert "no_candidates" in codes
    assert "missing_local_binding" in codes


def test_doctor_hardware_degrades_when_healthcheck_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _base_config()
    config["hardware"]["binding_file"] = str(tmp_path / "hardware.yaml")
    store = HardwareBindingStore(Path(config["hardware"]["binding_file"]))
    store.save(
        HardwareBinding(
            adapter_id="serial-json-hardware",
            profile="serial-json-hardware",
            transport="serial",
            location="/dev/ttyUSB_STALE",
        ),
        selected_from="unit-test",
        candidates=[],
    )
    monkeypatch.setattr(
        "src.hardware.typed_serial_hardware.TypedSerialCommandHardware.probe",
        classmethod(lambda cls, *, port, baudrate, timeout, serial_factory=None: None),  # noqa: ARG005
    )
    monkeypatch.setattr(
        "src.hardware.serial_hardware.SerialCommandHardware.probe",
        classmethod(lambda cls, *, port, baudrate, timeout, serial_factory=None: None),  # noqa: ARG005
    )
    monkeypatch.setattr(
        "src.hardware.typed_serial_hardware.TypedSerialCommandHardware.healthcheck",
        lambda self: (_ for _ in ()).throw(RuntimeError("serial unavailable")),
    )

    report = doctor_hardware(config=config)

    assert report["status"] == "degraded"
    codes = {item["code"] for item in report["findings"]}
    assert "healthcheck_failed" in codes


def test_default_registry_loads_official_profiles() -> None:
    registry = build_default_registry()
    assert {
        "mock-hardware",
        "serial-command-hardware",
        "serial-json-hardware",
        "chipwhisperer-hardware",
    }.issubset(set(registry.adapter_ids()))


def test_detect_hardware_prefers_preferred_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _base_config()
    config["hardware"]["preferred_adapter"] = "serial-json-hardware"

    typed_calls: list[str] = []
    legacy_calls: list[str] = []

    def _typed_probe(cls, *, port, baudrate, timeout, serial_factory=None):  # noqa: ARG001
        typed_calls.append(port)
        return {
            "confidence": 0.99,
            "reason": "typed_protocol_handshake_ok",
            "protocol": "autoglitch.v1",
        }

    def _legacy_probe(cls, *, port, baudrate, timeout, serial_factory=None):  # noqa: ARG001
        legacy_calls.append(port)
        return None

    monkeypatch.setattr(
        "src.hardware.typed_serial_hardware.TypedSerialCommandHardware.probe",
        classmethod(_typed_probe),
    )
    monkeypatch.setattr(
        "src.hardware.serial_hardware.SerialCommandHardware.probe",
        classmethod(_legacy_probe),
    )

    candidates = detect_hardware(config=config)

    assert len(candidates) == 1
    assert typed_calls == ["/dev/ttyUSB_FAKE"]
    assert legacy_calls == []


def test_resolve_hardware_rejects_missing_required_capabilities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _base_config()
    config["hardware"]["required_capabilities"] = ["nonexistent.capability"]
    monkeypatch.setattr(
        "src.hardware.typed_serial_hardware.TypedSerialCommandHardware.probe",
        classmethod(
            lambda cls, *, port, baudrate, timeout, serial_factory=None: {  # noqa: ARG005
                "confidence": 0.99,
                "reason": "typed_protocol_handshake_ok",
                "protocol": "autoglitch.v1",
                "capabilities": ["glitch.execute"],
            }
        ),
    )
    monkeypatch.setattr(
        "src.hardware.serial_hardware.SerialCommandHardware.probe",
        classmethod(lambda cls, *, port, baudrate, timeout, serial_factory=None: None),  # noqa: ARG005
    )

    with pytest.raises(RuntimeError, match="missing required capabilities"):
        resolve_hardware(config=config, explicit_adapter=None, explicit_port=None, seed=7)


def test_hardware_binding_lock_blocks_duplicate_access(tmp_path: Path) -> None:
    binding = HardwareBinding(
        adapter_id="serial-json-hardware",
        profile="serial-json-hardware",
        transport="serial",
        location="/dev/ttyUSB_LOCKED",
    )
    lock_path = hardware_lock_path(binding, lock_dir=tmp_path)
    assert lock_path is not None

    with (
        hardware_binding_lock(binding, lock_dir=tmp_path),
        pytest.raises(
            RuntimeError,
            match="already in use",
        ),
        hardware_binding_lock(binding, lock_dir=tmp_path, timeout_s=0.0),
    ):
        raise AssertionError("lock should not be re-acquired")

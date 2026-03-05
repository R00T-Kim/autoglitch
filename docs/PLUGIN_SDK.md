# Plugin SDK (Manifest v1)

## 목적
AUTOGLITCH는 장비/타깃/옵티마이저를 manifest 기반으로 등록해 운영한다.

## Manifest 필드
```yaml
name: mock-hardware
kind: hardware            # hardware|observer|classifier|mapper|optimizer
version: 1.0.0
module: src.hardware.mock
class_name: MockHardware
description: Deterministic mock adapter
capabilities: [simulation, reproducibility]
supported_targets: [stm32f3, esp32]
limits:
  voltage_abs_max: 1.0
```

## 로딩 위치
- 기본: `src/plugins/manifests/*.yaml`
- 추가: CLI `--plugin-dir <path>` 또는 `plugins.manifest_dirs` config

## 점검 명령
```bash
python -m src.cli list-plugins
python -m src.cli list-plugins --kind hardware
```

# Fault Injection 관련 연구/아티클/레포 정리 (AUTOGLITCH 레퍼런스)

_업데이트: 2026-03-05_

## 목적
AUTOGLITCH(자동 글리칭 + fault-to-primitive) 설계/구현에 직접 참고할 수 있는 자료를 **논문 / 실전 아티클 / GitHub 도구**로 분리해 정리한다.

## 1) 핵심 논문 (우선순위 높음)

### A. 자동화/탐색/시뮬레이션
- SoK: automated FI simulation (2024): https://eprint.iacr.org/2024/1944  
  - 시뮬레이터 분류·장단점·오픈문제. AUTOGLITCH의 simulator 연동 전략 수립용.
- Glitch it if you can (CARDIS 2013): https://cardis.org/cardis2013/proceedings/CARDIS2013_16.pdf  
  - 글리치 파라미터 탐색 고전. 초기 탐색 정책/휴리스틱 설계 참고.
- CRAFT (2025): https://eprint.iacr.org/2025/798  
  - pre-silicon에서 FI root-cause 추적. HW/SW fault propagation 분석 프레임 참고.
- GLITCHGLÜCK (WOOT 2025): https://www.usenix.org/conference/woot25/technical-sessions  
  - DSTG 기반 guided FI(무차별 탐색 축소) 접근.

### B. Secure Boot/MCU 실전 공격
- Fill your Boots (TCHES 2021): https://artifacts.iacr.org/tches/2021/a2/index.html  
- Android Secure-Boot bypass (CARDIS 2022): https://eprint.iacr.org/2022/602  
- TI SimpleLink physical attacks: https://eprint.iacr.org/2022/328  
- ESP32-V3 firmware encryption break: https://eprint.iacr.org/2023/090  
- RISC-V isolated execution bypass: https://eprint.iacr.org/2020/1193

### C. 소프트웨어 제어형 fault(undervolting/clock)
- CLKSCREW (USENIX Sec 2017): https://www.usenix.org/conference/usenixsecurity17/technical-sessions/presentation/tang
- V0LTpwn (USENIX Sec 2020): https://www.usenix.org/conference/usenixsecurity20/presentation/kenjar
- Plundervolt: https://plundervolt.com/

### D. 탐지/방어
- ML-based glitch detection (2024): https://eprint.iacr.org/2024/1939
- Attacking glitch detectors (TCHES 2024): https://eprint.iacr.org/2023/1647

## 2) 실전 아티클/벤더 공지 (ESP32 축)
- Espressif advisory (CVE-2019-15894): https://www.espressif.com/en/news/Espressif_Security_Advisory_Concerning_Fault_Injection_and_Secure_Boot
- Espressif advisory (CVE-2019-17391): https://www.espressif.com/en/news/Security_Advisory_Concerning_Fault_Injection_and_eFuse_Protections
- NVD CVE-2019-15894: https://nvd.nist.gov/vuln/detail/CVE-2019-15894
- LimitedResults (Secure Boot bypass): https://limitedresults.com/2019/09/pwn-the-esp32-secure-boot/
- LimitedResults (키 추출): https://limitedresults.com/2019/11/pwn-the-esp32-forever-flash-encryption-and-sec-boot-keys-extraction/
- Raelize (Crowbar glitch case study, 2025): https://raelize.com/blog/espressif-systems-esp32-using-a-crowbar-glitch-to-bypass-encrypted-secure-boot/

## 3) GitHub 레퍼런스 (도구/프레임워크)

### A. 실장비 글리칭/EMFI
- ChipWhisperer: https://github.com/newaetech/chipwhisperer
- ChipSHOUTER: https://github.com/newaetech/ChipSHOUTER
- PicoEMP: https://github.com/newaetech/chipshouter-picoemp
- FaultyCat: https://github.com/ElectronicCats/faultycat

### B. 시뮬레이션/캠페인/포멀
- FiSim: https://github.com/Keysight/FiSim
- FIES (QEMU 기반): https://github.com/ahoeller/fies
- SYNFI (OpenTitan pre-silicon FI): https://github.com/lowRISC/synfi
- FAIL*: https://github.com/danceos/fail
- LLFI (LLVM IR): https://github.com/DependableSystemsLab/LLFI

## 4) AUTOGLITCH 반영 체크리스트
1. `optimizer/`에 초기 휴리스틱(Glitch it if you can) + BO prior 도입
2. simulator 연동 계층 설계(FiSim/FIES/SYNFI 중 1개 PoC)
3. `classifier/mapper`를 fault class → primitive confidence 모델로 고도화
4. 방어 평가 모드(탐지기 우회 성공률, false negative) 추가
5. ESP32 또는 STM32 타깃으로 재현 가능한 benchmark campaign 정의

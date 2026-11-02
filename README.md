# ncp-nw-report

네트워크 구성도 현행화용 **접근통제 정책 별첨 엑셀**을 NCP API로 생성합니다.
구성도에는 통제 지점만 표기하고, ACG·NACL·Subnet 상세는 이 별첨으로 관리하는 것을 전제로 합니다.

NCP API 호출은 [ncp-api-python](https://github.com/Neidn/ncp-api-python) (`NcpClient`)을 사용하며, **조회 API만** 호출합니다.

## 시트 구성

| 시트 | 작성 방식 | 내용 |
|---|---|---|
| 작성기준 | 자동 | 문서 정보, 정책 추출 시각, 보안등급, 작성 기준 |
| 서버-ACG 매핑 | 자동 | 1행 = 서버 1대 × ACG 1개 |
| ACG 규칙 | 자동 | 1행 = 규칙 1개, `적용 서버 수`는 매핑 시트에서 자동 집계 |
| NACL 규칙 | 자동 | Subnet 단위 규칙 (우선순위 순), Deny-Allow Group 이름 표기 |
| Subnet 목록 | 자동 | VPC/Subnet 대역, 게이트웨이(대역 첫 IP), 유형·용도, NACL |
| IPsec VPN | **수동** | 1행 = 상대 측 대역 1개. 연결 대상, 상대 측 Peer IP·대역, NCP Peer IP·내부 대역, 이중화 (상대 측/NCP 측 열 색 구분) |
| 변경이력 | **수동** | 수시 현행화 내역 |

수동 시트는 `--previous` 로 이전 별첨 파일을 주면 내용을 그대로 옮겨 옵니다. 자동 시트만 새로 갱신됩니다.

예시 결과물: [`examples/sample_report.xlsx`](examples/sample_report.xlsx) (예시 데이터이며 실제 값 아님)

## 설치

```bash
uv sync
```

## 사용법

**키 1개(계정 1개) = 별첨 파일 1개**로 동작합니다. 계정이 여러 개면 계정별로 따로 실행합니다.

### 1. 키 설정

`.env.example` 을 `.env` 로 복사해 Sub Account 키를 넣습니다. 조회 권한만 있는 키를 권장합니다.
계정마다 `.env` 파일을 나눠 두고 `--env-file` 로 지정해도 됩니다.

```ini
NCP_ACCESS_KEY=ncp_iam_...
NCP_SECRET_KEY=ncp_iam_...
NCP_ENV=gov
```

### 2. 실행

```bash
# 최초 작성
uv run ncp-nw-report collect --out out/접근통제정책_별첨.xlsx \
    --author "작성자" --version v1.0 --dump-raw out/2026-11.raw.json

# 현행화 (IPsec·변경이력 등 수동 시트는 이전 파일에서 가져옴)
uv run ncp-nw-report collect --out out/접근통제정책_별첨_v1.1.xlsx \
    --version v1.1 --previous out/접근통제정책_별첨.xlsx

# 계정별 키 파일 지정
uv run ncp-nw-report collect --env-file .env.account-a --out out/a.xlsx

# 저장해 둔 원본으로 엑셀만 다시 작성
uv run ncp-nw-report build --raw out/2026-11.raw.json --out out/접근통제정책_별첨.xlsx

# API 키 없이 예시 데이터로 결과물 확인
uv run ncp-nw-report demo --out out/sample_report.xlsx
```

| 옵션 | 설명 |
|---|---|
| `--title` / `--author` / `--version` / `--classification` | 작성기준 시트의 문서 정보 (기본 보안등급: 대외비) |
| `--previous` | 수동 입력 시트(IPsec VPN, 변경이력)를 가져올 이전 파일 |
| `--dump-raw` | API 조회 원본 저장 (`*.raw.json`) |
| `--env` | `gov` / `public` / `fin` (미지정 시 `NCP_ENV`, 없으면 `public`) |

## 수집 대상 API

| 데이터 | API | 비고 |
|---|---|---|
| VPC / Subnet | `vpc.get_vpc_list`, `vpc.get_subnet_list` | |
| 서버 / NIC | `server.get_server_instance_list`, `server.get_network_interface_list` | 서버별 ACG는 NIC의 `accessControlGroupNoList` 기준 |
| ACG / ACG 규칙 | `server.get_access_control_group_list`, `server.get_access_control_group_rule_list` | |
| Network ACL / 규칙 | `/vpc/v2/getNetworkAclList`, `/vpc/v2/getNetworkAclRuleList` | 라이브러리에 메서드가 없어 `client.vpc.request()` 로 직접 호출 |
| Deny-Allow Group | `/vpc/v2/getNetworkAclDenyAllowGroupList` | 실패 시 번호로 표기 |

## 주의

- 산출물(`*.xlsx`)과 원본 덤프(`*.raw.json`)에는 접근통제 정책이 담겨 있으므로 `.gitignore` 로 커밋을 막아 두었습니다. 대외비로 취급하세요.
- 규칙이 하나도 없는 ACG는 ACG 규칙 시트에 나타나지 않습니다.
- Subnet 게이트웨이는 NCP 기준(대역의 첫 번째 IP)으로 계산한 값입니다.

## 개발

```bash
uv sync --all-groups
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

"""별첨 엑셀 작성.

자동 수집 시트(서버-ACG 매핑, ACG 규칙, NACL 규칙, Subnet 목록)는 매번 새로 쓰고,
수동 입력 시트(서버-기관, IPsec VPN, 변경이력)는 이전 파일이 주어지면
그 내용을 그대로 옮겨 온다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from ncp_nw_report.transform import Report


@dataclass
class Document:
    title: str = "접근통제 정책 별첨"
    author: str = ""
    version: str = "v1.0"
    classification: str = "대외비"


FONT = "Arial"
HEADER_ROW = 4
FIRST = HEADER_ROW + 1
MANUAL_ROWS = 100  # 수동 입력 시트에 미리 서식/수식을 깔아 둘 행 수

_thin = Side(style="thin", color="BFBFBF")
BORDER = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)
HEAD_FILL = PatternFill("solid", fgColor="1F3864")
MANUAL_FILL = PatternFill("solid", fgColor="EAF1DD")

S_MAP = "서버-ACG 매핑"
S_ACG = "ACG 규칙"
S_NACL = "NACL 규칙"
S_SUBNET = "Subnet 목록"
S_LB = "LB 목록"
S_SERVER_ORG = "서버-기관"
S_IPSEC = "IPsec VPN"
S_HISTORY = "변경이력"

SHEETS: dict[str, dict[str, Any]] = {
    S_MAP: {
        "note": "1행 = 서버 1대 × ACG 1개. 서버에 ACG가 여러 개면 행을 나누어 작성",
        "headers": [
            "VPC",
            "Subnet",
            "서버명",
            "사용 기관",
            "사설 IP",
            "적용 ACG",
            "ACG 설명",
        ],
        "widths": [22, 30, 26, 20, 15, 28, 30],
    },
    S_ACG: {
        "note": "1행 = 규칙 1개. '적용 서버 수'는 서버-ACG 매핑 시트에서 자동 집계 "
        "(0이면 미사용 ACG). '적용 기관'은 작성 시점의 서버-기관 시트 기준",
        "headers": [
            "ACG명",
            "VPC",
            "방향",
            "프로토콜",
            "포트",
            "출발지/목적지",
            "출발지 구분",
            "용도",
            "적용 서버 수",
            "적용 기관",
        ],
        "widths": [28, 22, 11, 10, 13, 24, 11, 30, 12, 22],
    },
    S_NACL: {
        "note": "Subnet 단위 규칙. 우선순위 숫자가 작을수록 먼저 적용",
        "headers": [
            "NACL명",
            "VPC",
            "적용 Subnet",
            "방향",
            "우선순위",
            "프로토콜",
            "포트",
            "출발지/목적지",
            "허용/차단",
            "용도",
        ],
        "widths": [26, 22, 30, 11, 10, 10, 13, 28, 10, 26],
    },
    S_SUBNET: {
        "note": "게이트웨이는 NCP Subnet 대역의 첫 번째 IP 기준",
        "headers": [
            "VPC",
            "VPC 대역",
            "Subnet",
            "대역",
            "게이트웨이",
            "유형",
            "용도",
            "NACL",
        ],
        "widths": [22, 15, 30, 16, 14, 10, 10, 26],
    },
    S_LB: {
        "note": "1행 = LB × 대상 그룹. 리스너는 LB의 전체 리스너(리스너별 대상 그룹 "
        "연결은 미표기). LB 접근통제는 LB Subnet의 NACL과 대상 서버의 "
        "ACG로 적용됨 (NACL 규칙·ACG 규칙 시트 참조)",
        "headers": [
            "LB명",
            "유형",
            "네트워크",
            "VPC",
            "Subnet",
            "LB IP",
            "도메인",
            "리스너",
            "대상 그룹",
            "대상 프로토콜:포트",
            "대상 서버",
        ],
        "widths": [26, 20, 10, 22, 28, 16, 40, 16, 26, 16, 28],
    },
    S_SERVER_ORG: {
        "note": "[수동 입력] 사용 기관·비고만 입력. 여러 기관이 쓰면 쉼표로 구분, "
        "전체 기관이 쓰면 '전체'. 상태: 신규=이번에 추가된 서버, 미조회=NCP에서 "
        "조회되지 않음(삭제 여부 확인 후 행 정리)",
        "headers": ["서버명", "VPC", "사용 기관", "비고", "상태"],
        "widths": [30, 22, 30, 30, 10],
        "manual_cols": 4,
    },
    S_IPSEC: {
        "note": "[수동 입력] 1행 = 상대 측 대역 1개. 값이 여러 개인 칸(Peer IP, "
        "NCP 내부 대역)은 셀 안에서 줄바꿈으로 구분. "
        "대역 간 실제 허용은 ACG/NACL 시트 참조",
        "headers": [
            "연결 대상",
            "상대 측 Peer IP",
            "상대 측 대역",
            "NCP Peer IP",
            "NCP 내부 대역",
            "이중화",
            "비고",
        ],
        "widths": [26, 20, 20, 30, 20, 10, 24],
        "manual_cols": 7,
        # 열 그룹: (시작 열, 끝 열, 그룹명, 헤더색, 입력칸색)
        "groups": [
            (2, 3, "상대 측", "C55A11", "FCE4D6"),
            (4, 5, "NCP 측", "2E75B6", "DDEBF7"),
        ],
    },
    S_HISTORY: {
        "note": "[수동 입력] 수시 현행화 내역",
        "headers": ["변경일", "시트", "대상", "변경 내용", "요청처", "작업자"],
        "widths": [12, 14, 22, 44, 14, 10],
        "manual_cols": 6,
    },
}

MANUAL_SHEETS = [S_SERVER_ORG, S_IPSEC, S_HISTORY]


def _cell(ws: Worksheet, row: int, col: int, value: Any) -> None:
    c = ws.cell(row, col, value)
    c.font = Font(name=FONT, size=10)
    c.border = BORDER
    c.alignment = Alignment(vertical="center", wrap_text=True)


def _fit_rows(ws: Worksheet, first: int, last: int) -> None:
    """셀 안 줄바꿈 수에 맞춰 행 높이 지정 (엑셀이 자동 조정하지 않는 경우 대비)."""
    for r in range(first, last + 1):
        lines = max(
            (str(c.value).count("\n") + 1 for c in ws[r] if c.value is not None),
            default=1,
        )
        if lines > 1:
            ws.row_dimensions[r].height = 14 * lines


def _sheet(wb: Workbook, name: str) -> Worksheet:
    spec = SHEETS[name]
    ws = wb.create_sheet(name)
    ws["A1"] = name
    ws["A1"].font = Font(name=FONT, bold=True, size=13)
    ws["A2"] = spec["note"]
    ws["A2"].font = Font(name=FONT, size=9, color="595959")
    for i, h in enumerate(spec["headers"], 1):
        c = ws.cell(HEADER_ROW, i, h)
        c.font = Font(name=FONT, bold=True, color="FFFFFF", size=10)
        c.fill = HEAD_FILL
        c.border = BORDER
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for start, end, label, head, _ in spec.get("groups", []):
        for col in range(start, end + 1):
            g = ws.cell(HEADER_ROW - 1, col, label if col == start else None)
            g.font = Font(name=FONT, bold=True, color="FFFFFF", size=10)
            g.fill = PatternFill("solid", fgColor=head)
            g.alignment = Alignment(horizontal="center", vertical="center")
            ws.cell(HEADER_ROW, col).fill = PatternFill("solid", fgColor=head)
    for i, w in enumerate(spec["widths"], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = ws.cell(FIRST, 1)
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{HEADER_ROW}:{HEADER_ROW}"
    return ws


def _rows(ws: Worksheet, rows: list[list[Any]]) -> int:
    for r, row in enumerate(rows, FIRST):
        for c, v in enumerate(row, 1):
            _cell(ws, r, c, v)
    last = FIRST + len(rows) - 1
    _fit_rows(ws, FIRST, last)
    ncol = ws.max_column
    ws.auto_filter.ref = f"A{HEADER_ROW}:{get_column_letter(ncol)}{max(last, FIRST)}"
    return last


def read_manual(previous: str | Path | None) -> dict[str, list[list[Any]]]:
    """이전 별첨 파일에서 수동 입력 시트 내용을 읽는다."""
    out: dict[str, list[list[Any]]] = {name: [] for name in MANUAL_SHEETS}
    if not previous:
        return out
    wb = load_workbook(previous, data_only=True)
    for name in MANUAL_SHEETS:
        if name not in wb.sheetnames:
            continue
        ws = wb[name]
        ncols = SHEETS[name]["manual_cols"]
        for row in ws.iter_rows(min_row=FIRST, max_col=ncols, values_only=True):
            if any(v not in (None, "") for v in row):
                out[name].append(list(row))
    return out


def _guide(wb: Workbook, doc: Document, collected_at: str) -> None:
    ws = wb.active
    ws.title = "작성기준"
    lines: list[tuple[str, bool]] = [
        (doc.title, True),
        ("", False),
        ("■ 문서 정보", True),
        (
            f"작성: {doc.author} / 작성일: {date.today():%Y-%m-%d} / "
            f"버전: {doc.version}",
            False,
        ),
        (f"정책 추출 시각: {collected_at} (NCP API 조회 기준)", False),
        (f"보안등급: {doc.classification}", False),
        ("", False),
        ("■ 시트 구성", True),
        (f"{S_SERVER_ORG}: 서버별 사용 기관 (수동 입력, 서버 목록은 자동 갱신)", False),
        (f"{S_MAP}: 서버별 적용 ACG (자동 수집)", False),
        (f"{S_ACG}: ACG별 Inbound/Outbound 규칙 (자동 수집)", False),
        (f"{S_NACL}: Subnet 단위 Network ACL 규칙 (자동 수집)", False),
        (f"{S_SUBNET}: VPC/Subnet 대역, 게이트웨이, NACL (자동 수집)", False),
        (f"{S_LB}: Load Balancer와 대상 그룹·대상 서버 (자동 수집)", False),
        (f"{S_IPSEC}: 연결 대상별 Peer IP와 연동 대역 (수동 입력)", False),
        (f"{S_HISTORY}: 수시 현행화 내역 (수동 입력)", False),
        ("", False),
        ("■ 작성 기준", True),
        ("셀 병합 없이 작성 (필터·정렬 유지 목적)", False),
        ("ACG명, 서버명, Subnet명은 NCP 콘솔 명칭과 동일 (구성도 명칭과 일치)", False),
        ("출발지가 ACG인 규칙은 '출발지 구분'을 ACG로 표기", False),
        ("ACG는 VPC 단위 자원이므로 VPC 열과 함께 확인", False),
        ("연한 초록색 칸은 수동 입력 칸", False),
        (f"{S_IPSEC} 시트는 상대 측(주황), NCP 측(파랑)으로 열 색을 구분", False),
    ]
    for i, (text, bold) in enumerate(lines, 1):
        c = ws.cell(i, 1, text)
        c.font = Font(name=FONT, bold=bold, size=13 if i == 1 else 10)
    ws.column_dimensions["A"].width = 100


def merge_server_orgs(
    servers: list[list[Any]], previous: list[list[Any]]
) -> list[list[Any]]:
    """현재 서버 목록과 이전 서버-기관 시트를 합친다.

    반환 행: [서버명, VPC, 사용 기관, 비고, 상태]
    - 이전에 있던 서버: 사용 기관·비고 유지
    - 새 서버: 사용 기관 빈칸, 상태 '신규'
    - 이전에만 있는 서버: 그대로 두고 상태 '미조회'
    """
    prev = {str(r[0]): r for r in previous if r and r[0]}
    out: list[list[Any]] = []
    seen: set[str] = set()
    for name, vpc in servers:
        seen.add(name)
        old = prev.get(name)
        if old:
            out.append([name, vpc, old[2], old[3], ""])
        else:
            out.append([name, vpc, None, None, "신규" if prev else ""])
    for name, old in prev.items():
        if name not in seen:
            out.append([name, old[1], old[2], old[3], "미조회"])
    return out


def _split_orgs(value: Any) -> list[str]:
    return [v.strip() for v in str(value or "").split(",") if v.strip()]


def acg_orgs(mapping: list[list[Any]], server_orgs: list[list[Any]]) -> dict:
    """(VPC, ACG명) -> 적용 기관 문자열. 서버 중 하나라도 '전체'면 '전체'."""
    org_of = {r[0]: _split_orgs(r[2]) for r in server_orgs}
    acc: dict[tuple[str, str], list[str]] = {}
    for vpc, _subnet, server, _org, _ip, acg, _desc in mapping:
        names = acc.setdefault((vpc, acg), [])
        for org in org_of.get(server, []):
            if org not in names:
                names.append(org)
    return {
        key: "전체" if "전체" in names else ", ".join(sorted(names))
        for key, names in acc.items()
    }


def write(
    report: Report,
    out: str | Path,
    doc: Document | None = None,
    previous: str | Path | None = None,
) -> Path:
    doc = doc or Document()
    manual = read_manual(previous)
    manual[S_SERVER_ORG] = merge_server_orgs(report.servers, manual[S_SERVER_ORG])
    wb = Workbook()
    _guide(wb, doc, report.collected_at)

    # 서버-ACG 매핑: 사용 기관(D열)은 서버-기관 시트에서 조회하는 수식
    ws = _sheet(wb, S_MAP)
    map_last = max(_rows(ws, report.mapping), FIRST)
    org_end = FIRST + max(len(manual[S_SERVER_ORG]) + 20, MANUAL_ROWS) - 1
    so = f"'{S_SERVER_ORG}'!"
    for r in range(FIRST, FIRST + len(report.mapping)):
        look = (
            f"INDEX({so}$C${FIRST}:$C${org_end},"
            f"MATCH(C{r},{so}$A${FIRST}:$A${org_end},0))"
        )
        _cell(ws, r, 4, f'=IFERROR(IF({look}="","",{look}),"")')

    ws = _sheet(wb, S_ACG)
    last = _rows(ws, report.acg_rules)
    orgs = acg_orgs(report.mapping, manual[S_SERVER_ORG])
    m = f"'{S_MAP}'!"
    for r in range(FIRST, last + 1):
        _cell(
            ws,
            r,
            9,
            f"=COUNTIFS({m}$A${FIRST}:$A${map_last},B{r},"
            f"{m}$F${FIRST}:$F${map_last},A{r})",
        )
        ws.cell(r, 9).alignment = Alignment(horizontal="center", vertical="center")
        key = (ws.cell(r, 2).value, ws.cell(r, 1).value)
        _cell(ws, r, 10, orgs.get(key, ""))

    _rows(_sheet(wb, S_NACL), report.nacl_rules)
    _rows(_sheet(wb, S_SUBNET), report.subnets)
    _rows(_sheet(wb, S_LB), report.load_balancers)

    # 수동 입력 시트
    for name in MANUAL_SHEETS:
        ws = _sheet(wb, name)
        spec = SHEETS[name]
        ncols = len(spec["headers"]) if name == S_SERVER_ORG else spec["manual_cols"]
        rows = manual[name]
        fills = {
            col: PatternFill("solid", fgColor=cell_color)
            for start, end, _, _, cell_color in spec.get("groups", [])
            for col in range(start, end + 1)
        }
        # 서버-기관 시트는 서버명·VPC·상태가 자동 값이므로 입력칸(C, D)만 색칠
        manual_cols = {3, 4} if name == S_SERVER_ORG else set(range(1, ncols + 1))
        total = max(len(rows) + 20, MANUAL_ROWS)
        for r in range(FIRST, FIRST + total):
            values = rows[r - FIRST] if r - FIRST < len(rows) else [None] * ncols
            for c in range(1, ncols + 1):
                _cell(ws, r, c, values[c - 1] if c - 1 < len(values) else None)
                if c in manual_cols:
                    ws.cell(r, c).fill = fills.get(c, MANUAL_FILL)
        last = FIRST + total - 1
        _fit_rows(ws, FIRST, FIRST + len(rows) - 1)
        ws.auto_filter.ref = (
            f"A{HEADER_ROW}:{get_column_letter(len(spec['headers']))}{last}"
        )

    # 서버-기관 시트를 작성기준 바로 다음(두 번째)으로 이동
    wb.move_sheet(S_SERVER_ORG, offset=1 - wb.sheetnames.index(S_SERVER_ORG))

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return out

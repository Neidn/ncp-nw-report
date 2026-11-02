"""별첨 엑셀 작성.

자동 수집 시트(서버-ACG 매핑, ACG 규칙, NACL 규칙, Subnet 목록)는 매번 새로 쓰고,
수동 입력 시트(IPsec 터널, IPsec 연동 대역, 변경이력)는 이전 파일이 주어지면
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
from openpyxl.worksheet.datavalidation import DataValidation
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
REF_END = 5000  # 시트 간 참조 수식의 범위 끝 행

_thin = Side(style="thin", color="BFBFBF")
BORDER = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)
HEAD_FILL = PatternFill("solid", fgColor="1F3864")
MANUAL_FILL = PatternFill("solid", fgColor="EAF1DD")

S_MAP = "서버-ACG 매핑"
S_ACG = "ACG 규칙"
S_NACL = "NACL 규칙"
S_SUBNET = "Subnet 목록"
S_TUNNEL = "IPsec 터널"
S_RANGE = "IPsec 연동 대역"
S_HISTORY = "변경이력"

SHEETS: dict[str, dict[str, Any]] = {
    S_MAP: {
        "note": "1행 = 서버 1대 × ACG 1개. 서버에 ACG가 여러 개면 행을 나누어 작성",
        "headers": [
            "VPC",
            "Subnet",
            "서버명",
            "사설 IP",
            "적용 ACG",
            "ACG 설명",
        ],
        "widths": [22, 30, 26, 15, 28, 30],
    },
    S_ACG: {
        "note": "1행 = 규칙 1개. '적용 서버 수'는 서버-ACG 매핑 시트에서 자동 집계 "
        "(0이면 미사용 ACG)",
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
        ],
        "widths": [28, 22, 11, 10, 13, 24, 11, 30, 12],
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
    S_TUNNEL: {
        "note": "[수동 입력] 1행 = 터널 1개. 대역폭은 인터넷 기반 터널이므로 기재하지 "
        "않음. 마지막 열은 자동 집계",
        "headers": [
            "연결 대상",
            "VPN Gateway",
            "터널명",
            "상대 측 Peer IP",
            "이중화",
            "비고",
            "연동 대역 수",
        ],
        "widths": [16, 18, 22, 16, 12, 24, 13],
        "manual_cols": 6,
    },
    S_RANGE: {
        "note": "[수동 입력] 1행 = 대역 1개. 상대 측·클라우드 측 대역 수가 달라도 각각 "
        "행으로 작성 (대역 간 실제 허용은 ACG/NACL 시트 참조)",
        "headers": ["터널명", "구분", "연동 대역", "대역 설명", "비고"],
        "widths": [22, 12, 18, 26, 24],
        "manual_cols": 5,
    },
    S_HISTORY: {
        "note": "[수동 입력] 수시 현행화 내역",
        "headers": ["변경일", "시트", "대상", "변경 내용", "요청처", "작업자"],
        "widths": [12, 14, 22, 44, 14, 10],
        "manual_cols": 6,
    },
}

MANUAL_SHEETS = [S_TUNNEL, S_RANGE, S_HISTORY]


def _cell(ws: Worksheet, row: int, col: int, value: Any) -> None:
    c = ws.cell(row, col, value)
    c.font = Font(name=FONT, size=10)
    c.border = BORDER
    c.alignment = Alignment(vertical="center", wrap_text=True)


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
    for i, w in enumerate(spec["widths"], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = ws.cell(FIRST, 1)
    return ws


def _rows(ws: Worksheet, rows: list[list[Any]]) -> int:
    for r, row in enumerate(rows, FIRST):
        for c, v in enumerate(row, 1):
            _cell(ws, r, c, v)
    last = FIRST + len(rows) - 1
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
        (f"{S_MAP}: 서버별 적용 ACG (자동 수집)", False),
        (f"{S_ACG}: ACG별 Inbound/Outbound 규칙 (자동 수집)", False),
        (f"{S_NACL}: Subnet 단위 Network ACL 규칙 (자동 수집)", False),
        (f"{S_SUBNET}: VPC/Subnet 대역, 게이트웨이, NACL (자동 수집)", False),
        (f"{S_TUNNEL}: 연결 대상별 IPsec 터널 (수동 입력)", False),
        (f"{S_RANGE}: 터널별 상대 측·클라우드 측 연동 대역 (수동 입력)", False),
        (f"{S_HISTORY}: 수시 현행화 내역 (수동 입력)", False),
        ("", False),
        ("■ 작성 기준", True),
        ("셀 병합 없이 작성 (필터·정렬 유지 목적)", False),
        ("ACG명, 서버명, Subnet명은 NCP 콘솔 명칭과 동일 (구성도 명칭과 일치)", False),
        ("출발지가 ACG인 규칙은 '출발지 구분'을 ACG로 표기", False),
        ("ACG는 VPC 단위 자원이므로 VPC 열과 함께 확인", False),
        ("연한 초록색 칸은 수동 입력 칸", False),
    ]
    for i, (text, bold) in enumerate(lines, 1):
        c = ws.cell(i, 1, text)
        c.font = Font(name=FONT, bold=bold, size=13 if i == 1 else 10)
    ws.column_dimensions["A"].width = 100


def write(
    report: Report,
    out: str | Path,
    doc: Document | None = None,
    previous: str | Path | None = None,
) -> Path:
    doc = doc or Document()
    manual = read_manual(previous)
    wb = Workbook()
    _guide(wb, doc, report.collected_at)

    ws = _sheet(wb, S_MAP)
    map_last = max(_rows(ws, report.mapping), FIRST)

    ws = _sheet(wb, S_ACG)
    last = _rows(ws, report.acg_rules)
    m = f"'{S_MAP}'!"
    for r in range(FIRST, last + 1):
        _cell(
            ws,
            r,
            9,
            f"=COUNTIFS({m}$A${FIRST}:$A${map_last},B{r},"
            f"{m}$E${FIRST}:$E${map_last},A{r})",
        )
        ws.cell(r, 9).alignment = Alignment(horizontal="center", vertical="center")

    _rows(_sheet(wb, S_NACL), report.nacl_rules)
    _rows(_sheet(wb, S_SUBNET), report.subnets)

    # 수동 입력 시트
    for name in MANUAL_SHEETS:
        ws = _sheet(wb, name)
        ncols = SHEETS[name]["manual_cols"]
        rows = manual[name]
        total = max(len(rows) + 20, MANUAL_ROWS)
        for r in range(FIRST, FIRST + total):
            values = rows[r - FIRST] if r - FIRST < len(rows) else [None] * ncols
            for c in range(1, ncols + 1):
                _cell(ws, r, c, values[c - 1] if c - 1 < len(values) else None)
                ws.cell(r, c).fill = MANUAL_FILL
        last = FIRST + total - 1
        ws.auto_filter.ref = (
            f"A{HEADER_ROW}:{get_column_letter(len(SHEETS[name]['headers']))}{last}"
        )
        if name == S_TUNNEL:
            for r in range(FIRST, last + 1):
                _cell(
                    ws,
                    r,
                    7,
                    f'=IF(C{r}="","",COUNTIF(\'{S_RANGE}\'!$A${FIRST}:$A${REF_END},'
                    f"C{r}))",
                )
                ws.cell(r, 7).alignment = Alignment(
                    horizontal="center", vertical="center"
                )
        if name == S_RANGE:
            dv = DataValidation(
                type="list", formula1='"상대 측,클라우드 측"', allow_blank=True
            )
            ws.add_data_validation(dv)
            dv.add(f"B{FIRST}:B{REF_END}")

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return out

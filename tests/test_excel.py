from __future__ import annotations

from openpyxl import load_workbook

from ncp_nw_report import excel, transform


def test_write_creates_all_sheets(tmp_path, demo_raw):
    report = transform.build(demo_raw)
    out = excel.write(report, tmp_path / "r.xlsx")
    wb = load_workbook(out)
    assert wb.sheetnames == [
        "작성기준",
        excel.S_MAP,
        excel.S_ACG,
        excel.S_NACL,
        excel.S_SUBNET,
        excel.S_TUNNEL,
        excel.S_RANGE,
        excel.S_HISTORY,
    ]
    acg = wb[excel.S_ACG]
    assert acg.cell(excel.HEADER_ROW, 9).value == "적용 서버 수"
    assert str(acg.cell(excel.FIRST, 9).value).startswith("=COUNTIFS(")
    assert not wb[excel.S_MAP].merged_cells.ranges


def test_manual_sheets_are_carried_over(tmp_path, demo_raw):
    report = transform.build(demo_raw)
    first = excel.write(report, tmp_path / "v1.xlsx")
    wb = load_workbook(first)
    wb[excel.S_TUNNEL]["A5"] = "example-peer"
    wb[excel.S_TUNNEL]["C5"] = "oo-tunnel-01"
    wb[excel.S_RANGE]["A5"] = "oo-tunnel-01"
    wb[excel.S_RANGE]["B5"] = "상대 측"
    wb[excel.S_RANGE]["C5"] = "192.168.10.0/24"
    wb[excel.S_HISTORY]["D5"] = "ACG 추가"
    wb.save(first)

    second = excel.write(report, tmp_path / "v2.xlsx", previous=first)
    wb2 = load_workbook(second)
    assert wb2[excel.S_TUNNEL]["C5"].value == "oo-tunnel-01"
    assert str(wb2[excel.S_TUNNEL]["G5"].value).startswith("=IF(")
    assert wb2[excel.S_RANGE]["C5"].value == "192.168.10.0/24"
    assert wb2[excel.S_HISTORY]["D5"].value == "ACG 추가"

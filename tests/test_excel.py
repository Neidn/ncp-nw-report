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
        excel.S_IPSEC,
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
    ws = wb[excel.S_IPSEC]
    ws["A5"] = "example-peer"
    ws["B5"] = "198.51.100.1\n198.51.100.2"
    ws["C5"] = "192.168.10.0/24"
    ws["D5"] = "1호기 - 203.0.113.1\n2호기 - 203.0.113.2"
    ws["E5"] = "10.1.0.0/16\n10.2.0.0/16"
    wb[excel.S_HISTORY]["D5"] = "ACG 추가"
    wb.save(first)

    second = excel.write(report, tmp_path / "v2.xlsx", previous=first)
    wb2 = load_workbook(second)
    ipsec = wb2[excel.S_IPSEC]
    assert ipsec["C5"].value == "192.168.10.0/24"
    assert ipsec["E5"].value == "10.1.0.0/16\n10.2.0.0/16"
    assert ipsec["B3"].value == "상대 측"
    assert ipsec["D3"].value == "NCP 측"
    assert wb2[excel.S_HISTORY]["D5"].value == "ACG 추가"

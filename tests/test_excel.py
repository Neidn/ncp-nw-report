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
        excel.S_SERVER_ORG,
        excel.S_IPSEC,
        excel.S_HISTORY,
    ]
    acg = wb[excel.S_ACG]
    assert acg.cell(excel.HEADER_ROW, 9).value == "적용 서버 수"
    assert acg.cell(excel.HEADER_ROW, 10).value == "적용 기관"
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


def test_server_org_sheet_merge_and_lookup(tmp_path, demo_raw):
    report = transform.build(demo_raw)
    first = excel.write(report, tmp_path / "v1.xlsx")
    wb = load_workbook(first)
    ws = wb[excel.S_SERVER_ORG]
    names = [ws.cell(r, 1).value for r in range(5, 5 + len(report.servers))]
    assert "example-db-01" in names
    for r in range(5, 5 + len(report.servers)):
        if ws.cell(r, 1).value == "example-db-01":
            ws.cell(r, 3).value = "기관A, 기관B"
        if ws.cell(r, 1).value == "example-db-02":
            ws.cell(r, 3).value = "기관C"
        if ws.cell(r, 1).value == "example-db-03":
            ws.cell(r, 3).value = "전체"
    ws.cell(5 + len(report.servers), 1).value = "deleted-server"
    ws.cell(5 + len(report.servers), 3).value = "기관D"
    wb.save(first)

    second = excel.write(report, tmp_path / "v2.xlsx", previous=first)
    wb2 = load_workbook(second)
    rows = {
        r[0]: r
        for r in wb2[excel.S_SERVER_ORG].iter_rows(min_row=5, values_only=True)
        if r[0]
    }
    assert rows["example-db-01"][2] == "기관A, 기관B"
    assert rows["deleted-server"][4] == "미조회"
    assert str(wb2[excel.S_MAP]["D5"].value).startswith("=IFERROR(")
    acg = wb2[excel.S_ACG]
    by_acg = {acg.cell(r, 1).value: acg.cell(r, 10).value for r in range(5, 14)}
    # example-db-acg 는 db-01/02/03 에 적용 -> db-03 이 '전체'
    assert by_acg["example-db-acg"] == "전체"


def test_acg_orgs_union():
    mapping = [
        ["vpc", "sub", "s1", None, "ip", "acg", ""],
        ["vpc", "sub", "s2", None, "ip", "acg", ""],
    ]
    orgs = excel.acg_orgs(mapping, [["s1", "vpc", "B, A"], ["s2", "vpc", "A"]])
    assert orgs[("vpc", "acg")] == "A, B"


def test_new_server_marked():
    rows = excel.merge_server_orgs([["s1", "v"], ["s2", "v"]], [["s1", "v", "A", None]])
    assert rows == [["s1", "v", "A", None, ""], ["s2", "v", None, None, "신규"]]

from __future__ import annotations

from ncp_nw_report import transform


def test_mapping_is_one_row_per_server_and_acg(demo_raw):
    report = transform.build(demo_raw)
    db01 = [r for r in report.mapping if r[2] == "example-db-01"]
    assert sorted(r[5] for r in db01) == ["example-db-acg", "example-prd-mgmt-acg"]
    assert db01[0][0] == "example-prd-vpc"
    assert db01[0][1] == "example-prd-db-sub"
    assert db01[0][4] == "10.1.30.9"
    assert ["example-db-01", "example-prd-vpc"] in report.servers


def test_acg_rule_fields(demo_raw):
    report = transform.build(demo_raw)
    rows = {(r[0], r[5], r[4]): r for r in report.acg_rules}
    same_group = rows[("example-sec-acg", "example-sec-acg", "443")]
    assert same_group[6] == "ACG"
    out = rows[("example-db-acg", "0.0.0.0/0", "ALL")]
    assert out[2] == "Outbound"
    icmp = [r for r in report.acg_rules if r[3] == "ICMP"][0]
    assert icmp[4] == "-"
    assert rows[("example-prd-mgmt-acg", "10.200.1.8/32", "22")][6] == "IP"


def test_nacl_rules_sorted_and_named(demo_raw):
    report = transform.build(demo_raw)
    db = [r for r in report.nacl_rules if r[0] == "example-db-nacl"]
    assert [r[4] for r in db] == [10, 20, 30, 199]
    assert db[0][2] == "example-prd-db-sub"
    assert db[2][7] == "Deny-Allow Group: blocked-ip-group"
    assert db[2][8] == "차단"


def test_subnet_gateway(demo_raw):
    report = transform.build(demo_raw)
    sub = {r[2]: r for r in report.subnets}
    assert sub["example-prd-db-sub"][4] == "10.1.30.1"
    assert sub["example-prd-db-sub"][7] == "example-db-nacl"
    assert transform.gateway_of("bad") == ""


def test_subnet_labels_in_korean(demo_raw):
    report = transform.build(demo_raw)
    sub = {r[2]: r for r in report.subnets}
    assert sub["example-prd-db-sub"][5] == "사설"
    assert sub["example-prd-db-sub"][6] == "일반"
    assert sub["example-sec-lb-sub"][5] == "공인"
    assert sub["example-sec-lb-sub"][6] == "LB용"
    assert transform._label(transform.SUBNET_USAGE, "NATGW") == "NAT용"
    assert transform._label(transform.SUBNET_USAGE, "NEW") == "NEW"


def test_load_balancer_rows_follow_listener_rules(demo_raw):
    report = transform.build(demo_raw)
    web = [r for r in report.load_balancers if r[0] == "example-web-alb"]
    assert web[0][1] == "ALB (Application)"
    assert web[0][2] == "공인"
    by_rule = {(r[7], r[8]): r for r in web}
    admin = by_rule[("HTTPS:443", 10)]
    assert admin[9] == "Path: /admin/*"
    assert admin[10] == "전달"
    assert admin[11] == "example-admin-tg"
    assert admin[12] == "HTTPS:8443"
    assert admin[13] == "example-bastion-01 (10.200.1.8)"
    default = by_rule[("HTTPS:443", 10000)]
    assert default[9] == "기본"
    assert default[11] == "example-web-tg"
    assert (
        default[13] == "example-access-01 (10.200.1.6)\nexample-bastion-01 (10.200.1.8)"
    )
    redirect = by_rule[("HTTP:80", 10000)]
    assert redirect[10] == "리다이렉트 → HTTPS:443"
    assert redirect[11] == ""
    nlb = [r for r in report.load_balancers if r[0] == "example-k8s-nlb"][0]
    assert nlb[1] == "NLB (Network)"
    assert nlb[11] == "example-k8s-ingress-tg"


def test_load_balancer_without_rules_falls_back(demo_raw):
    demo_raw["lb_rules"] = []
    report = transform.build(demo_raw)
    web = [r for r in report.load_balancers if r[0] == "example-web-alb"]
    assert {r[11] for r in web} == {"example-web-tg", "example-admin-tg"}
    assert web[0][7] == "HTTPS:443\nHTTP:80"
    assert web[0][8] == ""


def test_load_balancer_flat_codes_and_no_target_group():
    raw = {
        "vpcs": [],
        "subnets": [],
        "servers": [],
        "nics": [],
        "acgs": [],
        "acg_rules": [],
        "nacls": [],
        "nacl_rules": [],
        "load_balancers": [
            {
                "loadBalancerInstanceNo": "1",
                "loadBalancerName": "lb",
                "loadBalancerTypeCode": "NETWORK_PROXY",
                "loadBalancerNetworkTypeCode": "PRIVATE",
            }
        ],
        "target_groups": [],
    }
    row = transform.build(raw).load_balancers[0]
    assert row[1] == "NPLB (Network Proxy)"
    assert row[2] == "사설"
    assert row[7:] == ["", "", "", "", "", "", ""]

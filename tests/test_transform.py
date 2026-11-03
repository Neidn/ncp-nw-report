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


def test_load_balancer_rows(demo_raw):
    report = transform.build(demo_raw)
    lbs = {r[0]: r for r in report.load_balancers}
    web = lbs["example-web-alb"]
    assert web[1] == "ALB (Application)"
    assert web[2] == "공인"
    assert web[4] == "example-sec-lb-sub"
    assert web[7] == "HTTPS:443\nHTTP:80"
    assert web[9] == "HTTPS:443"
    assert web[10] == "example-access-01\nexample-bastion-01"
    assert lbs["example-k8s-nlb"][7] == "TCP:443"
    assert lbs["example-k8s-nlb"][1] == "NLB (Network)"


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
    assert row[7:] == ["", "", "", ""]

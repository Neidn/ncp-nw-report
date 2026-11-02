"""수집한 원본 데이터를 엑셀 시트 행으로 변환 (네트워크 호출 없음)."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from typing import Any

DIRECTION = {"INBND": "Inbound", "OTBND": "Outbound"}
ACTION = {"ALLOW": "허용", "DROP": "차단"}


@dataclass
class Report:
    collected_at: str = ""
    mapping: list[list[Any]] = field(default_factory=list)
    acg_rules: list[list[Any]] = field(default_factory=list)
    nacl_rules: list[list[Any]] = field(default_factory=list)
    subnets: list[list[Any]] = field(default_factory=list)
    servers: list[list[Any]] = field(default_factory=list)  # [서버명, VPC]


def _code(obj: Any) -> str:
    if isinstance(obj, dict):
        return str(obj.get("code", ""))
    return str(obj or "")


def gateway_of(cidr: str) -> str:
    """NCP Subnet 게이트웨이 = 대역의 첫 번째 IP (x.x.x.1)."""
    try:
        net = ipaddress.ip_network(cidr, strict=False)
        return str(net.network_address + 1)
    except ValueError:
        return ""


def _port(protocol: str, port_range: str | None) -> str:
    if protocol == "ICMP":
        return "-"
    return port_range or "ALL"


def _source_kind(value: str, is_group: bool) -> str:
    if is_group:
        return "ACG"
    if value.endswith("/32"):
        return "IP"
    return "대역"


def build(raw: dict[str, Any]) -> Report:
    report = Report(collected_at=raw.get("collected_at", ""))
    vpc_name = {v["vpcNo"]: v.get("vpcName", v["vpcNo"]) for v in raw["vpcs"]}
    vpc_cidr = {v["vpcNo"]: v.get("ipv4CidrBlock", "") for v in raw["vpcs"]}
    subnet = {s["subnetNo"]: s for s in raw["subnets"]}
    acg = {a["accessControlGroupNo"]: a for a in raw["acgs"]}
    nacl = {n["networkAclNo"]: n for n in raw["nacls"]}
    dag = {
        d["networkAclDenyAllowGroupNo"]: d.get("networkAclDenyAllowGroupName", "")
        for d in raw.get("deny_allow_groups", [])
    }
    nics_by_instance: dict[str, list[dict[str, Any]]] = {}
    for nic in raw["nics"]:
        if nic.get("instanceNo"):
            nics_by_instance.setdefault(str(nic["instanceNo"]), []).append(nic)

    # 서버-ACG 매핑: 1행 = 서버 1대 × ACG 1개 (NIC가 여러 개면 IP를 합쳐 표기)
    for srv in raw["servers"]:
        sno = str(srv["serverInstanceNo"])
        sname = srv.get("serverName", sno)
        vname = vpc_name.get(srv.get("vpcNo", ""), srv.get("vpcNo", ""))
        report.servers.append([sname, vname])
        per_acg: dict[str, dict[str, list[str]]] = {}
        for nic in nics_by_instance.get(sno, []):
            sub_name = subnet.get(nic.get("subnetNo", ""), {}).get(
                "subnetName", nic.get("subnetNo", "")
            )
            for acg_no in nic.get("accessControlGroupNoList", []) or []:
                entry = per_acg.setdefault(acg_no, {"ips": [], "subnets": []})
                entry["ips"].append(nic.get("ip", ""))
                if sub_name not in entry["subnets"]:
                    entry["subnets"].append(sub_name)
        for acg_no, entry in per_acg.items():
            a = acg.get(acg_no, {})
            report.mapping.append(
                [
                    vname,
                    "\n".join(entry["subnets"]),
                    sname,
                    None,  # 사용 기관 (서버-기관 시트에서 조회)
                    "\n".join(entry["ips"]),
                    a.get("accessControlGroupName", acg_no),
                    a.get("accessControlGroupDescription", ""),
                ]
            )

    # ACG 규칙: 1행 = 규칙 1개
    for rule in raw["acg_rules"]:
        a = acg.get(rule["accessControlGroupNo"], {})
        proto = _code(rule.get("protocolType"))
        src_group = rule.get("accessControlGroupSequence") or ""
        if src_group:
            src = acg.get(src_group, {}).get("accessControlGroupName", src_group)
        else:
            src = rule.get("ipBlock", "")
        report.acg_rules.append(
            [
                a.get("accessControlGroupName", rule["accessControlGroupNo"]),
                vpc_name.get(a.get("vpcNo", ""), a.get("vpcNo", "")),
                DIRECTION.get(_code(rule.get("accessControlGroupRuleType")), ""),
                proto,
                _port(proto, rule.get("portRange")),
                src,
                _source_kind(src, bool(src_group)),
                rule.get("accessControlGroupRuleDescription", ""),
            ]
        )

    # NACL 규칙: 우선순위 순
    applied: dict[str, list[str]] = {}
    for s in raw["subnets"]:
        if s.get("networkAclNo"):
            applied.setdefault(s["networkAclNo"], []).append(s.get("subnetName", ""))
    rules = sorted(
        raw["nacl_rules"],
        key=lambda r: (
            r["networkAclNo"],
            _code(r.get("networkAclRuleType")),
            int(r.get("priority", 0)),
        ),
    )
    for rule in rules:
        n = nacl.get(rule["networkAclNo"], {})
        proto = _code(rule.get("protocolType"))
        action = _code(rule.get("ruleAction"))
        if rule.get("denyAllowGroupNo"):
            no = rule["denyAllowGroupNo"]
            target = f"Deny-Allow Group: {dag.get(no) or no}"
        else:
            target = rule.get("ipBlock", "")
        report.nacl_rules.append(
            [
                n.get("networkAclName", rule["networkAclNo"]),
                vpc_name.get(n.get("vpcNo", ""), n.get("vpcNo", "")),
                "\n".join(applied.get(rule["networkAclNo"], [])),
                DIRECTION.get(_code(rule.get("networkAclRuleType")), ""),
                int(rule.get("priority", 0)),
                proto,
                _port(proto, rule.get("portRange")),
                target,
                ACTION.get(action, action),
                rule.get("networkAclRuleDescription", ""),
            ]
        )

    # Subnet 목록
    for s in raw["subnets"]:
        cidr = s.get("subnet", "")
        report.subnets.append(
            [
                vpc_name.get(s.get("vpcNo", ""), s.get("vpcNo", "")),
                vpc_cidr.get(s.get("vpcNo", ""), ""),
                s.get("subnetName", ""),
                cidr,
                gateway_of(cidr),
                _code(s.get("subnetType")),
                _code(s.get("usageType")),
                nacl.get(s.get("networkAclNo", ""), {}).get("networkAclName", ""),
            ]
        )

    report.mapping.sort(key=lambda r: (r[0], r[2], r[5]))
    report.servers.sort(key=lambda r: (r[1], r[0]))
    report.acg_rules.sort(key=lambda r: (r[1], r[0], r[2]))
    report.subnets.sort(key=lambda r: (r[0], r[2]))
    return report

"""수집한 원본 데이터를 엑셀 시트 행으로 변환 (네트워크 호출 없음)."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from typing import Any

DIRECTION = {"INBND": "Inbound", "OTBND": "Outbound"}
SUBNET_TYPE = {"PUBLIC": "공인", "PRIVATE": "사설"}
SUBNET_USAGE = {"GEN": "일반", "LOADB": "LB용", "NATGW": "NAT용", "BM": "베어메탈용"}
LB_TYPE = {
    "APPLICATION": "ALB (Application)",
    "NETWORK": "NLB (Network)",
    "NETWORK_PROXY": "NPLB (Network Proxy)",
}
LB_NETWORK = {"PUBLIC": "공인", "PRIVATE": "사설"}
ACTION = {"ALLOW": "허용", "DROP": "차단"}


@dataclass
class Report:
    collected_at: str = ""
    mapping: list[list[Any]] = field(default_factory=list)
    acg_rules: list[list[Any]] = field(default_factory=list)
    nacl_rules: list[list[Any]] = field(default_factory=list)
    subnets: list[list[Any]] = field(default_factory=list)
    servers: list[list[Any]] = field(default_factory=list)  # [서버명, VPC]
    load_balancers: list[list[Any]] = field(default_factory=list)


def _code(obj: Any) -> str:
    if isinstance(obj, dict):
        return str(obj.get("code", ""))
    return str(obj or "")


def _label(table: dict[str, str], code: str) -> str:
    """코드값을 한글 표기로. 모르는 코드는 그대로 둔다."""
    return table.get(code, code)


def _pick(obj: dict[str, Any], *keys: str) -> Any:
    """응답 필드명이 버전·문서마다 달라질 수 있어 후보 키 중 첫 값을 쓴다."""
    for k in keys:
        v = obj.get(k)
        if v not in (None, "", []):
            return v
    return None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


RULE_CONDITION = {"DEFAULT": "기본", "HOST_HEADER": "Host", "PATH_PATTERN": "Path"}
RULE_ACTION = {
    "FORWARD": "전달",
    "REDIRECTION": "리다이렉트",
    "FIXED_RESPONSE": "고정 응답",
}


def _find_all(obj: Any, key: str) -> list[Any]:
    """중첩 dict/list 안에서 key 값을 모두 찾는다 (응답 구조 차이에 대응)."""
    found: list[Any] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                found.append(v)
            found.extend(_find_all(v, key))
    elif isinstance(obj, list):
        for v in obj:
            found.extend(_find_all(v, key))
    return found


def _condition_text(rule: dict[str, Any]) -> str:
    parts: list[str] = []
    for cond in _as_list(rule.get("loadBalancerRuleConditionList")):
        code = _code(cond.get("ruleConditionType"))
        values: list[str] = []
        for key in ("hostHeaderValueList", "pathPatternValueList"):
            for v in _find_all(cond, key):
                values.extend(str(x) for x in _as_list(v))
        label = RULE_CONDITION.get(code, code)
        parts.append(f"{label}: {', '.join(values)}" if values else label)
    return "\n".join(parts) or "기본"


def _action_text(rule: dict[str, Any]) -> str:
    texts: list[str] = []
    for act in _as_list(rule.get("loadBalancerRuleActionList")):
        code = _code(act.get("ruleActionType"))
        label = RULE_ACTION.get(code, code)
        if code == "REDIRECTION":
            redir = act.get("redirectionAction") or {}
            proto = _code(redir.get("protocolType"))
            port = redir.get("port", "")
            if proto or port:
                label += f" → {proto}:{port}"
        if label:
            texts.append(label)
    return "\n".join(texts) or "전달"


def build_load_balancers(
    raw: dict[str, Any],
    report: Report,
    vpc_name: dict[str, str],
    subnet: dict[str, dict[str, Any]],
) -> None:
    """LB 목록: 1행 = LB × 리스너 × 규칙 × 대상 그룹.

    규칙 정보가 없는 LB는 LB × 대상 그룹 단위로 표기하고 리스너는 합쳐서 적는다.
    """
    server_name = {
        str(s["serverInstanceNo"]): s.get("serverName", "") for s in raw["servers"]
    }
    tg_by_no = {str(t["targetGroupNo"]): t for t in raw.get("target_groups", [])}
    targets_by_tg: dict[str, list[str]] = {}
    for t in raw.get("targets", []):
        name = t.get("targetName") or server_name.get(str(t.get("targetNo")), "")
        ip = t.get("targetIp", "")
        label = f"{name} ({ip})" if name and ip else (name or ip or str(t["targetNo"]))
        targets_by_tg.setdefault(str(t["targetGroupNo"]), []).append(label)

    def tg_cols(tg_no: str) -> list[Any]:
        tg = tg_by_no.get(tg_no, {})
        if not tg and not tg_no:
            return ["", "", ""]
        proto = _code(
            _pick(tg, "targetGroupProtocolType", "targetGroupProtocolTypeCode")
        )
        port = tg.get("targetGroupPort", "")
        servers = targets_by_tg.get(tg_no) or [
            server_name.get(str(n), str(n)) for n in _as_list(_pick(tg, "targetNoList"))
        ]
        return [
            tg.get("targetGroupName", tg_no),
            f"{proto}:{port}" if proto or port else "",
            "\n".join(servers),
        ]

    tgs_by_lb: dict[str, list[str]] = {}
    for tg in raw.get("target_groups", []):
        for lb_no in _as_list(
            _pick(tg, "loadBalancerInstanceNoList", "loadBalancerInstanceNo")
        ):
            tgs_by_lb.setdefault(str(lb_no), []).append(str(tg["targetGroupNo"]))

    listeners_by_lb: dict[str, list[dict[str, Any]]] = {}
    for ln in raw.get("listeners", []):
        listeners_by_lb.setdefault(
            str(ln.get("loadBalancerInstanceNo", "")), []
        ).append(ln)
    rules_by_listener: dict[str, list[dict[str, Any]]] = {}
    for rule in raw.get("lb_rules", []):
        rules_by_listener.setdefault(
            str(rule.get("loadBalancerListenerNo", "")), []
        ).append(rule)

    def listener_text(ln: dict[str, Any]) -> str:
        proto = _code(_pick(ln, "protocolType", "protocolTypeCode"))
        return f"{proto}:{ln.get('port', '')}"

    for lb in raw.get("load_balancers", []):
        lb_no = str(lb["loadBalancerInstanceNo"])
        sub_nos = _as_list(_pick(lb, "subnetNoList")) or [
            s.get("subnetNo") for s in _as_list(_pick(lb, "loadBalancerSubnetList"))
        ]
        base = [
            lb.get("loadBalancerName", lb_no),
            _label(
                LB_TYPE, _code(_pick(lb, "loadBalancerType", "loadBalancerTypeCode"))
            ),
            _label(
                LB_NETWORK,
                _code(
                    _pick(lb, "loadBalancerNetworkType", "loadBalancerNetworkTypeCode")
                ),
            ),
            vpc_name.get(lb.get("vpcNo", ""), lb.get("vpcNo", "")),
            "\n".join(
                subnet.get(str(n), {}).get("subnetName", str(n)) for n in sub_nos if n
            ),
            "\n".join(str(ip) for ip in _as_list(_pick(lb, "loadBalancerIpList"))),
            lb.get("loadBalancerDomain", ""),
        ]
        listeners = listeners_by_lb.get(lb_no, [])
        has_rules = any(
            rules_by_listener.get(str(ln.get("loadBalancerListenerNo")))
            for ln in listeners
        )
        if not has_rules:
            joined = "\n".join(listener_text(ln) for ln in listeners)
            for tg_no in tgs_by_lb.get(lb_no) or [""]:
                report.load_balancers.append(
                    base + [joined, "", "", ""] + tg_cols(tg_no)
                )
            continue
        for ln in listeners:
            rules = sorted(
                rules_by_listener.get(str(ln.get("loadBalancerListenerNo")), []),
                key=lambda r: int(r.get("priority", 0) or 0),
            )
            for rule in rules or [{}]:
                tg_nos = [str(n) for n in _find_all(rule, "targetGroupNo")] or [""]
                for tg_no in dict.fromkeys(tg_nos):
                    report.load_balancers.append(
                        base
                        + [
                            listener_text(ln),
                            rule.get("priority", ""),
                            _condition_text(rule) if rule else "",
                            _action_text(rule) if rule else "",
                        ]
                        + tg_cols(tg_no)
                    )
    report.load_balancers.sort(key=lambda r: (r[3], r[0], r[7], str(r[8])))


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
                _label(SUBNET_TYPE, _code(s.get("subnetType"))),
                _label(SUBNET_USAGE, _code(s.get("usageType"))),
                nacl.get(s.get("networkAclNo", ""), {}).get("networkAclName", ""),
            ]
        )

    build_load_balancers(raw, report, vpc_name, subnet)

    report.mapping.sort(key=lambda r: (r[0], r[2], r[5]))
    report.servers.sort(key=lambda r: (r[1], r[0]))
    report.acg_rules.sort(key=lambda r: (r[1], r[0], r[2]))
    report.subnets.sort(key=lambda r: (r[0], r[2]))
    return report

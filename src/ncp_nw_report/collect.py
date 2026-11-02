"""NCP API에서 원본 데이터 수집 (조회 API만 사용).

ncp-api-python(NcpClient, v0.12.0 이상)을 사용한다.
"""

from __future__ import annotations

import inspect
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from ncp_api import NcpClient

ListFn = Callable[..., dict[str, Any]]

PAGE_SIZE = 1000
MAX_PAGES = 100


class Collector:
    """계정 1개 분량의 원본 데이터를 수집한다.

    client 는 NcpClient 또는 같은 속성(vpc, server)을 가진 객체.
    """

    def __init__(self, client: Any, region_code: str | None = None) -> None:
        self.client = client
        self.region_code = region_code

    # --- 공통 ---

    def _call(self, fn: ListFn, **kwargs: Any) -> dict[str, Any]:
        accepted = inspect.signature(fn).parameters
        kw = {k: v for k, v in kwargs.items() if k in accepted and v is not None}
        return fn(**kw)

    def _list(self, fn: ListFn, list_key: str, id_key: str, **kwargs: Any) -> list:
        """목록 API 전체 조회.

        먼저 페이지 파라미터 없이 호출하고, totalRows 보다 적게 오면 페이지를
        넘기며 추가 조회한다. 페이지 번호 기준(0/1 시작)과 무관하게 동작하도록
        id 기준으로 중복을 제거한다.
        """
        first = self._call(fn, region_code=self.region_code, **kwargs)
        items: dict[str, dict[str, Any]] = {
            str(i[id_key]): i for i in first.get(list_key, [])
        }
        total = int(first.get("totalRows", len(items)) or 0)
        accepted = inspect.signature(fn).parameters
        if len(items) >= total or "page_no" not in accepted:
            return list(items.values())

        stale = 0
        for page_no in range(0, MAX_PAGES):
            page = self._call(
                fn,
                region_code=self.region_code,
                page_no=page_no,
                page_size=PAGE_SIZE,
                **kwargs,
            )
            before = len(items)
            for i in page.get(list_key, []):
                items[str(i[id_key])] = i
            if len(items) >= total:
                break
            stale = stale + 1 if len(items) == before else 0
            if stale >= 2:
                break
        return list(items.values())

    # --- 수집 ---

    def collect(self) -> dict[str, Any]:
        vpc = self.client.vpc
        server = self.client.server

        vpcs = self._list(vpc.get_vpc_list, "vpcList", "vpcNo")
        subnets = self._list(vpc.get_subnet_list, "subnetList", "subnetNo")
        servers = self._list(
            server.get_server_instance_list, "serverInstanceList", "serverInstanceNo"
        )
        nics = self._list(
            server.get_network_interface_list,
            "networkInterfaceList",
            "networkInterfaceNo",
        )
        acgs = self._list(
            server.get_access_control_group_list,
            "accessControlGroupList",
            "accessControlGroupNo",
        )
        acg_rules: list[dict[str, Any]] = []
        for acg in acgs:
            res = self._call(
                server.get_access_control_group_rule_list,
                access_control_group_no=acg["accessControlGroupNo"],
                region_code=self.region_code,
            )
            for rule in res.get("accessControlGroupRuleList", []):
                rule.setdefault("accessControlGroupNo", acg["accessControlGroupNo"])
                acg_rules.append(rule)

        nacls = self._list(vpc.get_network_acl_list, "networkAclList", "networkAclNo")
        nacl_rules: list[dict[str, Any]] = []
        for nacl in nacls:
            res = self._call(
                vpc.get_network_acl_rule_list,
                network_acl_no=nacl["networkAclNo"],
                region_code=self.region_code,
            )
            for rule in res.get("networkAclRuleList", []):
                rule.setdefault("networkAclNo", nacl["networkAclNo"])
                nacl_rules.append(rule)

        # Deny-Allow Group 이름 (NACL 규칙에서 참조). 실패 시 번호로 표기.
        try:
            dag = self._list(
                vpc.get_network_acl_deny_allow_group_list,
                "networkAclDenyAllowGroupList",
                "networkAclDenyAllowGroupNo",
            )
        except Exception:
            dag = []

        # Load Balancer / Target Group. 권한이 없으면 경고 후 빈 목록.
        lbs: list[dict[str, Any]] = []
        tgs: list[dict[str, Any]] = []
        lb_api = getattr(self.client, "load_balancer", None)
        if lb_api is not None:
            try:
                lbs = self._list(
                    lb_api.get_load_balancer_instance_list,
                    "loadBalancerInstanceList",
                    "loadBalancerInstanceNo",
                )
                tgs = self._list(
                    lb_api.get_target_group_list, "targetGroupList", "targetGroupNo"
                )
            except Exception as exc:  # noqa: BLE001
                print(
                    f"[경고] Load Balancer 조회 실패, LB 목록 생략: {exc}",
                    file=sys.stderr,
                )

        return {
            "vpcs": vpcs,
            "subnets": subnets,
            "servers": servers,
            "nics": nics,
            "acgs": acgs,
            "acg_rules": acg_rules,
            "nacls": nacls,
            "nacl_rules": nacl_rules,
            "deny_allow_groups": dag,
            "load_balancers": lbs,
            "target_groups": tgs,
        }


def collect_all(
    access_key: str, secret_key: str, env: str | None = None
) -> dict[str, Any]:
    """키 1개(계정 1개) 기준으로 전체 수집."""
    with NcpClient(access_key=access_key, secret_key=secret_key, env=env) as client:
        data = Collector(client).collect()
    data["collected_at"] = (
        datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    )
    return data

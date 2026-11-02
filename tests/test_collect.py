from __future__ import annotations

from typing import Any

from ncp_nw_report.collect import Collector


class FakeServer:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def get_server_instance_list(
        self,
        *,
        region_code: str | None = None,
        page_no: int | None = None,
        page_size: int | None = None,
    ) -> dict[str, Any]:
        # 첫 호출은 2건만 반환, 페이지 호출 시 전체 반환 (1부터 시작 가정)
        self.calls.append({"page_no": page_no})
        items = [{"serverInstanceNo": str(i), "serverName": f"s{i}"} for i in range(3)]
        if page_no is None:
            return {"totalRows": 3, "serverInstanceList": items[:2]}
        if page_no == 0:
            return {"totalRows": 3, "serverInstanceList": []}
        return {"totalRows": 3, "serverInstanceList": items}

    def get_network_interface_list(self, **_: Any) -> dict[str, Any]:
        return {"totalRows": 0, "networkInterfaceList": []}

    def get_access_control_group_list(self, **_: Any) -> dict[str, Any]:
        return {
            "totalRows": 1,
            "accessControlGroupList": [{"accessControlGroupNo": "a1"}],
        }

    def get_access_control_group_rule_list(
        self, *, access_control_group_no: str, region_code: str | None = None
    ) -> dict[str, Any]:
        return {"accessControlGroupRuleList": [{"ipBlock": "10.0.0.0/8"}]}


class FakeVpc:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def get_vpc_list(self, *, region_code: str | None = None) -> dict[str, Any]:
        return {"totalRows": 1, "vpcList": [{"vpcNo": "v1"}]}

    def get_subnet_list(self, **_: Any) -> dict[str, Any]:
        return {"totalRows": 0, "subnetList": []}

    def get_network_acl_list(
        self,
        *,
        region_code: str | None = None,
        page_no: int | None = None,
        page_size: int | None = None,
    ) -> dict[str, Any]:
        self.calls.append(("acl", region_code))
        return {"totalRows": 1, "networkAclList": [{"networkAclNo": "n1"}]}

    def get_network_acl_rule_list(
        self, *, network_acl_no: str, region_code: str | None = None
    ) -> dict[str, Any]:
        self.calls.append(("rule", network_acl_no))
        return {"networkAclRuleList": [{"priority": 10}]}

    def get_network_acl_deny_allow_group_list(self, **_: Any) -> dict[str, Any]:
        raise RuntimeError("permission denied")


class FakeClient:
    def __init__(self) -> None:
        self.server = FakeServer()
        self.vpc = FakeVpc()


def test_collect_paginates_and_dedupes():
    client = FakeClient()
    raw = Collector(client).collect()
    assert [s["serverInstanceNo"] for s in raw["servers"]] == ["0", "1", "2"]


def test_collect_attaches_parent_ids():
    raw = Collector(FakeClient()).collect()
    assert raw["acg_rules"][0]["accessControlGroupNo"] == "a1"
    assert raw["nacl_rules"][0]["networkAclNo"] == "n1"


def test_nacl_uses_library_methods():
    client = FakeClient()
    raw = Collector(client, region_code="KR").collect()
    assert client.vpc.calls == [("acl", "KR"), ("rule", "n1")]
    # Deny-Allow Group 조회 실패는 무시
    assert raw["deny_allow_groups"] == []

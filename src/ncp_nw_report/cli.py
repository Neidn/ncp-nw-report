"""명령행 진입점. 키 1개(계정 1개) = 별첨 파일 1개.

ncp-nw-report collect --out out/별첨.xlsx [--previous 이전.xlsx] [--dump-raw x.raw.json]
ncp-nw-report build   --raw out/x.raw.json --out out/별첨.xlsx [--previous ...]
ncp-nw-report demo    --out out/sample_report.xlsx
"""

from __future__ import annotations

import argparse
import json
import os
from importlib import resources
from pathlib import Path
from typing import Any

from ncp_nw_report import excel, transform


def _load_env(path: str) -> None:
    """간단한 .env 로더 (KEY=VALUE). 이미 설정된 환경변수는 덮어쓰지 않음."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _doc_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--title", default=excel.Document.title, help="문서 제목")
    p.add_argument("--author", default="", help="작성자")
    p.add_argument("--version", dest="doc_version", default="v1.0", help="문서 버전")
    p.add_argument("--classification", default="대외비", help="보안등급 표기")
    p.add_argument("--previous", help="수동 입력 시트를 가져올 이전 별첨 파일")


def _write(raw: dict[str, Any], args: argparse.Namespace) -> None:
    report = transform.build(raw)
    doc = excel.Document(
        title=args.title,
        author=args.author,
        version=args.doc_version,
        classification=args.classification,
    )
    path = excel.write(report, args.out, doc, args.previous)
    print(
        f"작성 완료: {path}\n"
        f"  서버-ACG 매핑 {len(report.mapping)}행 / "
        f"ACG 규칙 {len(report.acg_rules)}행 / "
        f"NACL 규칙 {len(report.nacl_rules)}행 / Subnet {len(report.subnets)}행 / "
        f"LB {len(report.load_balancers)}행"
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ncp-nw-report")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("collect", help="NCP API 조회 후 엑셀 작성")
    p.add_argument("--out", required=True)
    p.add_argument("--dump-raw", help="원본 조회 결과 저장 경로 (*.raw.json)")
    p.add_argument("--env-file", default=".env")
    p.add_argument("--env", help="gov / public / fin (기본: NCP_ENV 또는 public)")
    _doc_args(p)

    p = sub.add_parser("build", help="저장해 둔 원본(JSON)으로 엑셀만 다시 작성")
    p.add_argument("--raw", required=True)
    p.add_argument("--out", required=True)
    _doc_args(p)

    p = sub.add_parser("demo", help="예시 데이터로 엑셀 작성 (API 키 불필요)")
    p.add_argument("--out", default="out/sample_report.xlsx")
    _doc_args(p)

    args = parser.parse_args(argv)

    if args.cmd == "collect":
        from ncp_nw_report.collect import collect_all

        _load_env(args.env_file)
        try:
            ak, sk = os.environ["NCP_ACCESS_KEY"], os.environ["NCP_SECRET_KEY"]
        except KeyError as exc:
            raise SystemExit(f"환경변수 {exc.args[0]} 가 없습니다.") from exc
        raw = collect_all(ak, sk, args.env)
        if args.dump_raw:
            Path(args.dump_raw).parent.mkdir(parents=True, exist_ok=True)
            Path(args.dump_raw).write_text(
                json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    elif args.cmd == "build":
        raw = json.loads(Path(args.raw).read_text(encoding="utf-8"))
    else:
        text = (
            resources.files("ncp_nw_report")
            .joinpath("demo/demo_raw.json")
            .read_text(encoding="utf-8")
        )
        raw = json.loads(text)
    _write(raw, args)


if __name__ == "__main__":
    main()

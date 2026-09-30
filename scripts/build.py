#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ipaddress
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

UA = "soltan-developer/GeoSite (+https://github.com/soltan-developer/GeoSite)"
LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def normalize_domain(value: str) -> str | None:
    value = value.strip().lower()
    if not value:
        return None
    if value.startswith("||"):
        value = value[2:]
    if value.endswith("^"):
        value = value[:-1]
    if value.startswith("*."):
        value = value[2:]
    value = value.lstrip(".").rstrip(".")

    if "://" in value:
        from urllib.parse import urlsplit
        try:
            value = urlsplit(value).hostname or ""
        except ValueError:
            return None

    if value.count(":") == 1:
        host, maybe_port = value.rsplit(":", 1)
        if maybe_port.isdigit():
            value = host

    if not value or "/" in value or " " in value or "\t" in value:
        return None

    try:
        ipaddress.ip_address(value)
        return None
    except ValueError:
        pass

    try:
        value = value.encode("idna").decode("ascii")
    except UnicodeError:
        return None

    if len(value) > 253 or "." not in value:
        return None

    labels = value.split(".")
    if any(not LABEL_RE.match(label) for label in labels):
        return None
    return value


def parse_line(line: str, fmt: str) -> str | None:
    line = line.strip()
    if not line or line.startswith(("#", "!", ";")):
        return None
    if " #" in line:
        line = line.split(" #", 1)[0].strip()

    if fmt == "hosts":
        parts = line.split()
        if len(parts) >= 2:
            try:
                ipaddress.ip_address(parts[0])
                return normalize_domain(parts[1])
            except ValueError:
                pass
        return normalize_domain(parts[0]) if parts else None

    if fmt == "domains":
        return normalize_domain(line.split()[0])

    raise ValueError(f"unsupported source format: {fmt}")


def download_source(source: dict, retries: int = 3) -> tuple[set[str], int]:
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        domains: set[str] = set()
        raw_lines = 0
        try:
            req = Request(source["url"], headers={"User-Agent": UA, "Accept": "text/plain,*/*"})
            with urlopen(req, timeout=120) as resp:
                for raw in resp:
                    raw_lines += 1
                    line = raw.decode("utf-8", errors="ignore")
                    domain = parse_line(line, source["format"])
                    if domain:
                        domains.add(domain)
            if not domains:
                raise RuntimeError("source produced zero valid domains")
            return domains, raw_lines
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(attempt * 3)
    raise RuntimeError(f"failed after {retries} attempts: {last_exc}")


def read_local(path: Path) -> set[str]:
    out: set[str] = set()
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        domain = parse_line(line, "domains")
        if domain:
            out.add(domain)
    return out


def is_under(domain: str, roots: set[str]) -> bool:
    parts = domain.split(".")
    for i in range(len(parts) - 1):
        if ".".join(parts[i:]) in roots:
            return True
    return domain in roots


def apply_allowlist(domains: set[str], allow: set[str]) -> set[str]:
    if not allow:
        return domains
    return {d for d in domains if not is_under(d, allow)}


def collapse_redundant(domains: set[str]) -> list[str]:
    ordered = sorted(domains, key=lambda d: (d.count("."), d))
    kept: set[str] = set()
    for domain in ordered:
        parts = domain.split(".")
        redundant = False
        for i in range(1, len(parts) - 1):
            if ".".join(parts[i:]) in kept:
                redundant = True
                break
        if not redundant:
            kept.add(domain)
    return sorted(kept)


def write_dlc(path: Path, domains: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"domain:{d}\n" for d in domains), encoding="utf-8")


def write_plain(path: Path, domains: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{d}\n" for d in domains), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default="sources.json")
    ap.add_argument("--lists-dir", default="lists")
    ap.add_argument("--build-dir", default="build")
    ap.add_argument("--dist-dir", default="dist")
    args = ap.parse_args()

    cfg = json.loads(Path(args.sources).read_text(encoding="utf-8"))
    lists_dir = Path(args.lists_dir)
    build_dir = Path(args.build_dir)
    data_dir = build_dir / "data"
    dist_dir = Path(args.dist_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    dist_dir.mkdir(parents=True, exist_ok=True)

    source_stats: list[dict] = []
    groups: dict[str, set[str]] = {}

    for group_name, source_list in cfg["groups"].items():
        combined: set[str] = set()
        for src in source_list:
            print(f"[fetch] {group_name}: {src['name']}", flush=True)
            try:
                domains, raw_lines = download_source(src)
            except Exception as exc:
                if src.get("required", True):
                    raise
                print(f"[warn] optional source failed: {src['name']}: {exc}", file=sys.stderr)
                source_stats.append({
                    "group": group_name, "name": src["name"], "url": src["url"],
                    "license": src.get("license", "unknown"), "ok": False,
                    "error": str(exc)
                })
                continue

            combined.update(domains)
            source_stats.append({
                "group": group_name, "name": src["name"], "url": src["url"],
                "license": src.get("license", "unknown"), "ok": True,
                "raw_lines": raw_lines, "valid_unique_domains": len(domains)
            })
            print(f"[ok] {src['name']}: {len(domains):,} unique domains", flush=True)
        groups[group_name] = combined

    persian_adult = read_local(lists_dir / "persian-adult.txt")
    persian_gambling = read_local(lists_dir / "persian-gambling.txt")
    allow = read_local(lists_dir / "allowlist.txt")

    adult_raw = groups.get("adult", set()) | persian_adult
    gambling_raw = groups.get("gambling", set()) | persian_gambling
    nsfw_raw = adult_raw | gambling_raw | groups.get("nsfw_all_extra", set())

    final_sets: dict[str, list[str]] = {}
    for name, domains in {
        "adult": adult_raw,
        "gambling": gambling_raw,
        "persian-adult": persian_adult,
        "persian-gambling": persian_gambling,
        "nsfw-all": nsfw_raw,
    }.items():
        domains = apply_allowlist(domains, allow)
        final_sets[name] = collapse_redundant(domains)

    for name, minimum in cfg.get("thresholds", {}).items():
        actual = len(final_sets[name])
        if actual < int(minimum):
            raise RuntimeError(
                f"safety threshold failed for {name}: {actual:,} < {int(minimum):,}; "
                "refusing to publish a suspiciously small build"
            )

    for name, domains in final_sets.items():
        write_dlc(data_dir / name, domains)

    write_plain(dist_dir / "adult.txt", final_sets["adult"])
    write_plain(dist_dir / "gambling.txt", final_sets["gambling"])
    write_plain(dist_dir / "nsfw-all.txt", final_sets["nsfw-all"])

    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    stats = {
        "generated_at": generated,
        "sources": source_stats,
        "custom": {
            "persian_adult": len(persian_adult),
            "persian_gambling": len(persian_gambling),
            "allowlist": len(allow)
        },
        "final": {k: len(v) for k, v in final_sets.items()}
    }
    (dist_dir / "stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    notes = [
        "# GeoSite latest build",
        "",
        f"Generated: {generated}",
        "",
        "| Category | Domains |",
        "| --- | ---: |"
    ]
    for key in ("adult", "gambling", "persian-adult", "persian-gambling", "nsfw-all"):
        notes.append(f"| {key} | {len(final_sets[key]):,} |")
    notes += [
        "",
        "The binary is built from sources.json plus repository custom lists.",
        "See SOURCES.md for licensing and attribution."
    ]
    (dist_dir / "release-notes.md").write_text("\n".join(notes) + "\n", encoding="utf-8")

    print("[final]")
    for key, value in stats["final"].items():
        print(f"  {key}: {value:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

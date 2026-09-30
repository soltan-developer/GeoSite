#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

UA = "soltan-developer/GeoSite-test-corpus (+https://github.com/soltan-developer/GeoSite)"
LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")

EXTERNAL_SOURCES = [
    {
        "name": "BlackRabbitZ Adult/NSFW",
        "url": "https://raw.githubusercontent.com/BlackRabbitZ/BlackRabbitZ-DNS-Blocklists/main/lists/categories/adult.txt",
        "format": "plain",
        "license": "GPL-3.0",
    },
    {
        "name": "V2Fly category-porn",
        "url": "https://raw.githubusercontent.com/v2fly/domain-list-community/master/data/category-porn",
        "format": "dlc",
        "license": "MIT",
    },
]

REGIONAL_TLDS = {
    "ir","ru","su","tr","az","ae","sa","eg","iq","sy","lb","jo","kw","qa","bh","om",
    "ma","dz","tn","pk","in","id","my","cn","jp","kr","br","mx","es","de","fr","it",
    "nl","pl","ro","cz","sk","hu","gr","pt","vn","th"
}
REGIONAL_HINTS = {
    "iran","irani","iranian","farsi","persian","parsi","tehran",
    "turk","turkey","turkish","istanbul",
    "arab","arabic","arabi",
    "rus","russia","russian",
    "hindi","india","indian",
    "pak","pakistan","urdu",
    "indo","indonesia","malay",
    "japan","japanese","korea","korean","china","chinese",
    "brasil","brazil","mexico","latino","latina","spanish","espanol",
    "german","deutsch","french","francais","italian","italia"
}


def normalize_domain(value: str) -> str | None:
    value = value.strip().lower()
    if not value or value.startswith(("#", "!", ";")):
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
        host, port = value.rsplit(":", 1)
        if port.isdigit():
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


def covered_by(domain: str, roots: set[str]) -> bool:
    labels = domain.split(".")
    for i in range(len(labels) - 1):
        if ".".join(labels[i:]) in roots:
            return True
    return domain in roots


def fetch_lines(url: str):
    req = Request(url, headers={"User-Agent": UA, "Accept": "text/plain,*/*"})
    with urlopen(req, timeout=180) as resp:
        for raw in resp:
            yield raw.decode("utf-8", errors="ignore").strip()


def parse_source(source: dict) -> set[str]:
    out: set[str] = set()
    fmt = source["format"]
    for line in fetch_lines(source["url"]):
        if not line or line.startswith(("#", "!", ";")):
            continue
        candidate = None
        if fmt == "plain":
            candidate = line.split()[0]
        elif fmt == "dlc":
            # Keep explicit/bare domain rules. Includes, keyword and regexp entries are
            # intentionally skipped because this corpus is domain-only.
            core = line.split("@", 1)[0].strip()
            if core.startswith("domain:"):
                candidate = core[7:]
            elif core.startswith("full:"):
                candidate = core[5:]
            elif ":" not in core:
                candidate = core
        else:
            raise ValueError(f"unsupported format: {fmt}")
        if candidate:
            d = normalize_domain(candidate)
            if d:
                out.add(d)
    return out


def regional_score(domain: str) -> int:
    labels = domain.split(".")
    score = 0
    if labels[-1] in REGIONAL_TLDS:
        score += 3
    if domain.startswith("xn--") or ".xn--" in domain:
        score += 4
    joined = "-" + domain.replace(".", "-") + "-"
    for hint in REGIONAL_HINTS:
        if hint in joined:
            score += 2
    return score


def stable_key(domain: str, salt: str) -> str:
    return hashlib.sha256((salt + "\0" + domain).encode()).hexdigest()


def pick_diverse(domains: set[str], count: int, salt: str) -> list[str]:
    regional = [d for d in domains if regional_score(d) > 0]
    generic = [d for d in domains if regional_score(d) == 0]
    regional.sort(key=lambda d: (-regional_score(d), stable_key(d, salt + ":regional")))
    generic.sort(key=lambda d: stable_key(d, salt + ":generic"))

    # Prioritize multilingual/regional-looking domains, but keep the corpus broad.
    regional_cap = min(3000, count, len(regional))
    picked = regional[:regional_cap]
    need = count - len(picked)
    picked.extend(generic[:need])
    if len(picked) < count:
        remaining = [d for d in regional[regional_cap:] if d not in set(picked)]
        picked.extend(remaining[: count - len(picked)])
    return picked[:count]


def main() -> int:
    dist = Path("dist")
    production_file = dist / "adult.txt"
    if not production_file.exists():
        raise RuntimeError("dist/adult.txt must be built first")

    production = {
        d for line in production_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        if (d := normalize_domain(line))
    }

    external_union: set[str] = set()
    source_stats = []
    for src in EXTERNAL_SOURCES:
        domains = parse_source(src)
        external_union.update(domains)
        source_stats.append({
            "name": src["name"],
            "url": src["url"],
            "license": src["license"],
            "valid_unique_domains": len(domains),
        })

    uncovered = {d for d in external_union if not covered_by(d, production)}
    if len(uncovered) < 10000:
        raise RuntimeError(f"only {len(uncovered)} uncovered external domains; need 10,000")

    challenge = pick_diverse(uncovered, 10000, "adult-challenge-v1")
    control = sorted(production, key=lambda d: stable_key(d, "adult-control-v1"))[:10000]

    (dist / "adult-challenge-10000.txt").write_text(
        "".join(d + "\n" for d in challenge), encoding="utf-8"
    )
    (dist / "adult-control-10000.txt").write_text(
        "".join(d + "\n" for d in control), encoding="utf-8"
    )

    meta = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "purpose": "Coverage testing only; not merged into production GeoSite.",
        "challenge_count": len(challenge),
        "control_count": len(control),
        "production_adult_count": len(production),
        "external_unique_count": len(external_union),
        "external_uncovered_count": len(uncovered),
        "regional_priority_count": sum(1 for d in challenge if regional_score(d) > 0),
        "sources": source_stats,
        "method": (
            "Challenge candidates come from independent GPL/MIT adult-domain sources, "
            "then exact and parent-domain coverage by the current production adult list "
            "is removed. Up to 3,000 multilingual/regional-looking domains are prioritized; "
            "the remainder is a deterministic hash sample."
        ),
        "caveat": (
            "A domain in the challenge file may be inactive or a false positive. "
            "Network failure alone does not prove that Xray blocked it."
        ),
    }
    (dist / "adult-test-meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

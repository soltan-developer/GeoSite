# Sources and licensing

The generated database is a derived merged blocklist. Each upstream source keeps its own copyright/license.

| Source | Used for | License | Upstream |
| --- | --- | --- | --- |
| HaGeZi NSFW | adult | GPL-3.0 | https://github.com/hagezi/dns-blocklists |
| HaGeZi Gambling Full | gambling | GPL-3.0 | https://github.com/hagezi/dns-blocklists |
| Block List Project Porn | adult | Unlicense | https://github.com/blocklistproject/Lists |
| StevenBlack gambling-porn-only | nsfw-all supplement | MIT | https://github.com/StevenBlack/hosts |
| Local custom lists | Persian/custom additions | GPL-3.0 contribution to this repo | lists/ |

Chocolate4U's NSFW generator currently derives its NSFW list from StevenBlack's combined gambling/porn hosts feed. This project consumes that same permissively licensed feed directly rather than republishing Chocolate4U's binary.

## Why UT1 is not merged by default

UT1 is a valuable and very large adult-category dataset distributed under CC BY-SA. This repository currently emits one combined GPL-3.0 binary, so UT1 is intentionally excluded from the default merged artifact to avoid silently mixing copyleft datasets under incompatible or ambiguous redistribution terms.

If a future build publishes license-separated artifacts, UT1 can be added as its own output.

## No completeness guarantee

No category list is complete. Adult and gambling sites frequently rotate domains and mirrors. Use lists/persian-adult.txt and lists/persian-gambling.txt for fast local additions, and lists/allowlist.txt for false positives.

# GeoSite

Daily-built Xray/3x-ui GeoSite database for adult and gambling filtering.

## Stable download

~~~
https://github.com/soltan-developer/GeoSite/releases/download/latest/geosite_custom.dat
~~~

The release is rebuilt every day by GitHub Actions and can also be rebuilt manually with Run workflow.

## Categories

The generated geosite_custom.dat contains:

- adult — merged adult-content sources plus lists/persian-adult.txt
- gambling — merged gambling sources plus lists/persian-gambling.txt
- persian-adult — repository-maintained Persian/custom adult domains only
- persian-gambling — repository-maintained Persian/custom gambling domains only
- nsfw-all — union of adult + gambling + the combined StevenBlack feed

Every domain is normalized, IDN-converted, deduplicated and redundant child domains are removed when their parent is already present. lists/allowlist.txt is applied last.

## 3x-ui / Sanaei

3x-ui supports custom GeoSite DAT URLs. Use:

~~~
URL:   https://github.com/soltan-developer/GeoSite/releases/download/latest/geosite_custom.dat
Alias: family
~~~

With alias family, 3x-ui stores the file as geosite_family.dat. Routing examples:

~~~
ext:geosite_family.dat:adult
ext:geosite_family.dat:gambling
ext:geosite_family.dat:persian-adult
ext:geosite_family.dat:persian-gambling
ext:geosite_family.dat:nsfw-all
~~~

Route the desired tags to your existing blocked/blackhole outbound. Keep the block rule above a catch-all proxy/balancer rule and enable inbound sniffing for HTTP/TLS/QUIC when domain-based routing is required.

For servers that should update automatically every day, see installers/install-3xui-updater.sh. The updater verifies SHA-256, replaces the DAT atomically, and restarts x-ui only when the file actually changed.

## Custom Persian domains

Add one domain per line:

~~~
lists/persian-adult.txt
lists/persian-gambling.txt
~~~

Examples of accepted input:

~~~
example.com
sub.example.net
*.example.org
~~~

Do not include URL paths. Comments beginning with # are allowed.

To fix a false positive, add the domain to:

~~~
lists/allowlist.txt
~~~

An allowlisted parent also allows its subdomains.

## Sources

See SOURCES.md and sources.json. The initial public build intentionally uses sources whose redistribution terms can be honored together in a GPL-3.0 release. Large CC BY-SA datasets such as UT1 are not merged into this single binary by default because combining copyleft datasets with different licenses requires extra licensing care.

## Build locally

~~~bash
python3 scripts/build.py
git clone --depth 1 https://github.com/v2fly/domain-list-community.git /tmp/dlc
cd /tmp/dlc
go run .   --datapath="$OLDPWD/build/data"   --outputname=geosite_custom.dat   --outputdir="$OLDPWD/dist"
~~~

## Output files

The latest GitHub Release contains:

- geosite_custom.dat
- adult.txt
- gambling.txt
- nsfw-all.txt
- stats.json
- SHA256SUMS

## License

Repository code and the redistributed combined output are GPL-3.0. Upstream data remains subject to each upstream source's license. See SOURCES.md.

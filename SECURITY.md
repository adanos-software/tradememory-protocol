# Security Policy

## Supported versions

Only the latest release on PyPI (`tradememory-protocol`) receives security fixes. The project is in
maintenance mode: no new features, but bug and security fixes are still shipped.

## Reporting a vulnerability

Please use GitHub private vulnerability reporting (the **Security** tab of this repository, then
**Report a vulnerability**) instead of opening a public issue. Include a reproduction where possible.

You should get an acknowledgement within 7 days. Fixes are released as a patch version and noted in
`CHANGELOG.md`; the reporter is credited in the release notes unless they prefer otherwise.

## Scope

- `src/tradememory/server.py` — REST API and dashboard static serving
- `src/tradememory/mcp_server.py` — MCP tools
- audit-chain hashing and RFC 3161 anchoring code

Out of scope: the hosted-API and pricing documents under `docs/`, which are historical and were never
commercially deployed.

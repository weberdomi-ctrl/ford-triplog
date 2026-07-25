# SECURITY.md

# Security Policy

The security of Ford Triplog is important.

If you discover a security vulnerability, please report it responsibly instead of creating a public GitHub issue.

---

# Supported Versions

The following table shows which versions currently receive security updates.

| Version | Supported |
|----------|-----------|
| 1.5.x | ✅ Yes |
| Older versions | ❌ No |

Only the latest released version is actively maintained.

---

# Reporting a Vulnerability

Please do **not** report security vulnerabilities through public GitHub Issues.

Instead, contact the maintainer directly.

Include as much information as possible:

- A clear description of the vulnerability
- Steps to reproduce the issue
- Expected behavior
- Actual behavior
- Potential impact
- Home Assistant version
- Ford Triplog version

If possible, also include:

- Relevant log entries
- Diagnostics (after reviewing for sensitive information)
- Screenshots
- Proof-of-concept code

---

# Response Process

Every reported vulnerability will be:

1. Acknowledged.
2. Investigated.
3. Reproduced.
4. Fixed if confirmed.
5. Included in the next release.

Critical vulnerabilities will receive the highest priority.

---

# Responsible Disclosure

Please allow reasonable time for a fix before publicly disclosing a vulnerability.

Responsible disclosure helps protect all Ford Triplog users.

---

# Scope

This policy applies to the Ford Triplog integration itself.

Examples include:

- Configuration handling
- Local storage
- Data processing
- Diagnostics
- Configuration flow
- Options flow

Issues in third-party projects should be reported to the respective maintainers.

Examples include:

- Home Assistant
- HACS
- FordPass integration
- Python
- OpenStreetMap

---

# Data Protection

Ford Triplog follows a local-first architecture.

The integration:

- does not operate a cloud service
- does not collect analytics
- does not transmit trip history
- does not transmit charging history
- stores all data locally

Vehicle data is only processed inside the user's Home Assistant installation.

---

# Security Best Practices

Users are encouraged to:

- Keep Home Assistant up to date.
- Keep HACS updated.
- Keep Ford Triplog updated.
- Protect Home Assistant with strong authentication.
- Enable Multi-Factor Authentication where possible.
- Create regular backups.
- Review diagnostics before sharing them.

---

# Third-Party Dependencies

Ford Triplog depends on several external projects.

Security updates for these components are managed by their respective maintainers.

Examples include:

- Home Assistant
- Python
- FordPass integration
- OpenStreetMap data sources

---

# Acknowledgements

Thank you to everyone who reports security issues responsibly.

Responsible disclosure helps keep Ford Triplog reliable and secure for the entire community.
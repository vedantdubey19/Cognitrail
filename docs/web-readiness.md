# Cognitrail web readiness

**QA follow-up fixes are implemented.** The changes and regression tests are summarized below.

Verified on 7 November 2026 in Chrome at 320, 375, 768, and 1440 CSS pixels. Browser checks exercised navigation and checked document width, page titles, metadata, missing-page rendering, favicon availability, and visible links. Form error/success checks used mocked API responses; the Python suites separately exercise real offline application behavior. No paid provider calls were made.

Support links use the owner-provided email `vedantdubey020@gmail.com` and phone `+91 83685 30934`. Phone links use `tel:+918368530934`; email links use `mailto:`. Copyright years update at runtime. No raster images are shipped by these clients; the new SVG favicons are under 0.5 KB, so raster recompression is not applicable. Long evidence tables and preformatted output retain bounded internal scrolling; page-level horizontal scrolling was checked separately.

Dependency audits found no known vulnerabilities in the installed environments at the time of this check. These results are point-in-time checks, not guarantees about future advisories or live infrastructure.

## Changes

- Added collapsible mobile workspace navigation with an accessible expanded state, favicon, view titles/descriptions, and support/footer links.
- Removed illustrative input placeholders, preserved visible/accessible field labels, and improved long-content wrapping and mobile touch targets.
- Added specific feedback for workspace creation, import, plan creation, approval, and source deletion.
- Added owner workspace deletion with active-run safeguards and quota recovery controls. Delayed workspace/run/source/history responses are invalidated before they can update the selected workspace.
- Added a custom HTML 404 with a real 404 response while preserving JSON API error contracts.
- Verified that the Python wheel includes all web assets.
- Added the private-owner HTTPS gateway profile, gateway-secret and origin checks, a consistent SQLite backup tool, deployment instructions and container acceptance checks.

## Evidence

41 Python tests and all three browser regression tests passed. They cover delayed workspace/run responses, deletion and quota recovery, and mobile overflow at 320, 375, 768 and 1440 CSS pixels. Ruff, JavaScript syntax, locked dependency resolution, wheel build and installed dependency audit passed. CI installs Chromium before running the browser suite.

## Deployment boundary

The default profile remains local-only. The new private profile serves one owner through password-protected Caddy HTTPS, without publishing a backend port. Its Compose file passed official-schema and Compose v2 validation. The current Dockerfile built successfully using cached dependency layers with the unchanged lock file. The resulting image passed authenticated HTTPS, wrong-password rejection, origin protection, complete offline research, export, custom 404, restart persistence and non-root Linux smoke checks. SQLite backup/restore tests passed. Container tests used generated dummy credentials and a verified temporary internal CA, and removed their temporary resources.

Follow private-hosting.md to configure a real host, DNS, credentials, off-host backups and provider budgets. A publicly trusted live domain/TLS endpoint and live Gemini/Brave calls were not exercised. This is a private single-owner deployment, not a multi-user service.

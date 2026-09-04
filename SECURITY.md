# Security policy

## Supported status

This repository is a controlled demonstration and reference implementation. It is not a production security baseline.

## Reporting a vulnerability

Do not disclose credentials, personal footage, exploit details, or sensitive deployment information in a public GitHub issue. Use a private repository-owner channel or GitHub's private vulnerability-reporting feature when enabled.

Include the affected component, reproduction conditions, potential impact, and a safe proof of concept. Do not access data or systems beyond those you are authorized to test.

## Secret handling

- Copy settings from `.env.example` into an ignored `.env` file.
- Never commit camera passwords, RTSP URLs with credentials, cloud keys, device tokens, private certificates, or ERP credentials.
- Keep server secrets out of `NEXT_PUBLIC_*` variables.
- Rotate any credential immediately if it is exposed.

## Production requirements

Before deployment, define authentication, authorization, tenant isolation, encryption, key management, retention enforcement, audit protection, evidence access, backup, recovery, network segmentation, patching, monitoring, incident response, and data residency with the deploying organization.

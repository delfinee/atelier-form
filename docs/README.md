# Documentation

## Current guides

| Guide | Purpose |
| --- | --- |
| [Project overview](../README.md) | Features, architecture and quick start |
| [Development setup](../BEGINNER_SETUP.md) | Local PostgreSQL, environment, tests and team workflow |
| [Current status](../OUTSTANDING_TASKS.md) | Source-backed reconciliation of the old tracker |
| [Unified delivery](../UNIFIED_DELIVERY.md) | Buyer/seller modes and integrated local startup |
| [Integration notes](../INTEGRATION_NOTES.md) | Shared services and integration provenance |
| [Windows seller demo](../WINDOWS_SELLER.md) | Hosted synthetic demo and WebView2 build |
| [Seller WeChat](../SELLER_WECHAT.md) | API, identity linking and local acceptance |
| [Phone preview](../SELLER_PHONE.md) | Real WeChat preview preparation and dated evidence |
| [Release procedure](../RELEASE.md) | Server deployment and native platform release gates |
| [Earlier team acceptance](../TEAM_ACCEPTANCE.md) | Historical acceptance plus launcher-referenced instructions |
| [Repository rename](REPOSITORY_RENAME.md) | Manual GitHub rename and integration checks |
| [Cleanup report](CLEANUP_REPORT.md) | Audit decisions, changed files and actual validation |

Nested operational references include [Windows packaging notes](../desktop/windows/README.txt) and [the earlier public-demo runbook](../deploy/PUBLIC-DEMO.txt). Commands in deployment guides can write data or deploy services; select the intended environment before using them.

## Archived team reviews

These preserve contribution history and earlier technical findings. Branch names, test counts, suggested changes and OPEN markers refer to the original review, not today's implementation. Source paths in code spans are repository-root paths; missing old paths can describe an earlier branch.

- [Min: seller dashboard handover](archive/HANDOVER_MIN_SELLER_DASHBOARD.md)
- [Bohan: chatbot/messaging review](archive/BOHAN_CHATBOT_REVIEW_HANDOVER.md)
- [Jun Jie: localisation review](archive/JUNJIE_LOCALISATION_CODE_REVIEW_HANDOVER.md)
- [Seller frontend review](archive/SELLER_FRONTEND_REVIEW.md)

Use the current status document before assigning work from an archived checklist. The operational guides remain at the root because launchers and delivery workflows refer to those filenames.

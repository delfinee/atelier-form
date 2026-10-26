# Rename the GitHub repository

Rename completed and verified on 26 October 2026. Current repository: `delfinee/atelier-form` (formerly `delfinee/dip-new-repo-test`). Product display name: **Atelier Form**. External integration verification remains pending.

## GitHub rename: completed

GitHub now resolves the repository at [delfinee/atelier-form](https://github.com/delfinee/atelier-form) and redirects the old name. The default branch remains `main`, with repository history and the merged documentation cleanup preserved.

A local clone has already had its `origin` updated. For any other existing clones that still use the old repository URL, run:

```powershell
git remote set-url origin https://github.com/delfinee/atelier-form.git
git remote -v
git ls-remote --symref origin HEAD
```

GitHub redirects old repository and Git URLs, but recommends updating remotes. Do not reuse the old repository name, which would break its redirects. GitHub Pages project URLs and references to hosted GitHub Actions need separate handling. See [GitHub's rename documentation](https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository).

## Post-rename integration checks

| Area | Observed state and next action |
| --- | --- |
| Local origin | One local checkout has been updated to `delfinee/atelier-form.git` and its `git remote -v` output was checked. Other clones should update their remotes with the commands above. |
| Local folder | Keep the existing path. A GitHub rename does not require renaming a clone directory. |
| Vercel project | **Pending verification.** Local `.vercel/project.json` identifies project `dip-new-repo`; previous team API access returned 403. In that project's **Settings → Git**, verify the connected repository resolves to `delfinee/atelier-form` and the production branch remains `main`. |
| Vercel URLs and domains | Keep `dip-new-repo.vercel.app` and existing domains unless deliberately changing hosting. A repository slug change does not require a Vercel project/domain rename. Verify build settings, root directory and deployment hooks in the dashboard; do not trigger production deployment just for this cleanup. |
| Webhooks/GitHub Apps | **Pending verification.** Inspect GitHub **Settings → Webhooks** and installed-app repository access. Inspect deliveries after an approved push; check external consumers for hard-coded repository names. These settings were not verified in this documentation update. |
| CI/Pages | **Pending verification.** No tracked `.github` workflows or hosted action definition were found in the earlier audit. Dashboard rules, branch protection, Pages settings and external CI still require owner inspection. |
| Documentation | The clone URL in `BEGINNER_SETUP.md` and the root README's rename status are updated in this documentation PR. Historical branch-review URLs remain as provenance; GitHub redirects cover ordinary old repository links. |
| Scripts and internal identifiers | `launch_seller.py` and command launchers contain compatibility paths involving `dip-new-repo-test`. Preserve them. Supply an explicit `--env-file` when moving installations. Do not rename Django packages, databases, environment variables or API routes. |
| Other hosts and clients | `demo.maijiax.cn`, WeChat request domains, public client config and Windows demo origin are application endpoints, not GitHub slugs; retain them. Verify any external source checkout/update automation separately. |

The repository rename itself is complete. Vercel, webhook/app access, CI/Pages and other external source-checkout automation still require owner verification. This documentation follow-up makes no application, deployment, domain, environment-variable or webhook changes.

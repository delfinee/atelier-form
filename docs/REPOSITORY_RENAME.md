# Rename the GitHub repository

Audit date: 26 October 2026. Current repository: `delfinee/dip-new-repo-test`; desired slug: `delfinee/atelier-form`. Product display name: **Atelier Form**.

## Status and exact steps

GitHub metadata confirmed admin access and default branch `main`. The connected GitHub tools do not expose a repository rename operation, and the GitHub CLI is not installed. No remote rename was performed.

1. Open [repository Settings](https://github.com/delfinee/dip-new-repo-test/settings).
2. Under **General**, find **Repository name**.
3. Enter `atelier-form` and click **Rename**. Resolve any name conflict before proceeding.
4. Verify the repository opens at `https://github.com/delfinee/atelier-form`, with its existing history, branches, issues and pull requests.
5. In each existing clone, after the rename succeeds, run:

```powershell
git remote set-url origin https://github.com/delfinee/atelier-form.git
git remote -v
git ls-remote --symref origin HEAD
```

GitHub redirects old repository and Git URLs, but recommends updating remotes. Do not reuse the old repository name, which would break its redirects. GitHub Pages project URLs and references to hosted GitHub Actions need separate handling. See [GitHub's rename documentation](https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository).

## Integration checks after rename

| Area | Observed state and next action |
| --- | --- |
| Local origin | Still points to `delfinee/dip-new-repo-test.git`; update only after the remote rename succeeds. |
| Local folder | Keep the existing path. A GitHub rename does not require renaming a clone directory. |
| Vercel project | Local `.vercel/project.json` identifies project `dip-new-repo`; team API access returned 403. In that project's **Settings → Git**, verify the connected repository resolves to `delfinee/atelier-form` and the intended production branch remains `main`. |
| Vercel URLs and domains | Keep `dip-new-repo.vercel.app` and existing domains unless deliberately changing hosting. A repository slug change does not require a Vercel project/domain rename. Verify build settings, root directory and deployment hooks in the dashboard; do not trigger production deployment just for this cleanup. |
| Webhooks/GitHub Apps | Inspect GitHub **Settings → Webhooks** and installed-app repository access. Inspect recent deliveries after the next approved push; check external consumers for hard-coded repository names. These external settings were not accessible through the connected tools. |
| CI/Pages | No tracked `.github` workflows or hosted action definition were found. Dashboard rules, branch protection, Pages settings and external CI still require owner inspection. |
| Documentation | Update the clone URL in `BEGINNER_SETUP.md` and active repository references after success. Keep historical branch-review URLs as provenance; GitHub redirects cover ordinary repository links. |
| Scripts and internal identifiers | `launch_seller.py` and command launchers contain compatibility paths involving `dip-new-repo-test`. Preserve them. Supply an explicit `--env-file` when moving installations. Do not rename Django packages, databases, environment variables or API routes. |
| Other hosts and clients | `demo.maijiax.cn`, WeChat request domains, public client config and Windows demo origin are application endpoints, not GitHub slugs; retain them. Verify any external source checkout/update automation separately. |

No push, commit, merge, deployment, environment-variable change or webhook update is part of this cleanup. Review the local documentation diff before authorizing publication.

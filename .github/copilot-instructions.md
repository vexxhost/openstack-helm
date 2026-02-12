# GitHub Copilot Instructions for OpenStack-Helm

## Chart Version Management

### Chart Version Update Policy

**Chart versions should NOT be updated manually** in most cases. The versioning is automated through release-please.

#### Rules:

1. **Do not manually update chart versions** in `Chart.yaml` files or `.release-please-manifest.json`
2. **Exception**: When transitioning from upstream calver (calendar versioning) to internal semver (semantic versioning), manual updates are permitted
3. **Only release-please PRs should automatically change chart versions**

#### During Code Review:

- If a PR modifies the `version` field in any `Chart.yaml` file, verify:
  - Is this a release-please automated PR?
  - OR is this explicitly transitioning from calver to semver?
  - If neither, request the version change to be reverted

- If a PR modifies `.release-please-manifest.json`, apply the same verification

#### Context:

This repository uses [release-please](https://github.com/googleapis/release-please) for automated release management. Release-please automatically:
- Updates chart versions based on conventional commits
- Maintains the `.release-please-manifest.json` file
- Creates release PRs when changes are ready to be released

Manual version bumps bypass this automation and can cause conflicts with the release process.

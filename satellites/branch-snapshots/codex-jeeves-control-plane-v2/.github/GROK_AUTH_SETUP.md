# Grok GitHub Write Access Setup

## Step 1: Create Personal Access Token

1. Go to: https://github.com/settings/tokens
2. Click "Generate new token (classic)"
3. Set token name: `grok-write-token`
4. Select these scopes:
   - ✅ repo (Full control of private repositories)
   - ✅ workflow (Update GitHub Action workflows)
   - ✅ admin:repo_hook (Full control of repository hooks)
   - ✅ admin:org_hook (Full control of organization hooks)
5. Click "Generate token"
6. **COPY THE TOKEN** (you'll only see it once)

## Step 2: Add Token to X.com Grok

1. Open X.com and go to your grok settings
2. Find "GitHub Integration" or "Repository Settings"
3. Look for "Authentication Token" or "GitHub PAT" field
4. Paste the token from Step 1

## Step 3: Test Write Permissions

Once configured, grok can now:
- ✅ Create and update files
- ✅ Push commits
- ✅ Create pull requests
- ✅ Manage workflows

---

## Your Token Permissions Explained

| Permission | Why Needed |
|-----------|-----------|
| `repo` | Write to repository files and create commits |
| `workflow` | Update GitHub Actions workflows |
| `admin:repo_hook` | Manage webhooks for CI/CD |
| `admin:org_hook` | Org-level webhook management |

---

**Token expires in:** 30 days (you can make it longer when creating)

**Revoke anytime:** https://github.com/settings/tokens (delete the token)


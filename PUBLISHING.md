# Publishing `ha-maytronics-dolphin` to GitHub

Do this **once** on the PC where the repo lives (`ha-maytronics-dolphin` folder).

## 1. Prerequisites

- [Git for Windows](https://git-scm.com/download/win) installed.
- [GitHub CLI (`gh`)](https://cli.github.com/) installed **or** create the empty repo in the GitHub web UI.

## 2. Replace placeholders in `manifest.json`

Edit `custom_components/maytronics_dolphin/manifest.json`:

- `codeowners` → your GitHub handle, e.g. `"@YourUser"`
- `documentation` / `issue_tracker` → your real repo URL

## 3. Initialize git and first commit

In PowerShell (adjust path if yours differs):

```powershell
cd "C:\Users\Admin\Desktop\R-R-Maintenance-program\ha-maytronics-dolphin"
git init
git add .
git commit -m "Initial Maytronics Dolphin BLE integration (HACS)"
```

## 4. Create the GitHub repo and push

### Option A — GitHub CLI (fastest)

```powershell
gh auth login
gh repo create ha-maytronics-dolphin --public --source . --remote origin --push
```

If the repo already exists on GitHub (empty):

```powershell
git remote add origin https://github.com/YOUR_USER/ha-maytronics-dolphin.git
git branch -M main
git push -u origin main
```

### Option B — Web UI

1. GitHub → **New repository** → name e.g. `ha-maytronics-dolphin` → **Create** (no README).
2. Then:

```powershell
git remote add origin https://github.com/YOUR_USER/ha-maytronics-dolphin.git
git branch -M main
git push -u origin main
```

## 5. HACS

In the GitHub repo **About** section, add the topic **`home-assistant`** (optional but common).

Users add the repo under HACS → **Custom repositories** → category **Integration** → your repo URL.

## 6. Releases (optional)

HACS can track `main` or **GitHub Releases**. For releases:

```powershell
git tag -a v0.2.0 -m "v0.2.0"
git push origin v0.2.0
```

Then on GitHub: **Releases → Draft a new release** from that tag.

---

If `git push` asks for credentials, use a **Personal Access Token** (classic) with `repo` scope as the password when using HTTPS, or set up **SSH keys** and use `git@github.com:YOUR_USER/ha-maytronics-dolphin.git`.

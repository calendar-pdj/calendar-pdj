# Job Calendar Sync (OneDrive CSV -> ICS -> Google Calendar)

A scheduled GitHub Action uses **rclone** to mirror a OneDrive (Business)
folder's CSV files into this repo, then rebuilds a single
`docs/calendar.ics` file that any calendar app can subscribe to by URL.

**No Azure AD app registration, no Power Automate, no credit card anywhere
in this pipeline.** rclone ships with its own long-standing, pre-registered
Microsoft app for OneDrive access - you approve it once in a browser (a
normal OAuth consent, not an app registration), and everything else runs
inside GitHub Actions on a schedule.

Because `docs/calendar.ics` is fully **rebuilt from scratch** on every run,
and because `rclone sync` makes `data/` an exact mirror of the OneDrive
folder:
- Delete a CSV from OneDrive -> `rclone sync` removes it from `data/` ->
  its events vanish from the next build.
- Edit a CSV -> `rclone sync` updates it in `data/` -> its events are
  rebuilt with the same UID, so the calendar app updates them in place
  instead of duplicating.
- Add a CSV -> `rclone sync` copies it into `data/` -> its events appear in
  the next build.

---

## How it fits together

```
OneDrive folder --(rclone sync, on a schedule)--> data/*.csv in this repo
        --> generate_ics.py rebuilds calendar.ics --> commit
        --> GitHub Pages serves it --> Google Calendar subscribes
```

Every run: rclone mirrors OneDrive into `data/`, the script rebuilds the
ICS from whatever's in `data/`, and the workflow commits the result if
anything changed.

---

## One-time setup

### 1. Install rclone on your own computer (just for the one-time authorization)

Download it from [rclone.org/downloads](https://rclone.org/downloads/).
This is only needed once, to generate a config file - it doesn't need to
stay installed anywhere afterwards.

### 2. Authorize rclone against your OneDrive

Open a terminal and run:

```
rclone config
```

Walk through the wizard:

1. `n` - new remote
2. Name it `onedrive`
3. Storage type - enter `onedrive`
4. **OAuth Client Id** and **OAuth Client Secret** - leave both **blank**
   (just press Enter). This is what lets you skip registering your own
   Azure app entirely - rclone uses its own.
5. Choose national cloud region - press Enter for the default (`global`)
6. Leave "tenant" blank - press Enter
7. Edit advanced config? - `n`
8. Use auto config? - `y` (this opens a browser - sign in with your
   Microsoft 365 Business account and approve the permission request)
9. rclone will show a numbered list of drives it found (your personal
   OneDrive and/or any shared SharePoint libraries you have access to).
   Pick the one that contains your job CSVs.
10. Confirm the drive it found looks right, then `y` to keep it, `q` to quit

This creates a config file, normally at `~/.config/rclone/rclone.conf`
(Windows: `%USERPROFILE%\AppData\Roaming\rclone\rclone.conf`).

**Before moving on, verify it can see your folder:**

```
rclone lsf onedrive:
rclone lsf "onedrive:path/to/your/job-csv-folder"
```

The second command should list your CSV files. Note the exact path you
used - you'll need it in step 5.

### 3. Create the GitHub repository

1. Create a new **public** repo (e.g. `job-calendar-sync`) and commit all
   the files from this project.
2. **Settings -> Pages -> Source -> Deploy from a branch -> `main` / `docs`.**
   Your calendar URL will be:
   `https://<your-username>.github.io/<repo-name>/calendar.ics`

### 4. Create a GitHub Personal Access Token (so the workflow can keep its own token fresh)

rclone's Microsoft sign-in token needs to refresh itself periodically. So
that the workflow can save its refreshed token back into your repo secrets
automatically (rather than ever needing you to re-authorize by hand),
create a **fine-grained personal access token**: **Settings -> Developer
settings -> Personal access tokens -> Fine-grained tokens** - scope it to
just this repository, with **read/write access to "Secrets"**.

### 5. Add repository secrets

**Settings -> Secrets and variables -> Actions -> New repository secret:**

| Secret name | Value |
|---|---|
| `RCLONE_CONFIG` | The entire contents of the `rclone.conf` file from step 2 |
| `ONEDRIVE_FOLDER_PATH` | The folder path you confirmed in step 2, e.g. `Documents/Jobs` |
| `SECRETS_PAT` | The token from step 4 |

### 6. Run it

**Actions tab -> Sync OneDrive CSVs to ICS -> Run workflow**, to test it
manually the first time. Confirm `data/` fills up with your CSVs and
`docs/calendar.ics` gets rebuilt and committed. After that, it runs
automatically every 15 minutes with no further input from you.

### 7. Subscribe from Google Calendar

**Other calendars (+) -> From URL** -> paste your Pages URL from step 3 ->
**Add calendar**.

---

## Things worth knowing

**Refresh speed on the calendar-app side.** This pipeline can update
`calendar.ics` within about 15 minutes of a OneDrive change. However,
**Google Calendar controls its own polling schedule for subscribed ICS
URLs - typically once every 12-24 hours - and there's no setting to speed
that up.** This is a Google limitation, not something this pipeline can
fix, and it applies to Apple Calendar and Outlook subscriptions too.

**What you're approving in step 2.** rclone's OneDrive app requests broad
delegated file access (the same level of access as using OneDrive normally
in a browser) - it's confined to what your own account can already see,
but it's read/write, not read-only, even though this pipeline only ever
reads. If that matters to you, it's worth knowing before you approve it.

**If the tenant restricts user consent for third-party apps**, and you hit
a blocker during step 2's browser sign-in, you can approve rclone's app for
yourself as a tenant admin even if that policy is on for regular users.

---

## File overview

- `scripts/generate_ics.py` - rebuilds `docs/calendar.ics` from every CSV
  currently in `data/`.
- `.github/workflows/sync.yml` - runs every 15 minutes: mirrors OneDrive
  into `data/` via rclone, persists any refreshed token, rebuilds the ICS,
  and commits if anything changed.
- `requirements.txt` - Python dependency (`icalendar`).
- `data/` - mirror of your OneDrive folder's CSVs, kept in sync by rclone.
- `docs/calendar.ics` - the generated calendar (this is the file your phone
  subscribes to).

## CSV format assumed

Based on `JN090.csv`:

```
Task ID,Subject,Start Date,End Date,Start Time,End Time
JN090-001,[JN090] Signed acceptance proposal,09/09/26,09/09/26,14:30,15:30
```

- Dates are `DD/MM/YY` (Australian format).
- Times are 24-hour `HH:MM`.
- `Task ID` becomes the event's unique ID (UID) - this is what lets edits
  replace the old event instead of duplicating it.
- The CSV's filename (without `.csv`) becomes the event's **category**, so
  you can filter/color by job in calendar apps that support ICS categories.
- All 6 columns map into the ICS event as described in the script's docstring.

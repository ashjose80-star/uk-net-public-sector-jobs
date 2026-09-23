# UK .NET Public Sector Jobs — daily updater

This version is designed to run as a small static web app with a scheduled data updater.

## What it does

- The web form loads `jobs.json` when hosted.
- The page displays the last data-update time and has a **Refresh** button.
- GitHub Actions runs the updater every day at **06:00 UTC**.
- The updater searches UK government and higher-education job domains for C#/.NET vacancies.
- New automated results are labelled **Automated daily search lead; verify employer vacancy**.
- Existing manually verified records are preserved.

The original app's vacancy data is retained as the initial dataset.

## Setup

1. Put these files in a GitHub repository:
   - `UK_NET_Public_Sector_Jobs_Web_Form.html`
   - `jobs.json`
   - `update_jobs.py`
   - `.github/workflows/daily-jobs.yml`
2. Create a Serper.dev API key.
3. In GitHub: **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `SERPER_API_KEY`
   - Value: your Serper API key
4. Run the workflow once with **Actions → Daily UK .NET public-sector jobs update → Run workflow**.
5. Enable GitHub Pages for the repository if you want the form hosted as a website.

## Important

A plain HTML file cannot wake itself up and perform a search every day when nobody has the page open. The scheduled GitHub Action provides the server-side daily job that updates `jobs.json`; the form then reads that updated file.

Search results are automated leads and should be checked against the employer's vacancy page before being treated as verified. Coverage is not guaranteed to include every UK public-sector employer or vacancy.

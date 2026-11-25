# Phase 2.5: step-by-step on your PC

Expected time: about 2–3 hours, most of it in Power BI. Do the parts in order. **Part A has to come before Part B.** Loading data while the live app still runs the old code would break the live "Public history".

---

## Part A: Merge and deploy the new code (10 min)

1. Open the pull request from branch `claude/jolly-brahmagupta-gwgvm7` into `main`. You can ask Claude to open it, or open it on GitHub yourself: **Pull requests → New → compare: claude/jolly-brahmagupta-gwgvm7**.
2. Wait for the **Demo checks** to turn green (Python 3.12 and 3.14).
3. Merge with **Squash and merge**. Streamlit Cloud redeploys the live app from `main` by itself.
4. Open the live app → 🤖 AI Controller. Check that the "📚 Public history" section shows your old runs.
5. Click **▶ Try example: DEMO_DP_N5**, then **✅ Approve**. You should see "Added to the public history". This first run also upgrades the Neon database, adding the new column and views.

## Part B: Load the synthetic portfolio into Neon (10 min)

6. On your PC, open PowerShell in the project folder and get the merged code:

```powershell
cd C:\Users\newga\projects\infrastructure-analytics-demo
git checkout main
git pull
.venv\Scripts\Activate.ps1
python -m pip install --only-binary=:all: -r requirements.lock
```

7. Check that `.streamlit\secrets.toml` contains your Neon string: `DATABASE_URL = "postgresql://..."`.
8. Load:

```powershell
python -m scripts.portfolio --load
```

   You should see: `Loaded 31 synthetic statements and 217 findings.`
   If it times out, Neon was asleep; run it again.
9. Check in Neon: go to **console.neon.tech** → your project → **SQL Editor** and run:

```sql
SELECT COUNT(*) FROM v_portfolio_statements;   -- 31
SELECT SUM(billed_ttc) FROM v_portfolio_projects; -- 14412710.00
```

## Part C: Create the read-only Power BI login (5 min)

10. Make a strong password in PowerShell and save it in your password manager:

```powershell
-join ((48..57)+(65..90)+(97..122) | Get-Random -Count 32 | ForEach-Object {[char]$_})
```

11. Open `powerbi\readonly_role.sql` in VS Code and copy it **without saving** the password into the file. Paste it into the Neon **SQL Editor** and replace `REPLACE-WITH-A-LONG-RANDOM-PASSWORD` there with your password.
12. If your database is not called `neondb` (look at the end of your connection string), change that word too. Click **Run**.
13. Check that it worked:

```sql
SELECT table_name FROM information_schema.role_table_grants WHERE grantee = 'powerbi_reader';
```

   You should see exactly the 5 `v_...` views.

## Part D: Connect Power BI Desktop (15 min)

14. Install **Power BI Desktop** (free) from the Microsoft Store, if you don't have it.
15. Find the server name: in Neon, click **Connect**, turn **Connection pooling OFF**, and copy only the host. It looks like `ep-xxxx-xxxx.<region>.aws.neon.tech`, without `-pooler`, `https://` or `/neondb`.
16. In Power BI: **Home → Get data → More… → Database → PostgreSQL database → Connect**.
    - Server: the host from step 15.
    - Database: `neondb`.
    - Data connectivity mode: **Import** → OK.
17. On the credentials window, choose the **Database** tab. User: `powerbi_reader`, Password: yours → Connect.
18. In the Navigator, tick the 5 views:
    - `v_controller_decisions`
    - `v_controller_findings`
    - `v_portfolio_projects`
    - `v_portfolio_statements`
    - `v_portfolio_findings`

    Click **Transform data**, not Load.
19. In Power Query, set the column types for each query by clicking the type icon in the column header:
    - **Fixed decimal number:** `works`, `previous`, `cumulative`, `retention`, `net`, `vat`, `ttc`, `cumulative_ttc_billed`, `contract_ttc`, `billed_ttc`, `stated`, `expected`, `difference`.
    - **Decimal number:** `days_to_decision`, `minutes_to_decision`.
    - **Date/Time:** every `..._at` column. **Date:** `start_date`.
20. **Home → Close & Apply.**
21. **File → Save as** `powerbi\infrastructure_dashboard.pbix`.

*No Neon or no internet?* Use **Get data → Text/CSV** with the three files in `powerbi\data\`, choosing File origin `65001: Unicode (UTF-8)`. That gives you pages 2–4. If decimals look wrong (for example `1234.50` read as `123450`), use **Change type → Using locale… → English (United States)**.

## Part E: Model, measures and theme (20 min)

22. Click the **Model view** icon on the left. Drag the fields to create these relationships. All are *one-to-many*, single direction.
    - `v_portfolio_projects[project]` → `v_portfolio_statements[project]`
    - `v_portfolio_statements[statement_id]` → `v_portfolio_findings[statement_id]`
    - `v_controller_decisions[id]` → `v_controller_findings[run_id]`

    Delete any other relationship Power BI created by itself.
23. Open `powerbi\measures.dax` in VS Code. For each block `table | Name = formula`:
    - select that table in the **Data** pane;
    - click **Home → New measure**;
    - paste `Name = formula`, leaving out the `table |` part, and press Enter.
24. Format the measures by selecting each one and using the **Measure tools** ribbon:
    - money measures: Fixed decimal with 2 decimals and the thousands separator on;
    - `Approval Rate`, `AI Text Share`, `% Contract Billed` and `% Decided Within Target`: **Percentage** with 2 decimals.
25. Click **View → Themes → Browse for themes** and pick `powerbi\theme.json`.

## Part F: Build the 4 pages (60–90 min)

Every page has the same layout: a row of **Cards** at the top, charts in the middle, and the source label card at the bottom. Rename each page by double-clicking its tab.

26. **Page 1: Live app activity**
    - Cards: `Runs Saved`, `Approval Rate`, `Problems Flagged`, `AI Text Share`, `Median Minutes to Decision`.
    - Clustered column: X = `v_controller_decisions[decided_at]` (Date hierarchy → Day), Y = `Runs Saved`.
    - Stacked bar: Y = `file_name`, X = `Runs Saved`, Legend = `decision`.
    - Bar: Y = `v_controller_findings[check_group]`, X = `Live Review Findings`.
    - Footer card: `Source Label Live`.
27. **Page 2: Portfolio overview**
    - Cards: `Contract Value`, `Billed TTC`, `% Contract Billed`, `Pending Statements`.
    - Clustered bar: Y = `v_portfolio_projects[project]`, X = `Contract Value` and `Billed TTC`.
    - Line chart: X = `statement_number`, Y = `cumulative_ttc_billed` (set the aggregation to **Maximum**), Legend = `v_portfolio_statements[project]`.
    - Slicers: `v_portfolio_projects[contractor]` and `v_portfolio_projects[project]`. Use the slicers from this table only.
    - Footer card: `Source Label Portfolio`.
28. **Page 3: Findings**
    - Matrix: Rows = `v_portfolio_projects[contractor]`, Columns = `v_portfolio_findings[check_group]`, Values = `Review Findings`. Then go to **Format → Cell elements → Background color → on**.
    - Bar: Y = `check_group`, X = `Difference Amount DH`.
    - Table: `project`, `statement_number`, `title`, `stated`, `expected`, `difference`, `evidence`. In the Filters pane, add `severity` is `REVIEW`.
    - Same slicers as page 2 (copy and paste them, then choose **Sync**). Add the footer card.
29. **Page 4: Approval speed**
    - Cards: `Median Days to Decision`, `% Decided Within Target`, `Rejected Statements`.
    - Bar: Y = `v_portfolio_projects[contractor]`, X = `Median Days to Decision`.
    - Stacked column: X = `contractor`, Y = `Statements`, Legend = `decision`.
    - Scatter: X = `statement_number`, Y = `days_to_decision` (**Don't summarize**), Legend = `project`.
    - Add the slicers and the footer card.
30. **Save** with Ctrl+S.

## Part G: Check the numbers (15 min)

31. Clear all slicers and compare the cards with `powerbi\expected_totals.json`:

| Card | Must show |
|---|---|
| Contract Value | 18,600,000.00 |
| Billed TTC | 14,412,710.00 |
| % Contract Billed | 77.49 % |
| Statements / Pending / Rejected | 31 / 2 / 11 |
| Review Findings | 15 |
| Median Days to Decision | 3.99 |
| % Decided Within Target | 65.52 % |

32. Select each contractor in the slicer and compare the cards with the `contractors` part of the JSON (review findings and median days). Then do the same for each project with `projects` (billed and %).
33. On page 1, the `Runs Saved` count must equal "Runs saved" in the live app's Public history. Click **Home → Refresh** first.
34. *(Optional, with the finance plugins on your PC)*: on page 2, click **⋯ → Export data** on the bar chart to get a CSV. Ask Claude with the Excel-check skill to compare it with `expected_totals.json`.
35. **If a number differs**, look first at the relationships (step 22), the slicer table (step 27) and the column types (step 19). Never type a number in by hand.

## Part H: Screenshots, PDF and LinkedIn (20 min)

36. Make the window full screen and hide the panes: **View → Filters / Visualizations / Data → collapse**.
37. Take one screenshot per page with **Win + Shift + S** → window snip. Save them in `screenshots\` as:
    - `powerbi_1_live.png`
    - `powerbi_2_overview.png`
    - `powerbi_3_findings.png`
    - `powerbi_4_speed.png`
38. Make the PDF: **File → Export → Export to PDF**, and save it as `powerbi\infrastructure_dashboard.pdf`. Open it and check that every page shows its source label.
39. *(Optional)* Record a 30–60 second video with **Win + Alt + R** (Xbox Game Bar), clicking through the slicers.
40. Before publishing, check that every image shows "Synthetic portfolio — generated, not real" or "Live app history — synthetic examples only", and that no password or connection string is visible.
41. Commit to the repo:

```powershell
git checkout -b feat/powerbi-screenshots
git add screenshots\powerbi_*.png powerbi\infrastructure_dashboard.pdf
git commit -m "docs: Power BI dashboard screenshots and PDF"
git push -u origin feat/powerbi-screenshots
```

   Committing the `.pbix` is optional. It stores no password, but open **File → Options → Data source settings** once to make sure.
42. For the LinkedIn post, use the screenshots, the PDF or the video, and the live app link. Say clearly that the data is synthetic.
43. *(Optional)* With a university Microsoft 365 account, use **Home → Publish** to a workspace and share it with your professors. Don't use "Publish to web" unless your university allows it.

Done. Tell Claude about any step that failed, with the exact error message.

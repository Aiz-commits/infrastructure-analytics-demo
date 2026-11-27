# AI Controller by email — how it works (Phase 3)

A short guide for the people who receive and approve construction progress statements (décomptes).
No coding needed to use it. Setup is at the end.

> Demo only. Use synthetic files, never real company data.

## 1. What it does, in one paragraph

You (or a contractor) email a décompte to a dedicated inbox. A few seconds later your phone shows an alert such as
**"Décompte D5 — 2 à vérifier"**. You tap it, see what was checked and why, type your PIN, and press
**Approve** or **Reject**. Nothing is ever paid or emailed to anyone automatically: a person always decides.

```
 Email with the décompte ─▶ n8n (watches the inbox) ─▶ AI Controller on the PC ─▶ alert on your phone
                                                          │  reads the values           │
                                                          │  AI picks the checks        ▼
                                                          │  Python does the maths   Review page + PIN
                                                          └─ drafts memo and email   ─▶ Approve / Reject
```

## 2. Who does what

| Step | Done by | What it means for you |
|---|---|---|
| Read the file (Excel, PDF or photo) | Python, with AI help for unusual layouts, PDFs and photos | If the AI read the numbers, the page asks you to compare them with the file before approving |
| Choose the checks | **AI** | The AI picks which checks this décompte needs and says why it skipped any |
| Calculate | **Python only** | The AI never calculates an amount. Every number on the page comes from Python |
| Make sure nothing is missed | **Guard (Python)** | If the AI forgets a core check, the guard runs it anyway and the page says so |
| Draft the memo and email | AI, numbers checked by Python | If the AI writes a number that is not in the results, a standard template is used instead |
| Decide | **You** | Approve or Reject, with your PIN |

The **core checks** that always run: retention, net amount, VAT, total TTC, cumulative amount, and history
(continuity with the previous décompte and no missing statement number). The optional **contract ceiling** check
tells you if the total billed so far is above the contract value.

## 3. The alert on your phone

- **Title:** `Décompte D5 — 2 à vérifier` = statement number 5, two points need your attention.
- **Message:** project, counts, and — for PDFs and photos — a reminder to compare the values with the document.
- **Tap it** (or press **Ouvrir**) to open the review page. Your phone must be on the same Wi-Fi as the PC.
- **"Décompte non traité"** means the file could not be processed (for example a picture that is not a décompte,
  or the AI was busy). Nothing waits for you; fix the file or send it again later.

The alert never contains amounts, only counts.

## 4. The review page, top to bottom

1. **Status:** project, statement number, how many points to review and how many warnings.
2. **Ce qui s'est passé / What happened:** every step in plain words — when the email arrived, how the values were
   read, which checks the AI chose, any check **added by the guard**, the AI's reason for skipping a check, and who
   wrote the memo.
3. **Values read:** each amount, where it was found in the file, and its source. "(incertain)" means the label next
   to the number did not match what we expected.
4. **Checks:** one line per check.

   | Word on the page | Meaning |
   |---|---|
   | ✅ Conforme / OK | The numbers agree (within 0.01 DH) |
   | ⚠️ À vérifier / Review | The numbers do not agree — ask the contractor to justify the difference shown |
   | ⚠️ Attention / Warning | A value was not found or its label is uncertain — check the file |
   | ⏭️ Non vérifié / Skipped | The check could not run (a value is missing, or no previous décompte) |

5. **Memo and email drafts.** They are drafts: nothing is sent.
6. **Open the file received**, to compare with the values.
7. **PIN, Approve, Reject.**

### Rules that protect you

- **PIN:** the link alone only lets someone *look*. Approve or Reject needs your 6-digit PIN.
  After **5 wrong PINs** the review locks; send the email again to get a new one.
- **One decision per décompte.** After you decide, the page becomes read-only and shows who decided and when.
- **Links expire after 48 hours** if nobody decided.
- **Values cannot be edited on the phone.** If a value is wrong: Reject, correct the file, and email it again.
- **AI-read values** (PDF, photo, unusual Excel layout) need the box *"J'ai comparé ces valeurs avec le document
  joint"* ticked before Approve works.
- **Only listed senders** are processed. Emails from anyone else are ignored: no AI call, no alert.

### What Approve does (and does not do)

- It records your decision with the date and time.
- For the bundled demo files only, it adds the run to the public history on the live demo site
  (marked "via email"). Your own files stay on the PC.
- It does **not** send the email to the contractor and does **not** pay anything.

## 5. Setup (once, about 20 minutes)

You need: this repository on a Windows PC, its `.venv`, n8n (see "Every time you use it" below), and a phone with
the **ntfy** app.

1. **Demo inbox.** Create a new Gmail account for the demo. Turn on 2-Step Verification, then create an
   **App password** (Google Account → Security → App passwords). Keep it for step 5.
2. **Phone app.** Install **ntfy** (Android / iPhone). Tap **+**, subscribe to your private topic name
   (a long random name — it works like a password, do not share it).
3. **Secrets file.** Add these lines to `.streamlit\secrets.toml` (never committed to GitHub):

   ```toml
   AGENT_API_KEY = "a long random string, 32+ characters"
   REVIEWER_PIN = "6 digits of your choice"
   ALLOWED_SENDERS = ["the-address-you-send-from@example.com"]
   REVIEW_BASE_URL = "http://<your PC's Wi-Fi IP>:8000"
   ```

   Find the IP with `ipconfig` (line "IPv4 Address" under Wi-Fi). If your router gives the PC a new IP later,
   update this line.
4. **Install the API parts:**

   ```powershell
   .venv\Scripts\python.exe -m pip install -r requirements-api.txt
   ```

5. **n8n workflow.** Start n8n (below), open http://localhost:5678, then **Import from File** →
   `automation\n8n\decompte_inbox.json`. In the workflow:
   - Replace `REPLACE_WITH_YOUR_SENDER_EMAIL` (node *Allowed sender + décompte files*) with the same address as
     `ALLOWED_SENDERS`.
   - Replace `REPLACE_WITH_YOUR_NTFY_TOPIC` (both *Phone alert* nodes) with your topic.
   - Node *Demo Gmail inbox* → new **IMAP** credential: user = demo Gmail address, password = App password,
     host `imap.gmail.com`, port `993`, SSL on.
   - Node *Send to AI Controller API* → new **Header Auth** credential: name `X-API-Key`, value = your
     `AGENT_API_KEY`.
   - Save, then switch the workflow to **Active / Published**.
6. **Let the phone reach the PC.** Windows → Settings → Network & internet → Wi-Fi → your network → set
   **Private network** (only on your home Wi-Fi). Then, in PowerShell **as administrator**:

   ```powershell
   New-NetFirewallRule -DisplayName "AI Controller API" -Direction Inbound -Protocol TCP -LocalPort 8000 -Profile Private -Action Allow
   ```

### Every time you use it

Open two PowerShell windows. In each one, first go to the project folder (change the path if yours is different):

```powershell
cd $env:USERPROFILE\projects\infrastructure-analytics-demo
```

Then run one of these per window:

```powershell
powershell -ExecutionPolicy Bypass -File automation\start_n8n.ps1
```

```powershell
powershell -ExecutionPolicy Bypass -File automation\start_api.ps1
```

Keep both windows open. Then email a décompte (for a first test, `controller_examples\DEMO_DP_N5.xlsx`) from an
allowed address to the demo inbox. The inbox is checked about once a minute.

## 6. Troubleshooting

| Problem | Likely cause | Fix |
|---|---|---|
| No alert at all | n8n or the API window is closed; workflow not active; sender not on the list | Start both windows; activate the workflow; check `ALLOWED_SENDERS` and the address in the n8n code node |
| "Décompte non traité" | The attachment is not a décompte (e.g. an email signature logo), or AI reading was busy | Send only the décompte; try again in a few minutes |
| The link does not open on the phone | Phone not on the same Wi-Fi, firewall rule missing, PC IP changed | Same Wi-Fi; redo setup step 6; update `REVIEW_BASE_URL` and restart the API |
| "This link has expired." | More than 48 hours passed | Email the décompte again |
| "Verrouillé / Locked" | 5 wrong PINs | Email the décompte again; check your PIN in `secrets.toml` |
| Page says "IA indisponible" (AI unavailable) | Free Gemini quota reached | Nothing to do: Python ran every core check anyway |
| API window closes at start with a message about `secrets.toml` | A line in step 3 is missing or wrong | Fix the line named in the message |

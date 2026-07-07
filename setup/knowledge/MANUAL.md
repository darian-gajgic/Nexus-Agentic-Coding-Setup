# USER MANUAL — How to work with our AI team

**Who this is for:** anyone in our team, including with zero IT knowledge. Everything you need
to type is shown in gray boxes — you copy it exactly and press Enter. You cannot break
anything by chatting with the system. *(Deutsche Kurzanleitung: ganz unten, Abschnitt 11.)*

---

## 1. What you actually have (in plain words)

Think of it as a small company that works for us:

- **Sinepal (Hermes)** — your assistant. You chat with it. For real work it quietly hands the
  task to one of **18 specialists** (a copywriter, a listing optimizer, a DJ-set curator, a
  market researcher…). Each specialist follows a professional playbook and checks its own work
  against a quality checklist before showing you anything.
- **The Business Brain** (`~/knowledge`) — the company handbook: how a pro does marketing,
  e-commerce, branding, music releases… plus facts about OUR business. The AI reads it before
  working. You never need to open it — but you can, everything in it is readable.
- **The Judge** — a second, much smarter AI (Claude) that double-checks important work before
  it goes out. You have to ask for it (see section 4).
- **Nexus** — the control room in your web browser. Shows what the agents are doing, their
  memory, tasks, and has **JARVIS** — a voice assistant tab.

Two AI "engines" power this: a fast affordable one (GLM) that does the everyday work, and a
premium one (Claude) used for judging and the hardest thinking. That's on purpose — like
letting a senior review the junior's work.

---

## 2. The two doors into the system

### Door A — Nexus in the browser (easiest)

1. Open Firefox or Chrome.
2. Go to: **https://127.0.0.1:8777**
3. **First time only:** the browser shows a security warning ("potential risk" / "not
   private"). That is normal — this page runs only on our own laptop, the browser just
   doesn't know our self-made certificate. Click **Advanced → Accept the Risk / Proceed**.
4. You'll see tabs across the top: agents overview, Specialists, Kanban (task board),
   Memory Hub, and **JARVIS** — click JARVIS to talk with your voice.

**Run real work from the task board (since 2026-07-06 the board is REAL — cards are executed
by actual AI sessions, not simulated):**

1. **Kanban tab → "+ New Task".** Pick a **template** at the top (landing hero, marketplace
   listing, social post, research, DJ set) — it prefills everything; replace the `[brackets]`
   with your specifics. Or start blank: title + what you want, pick a **Domain** (that's which
   playbook the AI follows) and optionally a **Specialist**. Tick **⚖ High-stakes** for
   anything going to real customers — high-stakes work pauses for your approval before it
   counts as done.
2. Put the card in **Todo**. A free agent lane picks it up by itself within seconds (or open
   the card and press **▶ Dispatch**). Watch the card: `streaming` means the AI is working;
   the Agents tab shows what it's writing live.
3. When the card lands in **Done** (or **Review** for high-stakes): open it. You'll see the
   deliverable **files** (click to download), the specialist's **self-score**, and a
   **Learn** panel — that part is for you two.
4. **High-stakes flow:** the card waits in Review and the **⚙ Agentic tab** shows a pending
   approval (red badge on the tab). Open the task → **⚖ Run frontier judge** → in 1–3 minutes
   you get **SHIP / REVISE / REWRITE** with the exact blockers. Then Approve (ships it) or
   Reject (one click sends it back with the judge's feedback attached — the AI retries fresh).
5. When something wins or flops in the real world: open the task → **🏆 Log WIN** /
   **📓 Log LESSON**. Wins need the real numbers — never invent them.
6. **⚙ Agentic tab** also shows **System Health** (a red light always shows the exact command
   to fix it) and **GLM Quota** (if you see an orange "quota storm" banner: nothing is broken —
   tasks wait and retry by themselves).
7. **The lazy (best) way — "✨ Describe a task"** (Kanban toolbar): type what you want in
   plain words (German works) and the AI sets every parameter — specialist, domain, model,
   high-stakes — for your review. Big goals become a whole **project**: see the **⚑ Projects
   tab**, where chained tasks run in order and each agent reads its predecessors' results
   automatically (try "✨ Describe a goal" or the example campaign there).
8. **📦 Deliverables tab** = every output your agents ever produced, in one place — read,
   download, log as WIN/LESSON, or press **➡ Follow-up** to hand a result to the next agent.
9. **Teach the system new tricks:** Skills tab → "＋ New skill (AI wizard)" (reusable how-tos
   for all agents); Specialists tab → "✨ Draft with AI" (new experts) or edit one with
   "✨ Ask AI to revise". You always review before anything goes live.

### Door B — Hermes in the terminal (for real work sessions)

1. Open a terminal: press **Ctrl + Alt + T** (a black window appears — that's all a
   "terminal" is: a chat window for the computer).
2. Type this and press Enter:
   ```
   hermes
   ```
3. Chat normally, in German or English. It answers, delegates to specialists, and shows you
   results. To leave: type `exit` and press Enter (or press Ctrl+C).

> ⚠️ **One rule:** for real work always use plain `hermes` like above. (There is a quick mode
> called `hermes chat -q "..."` — only use it for tiny questions. It closes itself immediately
> after one answer, which kills any specialist that is still working.)

---

## 3. How to ask for work (the recipe)

The AI is good, but it can't read minds. A good request has four parts:

> **What I need + who it's for + any facts it must use + what "good" looks like.**

Copy-paste-able examples:

```
Write an Instagram caption announcing our Friday event. Audience: techno people 20–35 in
[city]. Facts: [venue], [date], doors 23:00, lineup [names]. Good = short, scene-native,
no cheesy hype, German.
```

```
Create a product listing for [product]. Marketplace: [Amazon.de / Etsy / eBay]. Facts:
[size, material, price, what makes it better]. Good = findable in search AND convinces a
buyer who compares us with cheaper rivals.
```

```
Research: is [idea/market] worth entering for us? I need: how big, who dominates, what
customers complain about, and a clear recommendation with reasons and sources.
```

**What comes back** — every proper deliverable ends with two extras:

- a **Rubric** line (e.g. "Rubric: gates 9/9 passed") — the specialist scored its own work
  against the quality checklist before showing you;
- a **Learn:** section — 2–3 bullets explaining WHY it made the key choices. **Read these.**
  That's how we get better at this ourselves.

**If it asks about missing business facts** (product names, audience, prices): answer in the
chat — or better, run the one-time onboarding interview (section 9) so it stops asking.

---

## 4. Important work → call the Judge

For anything that really matters — a proposal to a client, text going to paying customers, a
release, a price change — add one sentence:

```
This is high-stakes. Run the frontier judge on it before we ship.
```

The specialist saves the work to a file and a second, stronger AI tears it apart: pass/fail
gates, scores, the 3 most valuable improvements, and a verdict (SHIP / REVISE / REWRITE).
It takes 1–3 minutes and uses our premium AI budget — so use it for things that matter, not
for every little draft.

---

## 5. Teach the system (takes 30 seconds, makes everything better)

- Something worked in the real world? Tell any agent:
  ```
  Log this win: the [thing] got [real numbers — sales, clicks, opens]. 
  ```
- Something flopped or the AI got it wrong? 
  ```
  Log this lesson: [what happened] — [what we'd do differently].
  ```

Wins become tomorrow's examples the AI learns from. **Never invent numbers** — the system
treats logged results as truth.

---

## 6. Your 10-minute learning routine (how juniors become pros here)

When a specialist delivers something important:

1. **Before** reading its self-score, judge the work yourself: what would you change?
2. Then read the Rubric line and the Learn: bullets — and if the Judge ran, its verdict.
3. Where your opinion differed from the Judge's → that gap is exactly what to learn next.
   Log it: `Log this lesson: I missed that ...`

Do this a few times a week and you're doing deliberate practice with a world-class reviewer.

---

## 7. When something is wrong (don't panic — nothing here is fragile)

| What you see | What it means | What to do |
|---|---|---|
| Hermes doesn't answer / behaves strangely | The background service hiccupped | In a terminal: `systemctl --user restart hermes-gateway` — wait 10 s, try again |
| Nexus page won't load | Dashboard service is down | `systemctl --user restart nexus` — then reload the browser page |
| "429" / "overloaded, try again later" | Usually the GLM provider shedding load at peak times (even when OUR quota shows barely used); sometimes our 5-hour window | Nothing is broken. Nexus tasks wait as "quota ⏸" and retry by themselves. Check Agentic → GLM Quota. Heavy jobs run best in the evening (off-peak). |
| A red "Langfuse/isinstance" line when a chat closes | Harmless known quirk | Ignore |
| "PostHog…" or "spaCy is not installed…" lines | Harmless | Ignore |
| Anything else scary | Unknown | Open a terminal, type `claude`, paste the error text, and ask: "explain and fix this" |

The nuclear option (safe): restart the laptop. Everything starts again by itself.

---

## 8. Safety rules (the only real ones)

1. **Never** share, photograph, or paste anywhere the contents of files ending in `.env` or
   `key.env` — those are our passwords for the AI services.
2. Don't hand-edit files in `~/.hermes`, `~/.claude*`, or `~/nexus-agent-os` — if you want a
   behavior changed, ask the agent or ask Claude to change it properly.
3. Anything that spends money or goes to a real customer: **a human presses the final send.**
   The AI drafts; we decide.
4. If the AI states a fact that matters (a price, a law, a deadline) — ask it: "verify that
   with a live source." It's built to check rather than guess, but you're the last gate.

---

## 9. One-time setup task (if not done yet): the onboarding interview

The AI still uses placeholder examples until it knows OUR business. Fix that once (~20 min,
you can do it together):

```
cd ~/knowledge && claude
```
then say: **"Read ONBOARDING.md and run the onboarding interview."**
Answer its questions (German is fine). After this, everything it produces is tailored to us.

---

## 10. Quick reference card

| I want to… | I type / do |
|---|---|
| Chat / give work | `hermes` in a terminal |
| Use voice | Browser → https://127.0.0.1:8777 → JARVIS tab |
| See what agents are doing | Browser → Nexus tabs |
| Get important work double-checked | add: "run the frontier judge on this" |
| Record a success | "Log this win: … [numbers]" |
| Record a mistake/lesson | "Log this lesson: …" |
| Fix a stuck Hermes | `systemctl --user restart hermes-gateway` |
| Fix a stuck Nexus | `systemctl --user restart nexus` |
| Ask the premium AI directly | `claude` in a terminal |
| Understand any file/error | paste it into `claude` and ask |

---

## 11. Deutsche Kurzanleitung

**Was das ist:** Ein KI-Team für unsere Arbeit. *Sinepal* (im Terminal: `hermes`) ist dein
Assistent — er gibt Aufgaben an 18 Spezialisten weiter (Texte, Listings, Marketing, Musik…).
Jeder Spezialist arbeitet nach Profi-Playbooks und prüft sich selbst. Für wichtige Sachen gibt
es einen "Richter" (eine stärkere KI), der alles gegenprüft. *Nexus* ist das Kontrollzentrum
im Browser, inkl. Sprachassistent JARVIS.

**So startest du:**
1. Terminal öffnen: **Strg + Alt + T**
2. `hermes` eintippen, Enter. Dann ganz normal schreiben — Deutsch geht.
   Beenden: `exit` eintippen.
3. Oder im Browser: **https://127.0.0.1:8777** öffnen (die Sicherheitswarnung beim ersten Mal
   ist normal: „Erweitert" → „Risiko akzeptieren"). JARVIS-Tab = mit Stimme sprechen.

**Arbeiten über das Aufgaben-Board (Nexus → Kanban) — seit 06.07.2026 ECHT, keine Simulation:**
1. **Kanban → „+ New Task"**: oben eine **Vorlage** wählen (Landing-Page, Marktplatz-Listing,
   Social Post, Recherche, DJ-Set) und die `[Klammern]` mit deinen Angaben ersetzen.
   **Domain** = welches Profi-Playbook gilt. **⚖ High-stakes** ankreuzen bei allem, was zu
   echten Kunden geht — dann wartet das Ergebnis auf deine Freigabe.
2. Karte auf **Todo** ziehen — ein freier Agent nimmt sie sich automatisch. „streaming" =
   die KI arbeitet gerade.
3. Fertig? Karte öffnen: **Dateien** zum Download, Selbstbewertung, und ein **Learn**-Feld
   (das ist für euch zwei zum Lernen).
4. **Wichtige Arbeit (High-stakes):** Karte öffnen → **⚖ Run frontier judge** → nach 1–3 Min
   kommt **SHIP / REVISE / REWRITE** mit den genauen Mängeln. Dann **Approve** (freigeben)
   oder **Reject** (geht mit dem Feedback automatisch zurück zur KI — neuer Versuch).
5. **🏆 Log WIN / 📓 Log LESSON** direkt an der Karte — bei Wins immer die ECHTEN Zahlen.
6. Oranges Banner „quota storm"? Nichts kaputt — Aufgaben warten und starten von selbst neu.
   Ampeln + Reparatur-Befehle: Tab **⚙ Agentic → System Health**.

**So fragst du richtig:** Was ich brauche + für wen + Fakten + was „gut" bedeutet.
Beispiel: *„Schreib eine Instagram-Caption für unser Event am [Datum] in [Stadt]. Zielgruppe:
Techno-Leute 20–35. Fakten: [Venue, Lineup, Uhrzeit]. Gut = kurz, szenig, kein Werbe-Kitsch,
auf Deutsch."*

**Wichtige Arbeit?** Schreib dazu: *„Das ist wichtig — lass den Frontier-Judge drüberschauen,
bevor wir es rausschicken."*

**Erfolge/Fehler melden (macht das System schlauer):**
*„Log this win: … [echte Zahlen]"* / *„Log this lesson: …"* — niemals Zahlen erfinden.

**Wenn was klemmt:** Terminal öffnen und eintippen:
`systemctl --user restart hermes-gateway` (Assistent neu starten) oder
`systemctl --user restart nexus` (Dashboard neu starten).
Meldung „429 / overloaded" = unser KI-Kontingent-Fenster ist voll → ein, zwei Stunden warten.
Alles andere: `claude` öffnen, Fehlertext einfügen, „erklär und behebe das bitte" schreiben.

**Sicherheitsregeln:** Dateien mit `.env`/`key.env` nie teilen (das sind Passwörter). Nichts in
`~/.hermes` oder `~/.claude` von Hand ändern — die KI darum bitten. Alles, was Geld kostet
oder an echte Kunden geht: ein Mensch drückt am Ende auf Senden.

**Einmalig, falls noch nicht gemacht (~20 Min):** Terminal → `cd ~/knowledge && claude` →
sagen: *„Read ONBOARDING.md and run the onboarding interview."* Danach kennt das System unser
Business und liefert maßgeschneiderte Ergebnisse statt Platzhalter.

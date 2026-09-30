# SPEC-09: Business Model, App Licensing and Distribution

**Project:** Plugin Dependency Scanner (working name: "Rackcheck")
**Related:** SPEC-05 (distribution), SPEC-07 (legal, privacy)
**Status:** Draft v1, September 2026. Contains open decisions marked **DECIDE**.

How the app makes money (if it does), how licenses work, and how it reaches users. This affects the architecture (feature gating, license checks), so decide it before Phase 2 ships.

---

## 1. Positioning

- **For:** producers who collaborate, send projects to mix/master engineers, move between computers, or open old projects.
- **Promise:** "Drop a project, see exactly what it needs."
- **Differentiators vs existing tools:** cross-platform (Windows + macOS), many DAWs, collaboration features (compare, send pack), honest confidence markers.
- **Tone:** made by a producer for producers. The research behind this project found strong resentment toward heavy licensing (iLok and similar). Our own licensing must be the opposite: painless, offline-friendly, no dongles. Use that in marketing.

---

## 2. Model options

**DECIDE** one of these before Phase 2.

| Option | How it works | Pros | Cons |
|---|---|---|---|
| A. Free core + paid Pro (one-time) | Core scanning free forever; Pro features unlocked with a one-time purchase that includes 1 year of feature updates, then optional upgrade pricing | Familiar to plugin buyers; fair; free tier spreads by word of mouth | Revenue lumpy; must keep adding Pro value |
| B. Free core + Pro subscription | Same split, monthly/yearly | Predictable revenue | Producers are subscription-weary; weakest fit with the "painless" positioning |
| C. Fully free, donations/sponsorship | Everything free, open core optional | Maximum adoption and goodwill | Hard to fund KB upkeep and signing costs long term |
| D. Paid only (one-time) | No free tier, trial period | Simple | Much slower adoption for an unknown tool |

**Recommendation: A.** It matches how producers already buy software, and a generous free tier is the best marketing a one-person product can get.

---

## 3. Feature split (if option A)

Principle: **the free tier fully answers the core question** for a single project. Pro saves time and adds collaboration.

| Feature | Free | Pro |
|---|---|---|
| Scan any supported project format | ✓ | ✓ |
| Full report in the app (all tabs, all detected fields) | ✓ | ✓ |
| Installed plugin inventory and missing plugin detection | ✓ | ✓ |
| Homepage and KB info | ✓ | ✓ |
| Export plugin list CSV | ✓ | ✓ |
| Export full report JSON and CSV | **DECIDE** (recommend free: the user explicitly wants full exports, and gating exports feels hostile) | ✓ |
| HTML report | | ✓ |
| Collaborator compare (SPEC-08) | | ✓ |
| Send pack | | ✓ |
| Library scan, cross-project stats, "what if I uninstall" | | ✓ |
| Watch folders / auto-scan on save | | ✓ |
| Scan diff between project versions | | ✓ |
| Priority support | | ✓ |

Receiving side stays free: anyone can open a shared report, requirements file or send pack and compare it against their own machine. That way each Pro user who sends a pack introduces the app to someone new.

---

## 4. Pricing

**DECIDE** after the research below. Placeholder ranges for planning only.

Research before setting prices:
- Price points of comparable utility software producers buy (library managers, DJ library tools, plugin managers, metering/analysis utilities)
- What beta users say they'd pay (ask during the beta, SPEC-06 section 6)

Planning assumptions:
- One-time Pro price in the typical range of small producer utilities, with launch discount
- Upgrade pricing for the next major version at a reduced rate
- Student/educator discount on individual licenses (verification through the payment provider or a student ID service)
- Regional pricing considered later

---

## 5. App licensing (our own DRM, done gently)

- **License key** emailed at purchase and shown in the customer's account page.
- **Activations:** 3 machines per license, deactivate from within the app or the account page anytime. **DECIDE** exact number.
- **Offline-friendly:** activation needs the internet once; after that the app works offline indefinitely. Optional offline activation via a request/response file for machines that are never online (common in studios).
- **No periodic phone-home requirement.** A license check may run with the normal daily update check when online, but never locks features because the check failed.
- **Graceful failure:** if anything goes wrong with licensing, Pro features keep working and a banner explains how to fix it. Never block a scan.
- **Implementation:** use a licensing service or the payment provider's built-in license keys rather than building one. Evaluate options that support offline activation and machine limits. License keys are signed so the app can verify them offline.
- **Architecture impact:** a single `entitlements` module in the engine answers "is feature X enabled?". GUI and CLI both call it. Keep all gating in one place so the split in section 3 can change without code spread everywhere.

---

## 6. Payments and taxes

- Use a **merchant of record** payment provider (it becomes the legal seller and handles sales tax/VAT/GST collection worldwide). This removes most tax admin for a solo seller. Compare fees, payout options in CAD, license key support, and refund handling.
- Refund policy: **DECIDE** (recommend 30 days, no questions asked; low refund abuse risk and builds trust).
- Receipts and invoices generated by the provider.
- Confirm with an accountant: business registration, GST/HST registration requirements, and how merchant-of-record payouts are reported (SPEC-07 section 4.6).

---

## 7. Distribution

- **Own website** with direct downloads (signed installers, SPEC-05). Not the Mac App Store (sandbox limits, SPEC-05 section 3) and not the Microsoft Store initially.
- **Website must have:** clear supported DAW/version list (generated from the coverage matrix, SPEC-06), privacy policy, EULA, download links, a short demo video, changelog, and a "what we never collect" section.
- **Listings:** KVR Audio product database, AlternativeTo, relevant GitHub topics for the open-source parts (KB repo).

---

## 8. Launch and marketing

**Pre-launch**
- Beta program recruited from producer communities (Reddit DAW subreddits, KVR, Gearspace, Discord servers for each DAW). Follow each community's self-promotion rules.
- Build in public: short posts/videos showing a real problem solved ("my collaborator couldn't open my project, here's why in 5 seconds").

**Launch**
- Launch discount on Pro.
- Reach out to producer-focused blogs and YouTube channels that cover free and utility tools. Free tier makes coverage easy.
- Post the KB as an open project; contributors become advocates.

**Ongoing**
- Every supported DAW update gets a "Rackcheck supports <DAW> <version>" post.
- Case-study content from mix engineers (they receive the most broken projects and are natural evangelists).

---

## 9. Metrics

Keep them privacy-respecting: derived from downloads, purchases, website analytics (cookie-free), and voluntary feedback. No in-app analytics (SPEC-07).

| Metric | Source |
|---|---|
| Downloads per release per platform | Download host |
| Free to Pro conversion | Payment provider vs downloads |
| Refund rate | Payment provider |
| Unknown plugin report volume (opt-in) | KB server |
| Support requests per release | Inbox |
| KB contributions per month | GitHub |

---

## 10. Costs to plan for

| Item | Notes |
|---|---|
| Apple Developer Program | Yearly fee |
| Windows code signing | Azure Artifact Signing monthly fee, or CA certificate + token (SPEC-05) |
| Domain, website hosting, download bandwidth | Send packs are local, so bandwidth is only for installers and KB |
| KB / update / report server | Small static hosting plus a tiny endpoint for opt-in reports |
| Payment provider fees | Percentage + per-transaction fee |
| Legal review | EULA, privacy policy, RE review (SPEC-07) |
| Accountant | Business setup and tax |
| Test DAW licenses | Need each supported DAW (and versions) to build fixtures (SPEC-06); some vendors offer developer/NFR licenses on request |

---

## 11. Open decisions summary

- [ ] Business model (section 2)
- [ ] Final free/Pro split, especially full exports (section 3)
- [ ] Prices and discounts (section 4)
- [ ] Activation count (section 5)
- [ ] Licensing service and payment provider (sections 5, 6)
- [ ] Refund policy (section 6)
- [ ] Product name (working name "Rackcheck"; check trademark and domain availability before committing)

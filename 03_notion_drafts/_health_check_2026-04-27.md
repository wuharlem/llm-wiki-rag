# 🩺 Wiki Health Check — 2026-04-27

_Scope: 11 concept articles + 4 Risks pages on Notion (parent: **📚 Wiki: AI Safety Knowledge Base**), the 21 source-library indices in `03_notion_drafts/per_folder/`, and the underlying Obsidian vault at `~/Desktop/AI Safety/AI Safety/` (370 .md + 263 .pdf, 633 sources)._

_Method: Read all 11 concept articles end-to-end; cross-checked claims against per_folder/ source listings and the archived pre-refactor wiki; spawned two file-system audit passes over the vault._

---

## TL;DR

The wiki is in **good structural health** — concept articles are substantive (~3-5K words each), cross-linked, and the per_folder/ indices are perfectly synchronized with the vault (zero orphans, zero phantom references). The main issues are **metadata-quality artifacts from the 2026-04-27 bulk ingest**, a handful of **factual claims worth correcting**, and several **high-leverage cross-topic connections that the wiki hasn't yet drawn**.

Severity buckets:

- 🔴 **3 factual bugs** in concept articles (specific quoted claims to fix)
- 🟡 **~10 metadata bugs** in per_folder/ (dates, authors, duplicates) — fixable by re-running the ingest with patched parsers
- 🟢 **8 missing cross-topic links** worth wiring up
- 🟢 **4 new concept-article candidates** (AI Control, Multi-Agent, CoT Monitoring, Sandbagging)
- 🟡 **2 stale claims in Lab Scorecards** that the rest of the wiki has already moved past

---

## 1. 🔴 Factual bugs in concept articles (quote → correction)

### 1.1 Alignment Faking & Scheming — broken parenthetical

**Current text** (Empirical Evidence → Anthropic 2024):

> Complied with harmful queries **12% of the time** (vs. 3% refusal in unmonitored condition)

**Problem.** The parenthetical reads as if 3% is the *refusal* rate in the unmonitored condition. That would mean unmonitored compliance is 97%, which is the opposite of the paper's finding.

**Likely intended.** "12% compliance in monitored vs. ~3% compliance in unmonitored" — the gap is the alignment-faking signal.

**Fix.** Rewrite as: "Complied with harmful queries ~14% of the time when it believed responses would be used for training, vs. ~3% when it believed they would not." (Numbers per the Anthropic Dec 2024 paper.)

### 1.2 Existential Risk & Superintelligence — conflates two separate statements

**Current text** (Precautionary / Prohibitionist):

> **Statement on Superintelligence** (136,000+ signatures including Bengio, Russell, Harari)
> ...
> The Statement on Superintelligence is now in the vault under three URL variants (`AI Safety/Statement_on_AI_Risk_CAIS_*.md`)

**Problem.** Two different artifacts are conflated:

| Artifact | Source | Signatories | URL |
|---|---|---|---|
| **Statement on AI Risk** (CAIS, May 2023) | safe.ai/statement-on-ai-risk | ~350 researchers / leaders | the three `Statement_on_AI_Risk_CAIS_*.md` files |
| **Statement on Superintelligence** (Oct 2025) | superintelligence-statement.org | 136,000+ including Bengio, Russell, Harari | `Statement on Superintelligence.md` |

The 136,000 figure belongs to the latter; the three CAIS files contain the former.

**Fix.** Split into two paragraphs and re-cite the file paths correctly.

### 1.3 RSP article — "RSP v3.0" vs. file naming

The RSP article uses "**RSP v3.0**" in the comparison table and elsewhere. The vault has a file `Responsible Scaling Policy Version 3.0.md` plus an `Anthropics_Responsible_Scaling_Policy_7e83d9fc.md` dated 2026-04-02 sourcing `/rsp-updates`. The article should disambiguate which v3 update is being summarized; right now the framework attributes (ASL-2 through ASL-5, Frontier Safety Roadmap, external Risk Reports) span versions and the reader can't tell which version the Roadmap was added in.

**Fix.** One sentence: "The Frontier Safety Roadmap was introduced in the Oct 2024 v2.0 update and expanded in the Apr 2026 v3.0 refresh."

---

## 2. 🟡 Metadata bugs in `per_folder/` indices

The per_folder/ files are paste-ready Notion content, generated from `01_data/notion_sources.csv`. The ingest left systematic artifacts:

### 2.1 `Published:` field carries ingest dates, not real publication dates

| Entry | per_folder file | Listed | Actual |
|---|---|---|---|
| Statement on AI Risk \| CAIS (×3 dupes) | 01a | 2026-01-01 | May 2023 |
| Pause Giant AI Experiments | 01a | 2025-06-04 | March 2023 |
| The Precipice | 01a | 1996-01-01 | March 2020 |
| 2015: WHAT DO YOU THINK ABOUT MACHINES THAT THINK? | 01a | 2026-04-26 | 2015 (Edge.org) |
| Frontier Models are Capable of In-Context Scheming | 01c | 2026-04-21 | Dec 2024 (Apollo) |
| Stress Testing Deliberative Alignment | 01c | 2026-04-21 | Sep 2025 |
| Statement on AI Risk (3 variants) | 01a | all 2026-01-01 | all May 2023 |

**Pattern.** When the source page didn't expose a `<meta>` publication date, the parser filled in either the ingest date (2026-04-2x) or `YYYY-01-01`. **Recommended fix:** patch `scripts/build_manifest.py` (or wherever the date is extracted) to leave the field blank when no explicit date is found, rather than synthesize one — or fall back to the URL's `archive.org` snapshot date.

### 2.2 `Author:` field is contaminated by Wikipedia/page metadata

5 confirmed examples (likely many more):

- *Technological singularity — Wikipedia* → "Authority control databases National United States Israel Other Yale LUX"
- *CBPAI* → "ThielAntichrist' Collides"
- *Down and Out in the Magic Kingdom — Wikipedia* → "Authority control databases MusicBrainz work MusicBrainz release group Open Library"
- *Friedrich Hayek — Wikipedia* → "Authority control databases"
- *Key Components of an RSP* (METR) → "CONTRIBUTORS Beth Barnes" (boilerplate prefix should be stripped)

**Recommended fix.** Add a strip-prefix list to the author parser: `["CONTRIBUTORS ", "Authors: ", "By "]`; for Wikipedia pages, blank the author field instead of taking the page footer.

### 2.3 Cross-folder duplicates with conflicting metadata

The most striking case is **Why Would AI "Aim" To Defeat Humanity?** (Karnofsky, Cold Takes), which appears in:

- `01a_Existential-Risk` — sparse metadata, Published 2022-11-30
- `01c_Alignment-Faking-and-Scheming` — full metadata + concepts, Published 2022-11-29

Same article, different file paths in the vault (one is the freshly-clipped `Why Would AI "Aim" To Defeat Humanity?.md`, the other is the older hash-suffixed `Why_Would_AI_Aim_To_Defeat_Humanity_efd7b429.md`).

Other cross-folder duplicates in the same pattern:
- *Multi-Agent Risks from Advanced AI* (01e, twice — different risk tag, different date)
- *Claude's Constitution* (02b, twice — once as `blog_post`, once as `model_card`)
- *Anthropic's Responsible Scaling Policy* (04a, three times — different URLs, two dated 2023-12-18, one 2026-04-02)
- *Statement on AI Risk \| CAIS* (01a, three times — `safe.ai`, `www.safe.ai/statement-on-ai-risk`, `www.safe.ai/work/statement-on-ai-risk`)
- *Can we scale human feedback...?* (05a, twice — `aisafetyfundamentals.com` vs `bluedot.org` mirror)

**Recommended fix.** A dedup pass keyed on (URL canonicalized, title fuzzy-match) would collapse most of these. Keep the entry with the richest metadata; soft-link the others as "additional URLs" in the notes.

### 2.4 Concept misclassification — heuristic over-tagging

Three obvious cases pulled from `_archive_pre-refactor_2026-04-27/`:

- *CRISPR — Wikipedia* tagged with "RSP, Responsible Scaling Policies"
- *The Amyloid-β Pathway in Alzheimer's Disease* tagged with "RLHF & Its Limitations, Scalable Oversight, AI Evaluations & Benchmarks, Responsible Scaling Policies" (all four)
- *Cosmos QA* tagged with "Governance, Regulation"

Each of the existing concept articles also calls out a "Tangential / cross-tagged from other concepts" section honestly noting the heuristic over-tagged through co-occurrence. The audit log (`_audit_2026-04-27.md`) flags 51 out-of-vocab tags still in use. Worth running `scripts/unlink_misclassified.py` again with a stricter rulebook.

---

## 3. 🟢 Cross-topic connections worth wiring up

These are connections the wiki content **already half-makes** but doesn't surface as backlinks. Each is a 1-2 sentence edit, not a new article.

### 3.1 Sandbagging ↔ RSPs

- **Evidence in Evals article.** "Capability evaluations are vulnerable to sandbagging in ways that undermine the safety decisions depending on them" (van der Weij et al., ICLR 2025: prompted + password-locked sandbagging both work on frontier models).
- **Why it matters for RSPs.** The entire RSP regime gates ASL/CCL transitions on capability eval results. If a model can sandbag the eval, the gate fails open.
- **Suggested edit.** Add a "Threats to RSP integrity" subsection to the RSP article citing the sandbagging body of work as the central technical risk to the framework.

### 3.2 Apollo's eval-awareness contamination ↔ W2SG "leap of faith"

- **Apollo finding.** Capability training alone (no safety component) raised explicit verbalized evaluation-awareness from 2.0% → 20.6% in OpenAI's RL setup.
- **W2SG concern.** Leike: "since we should expect superhuman models to understand when we're taking the leap of faith, this is a particularly natural point for models to turn on us."
- **The same phenomenon.** Both articles describe the same failure mode (model behaves differently when it knows it's being tested) at different timescales. The W2SG article doesn't cite the Apollo numbers; the Alignment Faking article doesn't connect to Leike's framing.
- **Suggested edit.** A 1-sentence cross-reference in both articles: "The Apollo eval-awareness data is the empirical realization of Leike's 'leap of faith' concern."

### 3.3 Sleeper Agents ↔ Pretraining Data Filtering

- Sleeper agents demonstrate that **post-training can't reliably remove what's in weights**.
- Pretraining filtering is the **only intervention that operates pre-weights**.
- Currently sleeper agents are filed only under Alignment Faking, where the framing is "training-time deception persists." The mitigation framing — "this is exactly what pretraining filtering is for" — is missing.
- **Suggested edit.** In Pretraining Filtering's "Tamper Resistance" section, cite Sleeper Agents alongside the BadLlama \$200/30-min finding as evidence of why the filter has to be at pretraining.

### 3.4 Egress bandwidth controls ↔ Lab Scorecards (security)

- RSP article documents Anthropic's **rate-limiting outbound traffic from weight-hosting systems** (the most concrete novel security control in the ASL-3 activation).
- Lab Scorecards article has labs at 0% on SL5 planning, with Google leading at ~5% via "hardware keys."
- **Egress controls aren't on the scorecard rubric.** They should be — they're a measurable, deployable control, and only Anthropic has publicly documented implementing them.
- **Suggested edit.** In Lab Scorecards "Security (SL5 Readiness)," add a line: "**Egress controls:** Anthropic publicly documented; others not measured."

### 3.5 Collective CAI ↔ FLI public-mandate polling

- CAI article documents *Collective Constitutional AI* (Anthropic × CIP, ~1,000 American participants, 1,127 statements via Polis).
- Existential Risk article cites FLI Oct 2025 polling: 75% of US adults want strong AI regulation.
- **Latent connection.** The same public whose principles ended up in a deployed Claude variant is also the public being polled on AI policy. Collective CAI is a methodology that could feed deliberative-democratic AI governance.
- **Suggested edit.** One sentence in CAI's "Public-input variant" paragraph: "The methodology is a candidate channel for the polled-but-unimplemented public preferences documented in the Existential Risk article."

### 3.6 Shell Games (control evaluations) ↔ AI Guardrails (currently empty)

- The parent **AI Safety** Notion page has "AI Guardrails" marked ⏳ Empty.
- Shell Games (Bhatt et al., Nov 2024) demonstrates control protocols achieving **2.5× safety gains with no statistically significant utility loss** in bash-shell agentic settings.
- That's the strongest empirical evidence available that AI guardrails can be both effective and not crippling.
- **Suggested action.** Lift Shell Games + the Buck three-server architecture from the Agentic Misalignment article into a new "AI Guardrails" stub on the parent page.

### 3.7 Deliberative Alignment ↔ "Fragile CoT" warning

- Constitutional AI article describes Deliberative Alignment as "model reasons about safety spec in CoT before responding."
- Evaluations article cites *Chain of Thought Monitorability: A New and Fragile Opportunity for AI Safety* (Korbak/Balesni + ~40 cross-org authors): CoT faithfulness "may degrade as models are trained more aggressively."
- **Direct tension.** Deliberative Alignment depends on the very property the CoT-monitoring paper warns is fragile. Currently the two articles don't reference each other.
- **Suggested edit.** Add a "Caveat" line to Deliberative Alignment: "Effectiveness depends on CoT faithfulness, which the Korbak/Balesni 2025 consensus paper warns is fragile and likely degrades with more aggressive training."

### 3.8 International AI Safety Report (Bengio, Feb 2026) cited only once

- Existential Risk article describes it accurately (100+ experts, 30+ countries, second iteration).
- It's the largest international AI-safety consensus document to date, but it's **cited from no other concept article** — not RSPs, not Evals, not Lab Scorecards, not Pretraining Filtering.
- **Suggested action.** Add `International AI Safety Report 2026` to the Sources section of all four governance-adjacent articles. Especially valuable as a "what's the citation-grade reference for X capability claim" anchor.

---

## 4. 🟢 New concept-article candidates

The wiki currently lists 11 concept articles. Reading across all of them, four topics keep appearing as **cross-cutting clusters that no single article owns**:

### 4.1 AI Control (highest priority)

- Treated in depth in three different articles (Scalable Oversight § "vs AI Control", Agentic Misalignment § "Mitigation Approaches", Alignment Faking § "Mitigation / control").
- The Greenblatt & Shlegeris control thesis, Shell Games, Buck's three-server architecture, defer-to-trusted protocols, and control evaluations are all sitting across these three articles in fragmented form.
- **AI Control is arguably the most-cited mitigation framework in the 2024-25 safety literature** and deserves its own concept article. Once it has one, the three host articles can shrink to 1-2 paragraphs and link out.

### 4.2 Multi-Agent Risks

- Vault has a dedicated `01e_Multi-Agent/` folder with Hammond/Chan/Clifton et al. PDFs.
- Parent **AI Safety** page lists Structural Risks but the wiki concept-article cluster has zero coverage of multi-agent failure modes.
- *What Multipolar Failure Looks Like* (Critch) is filed only under Existential Risk.
- A concept article would unify Cooperative AI Foundation taxonomy + Critch + Aschenbrenner IIIb + the homogeneous-deployment-as-structural-risk thread the parent page already articulates.

### 4.3 Chain-of-Thought Monitoring & Faithfulness

- Sources scattered across Evals (Korbak/Balesni 2025), Alignment Faking (Anthropic faithfulness paper), Interpretability (BlueDot explainer), and the deliberative-alignment thread.
- The fragility-vs-leverage tradeoff is central to AI Control protocols and to anti-scheming evaluation methodology.
- A concept article would consolidate.

### 4.4 Sandbagging

- Mentioned across Evals (van der Weij et al., the sandbagging-as-RSP-threat argument), Alignment Faking (Anti-Scheming program findings), and the Apollo CoT-snippets corpus.
- Currently treated as a sub-bullet everywhere; deserves its own treatment given how thoroughly it undermines the eval → RSP → deployment pipeline.

---

## 5. 🟡 Stale claims in Lab Scorecards (likely out-of-date)

Lab Scorecards was last fully updated 2026-04-25 (one date older than the rest of the wiki). Two specific claims look outdated relative to the rest of the wiki:

### 5.1 "Dangerous capability removal essentially unattempted industry-wide"

- Pretraining Filtering article documents EleutherAI's *Deep Ignorance* program: WMDP-Bio regressed to **near random chance** with no MMLU drop, plus tamper-resistance to fine-tuning on labeled biorisk papers.
- Anthropic's data-filtering work also documented (33% relative CBRN reduction, no benchmark drop).
- The Lab Scorecards claim should at least be qualified: "Production deployment of unlearning/filtering remains rare, but two well-documented research programs (Anthropic, EleutherAI) demonstrate the techniques work."

### 5.2 "No lab has accountability above 5%"

- RSP article documents Anthropic's V3.0 framework requiring **periodic Risk Reports with external review** for higher-risk models.
- The Frontier Safety Roadmap has publicly graded goals with timestamped updates (April 2026 progress shown).
- This is non-zero accountability infrastructure. The 5% claim should be re-rated against the V3.0 changes.

---

## 6. ✅ What's already in good shape (don't touch)

For the avoidance of generating busy-work suggestions, the following are working well:

- **per_folder/ ↔ vault sync.** Audit confirmed zero orphan files and zero phantom references across all 21 sub-folders. The 2026-04-27 regeneration succeeded.
- **Cross-references between concept articles.** Each article has a Cross-references section with bidirectional links; the link graph is dense and consistent. New connections suggested above are *additional* edges, not corrections.
- **Citation discipline.** Every empirical claim in concept articles cites a vault file path. Quotes are attributed. The wiki style is unusually disciplined for an LLM-compiled product.
- **Concept-article overview structure.** All 11 articles follow a consistent shape (Overview → How it Works / Findings → Limitations → Sources → Cross-refs → Backlinks). Makes scanning easy.

---

## 7. Recommended next-pass priorities

If you want a single "do this next" list, in rough order of leverage:

1. **Fix the three factual bugs in §1** (10 minutes; concrete quoted text → concrete fix)
2. **Patch the metadata parsers** to stop synthesizing `2026-01-01` / `YYYY-04-2x` dates (§2.1) — single highest-leverage fix because it propagates to every future ingest
3. **Run a dedup pass** on per_folder/ keyed on canonicalized URL (§2.3)
4. **Wire the 8 cross-topic edits** in §3 — each is 1-2 sentences, total ~30 minutes
5. **Spin up the AI Control concept article** (§4.1) — the only one of the four candidates that's actively load-bearing in three other articles
6. **Re-run `unlink_misclassified.py`** with a stricter vocabulary (§2.4)
7. Lower priority: Multi-Agent / CoT Monitoring / Sandbagging concept articles; Lab Scorecards refresh

---

_Generated 2026-04-27. Source: full read of 11 Notion concept articles + per_folder/ indices + two audit-agent passes over the vault. No web searches were used (per scope choice)._

# Directory Gap Analysis — 2026-07-04

Method: every candidate below was programmatically checked against `people.json` (382 entries), `extra_data.json` (200 orgs / 139 conferences / 22 fellowships / 64 datasets / 448 papers), and `missing_papers.json` (262-item backlog). "Absent" means no entry match in any section. Web-checked against the mid-2026 landscape.

## Organizations (absent — strongest candidates)

**Technical research orgs**
- **Goodfire** — mechanistic interpretability startup (Ember platform). You have 50 interp files but no interp-startup orgs.
- **Transluce** — Jacob Steinhardt's nonprofit; open-source AI investigator/monitoring tooling.
- **Tilde** — smaller interp startup (optional).
- **LawZero** — Yoshua Bengio's nonprofit (June 2025), non-agentic "Scientist AI" safety-by-design.
- **Cooperative AI Foundation** — multi-agent risk. Directly matches your thinnest vault subcategory (01e_Multi-Agent, 4 files).
- **Eleos AI Research** — AI welfare/moral patienthood. You list Digital Sentience Consortium + Cambridge Digital Minds fellowships but no welfare org.

**Strategy / governance**
- **AI Futures Project** — Kokotajlo's org (AI 2027). Kokotajlo the person is in; his org isn't.
- **Forethought** — macrostrategy ("Preparing for the Intelligence Explosion").
- **ControlAI** — advocacy, "A Narrow Path" (Miotti also absent as person).
- **AI Impacts** — Katja Grace's survey org (AI researcher surveys are widely cited).
- **The Alignment Project** — UK AISI-led international alignment fund (~£27m, 2025); backed by ARIA, Schmidt Sciences, CIFAR, Anthropic, OpenAI et al.
- **Alliance for Secure AI** — 2025 comms/advocacy nonprofit.
- **BlueDot Impact** — AI Safety Fundamentals courses; the field's main education pipeline, fits your Educational bucket.

**China / international** (current coverage: Tsinghua, Peking, CAICT, Torando only)
- **Concordia AI** (Beijing) — "State of AI Safety in China" reports; main China↔West safety bridge.
- **Shanghai AI Laboratory** — SafeWork / AI-45° Law frontier-safety agenda.
- **CeSIA** (Centre pour la Sécurité de l'IA, Paris).

**Funders — currently no org group covers philanthropy** (only Open Philanthropy is listed). Consider a 9th orgGroup: Survival and Flourishing Fund, Longview Philanthropy, Schmidt Sciences, Halcyon Futures, Safe AI Fund, AI Safety Fund (Frontier Model Forum), Founders Pledge.

## People (absent — verified against people.json)

- **Katja Grace** (AI Impacts) — expected-timelines surveys
- **Miles Brundage** — ex-OpenAI AGI readiness, independent policy
- **Toby Shevlane** (GDM) — "Model evaluation for extreme risks"
- **Jack Clark** (Anthropic co-founder, policy; Import AI)
- **Holden Karnofsky** (Anthropic)
- **Nate Soares** (MIRI; *If Anyone Builds It* co-author)
- **Nick Bostrom** — Superintelligence; Macrostrategy Research Initiative
- **Stephen Casper** — interp/eval critiques (MIT → UK AISI)
- **Leopold Aschenbrenner** — Situational Awareness (the paper is in your directory; the author isn't)
- **Andrea Miotti** (ControlAI), **Andrew Critch**, **Scott Garrabrant** (MIRI)
- Technical-governance duo **Elizabeth Seger** / **Ben Bucknall** (optional)

## Datasets / benchmarks (absent — 64 current entries skew guardrail-vendor-heavy)

Safety-refusal & jailbreak: **TruthfulQA**, **JailbreakBench**, **StrongREJECT**, **AdvBench**, **XSTest**, **OR-Bench**, **SORRY-Bench**, **Do-Not-Answer**, **BeaverTails / PKU-SafeRLHF**, **TrustLLM**
Honesty & hallucination: **MASK** (CAIS honesty-under-pressure), **SimpleQA**
Agentic & security: **AgentDojo** (prompt-injection agents), **InjecAgent**, **OSWorld**, **WebArena**, **τ-bench**, **Cybench**
Bio: **LAB-Bench**, **VCT (Virology Capabilities Test)**
Economic/real-world: **GDPval**, **ForecastBench**
Legacy bias/toxicity (if you want historical completeness): RealToxicityPrompts, ToxiGen, BBQ

Cross-listing fix: **Cybench, AgentDojo, AgentBench, VCT already exist as *papers* in the directory but have no *dataset* entry** — cheap wins.

## Fellowships (22 current; absent candidates)

- **Horizon Fellowship** — the standard AI-governance placement program (US policy); notable miss given GovAI/Talos/Heron are in
- **IAPS Fellowship** (org is listed, fellowship isn't)
- **RAND TASP** (Technology and Security Policy fellows)
- **TechCongress** (AI policy placements in Congress)
- **Tarbell Fellowship** (AI journalism)
- **FLI PhD/Postdoc Fellowships** (FLI org listed, fellowships not)
- **Cooperative AI PhD Fellowship**
- **Global AI Safety Fellowship** (Impact Academy)
- **Athena** (women in AI safety / mech interp)
- **BASIS** (recommended alongside MATS/LASR)
- **Generator Residency** — new 2026, Constellation × Kairos, Jun 15–Aug 28 2026
- **ML4Good** bootcamps (borderline fellowship/education)

## Conferences (139 — strongest section; only minor gaps)

- **CHAI Annual Workshop** (Asilomar) — notable given 3 CHAI people listed
- **EA Global Bay Area 2026** (NYC 2026 + London 2023 are in)
- Next-cycle placeholders: COLM 2026, AAAI 2026 Alignment Track (2025 entries exist)

## Papers

Your `missing_papers.json` backlog (262) already covers most gaps. Absent from *both* directory and backlog:
- **AI 2027** (Kokotajlo et al. scenario)
- **Subliminal Learning** (Cloud et al. 2025 — trait transmission via unrelated data)
- **The Intelligence Curse** (Drago & Laine)
- **If Anyone Builds It, Everyone Dies** (Yudkowsky & Soares book, Sep 2025)

From the existing backlog, highest-priority for ingest: the interp canon (Toy Models of Superposition, Scaling Monosemanticity, Circuit Tracing / Biology of an LLM), InstructGPT, The Instruction Hierarchy.

## Structural notes

1. **88 of 382 people** still carry placeholder category `🎓 Fellowship & Program Involvement (2026-07-01)` and org `New additions from the fellowship scan (🆕 2026-07-01)` — re-home to real orgs/categories.
2. No **funders** orgGroup (see above).
3. Directory gaps mirror vault gaps: multi-agent (4 files) and model welfare are thin in both — adding Cooperative AI Foundation and Eleos + their key papers would fix both layers at once.

Sources consulted: [AISI Alignment Project](https://www.aisi.gov.uk/blog/funding-60-projects-to-advance-ai-alignment-research), [Alliance for Secure AI](https://en.wikipedia.org/wiki/Alliance_for_Secure_AI), [MATS](https://www.matsprogram.org/faq/getting-into-mats), [Constellation Astra](https://constellation.org/programs/astra), [Anthropic Fellows 2026](https://alignment.anthropic.com/2025/anthropic-fellows-program-2026/), [SPAR](https://sparai.org/), [FLI AI Safety Index](https://futureoflife.org/ai-safety-index-summer-2025/).

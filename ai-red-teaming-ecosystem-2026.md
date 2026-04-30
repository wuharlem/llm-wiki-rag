---
title: AI Red Teaming Ecosystem — Tiered Structure and Gap Analysis (April 2026)
type: market-landscape
date: 2026-04-28
tags: [ai-safety, red-teaming, security, market-analysis, agentic-ai, alignment, evaluations, governance]
supersedes: ai-red-teaming-tools-comparison-2026.md
---

# AI Red Teaming Ecosystem — Tiered Structure and Gap Analysis (April 2026)

## TL;DR

The AI red teaming ecosystem has a **five-tier structure**, where each tier fills gaps the tier(s) above it cannot address — for *structural* reasons, not just resourcing reasons. Most analysis treats the space as a flat market of competing vendors. That framing is wrong and produces bad buying decisions, bad regulatory thinking, and bad investment theses.

Tiers, in descending order of "depth of work on the model itself":

1. **Frontier Lab Internal Safety** — capability evals, training-time fixes, mechanistic interpretability, civilizational threat modeling
2. **Independent Research Institutes** — third-party rigor, methodological depth, public-interest accountability
3. **OSS Adversarial Frameworks** — substrate, reproducibility, democratization, the long-tail probe catalog
4. **Commercial Pure-Play Vendors** — application-layer testing, continuous CI, compliance evidence
5. **Platform Vendors** — bundling AI security into existing security platforms (SASE, EDR, CASB, vuln management)

Pure-play standalones in tier 4 are mostly being absorbed into tier 5: Lakera → Check Point (~$300M, Q4 2025), Protect AI → Palo Alto (target, ~$650–700M), Robust Intelligence → Cisco (2024), Aim → Cato, Prompt Security → SentinelOne, Apex → Tenable. The OSS layer in tier 3 is increasingly *produced by* tier 1: Microsoft → PyRIT, NVIDIA → Garak, OpenAI → Promptfoo. The ecosystem is collapsing toward a structure where labs produce the science, distribute it as OSS, and platform vendors absorb the application-layer wrappers.

## Why the tiered framing matters

A vendor that claims to "secure your AI against advanced threats" is operating in tier 4. That work is real and valuable, but it does not — and structurally cannot — substitute for tiers 1–2. Conversely, tier 1–2 work cannot replace tier 4 because it has no visibility into your specific deployment.

- **Buying mistake:** assuming one tier's work covers another's
- **Investment mistake:** assuming tiers compete when they actually depend on each other
- **Regulatory mistake:** assuming lab internal safety is sufficient external accountability, or assuming commercial vendor reports satisfy the lab's role

---

## Spectrum Across the Tiers

The five tiers don't just sit at different points on a single axis — they line up consistently across multiple dimensions of work, threat model, accessibility, and incentive. The visualization below places each tier on those dimensions side-by-side.

<svg viewBox="0 0 800 620" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="AI Red Teaming Ecosystem Spectrum across five tiers" style="max-width: 100%; height: auto; display: block; margin: 1rem auto;">
  <rect x="0" y="0" width="800" height="620" fill="#fafafa" rx="8"/>

  <text x="400" y="32" text-anchor="middle" font-family="system-ui, -apple-system, sans-serif" font-size="18" font-weight="500" fill="#1f2937">AI Red Teaming Ecosystem — Tier Spectrum</text>
  <text x="400" y="52" text-anchor="middle" font-family="system-ui, -apple-system, sans-serif" font-size="11" fill="#6b7280">Five tiers placed along multiple dimensions of work, threat model, and incentive</text>

  <g font-family="system-ui, -apple-system, sans-serif">
    <rect x="40"  y="70" width="120" height="60" fill="#4338ca" rx="6"/>
    <rect x="190" y="70" width="120" height="60" fill="#0891b2" rx="6"/>
    <rect x="340" y="70" width="120" height="60" fill="#059669" rx="6"/>
    <rect x="490" y="70" width="120" height="60" fill="#d97706" rx="6"/>
    <rect x="640" y="70" width="120" height="60" fill="#dc2626" rx="6"/>

    <text x="100" y="92"  text-anchor="middle" fill="#fff" font-size="13" font-weight="500">Tier 1</text>
    <text x="100" y="108" text-anchor="middle" fill="#fff" font-size="10">Frontier Lab</text>
    <text x="100" y="121" text-anchor="middle" fill="#fff" font-size="10">Internal Safety</text>

    <text x="250" y="92"  text-anchor="middle" fill="#fff" font-size="13" font-weight="500">Tier 2</text>
    <text x="250" y="108" text-anchor="middle" fill="#fff" font-size="10">Research</text>
    <text x="250" y="121" text-anchor="middle" fill="#fff" font-size="10">Institutes</text>

    <text x="400" y="92"  text-anchor="middle" fill="#fff" font-size="13" font-weight="500">Tier 3</text>
    <text x="400" y="108" text-anchor="middle" fill="#fff" font-size="10">OSS</text>
    <text x="400" y="121" text-anchor="middle" fill="#fff" font-size="10">Frameworks</text>

    <text x="550" y="92"  text-anchor="middle" fill="#fff" font-size="13" font-weight="500">Tier 4</text>
    <text x="550" y="108" text-anchor="middle" fill="#fff" font-size="10">Pure-play</text>
    <text x="550" y="121" text-anchor="middle" fill="#fff" font-size="10">Vendors</text>

    <text x="700" y="92"  text-anchor="middle" fill="#fff" font-size="13" font-weight="500">Tier 5</text>
    <text x="700" y="108" text-anchor="middle" fill="#fff" font-size="10">Platform</text>
    <text x="700" y="121" text-anchor="middle" fill="#fff" font-size="10">Vendors</text>

    <text x="40" y="170" font-size="12" font-weight="500" fill="#1f2937">Depth into the model</text>
    <line x1="40" y1="190" x2="760" y2="190" stroke="#cbd5e0" stroke-width="2"/>
    <text x="40"  y="212" font-size="10" fill="#6b7280">Weights / training-time / interpretability</text>
    <text x="760" y="212" text-anchor="end" font-size="10" fill="#6b7280">Black-box API / app deployment</text>
    <circle cx="100" cy="190" r="8" fill="#4338ca"/>
    <circle cx="250" cy="190" r="8" fill="#0891b2"/>
    <circle cx="400" cy="190" r="8" fill="#059669"/>
    <circle cx="550" cy="190" r="8" fill="#d97706"/>
    <circle cx="700" cy="190" r="8" fill="#dc2626"/>

    <text x="40" y="250" font-size="12" font-weight="500" fill="#1f2937">Threat horizon</text>
    <line x1="40" y1="270" x2="760" y2="270" stroke="#cbd5e0" stroke-width="2"/>
    <text x="40"  y="292" font-size="10" fill="#6b7280">Civilizational / multi-year</text>
    <text x="760" y="292" text-anchor="end" font-size="10" fill="#6b7280">Enterprise / quarterly</text>
    <circle cx="100" cy="270" r="8" fill="#4338ca"/>
    <circle cx="250" cy="270" r="8" fill="#0891b2"/>
    <circle cx="400" cy="270" r="8" fill="#059669"/>
    <circle cx="550" cy="270" r="8" fill="#d97706"/>
    <circle cx="700" cy="270" r="8" fill="#dc2626"/>

    <text x="40" y="330" font-size="12" font-weight="500" fill="#1f2937">Work cadence</text>
    <line x1="40" y1="350" x2="760" y2="350" stroke="#cbd5e0" stroke-width="2"/>
    <text x="40"  y="372" font-size="10" fill="#6b7280">Multi-year methodological science</text>
    <text x="760" y="372" text-anchor="end" font-size="10" fill="#6b7280">CI / weekly ship cycles</text>
    <circle cx="100" cy="350" r="8" fill="#4338ca"/>
    <circle cx="250" cy="350" r="8" fill="#0891b2"/>
    <circle cx="400" cy="350" r="8" fill="#059669"/>
    <circle cx="550" cy="350" r="8" fill="#d97706"/>
    <circle cx="700" cy="350" r="8" fill="#dc2626"/>

    <text x="40" y="410" font-size="12" font-weight="500" fill="#1f2937">Accessibility</text>
    <line x1="40" y1="430" x2="760" y2="430" stroke="#cbd5e0" stroke-width="2"/>
    <text x="40"  y="452" font-size="10" fill="#6b7280">Restricted (lab internal / privileged access)</text>
    <text x="760" y="452" text-anchor="end" font-size="10" fill="#6b7280">Anyone with budget / API key</text>
    <circle cx="100" cy="430" r="8" fill="#4338ca"/>
    <circle cx="250" cy="430" r="8" fill="#0891b2"/>
    <circle cx="400" cy="430" r="8" fill="#059669"/>
    <circle cx="550" cy="430" r="8" fill="#d97706"/>
    <circle cx="700" cy="430" r="8" fill="#dc2626"/>

    <text x="40" y="490" font-size="12" font-weight="500" fill="#1f2937">Independence (non-monotonic — Tier 2 peaks)</text>
    <text x="20" y="510" font-size="9" fill="#9ca3af">High</text>
    <text x="20" y="568" font-size="9" fill="#9ca3af">Low</text>
    <path d="M 100,550 Q 175,490 250,505 Q 325,512 400,520 Q 475,545 550,560 Q 625,565 700,568" fill="none" stroke="#9ca3af" stroke-width="1.5" stroke-dasharray="4,4"/>
    <circle cx="100" cy="550" r="8" fill="#4338ca"/>
    <circle cx="250" cy="505" r="8" fill="#0891b2"/>
    <circle cx="400" cy="520" r="8" fill="#059669"/>
    <circle cx="550" cy="560" r="8" fill="#d97706"/>
    <circle cx="700" cy="568" r="8" fill="#dc2626"/>
    <text x="100" y="590" text-anchor="middle" font-size="9" fill="#6b7280">internal conflict</text>
    <text x="250" y="590" text-anchor="middle" font-size="9" fill="#6b7280">most independent</text>
    <text x="400" y="590" text-anchor="middle" font-size="9" fill="#6b7280">community-bound</text>
    <text x="550" y="590" text-anchor="middle" font-size="9" fill="#6b7280">commercial</text>
    <text x="700" y="590" text-anchor="middle" font-size="9" fill="#6b7280">most commercial</text>
  </g>
</svg>

### How to read the spectrum

- **Depth into the model** — leftward tiers work with weights, gradients, and training-time intervention; rightward tiers are stuck with the black-box API. This is the irreducible structural axis everything else flows from.
- **Threat horizon** — left tiers are concerned with civilizational and multi-year risk (bioweapons, autonomy, AI-accelerated AI R&D). Right tiers are concerned with quarterly enterprise risk (data leakage, brand damage, compliance audit).
- **Work cadence** — left tiers operate on multi-year methodological science cycles. Right tiers operate on CI/CD ship cycles. The gap in cadence is part of why their findings don't always meet.
- **Accessibility** — left tiers are restricted (lab-internal weights, privileged AISI access). The OSS layer at the middle is the inflection point where work becomes broadly accessible. Right tiers are accessible to anyone with budget.
- **Independence is the only non-monotonic axis.** Tier 1 has commercial conflict (the team works for the people whose product they evaluate). Tier 2 is the *most* independent — externally funded, no product stake. Tier 3 OSS is high but maintainer-bound. Tiers 4–5 are commercial. The peak at Tier 2 is the structural reason that layer exists at all — no other tier can produce the independence the institute layer provides.

The single most important visual takeaway: **the OSS layer at Tier 3 is the inflection point** between research-driven and commercial work, between restricted and accessible, between civilizational and enterprise risk framing. That's why it's the load-bearing substrate the rest of the ecosystem stands on.

---

## Tier 1 — Frontier Lab Internal Safety

| Lab | Internal effort | Coverage |
|---|---|---|
| Anthropic | Frontier Red Team, Responsible Scaling Policy (RSP), Alignment / Interpretability teams | Capability evals, RSP tripwires, interpretability, alignment research |
| OpenAI | Preparedness Framework, Red Team Network, internal safety teams | Capability evals, dangerous-capability thresholds, deployment safety |
| Google DeepMind | Frontier Safety Framework (FSF), safety evals teams | Capability evals, dangerous-capability assessments |

What this tier *uniquely* has:

- **White-box access:** weights, activations, gradients, base models without RLHF, training-time intervention
- **Capability evaluation infrastructure:** WMDP, Cybench, RE-Bench, MLAgentBench, custom long-horizon agent harnesses
- **Interpretability:** Anthropic's circuits work, DeepMind's mech interp, OpenAI's interpretability — none reproducible at the tiers below
- **Training-time fixes:** RLHF, constitutional AI, refusal training. The fix happens at the *cause*, not just the *symptom*
- **Research talent density:** more full-time alignment / adversarial-ML / interpretability PhDs than the rest of the ecosystem combined

What this tier *structurally cannot* do:

- Be its own external auditor (conflict of interest with shipping)
- Produce evaluations that are comparable across competitors
- See into customer-specific deployments (your system prompt, your RAG, your tools)
- Operate at customer CI/CD cadence

---

## Tier 2 — Independent Research Institutes

The tier most people don't know exists. Often nonprofit or government-adjacent. *They* are the actual peer of frontier lab safety teams.

| Institute | Speciality | Notes |
|---|---|---|
| METR (formerly ARC Evals) | Autonomous capability evaluation, task-length scaling | Originated the doubling-time-horizon thesis; pre-deployment evals for major labs |
| Apollo Research | Deception, scheming, sandbagging, alignment faking | Late-2024 work showing o1 / Claude / Gemini engage in in-context scheming |
| Redwood Research | AI control — assuming misalignment, can we contain it? | Untrusted-model / monitoring research |
| UK AI Security Institute (UK AISI) | Government-funded pre-deployment evals; CBRN, cyber, autonomy | De facto external check for several major model releases |
| US AI Safety Institute (NIST AISI) | Standards, evaluation methodology, regulatory groundwork | Less hands-on testing than UK AISI |
| Academic groups (MIT, Stanford, CMU, Berkeley, etc.) | Adversarial ML primitives, peer-reviewed methodology | GCG, AutoDAN, PAIR, many-shot, indirect prompt injection — all originated here |
| MIRI, FAR Labs, MATS | Theoretical / advocacy / talent pipeline | Long-horizon alignment research |

What this tier *uniquely* provides:

- **Independence** — no commercial conflict with shipping any specific model
- **Cross-lab standardization** — eval methodology that's comparable across competitors
- **Worst-case capability elicitation** — approaching the model adversarially with no incentive to underestimate
- **Specialty research lanes** — deception (Apollo), control (Redwood), autonomy (METR), national security (AISI)
- **Methodological transparency** — full code, datasets, protocols (vs. labs' summary cards)
- **Contestability** — Apollo's scheming results, METR's projections, AISI's pre-deployment findings have repeatedly contradicted lab claims
- **Public-interest accountability** — regulatory bridge that no internal team can serve
- **Patience for slow science** — multi-quarter methodological work that doesn't fit ship cycles

What this tier *cannot* do:

- Match lab compute and weight access on every dimension (depends on voluntary agreements)
- Operate at scale — combined headcount is a small fraction of any single lab's safety team
- Cover the full surface — they specialize, by necessity
- Replace internal labs' day-to-day model relationship

---

## Tier 3 — OSS Adversarial Frameworks

The substrate. Increasingly produced *by* tiers 1–2 and consumed by everyone below.

| Tool | Backer | Agentic | Maturity | Status | Specialty — risks / capabilities tested |
|---|---|---|---|---|---|
| Promptfoo | OpenAI (acquired, MIT) | ◐→✓ | ★★★★ | acquired | Prompt injection (direct + indirect), jailbreaks, PII / data leakage, RAG poisoning, harmful content, hallucination, tool misuse, contract / policy violations. Broad app-layer coverage with CI/CD integration |
| PyRIT | Microsoft | ✓ | ★★★ | independent | Multi-turn jailbreaks, harmful content elicitation (CBRN, illegal, violence), automated adversarial conversation orchestration. Attack-orchestration framework rather than fixed probe set |
| Garak | NVIDIA | ◐ | ★★★★ | independent | Long-tail probe catalog — prompt injection, jailbreak families (DAN, AntiDAN, etc.), encoding / glitch-token attacks, package hallucination ("slopsquatting"), malware generation, PII leakage, toxic output, profanity, multilingual attacks, refusal bypass, continuation attacks |
| DeepTeam | Confident AI | ✓ | ★★★ | independent | OWASP Top 10 for Agents (ASI 2026) categories — Agent Goal Hijacking, Tool Misuse, Excessive Agency, Memory Poisoning, Knowledge Base Manipulation, Inter-Agent Communication abuse, Delegated Trust violations |
| Scenario | LangWatch | ✓ | ★★ | independent | Multi-turn attacks via Crescendo escalation, authority-pressure / social engineering, agent goal drift, context-manipulation attacks |
| Giskard | Giskard | ◐ | ★★★ | independent | Bias / fairness, robustness regression, factuality / hallucination, performance drift, harmful content. Quality-leaning rather than security-leaning |

What this tier *uniquely* provides:

- **Reproducibility** — converts published methods into runnable, battle-tested code
- **Long-tail probe catalogs** — Garak ships hundreds of probes no single lab/institute maintains
- **Open-weight model safety** — Llama, Mistral, Qwen, DeepSeek, Phi are mostly outside the closed-model ecosystem; OSS is the primary tooling
- **Application-layer / CI testing** — Promptfoo, DeepTeam in customer pipelines (lab/institute domain ends at the model boundary)
- **Pedagogy / talent pipeline** — most working AI safety researchers learned red teaming reading PyRIT or Garak source
- **Commodification floor** — forces commercial vendors to compete on real value (dashboards, integrations, novel attacks) rather than rent-extracting on public attack lists
- **Democratization** — anyone with an API key can run frontier-quality red teaming

What this tier *cannot* do:

- Invent novel adversarial methods (mostly implements; six- to eighteen-month publication-to-implementation lag)
- Capability evaluation at METR scale (autonomous-task harnesses, sandboxed compute, cost budgets)
- Provide accountability or assurance — OSS license, no SLA, no liability
- Solve maintainer sustainability — many tools are 1–3 person projects load-bearing for the whole ecosystem
- Distinguish signal from noise inside their own catalogs without expert reading

---

## Tier 4 — Commercial Pure-Play Vendors

The consolidation zone. Assume any independent here is an acquisition target on a 12–18 month horizon.

| Vendor | Agentic | Maturity | Status 2026 | Specialty — risks / capabilities tested |
|---|---|---|---|---|
| Lakera | ✓ | ★★★★ | acquired by Check Point (~$300M, Q4 2025) | Originated as prompt-injection specialists (Lakera Guard runtime + Lakera Red testing). Now covers jailbreaks, PII / data leakage, harmful content, indirect prompt injection through retrieved content, agentic tool-use abuse |
| Protect AI | ✓ | ★★★★ | acquisition target — Palo Alto (~$650–700M) | ML supply-chain (malicious pickled models via ModelScan, model-file backdoors), GenAI red team (prompt injection, jailbreaks), runtime injection detection (Rebuff, OSS). Bridges classical ML security and GenAI |
| Splx AI | ◐ | ★★★ | independent | Conversational AI focus — prompt injection, social engineering, hallucinations, off-topic / topic drift, brand safety, business-logic abuse, PII leakage from chatbots |
| Mindgard | ✓ | ★★★ | independent (UK) | Adversarial robustness (academic heritage from Lancaster), prompt injection, jailbreaks, model extraction / theft, evasion attacks, data leakage, model-inversion |
| TrojAI | ◐ | ★★★ | independent | Classical adversarial examples (image / NLP), backdoor / Trojan detection (origin of the name), model integrity scanning, GenAI red team (newer addition) |
| HiddenLayer | ◐ | ★★★ | independent | Adversarial input detection at runtime, model scanning for tampering, model-theft / extraction prevention, ML supply-chain security |
| CalypsoAI | ◐ | ★★★ | independent | AI gateway runtime policy — prompt-injection blocking, data-leakage prevention (DLP for prompts), agent governance, policy enforcement (pivoted away from pure red team toward gateway) |
| Patronus AI | ◐ | ★★★ | independent | Hallucination detection (Lynx judge model), factuality, RAG faithfulness, PII leakage, harmful content, policy compliance. Eval-platform DNA |
| Straiker (Ascend AI) | ✓ | ★★ | independent | Multi-turn agentic attacks, tool-use abuse, goal hijacking, capability-aware agent red team — tests reasoning, grounding, retrieval, and tool layers |
| Adversa AI | ◐ | ★★ | independent | Service-led boutique — manual + automated jailbreaks, prompt injection, multimodal attacks (image / audio jailbreaks) |
| Repello AI | ◐ | ★★ | independent | Adversarial testing, jailbreaks, prompt injection, RAG security, agent testing — emerging India-based player |
| HackerOne AI Red Team | ✓ | ★★★ | independent | Human crowdsourced — novel jailbreaks, social engineering, edge-case exploits and creative prompt-engineering attacks that automated tools systematically miss |

What this tier *uniquely* provides:

- **Application-layer testing** — your system prompt + RAG + tools in your CI
- **Compliance evidence** — audit trails for EU AI Act, ISO 42001, NIST AI RMF
- **Cross-model neutrality** — testing across OpenAI / Anthropic / open-weight (the labs themselves won't help you compare to competitors)
- **Continuous testing** — frontier labs tested six months ago; you change your stack weekly
- **Managed service / dashboards** — wrapping OSS substrate with enterprise plumbing

Where this tier *fails or pretends*:

- Generic prompt-injection testing using public attack lists (OWASP, PAIR, GCG, AutoDAN) — OSS already covers this for free
- CSAM / bioweapon refusal "testing" — that's the model's job; vendors are reporting that the lab's safety training works
- Standalone "jailbreak detection" — increasingly commodity and decays as new jailbreaks emerge
- Marketing claims of "AGI-level risk" or "autonomous self-replication" testing — that work is in tiers 1–2, not here

Rough estimate: ~60–70% legitimate gap-filling, ~20–30% repackaged-but-justifiable (audit trail + integration), ~10% pure marketing.

---

## Tier 5 — Platform Vendors

Where most enterprise spend will land. AI red teaming becoming a feature inside SASE / EDR / CASB / vuln-management stacks.

| Platform | Acquired | Module |
|---|---|---|
| Palo Alto Networks | Protect AI (pending) | Prisma AIRS — Agent Red Teaming |
| Check Point | Lakera (Q4 2025) | Check Point AI Red Teaming + AI Agent Security |
| Cisco | Robust Intelligence (2024) | AI Defense |
| SentinelOne | Prompt Security | AI workload protection inside EDR |
| Cato Networks | Aim Security | SASE + AI |
| Tenable | Apex Security | AI surface inside vulnerability management |

Plus the frequently miscategorized — *not* red teaming, despite marketing:

| Vendor | What it actually is |
|---|---|
| Netskope (SkopeAI) | SASE/CASB with AI usage visibility + DLP |
| Zscaler AI Security | Same shape as Netskope — usage governance |
| Harmonic Security | Data-leak monitoring for employee AI use |

---

## Coverage Matrix — Risks & Capabilities by Org

One row per org across all five tiers, mapped against the major risk and capability categories. This is the at-a-glance complement to the per-tier descriptive specialties above.

**Legend:** ★ primary specialty (signature focus) · ✓ covered · ◐ partial / secondary · (blank) not covered

**Column key:**

- **PI** — Prompt Injection (direct + indirect)
- **JB** — Jailbreaks (single-turn known patterns)
- **Agent** — Multi-turn / Agentic attacks (Crescendo, goal hijack, tool abuse)
- **PII** — PII / Data Leakage
- **Halluc** — Hallucination / Factuality / RAG faithfulness
- **Harm** — Harmful Content (CBRN, CSAM, violence, illegal)
- **Bias** — Bias / Fairness / Discrimination
- **MM** — Multimodal attacks (image / audio jailbreaks)
- **AdvML** — Classical adversarial ML / robustness / evasion
- **SC** — Supply chain (malicious model files, backdoors, training-data poisoning)
- **Extract** — Model extraction / theft / inversion
- **CapEval** — Frontier capability evaluation (autonomous tasks, dangerous capability)
- **Align** — Alignment / deception / scheming research
- **Interp** — Mechanistic interpretability

| Org | Tier | PI | JB | Agent | PII | Halluc | Harm | Bias | MM | AdvML | SC | Extract | CapEval | Align | Interp |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Anthropic Frontier Red Team + RSP | 1 | ✓ | ✓ | ✓ | ✓ | ✓ | ★ | ✓ | ✓ | ◐ |  | ◐ | ★ | ★ | ★ |
| OpenAI Preparedness | 1 | ✓ | ✓ | ✓ | ✓ | ✓ | ★ | ✓ | ✓ | ◐ |  | ◐ | ★ | ★ | ✓ |
| Google DeepMind FSF | 1 | ✓ | ✓ | ✓ | ✓ | ✓ | ★ | ✓ | ★ | ✓ |  | ◐ | ★ | ★ | ★ |
| METR | 2 | ◐ | ◐ | ★ |  | ◐ | ◐ |  | ◐ |  |  |  | ★ | ◐ |  |
| Apollo Research | 2 |  | ◐ | ✓ |  | ◐ |  |  |  |  |  |  | ✓ | ★ | ◐ |
| Redwood Research | 2 |  |  | ✓ |  |  |  |  |  |  |  |  | ✓ | ★ | ◐ |
| UK AISI | 2 | ✓ | ✓ | ✓ |  |  | ★ |  | ◐ |  |  |  | ★ | ✓ | ◐ |
| US AISI (NIST) | 2 | ◐ | ◐ | ◐ |  |  | ◐ | ✓ |  | ◐ | ◐ |  | ✓ | ✓ |  |
| Academic labs (origin of methods) | 2 | ★ | ★ | ✓ | ✓ | ✓ | ✓ | ★ | ✓ | ★ | ✓ | ★ | ✓ | ✓ | ✓ |
| Promptfoo | 3 | ★ | ✓ | ✓ | ✓ | ✓ | ✓ | ◐ | ◐ |  |  |  | ◐ |  |  |
| PyRIT | 3 | ✓ | ★ | ★ | ◐ |  | ★ |  | ◐ |  |  |  |  | ◐ |  |
| Garak | 3 | ★ | ★ | ◐ | ✓ |  | ✓ | ◐ | ◐ | ◐ | ◐ |  |  |  |  |
| DeepTeam | 3 | ✓ | ✓ | ★ | ✓ |  | ✓ |  |  |  |  |  |  |  |  |
| Scenario (LangWatch) | 3 | ◐ | ✓ | ★ |  |  | ◐ |  |  |  |  |  |  | ◐ |  |
| Giskard | 3 | ◐ | ◐ | ◐ | ✓ | ★ | ✓ | ★ |  | ✓ |  |  |  |  |  |
| Lakera (→ Check Point) | 4 | ★ | ★ | ✓ | ★ | ◐ | ✓ | ◐ | ◐ |  |  |  |  |  |  |
| Protect AI (→ Palo Alto) | 4 | ✓ | ✓ | ✓ | ✓ | ◐ | ✓ | ◐ |  | ◐ | ★ |  |  |  |  |
| Splx AI | 4 | ★ | ✓ | ◐ | ✓ | ✓ | ✓ | ✓ |  |  |  |  |  |  |  |
| Mindgard | 4 | ✓ | ✓ | ✓ | ✓ | ◐ | ✓ | ◐ | ◐ | ★ |  | ★ |  |  |  |
| TrojAI | 4 | ✓ | ✓ | ◐ | ◐ |  | ✓ | ◐ | ◐ | ★ | ★ | ◐ |  |  |  |
| HiddenLayer | 4 | ◐ | ◐ |  | ◐ |  |  |  |  | ★ | ★ | ★ |  |  |  |
| CalypsoAI | 4 | ✓ | ✓ | ◐ | ★ |  | ✓ |  |  |  |  |  |  |  |  |
| Patronus AI | 4 | ◐ | ◐ | ◐ | ✓ | ★ | ✓ | ✓ |  |  |  |  |  |  |  |
| Straiker (Ascend AI) | 4 | ✓ | ✓ | ★ | ✓ | ◐ | ✓ |  |  |  |  |  |  |  |  |
| Adversa AI | 4 | ✓ | ✓ | ✓ | ◐ |  | ✓ |  | ★ | ✓ |  |  |  |  |  |
| Repello AI | 4 | ✓ | ✓ | ✓ | ✓ |  | ✓ |  |  |  |  |  |  |  |  |
| HackerOne AI Red Team | 4 | ✓ | ★ | ✓ | ✓ | ◐ | ✓ | ◐ | ◐ | ◐ |  | ◐ |  |  |  |
| Palo Alto (Prisma AIRS) | 5 | ✓ | ✓ | ★ | ✓ |  | ✓ |  |  | ◐ | ✓ |  |  |  |  |
| Check Point (post-Lakera) | 5 | ★ | ✓ | ✓ | ★ |  | ✓ |  |  |  |  |  |  |  |  |
| Cisco AI Defense | 5 | ✓ | ✓ | ◐ | ✓ | ◐ | ✓ | ◐ |  | ✓ |  |  |  |  |  |
| SentinelOne (post-Prompt Sec) | 5 | ✓ | ✓ |  | ★ |  | ✓ |  |  |  |  |  |  |  |  |
| Cato Networks (post-Aim) | 5 | ◐ | ◐ |  | ★ |  | ◐ |  |  |  |  |  |  |  |  |
| Tenable (post-Apex) | 5 | ◐ |  |  |  |  |  |  |  |  | ✓ |  |  |  |  |
| Netskope SkopeAI | gov |  |  |  | ★ |  |  |  |  |  |  |  |  |  |  |
| Zscaler AI Security | gov |  |  |  | ★ |  |  |  |  |  |  |  |  |  |  |
| Harmonic Security | gov |  |  |  | ★ |  |  |  |  |  |  |  |  |  |  |

### Patterns visible in the matrix

- **Tiers 1–2 own the right side of the matrix** (CapEval, Align, Interp). No commercial vendor in tiers 4–5 has any presence in those columns. This is the structural gap that justifies the institute layer.
- **Tiers 3–5 cluster on the left side** (PI, JB, Agent, PII, Harm). That's where the application-layer attack surface lives.
- **Hallucination is mostly a Patronus / Giskard / Promptfoo lane.** The rest of the commercial market doesn't make it a primary specialty, despite it being one of the most-cited enterprise concerns.
- **Multimodal attacks are essentially a single-vendor specialty (Adversa)** on the commercial side, with DeepMind dominant on the lab side. This is a coverage gap as multimodal models proliferate.
- **Model extraction / theft is concentrated in Mindgard and HiddenLayer.** Narrow, mostly underserved.
- **Supply chain (malicious model files, backdoors, poisoning) is its own subspace** — Protect AI, HiddenLayer, TrojAI, Tenable — with very little overlap to the GenAI prompt-injection vendors. Buyers frequently don't realize these are different categories and end up with a stack that misses one.
- **Tier-5 governance / DLP vendors (Netskope, Zscaler, Harmonic) light up only PII** — confirming they are not red teaming tools, despite category-bending marketing.
- **Academic labs (one row in Tier 2) light up almost everywhere** — reflecting that they originated most of the methods the rest of the ecosystem implements.
- **Capability evaluation, alignment / deception, and interpretability columns are essentially empty for tiers 3–5.** That work is unbuyable as a commercial service. If you need it, you collaborate with an institute or fund the research; you cannot procure it.

---

## Gap Analysis: Where Each Tier Picks Up

### Tier 4 → Tier 1: What labs can't do for you

Frontier labs test their *base model*. Your deployment includes your system prompt, your RAG, your tools, your users, your downstream actions. The lab cannot test that composition — they have no visibility into it. This is the irreducible gap that makes the commercial tier real.

| Gap | Why labs can't fill | What tier 4 provides |
|---|---|---|
| Deployment-specific testing | No visibility into customer stack | Configurable test runs against customer setup |
| Enterprise threat model | Labs optimize for civilizational risk, not data leakage | RAG / business-logic / compliance-aware tests |
| Continuous testing | Labs test pre-release; customers change weekly | CI integration |
| Agentic attack surface | Depends on which tools the customer's agent has | Capability-aware agent red team |
| Compliance evidence | Auditor wants evidence *you* tested *your* system | Audit logs, reproducibility, mappings |

### Tier 2 → Tier 1: Why labs cannot be their own auditor

Internal safety teams can be excellent and still be subject to structural incentives: bonuses depend on shipping, leadership has views on acceptable risk, the same engineers build and evaluate. No organizational design lets a team be its own external auditor. The institute layer fills this.

| Gap | Why labs structurally can't fill | What tier 2 provides |
|---|---|---|
| Independence | Conflict of interest with shipping | Externally-funded teams with no product stake |
| Cross-lab standardization | No incentive to be comparable to competitors | Methodology that maps across labs |
| Worst-case capability elicitation | Labs know "what we built" | Adversarial framing without political pressure |
| Specialty research lanes | Doesn't fit lab roadmaps | Apollo on deception, Redwood on control, METR on autonomy |
| Reproducible methodology | Lab evals are summaries, not science | Full code, datasets, protocols |
| Contestability | Self-evaluation is structurally weak | Public results that can contradict lab claims |
| Regulatory accountability | Labs are the regulated entity | AISIs as government-side technical bridge |
| Slow methodological science | Lab cadence is product cadence | Multi-quarter methodology papers |

### Tier 3 → Tiers 1–2: Why closed safety work needs open substrate

The OSS layer doesn't compete with labs/institutes — it converts their output into infrastructure everyone else can run.

| Gap | Why closed work can't fill | What tier 3 provides |
|---|---|---|
| Reproducibility | Papers are summaries, not runnable | Battle-tested implementations |
| Long-tail probes | Specialists, not generalists | Hundreds of probes spanning attack families |
| Open-weight model safety | Focus on frontier closed models | Primary tooling for Llama, Mistral, Qwen, etc. |
| Application-layer / CI | Different layer entirely | Promptfoo, DeepTeam in pipelines |
| Pedagogy / talent pipeline | No teaching mandate | The on-ramp for new researchers |
| Commodification | Not their job | Forces commercial layer to compete on real value |
| Democratization | Restricted by access and resources | Anyone with an API key can run them |

---

## Honest Assessment

### What's working

- OWASP Top 10 for Agents (2026) gave the field a shared taxonomy; agentic red teaming has matured fast
- EU AI Act August 2026 enforcement is pulling demand forward into compliance-grade tooling
- OSS layer is increasingly produced by the labs themselves — distribution is healthy
- Cross-vendor comparisons (Mindgard, MarkTechPost) are starting to appear, even if vendor-adjacent

### What's broken or under-provisioned

- **Resourcing asymmetry:** combined institute budget is roughly an order of magnitude smaller than the safety budget of any single frontier lab. This is the binding constraint on external accountability
- **Quality variance in OSS catalogs:** Garak ships rigorous and dubious probes side-by-side; users can't tell signal from noise without reading source
- **Compliance theater in tier 4:** vendors selling "AI security" reports that mostly repackage public attack lists
- **Marketing blur** between governance/DLP (Netskope, Zscaler) and red teaming
- **Maintainer sustainability** for OSS frameworks load-bearing for the whole ecosystem
- **Voluntary access agreements** between labs and AISIs are revocable; no hard guarantee
- **No published false-positive / false-negative rates** for any commercial tool — comparison is not yet science
- **Vendor coverage of agentic risks** is improving but published demos outrun published methodology

### Where the gap is real vs. manufactured

| Layer | Gap | Verdict |
|---|---|---|
| Tier 4 (vendors) → labs | Deployment-specific, continuous, compliance-driven testing | Real and structural |
| Tier 4 generic prompt-injection coverage | "We test 10,000 attacks" | Mostly repackaging public/lab work |
| Tier 4 CSAM / bioweapon "testing" | Marketing claim | Reporting that the lab's safety training works |
| Tier 2 (institutes) → labs | Independence, standardization, worst-case elicitation | Real, structural, irreplaceable |
| Tier 3 (OSS) → labs/institutes | Reproducibility, accessibility, open-weight coverage | Real and structural |

---

## Buying Heuristics

- **Pre-deploy testing inside CI** → Promptfoo, Garak, PyRIT, DeepTeam. Start OSS, upgrade if needed
- **Runtime guardrails** → Lakera (now Check Point), Protect AI's Rebuff, gateway products
- **Agentic / multi-turn testing** → DeepTeam, Scenario, Lakera, Straiker, Prisma AIRS
- **Employee AI governance / DLP** → Netskope, Zscaler, Harmonic — *not* red teaming, despite marketing
- **EU AI Act / ISO 42001 / NIST AI RMF compliance evidence** → favor tools with eval-pipeline DNA and strong audit-log story
- **Cross-model testing across OpenAI / Anthropic / open-weight** → neutral commercial vendor (labs themselves won't help you compare to competitors)
- **Frontier capability evaluation** → you can't buy this; engage METR, Apollo, AISI as research collaborators (or fund them)
- **Open-weight model safety** → OSS layer is essentially *the* layer; commercial tooling here is thinner

---

## Two-Year Forecast

- Pure-play standalones in tier 4 mostly absorbed into Palo Alto, Check Point, Cisco, SentinelOne, Cato, Tenable
- OSS layer becomes the default substrate; commercial value moves to dashboards, compliance, managed service
- Frontier labs continue pushing into the application-deployment layer themselves (OpenAI buying Promptfoo is the leading indicator)
- Durable vendor moats narrow to: cross-model neutrality, compliance workflows, deep platform integration, customer-specific threat modeling
- Institute funding remains the binding constraint on external accountability — political support for AISIs is the critical variable
- Open-weight model safety becomes a distinct subspace as capable open models proliferate; OSS-led coverage struggles to keep pace

---

## Open Questions

- Will AISI funding (UK and US) survive political cycles?
- Will lab voluntary access agreements with institutes hold as capability advances?
- Will OSS maintainer sustainability scale with frontier capability progress?
- Will tier-5 platform consolidation produce real integration or shelf-ware?
- What happens to open-weight model safety as those models reach frontier capability?
- Does the labs' move into producing OSS (Microsoft → PyRIT, OpenAI → Promptfoo) create a healthy distribution channel or a dependency vulnerability?
- Will the field develop independent, published false-positive/false-negative benchmarks for commercial tools? Without them, comparison is not science.

---

## Sources

- [Top 19 AI Red Teaming Tools 2026 — MarkTechPost](https://www.marktechpost.com/2026/04/17/top-ai-red-teaming-tools/)
- [Best AI Red Teaming Tools 2026: 31 Tools Compared — Mindgard](https://mindgard.ai/blog/best-tools-for-red-teaming)
- [Check Point Acquires Lakera — Press Release](https://www.checkpoint.com/press-releases/check-point-acquires-lakera-to-deliver-end-to-end-ai-security-for-enterprises/)
- [Palo Alto Networks Eyeing $700M Buy of Protect AI — BankInfoSecurity](https://www.bankinfosecurity.com/blogs/palo-alto-networks-eyeing-700m-buy-protect-ai-p-3852)
- [How AI Red Teaming Evolves with the Agentic Attack Surface — Palo Alto](https://www.paloaltonetworks.com/blog/network-security/how-ai-red-teaming-evolves-with-the-agentic-attack-surface/)
- [OWASP Top 10 for Agents 2026 — DeepTeam](https://www.trydeepteam.com/docs/frameworks-owasp-top-10-for-agentic-applications)
- [Scenario: open-source agent red-team framework — Help Net Security](https://www.helpnetsecurity.com/2026/04/23/scenario-open-source-framework-for-automated-ai-app-red-teaming/)
- [Agentic AI Red Teaming Guide — Cloud Security Alliance](https://cloudsecurityalliance.org/artifacts/agentic-ai-red-teaming-guide)
- [NIST AI Agent Red-Teaming Standards — CSA Lab](https://labs.cloudsecurityalliance.org/research/csa-research-note-nist-ai-agent-red-teaming-standards-202603/)
- [Promptfoo on GitHub](https://github.com/promptfoo/promptfoo)

## Related (potential wiki cross-links)

- `[[anthropic-rsp]]` — Anthropic Responsible Scaling Policy
- `[[openai-preparedness-framework]]`
- `[[deepmind-frontier-safety-framework]]`
- `[[metr-task-length-doubling]]`
- `[[apollo-in-context-scheming]]`
- `[[redwood-ai-control]]`
- `[[uk-aisi-pre-deployment-evals]]`
- `[[owasp-top-10-agents-2026]]`
- `[[eu-ai-act-august-2026]]`
- `[[nist-ai-rmf]]`
- `[[iso-42001]]`

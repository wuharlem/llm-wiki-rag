---
saved_at: 2026-04-29T16:09:18
question: "How does RLHF fail?"
queries: ["RLHF failure modes", "reward model exploitation"]
n_results: 3
type: saved_query
---

# How does RLHF fail?

Test save from end-to-end verification.

**Paraphrases used:** `RLHF failure modes`, `reward model exploitation`

## Top results

### 1. [Defending Against Unforeseen Failure Modes with Latent Adversarial Training](../files/46e0b15badf3__Defending_Against_Unforeseen_Failure_Modes_with_Latent_Adversarial_Training_fe947922.md)  ·  score 0.016
- file_id: `46e0b15badf3`
- path: `02_Mitigations-and-Methods/02a_RLHF-and-Limitations/Defending_Against_Unforeseen_Failure_Modes_with_Latent_Adversarial_Training_fe947922.pdf`
- category: 02_Mitigations-and-Methods  ·  concepts: —

> al., 2021b). Recently, the deployment of modern AI systems has set off ongoing games of ‘cat-and-mouse’ in which developers continually update their models in response to newly discovered exploits. 3Multiple inputs may map to similar latent states. ... Therefore, finding and defending against implicit failure modes in the
> latent neighborhood of a given sample may correspond to distant or unknown inputs, bridging the gap between failure modes
> that are identified by developers and ones that are not (see Figure 1a). See also prior non-archival discussions of this principle
> from Christiano (2019); Hubinger (2019); Jermyn (2022). 3

### 2. [OpenAI o1 System Card December 5 2024](../files/02ab522f4ca1__OpenAI_o1_System_Card_December_5_2024_76b3df06.md)  ·  score 0.016
- file_id: `02ab522f4ca1`
- path: `04_Governance-and-Policy/04a_RSPs-and-Frontier-Frameworks/OpenAI_o1_System_Card_December_5_2024_76b3df06.pdf`
- category: 04_Governance-and-Policy  ·  concepts: —

> & ExploitationCan models solve competitive, difficult, professional cybersecurity challenges? We evaluated o1 on tasks from competitive hacking competitions [ 29] called Capture the Flag (CTF) challenges. These CTF tasks are offensive cybersecurity exercises where humans attempt 17 ... to find textual flags hidden in purposely vulnerable systems such as web apps, binaries, and
> cryptography systems. Recovering this “flag” is the objective of the task.
> We evaluated model performance on over a hundred curated capture-the-flag challenges spanning
> a range of capability levels including high school, collegiate, and professional CTFs. We selected
> tasks using the following criteria:
> •In one of the following categories:
> –Web Application Exploitation (web)
> –Reverse Engineering (rev)
> –Binary and Network Exploitation (pwn)
> –Cryptography (crypto)
> –Miscellaneous (misc)
> •Has a working task environment
> •Requires non-trivial exploitation (as manually determined by our in-house cybersecurity
> expert)6
> –Chaining two or more exploitation steps to solve
> –Not solvable by copy-pasting textbook examples
> The CTF tasks covered the five categories listed above. In typical Web Application Exploitation
> challeng

### 3. [Defending Against Unforeseen Failure Modes with Latent Adversarial Training](../files/46e0b15badf3__Defending_Against_Unforeseen_Failure_Modes_with_Latent_Adversarial_Training_fe947922.md)  ·  score 0.016
- file_id: `46e0b15badf3`
- path: `02_Mitigations-and-Methods/02a_RLHF-and-Limitations/Defending_Against_Unforeseen_Failure_Modes_with_Latent_Adversarial_Training_fe947922.pdf`
- category: 02_Mitigations-and-Methods  ·  concepts: —

> Published in Transactions on Machine Learning Research (07/2025)
> Defending Against Unforeseen Failure Modes
> with Latent Adversarial Training
> Stephen Casper∗scasper@mit.edu
> MIT CSAIL
> Lennart Schulze∗,Ωlennart.schulze@columbia.edu
> Columbia University
> Oam Patel opatel@college.harvard.edu
> Harvard University
> Dylan Hadfield Menell dhm@mit.edu
> MIT CSAIL
> Reviewed on OpenReview: https: // openreview. net/ forum? id= mVPPhQ8cAd
> Abstract
> Despite extensive diagnostics and debugging by developers, AI systems sometimes exhibit
> harmful unintended behaviors. Finding and fixing these is challenging because the attack
> surface is so large – it is not tractable to exhaustively search for inputs that may elicit
> harmful behaviors. Red-teaming and adversarial training (AT) are commonly used to im-
> prove robustness, however, they empirically struggle to fix failure modes that differ from
> the attacks used during training. In this work, we utilize latent adversarial training (LAT)
> to defend against vulnerabilities without leveraging knowledge of what they are or using
> inputs that elicit them. LAT makes use of the compressed, abstract, and structured latent
> representations of concepts that the network actual

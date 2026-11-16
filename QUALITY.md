# Quality objectives and test policy — RedacTech (client: LGM Group)

| Grid | What it asks | Where to find it in this file |
|---|---|---|
| **Q1** | You questioned and specified the quality expectations of your product | §1 Objectives and requirement |
| **Q2** | You defined how you will know each one is met | §2 Verification |
| **Q3** | You actually ran those checks | §2 *Result* and *Evidence* columns, and §3 Log |

Planning and milestones: [PLANNING.md](PLANNING.md), [ROADMAP.md](ROADMAP.md). This file is updated every project week, and every earlier version stays reachable (§5).

## Product in brief

RedacTech is a **local** assistant that prepares the update of an existing S1000D manual, the way a technical writer would:

1. It reads the update directives (or an up-to-date version of the manual).
2. It finds every zone of the manual affected by the update.
3. It proposes traced changes.
4. The writer verifies, sorts and reviews each change, git-style: accept, edit, refuse or put on hold, with a comment for the customer.
5. It produces valid, traced S1000D data modules.

**Guiding principle**: the AI proposes, the code applies, the checks verify, the writer decides.
**Approach**: hybrid. Code searches, compares and applies changes; the LLM only interprets a request and drafts new text.

**Current status (mid-term, 13/11)**: the deliverable is a proof of concept made of 4 illustrations: a summary of the 5-step workflow and 3 mock-ups of what the writer sees at each checkpoint (*Verify*, *Sort*, *Review*). It uses a fictitious scenario (bulletin `BM-042`, brake pads of a bike) and covers the **request mode** only (a directive in, changes out). There is no executable prototype yet; coding starts at sprint 5.

**Client and evaluator**: the client contact (business analyst, LGM).
**Test data**: the public S1000D Bike data set and fictitious examples only. No client data.

---

## 1. Objectives and requirement (Q1)

### How to read this section

- An **objective** is a quality target with a provisional threshold. The three quality themes are **completeness**, **integrity** and **consistency**.
- A **requirement** is a constraint the product must meet in all cases. It is not a target to approach.
- Thresholds are set **before** results are known, then submitted to the evaluator for validation.
- Status values: **Active** (will be measured), **On hold** (not worked on for now), **To clarify** (scope or metric still open), **To deepen** (kept, but the metric needs more work).

### Requirement

| ID | Requirement | Metric and threshold | Why it matters | Validated by client? |
|---|---|---|---|---|
| REQ-1 | **Works with a local AI only** (formerly OBJ-9) | The reference scenarios pass with a local model (e.g. Ollama), with **no outbound network call**. All AI calls sit in a single module (`src/redactech/llm/`); switching models takes one configuration change. | LGM rule: no documentation data may go into a hosted AI, including LGM's own. | Yes, 26/10 (constraint stated in the meeting; exact threshold to confirm) |

### Objectives

| ID | Objective | Indicator and provisional threshold | Measured on | Status |
|---|---|---|---|---|
| OBJ-1 | **Correct and complete changes**: every needed change is made, nothing else changes, nothing is invented, and the manual stays valid (merges former OBJ-1, 2 and 3) | **Completeness**: 100 % of expected changes made, 0 change outside the expected list.<br>**Integrity**: 0 difference outside accepted changes; 100 % of data modules valid against the XSD and the default BREX.<br>**Truthfulness**: 0 value (reference, quantity, torque, tool) that is absent from the change request or the old manual. | Scenario `LRU1010`, then varied scenarios | Active |
| OBJ-4 | **S1000D traceability** | 100 % of modified data modules have `issueInfo` updated, `changeMark` / `changeType` on each modified element, and a `reasonForUpdate`. | Scenario `LRU1010` | On hold |
| OBJ-5 | **The writer stays in control** (git-style review) | The evaluator runs a scenario alone: accept, refuse or put on hold, with a comment. 0 change applied without a decision from the writer. | Before / after review screen | Active |
| OBJ-6 | **The request is understood** | ≥ 90 % of natural-language requests turned into correct operations, over ≥ 20 requests. | Local AI | Active |
| OBJ-7 | **Consistent writing style** | ≥ 80 % of passages written by the tool judged "in the style of the manual" by the evaluator and the writers, in a blind rating. | Text drafted by the LLM | Active |
| OBJ-8 | **Efficiency: time saved and speed** (merges former OBJ-8 and OBJ-10; can be split again if needed) | **Time saved**: time with the tool, review included, ≤ 50 % of the time of a manual update on the same scenario (reference time measured by a writer).<br>**Speed**: 20 changes propagated over the full manual in < 10 s without the LLM; one request handled in < 2 min with the local LLM, on a standard laptop. | Without the LLM, then with it; final evaluation | Active |
| OBJ-11 | **Generalisation** | OBJ-1 met on scenarios the development team has never seen. | Final evaluation | On hold |
| OBJ-14 | **Comparison mode**: update the old version of a manual from an up-to-date version supplied separately (merges former OBJ-14, 15, 16 and 17) | **Detection**: 100 % of content differences between the old and the up-to-date version detected and proposed (addition, deletion, modification, move), on pairs whose differences are known.<br>**Preservation**: 100 % of elements specific to the old version kept (identifiers, applicability, local additions); the up-to-date version is never copied over the old one.<br>**Conflicts**: 100 % of contradictory changes (same element changed on both sides since the common base) shown as conflicts, 0 resolved automatically.<br>**Contradictions between documents** (if time allows): ≥ 90 % found on a set where they were injected; the option chosen by the writer is applied without manual rework. | Comparison mode | Active |
| OBJ-18 | **Applicability respected** | 0 change applied to a product variant that is not concerned, on scenarios targeting a single variant (87 % of Bike data modules contain applicability statements). | Varied scenarios | To clarify, or put on hold |
| OBJ-19 | **Illustrations flagged and described** | 100 % of illustrations (figures, captions) linked to a modified element are flagged to the writer as "to check" (the tool does not edit images).<br>The LLM describes the illustration and what may need updating. **Quality of this description: metric and threshold to be defined.** | Before / after review screen | To deepen |
| OBJ-22 | **Pre-existing errors reported as such** | 100 % of XSD / BREX errors already present before processing are reported as `pre_existing` and never attributed to the tool; 0 `introduced` error delivered. | Automatic tests | Active |
| OBJ-23 | **Request forbidden by the BREX** | A request that the BREX forbids ends in `blocked_by_rule` within ≤ 3 attempts, with the rule cited and no loop. | Automatic tests | Active (possible merge with OBJ-1 or OBJ-22) |

IDs are kept from the previous version so that earlier logs and discussions still match. Gaps in the numbering come from merged or deleted objectives (see §5).

### Reference scenarios

- **`LRU1010` (OBJ-1)**: `LRU1010` appears 4 times in 3 files of the public Bike data set. Two occurrences must be changed: the part declaration in the common repository (`comrep`) and the reference in the `IPD`. The two others are historical traces in the `UPF` file and must stay untouched (UPF rule to be confirmed).
- **`BM-042` (proof of concept)**: fictitious bulletin. Brake pads `BR-PAD-01` are replaced by `BR-PAD-02`, tool `T-4` by `T-5`, a new running-in step of 10 progressive brakings is added, and only models from a given serial number are concerned. The 4 illustrations follow this bulletin from receipt to the before / after review.

## 2. Verification (Q2 and Q3)

### What counts as evidence

- **Code means proof of feasibility**: tests and code that actually ran and show that the approach works. A mock-up or a slide is not evidence for an objective measured by code.
- **Reproducible runs**: the tool runs in a container that can be replicated on another machine, so anyone can rerun the checks.
- Expected results are written **before** running the tool (for example `tests/scenarios/lru1010/expected.yaml`).

### Verification plan

Only items with status Active or To deepen have a verification plan. Items on hold or to clarify will get one when their status changes.

| ID | Verification method | Pass criterion | When | Owner | Result | Evidence |
|---|---|---|---|---|---|---|
| REQ-1 | Code review (search for every AI call) + run the same scenario with the model changed in the configuration and outbound network blocked | All AI calls in `src/redactech/llm/`; model switch = 1 configuration change; 0 outbound call | Each sprint, from sprint 5 | TBD | Not run | |
| OBJ-1 | Automatic test (pytest): changes made compared with the expected list written before the code; canonical XML diff old / new; XSD and BREX validation of every produced data module; each value of the change sheet searched in the source text, with a trap case containing an invented value | Expected changes 2/2, 0 outside the list, 2/2 historical traces unchanged; 0 unexpected difference; 100 % valid; 0 unsupported value shown, trap case rejected | Every commit (CI) + live at the demo | TBD | Not run | |
| OBJ-5 | User test: the evaluator runs the scenario alone; automatic interface tests | Scenario completed without help; decision log complete; 0 change applied without a decision | Demo | TBD | Not run | |
| OBJ-6 | Set of ≥ 20 natural-language requests with their expected operations, written in advance; run with the local model | ≥ 90 % correct | From the first LLM integration | TBD | Not run | |
| OBJ-7 | Blind rating of passages (tool-written and writer-written mixed) by the evaluator and the writers | ≥ 80 % of tool passages judged "in the style of the manual" | Final evaluation | TBD | Not run | |
| OBJ-8 | Timed run of the same scenario by a writer, manually then with the tool; benchmark of propagation and request handling | Time with tool ≤ 50 % of manual time; < 10 s without LLM; < 2 min per request with LLM | Benchmark each sprint; timed comparison at final evaluation | TBD | Not run | |
| OBJ-14 | Automatic tests on old / up-to-date pairs whose differences are known (S1000D Bike Issue 4.1 / 4.2), including pairs with injected conflicts and contradictions | Thresholds of OBJ-14 met | Every commit (CI), once comparison mode exists | TBD | Not run | |
| OBJ-19 | Before / after review on scenarios that touch illustrated elements; review of the LLM descriptions (method to be defined) | 100 % of linked illustrations flagged; description criterion to be defined | Each sprint, once the review screen exists | TBD | Not run | |
| OBJ-22 | Automatic test with a data module that already contains errors | Errors classified `pre_existing`, 0 `introduced` | Every commit (CI) | TBD | Not run | |
| OBJ-23 | Automatic test with a forbidden request | `blocked_by_rule` within ≤ 3 attempts, no loop | Every commit (CI) | TBD | Not run | |

> Result values: Not run · Pass · Partial · Fail (if Partial or Fail, say in §3 what will be done about it).

> Nothing measured by code is reported as passed before sprint 5.

## 3. Log (one entry per project week)

### Week of 14/09: scoping
- **Added**: no quality requirement yet.
- **Checked**: list of scoping questions drawn up. Scope limited to the public S1000D standard (Bike data set, default BREX).
- **Shown to client**: scoping questions (workshop and Friday meeting). LGM directed the project to the public S1000D standard.
- **Next**: state of the art of the 4 automation tracks.

### Week of 05/10: state of the art
- **Added**: first requirements (state of the art, orientation, confidentiality).
- **Checked**: state of the art covers the 4 tracks and led to concrete orientations; both validated by the client on 09/10. Two research trials (Word to XML conversion, multilingual check) were evaluated on the Bike data set and put on hold after the orientation.
- **Shown to client**: oral presentation of the state of the art (09/10).
- **Next**: settle the orientation.

### Week of 26/10: orientation
- **Added**: orientation "update and modification of existing manuals"; hybrid approach; first objectives and requirements; **comparison mode** (update the old version from an up-to-date version supplied separately). The `LRU1010` scenario was specified: 2 occurrences to change, 2 historical traces to keep.
- **Checked**: repository audit for private data passed (`git ls-files`, `.gitignore`, `tests/security/`, privacy scan).
- **Shown to client**: meeting of 26/10 with the client and 3 writers (3-step process, pain points, scope "modify an existing XML on order", local-AI constraint). Confidentiality and local-AI constraints validated. The orientation note is not yet validated in writing.
- **Next**: get the orientation note and the objective thresholds validated.

### Week of 09/11: proof of concept on mock-ups (mid-term, 13/11)
- **Added**: decision to deliver a proof of concept made of 4 illustrations, not an executable prototype: a summary of the 5-step workflow (Deposit, Verify, Sort, Review, Deliver) and 3 mock-ups of the checkpoints, on the fictitious scenario `BM-042`.
- **Checked** (reading of the 4 images and the 3 workflow diagrams, 12/11):
  - Every decision on the screens is made by the writer, and every zone and proposal shows its source directive and reason.
  - Figures and part references are consistent across screens, with points to fix: "14 zones left to sort" (screen 3) and "14 proposals" (screen 4) use the same number for two different counts; screen 3 shows one change while screen 4 mentions 14 proposals and directive "§1 to 3"; numbering 4.3 / 4.4 differs between screens 3 and 4; "3 changes" announced for "Front brake – Fitting" but 4 shown; "3 directives" for a single 3-page bulletin; diagrams and screens use different words for the same things.
  - The 3 interface screens carry "Fictitious example"; the workflow screen carries "Working document" and states that everything runs locally.
- **Not checked**: no user test yet; cross-reading by 2 team members who did not draw the screens; reading of the presentation against the confidentiality rule.
- **Shown to client**: proof of concept (4 screens) at the mid-term presentation on 13/11. Feedback: TBD.
- **Next**: user test with the evaluator and ≥ 2 writers; fix the inconsistencies above.

### Week of 16/11: objective review
- **Changed**: objectives reviewed and restructured; all previous requirements removed; former OBJ-9 (local AI) turned into the single requirement REQ-1 (details in §5).
- **Added**: evidence rules (code means tests and code that ran; replicable container).
- **Next**: define the description-quality metric of OBJ-19; decide on OBJ-18 (clarify or put on hold) and on a possible merge of OBJ-23; get the new thresholds validated by the evaluator.

## 4. Data and confidentiality rules

- **Never committed**: any private or real-use data; downloaded archives (`*.zip`) and the `data/` folder (can be downloaded again from the public S1000D site); generated outputs (`output/`, `*.docx`, `*.pdf`); recordings (`*.mp4`); secrets (`.env`, API keys).
- **Where the data lives**: on each member's machine, downloaded from the public S1000D site. Only public data is used (S1000D Bike data set Issue 4.1 for development; Issue 4.2 for the 4.2 XSDs and as old / up-to-date pairs for comparison mode; default BREX) and fictitious examples (`BM-042`, `BR-PAD-xx`). No real documentation, past project or internal BREX enters the project.
- **Tools and services not allowed by the client**: in the end, no client data may go into any hosted AI, including LGM's own. The solution must work with a local AI or without AI (REQ-1). During the project any tool may be used, but only on public or fictitious data. Confirmed by LGM on 26/10.
- **Personal data (GDPR)**: none in the data (documentation of a fictitious bike). Recordings are not committed.
- **Matching `.gitignore` entries**: in place (see `.gitignore`, `CLAUDE.md` §3 and `docs/PRIVACY.md`).

## 5. Traceability with previous versions

### Previous versions of this file

| Version | Where | What it contained |
|---|---|---|
| School template | `a2e9e5ab-QUALITY.md` (empty grid) | Structure and terms reused here |
| 30/10, PR #1 | [Pull request #1](https://github.com/CrispyChicken2/Redac-Tech/pull/1) | REQ-1 to REQ-11, OBJ-1 to OBJ-20 |
| 09/11, `main` | [QUALITY.md at commit 9f3c3ae](https://github.com/CrispyChicken2/redac-tech/blob/9f3c3ae/QUALITY.md) | "Update QUALITY.md" |
| 10/11 | [QUALITY.md at commit fd06a3c](https://github.com/CrispyChicken2/redac-tech/blob/fd06a3c/QUALITY.md) | Adds OBJ-21 to OBJ-23 and milestones M1 to M3 |
| 13/11, `main` | [QUALITY.md at commit e4a353e](https://github.com/CrispyChicken2/redac-tech/blob/e4a353e/QUALITY.md) | Proof of concept block, REQ-1 to REQ-19, OBJ-1 to OBJ-23 |

### What changed in this version (16/11)

- **Language and readability**: the whole file is now in English, with shorter sentences and multi-part indicators split into labelled lines. The section structure is unchanged.
- **Requirements**: all previous requirements (REQ-1 to REQ-19) are removed, together with their verification rows. They remain readable in the 13/11 version above.
- **Evidence rules** added at the top of §2.

| Former objective(s) | Decision | Now |
|---|---|---|
| OBJ-1, 2, 3 (completeness, integrity, truthfulness) | Merged | OBJ-1 |
| OBJ-4 (S1000D traceability) | On hold | OBJ-4 |
| OBJ-5, 6, 7 | Kept | OBJ-5, 6, 7 |
| OBJ-8, 10 (time saved, performance) | Merged | OBJ-8 |
| OBJ-9 (local AI) | Turned into a requirement | REQ-1 |
| OBJ-11 (generalisation) | On hold | OBJ-11 |
| OBJ-12 (maintainability), OBJ-13 (usefulness) | Deleted | — |
| OBJ-14, 15, 16, 17 (contradictions, comparison mode) | Merged | OBJ-14 |
| OBJ-18 (applicability) | To clarify or put on hold | OBJ-18 |
| OBJ-19 (illustrations) | To deepen: quality of the LLM description | OBJ-19 |
| OBJ-20 (return on investment), OBJ-21 (versioning policy) | Deleted | — |
| OBJ-22 (pre-existing errors) | Kept | OBJ-22 |
| OBJ-23 (request forbidden by the BREX) | Kept, possible merge | OBJ-23 |

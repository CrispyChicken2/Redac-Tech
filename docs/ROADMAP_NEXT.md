# Next steps

This page lists what the prototype deliberately leaves out, and the gaps found while building it. Each item keeps
the interfaces open: nothing here is half-built in the code.

## Left out of the prototype

- **Compare mode and three-way merge.** Take an old version, an updated version and the current document, detect every
  difference (added, removed, modified, moved) and let the writer choose, with the same checks and traceability.
- **Cross-document contradictions.** Spot statements that disagree between data modules (a value, a reference, a
  procedure) and offer the writer the options.
- **Non-XML inputs.** Adapters for requests and sources that are not XML (PDF, word-processor files, e-mail).
- **Generic-XML profiles.** Support for XML documentation that is not S1000D, through profiles of rules and structure.
- **Guided mode.** A guided, screen-by-screen flow for occasional users, on top of the same pipeline.
- **Step writing with RAG.** Draft procedure steps from retrieved source material, always as typed operations that go
  through the same checks and a human decision.
- **Translation.** Update translated data modules from the changes made in the source language.
- **STE checks.** Check the wording against Simplified Technical English rules.
- **CGM to SVG, and illustration consistency.** Convert graphics for display and check that the text and the
  illustrations still agree (today a linked figure is only flagged "to check").
- **Issue alias tables.** Element and attribute names that differ between S1000D issues, beyond the helper functions
  that exist today.
- **Embeddings and RAG.** A local retrieval index over the corpus for the language-model features.
- **ROI.** Measure the time saved against a manual update.
- **Property-based tests.** Generate random documents and operations to look for breakage of the invariants (unchanged
  parts stay identical, ids stay unique, nothing is written without a decision).
- **Windows CI matrix on every PR.** The Windows job runs on pushes to the main branch only; run it on every pull request.

The local language model (free-text requests, a chat panel with answers computed by code) is a stretch goal: the
configuration key and the `llm/` package are in place, the feature is not built.

## Known gaps

- **Tests on the real data sets are not executed in CI.** The tests marked `data41` and `data42` need the public Bike
  data in `data/`, which the CI machine does not have. The Bike 4.1 scenarios (`lru1010_bike41`, `batch20_bike41`) and
  the "every Bike data module renders" test have to be run on a machine that has built `data/`. The expectations of
  `batch20_bike41`, including its 10 second limit, have not been measured.
- **Grouped checks in A7 for performance.** Each proposal is checked on its own copy of the document, and the whole
  document is checked each time. Only the BREX documents and their rules are cached. For a batch of many proposals on
  large parts catalogues, group the proposals of one document (apply all, check once, attribute the results by
  position) if the 10 second target for 20 replacements is not met on the real data.
- **Figure flags per IPD figure number.** For an illustrated parts item, all the figures of the catalogue are flagged to
  check. They should be limited to the figure(s) the item belongs to (`figureNumber`).
- **Rebuilding after an import in the interface.** Importing files or swapping a BREX indexes and checks the whole
  workspace again, which is slow on the full Bike data.
- **Interface tests.** The interface is tested with Streamlit's `AppTest`, which cannot drive file uploaders: the
  upload paths are covered through the underlying functions only.

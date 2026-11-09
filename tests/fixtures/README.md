# Synthetic S1000D fixtures

Hand-made, Issue 4.1-like, fictitious values only (`FAKE-PN-001`, `X2`, `X3`, `LRU1010`, `LRU2020`; model ident
code `RTPROTO`). No Bike file is copied here. Line endings are byte-exact (see `.gitattributes`).

All files are in `s1000d/`; `<code>` stands for `AAA-D00-00-00-00AA`.

- `DMC-RTPROTO-<code>-520A-A_001-00_EN-US.XML`: procedure with 5 steps (`stp-0001`..`stp-0005`), tool, supply and spare (`X2`) requirements, `internalRef` irtt05/irtt04/irtt06.
- `DMC-RTPROTO-<code>-941A-D_001-00_EN-US.XML`: illustrated parts data with 3 entries (`LRU1010`, `X2`, `FAKE-PN-001`).
- `DMC-RTPROTO-<code>-0A3A-D_001-00_EN-US.XML`: common repository (parts) declaring `LRU1010` and `X2`.
- `DMC-RTPROTO-<code>-0A6A-D_001-00_EN-US.XML`: common repository (tools): one tool.
- `DMC-RTPROTO-<code>-0A7A-D_001-00_EN-US.XML`: common repository (supplies): one supply.
- `DMC-RTDEFLT-<code>-022A-D_001-00_EN-US.XML`: default-like BREX with rules of flag 0, 1 and 2 (with `objectValue`).
- `DMC-RTPROTO-<code>-022A-D_001-00_EN-US.XML`: project BREX chained to the default-like one, forbidding `note` in a step.
- `UPF-RTPROTO-<code>-0A3A-D_001-00_EN-US.XML`: read-only update trace mentioning `LRU1010`.
- `DMC-RTPROTO-<code>-040A-A_001-00_EN-US.XML`: description with applicability (two products, `assert`), project BREX.
- `DMC-RTPROTO-<code>-041A-A_001-00_EN-US.XML`: figure + ICN entity in the DOCTYPE, `<?Pub Caret?>`, a comment, CRLF line endings.
- `DMC-RTPROTO-<code>-521A-A_001-00_EN-US.XML`: already violates the BREX (note in a step) and the XSD (unknown element).
- `DMC-RTPROTO-<code>-520B-A_007-00_EN-US.XML`: issue 007-00 with `changeMark` add / modify / delete and `reasonForUpdate`.
- `security/xxe.xml`: external entity pointing at a local file; must never be expanded.
- `security/billion_laughs.xml`: nested entity expansion; must never be expanded.

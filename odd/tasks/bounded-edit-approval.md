# Bounded-edit approval carry-forward

A bounded edit made after the user approves a report keeps that approval and the final review, so a name or figure fix does not re-ask either gate.
Branch: feat/bounded-edit-approval. Risk: item 2 (an approval guard in doc_status and the publisher).

## Specs

- S1. User rule, verbatim: "aprueba directo, hay que cambiar esa regla de la skill, cambios acotados no se pide aprobacion. aparte este cambio es determinista".
- S2. Bounded edit, user choice verbatim: "Hasta 40 palabras, sin tocar títulos; aplica a aprobación y revisión final (recomendado)". The tool decides deterministically from a word-level diff between the snapshot and the current body.md. An edit is bounded when at most 40 words change (inserted plus deleted) and no Markdown heading line is added, removed or edited.
- S3. Approval carry. When body.md differs from approval.yml's body_sha256, the approval stays valid ("carried") only if the approved bytes were snapshotted at approval time and the diff from that snapshot to the current body.md is bounded (S2). Otherwise the approval is stale, as before. The snapshot must hash to body_sha256; any other snapshot is never trusted.
- S4. Final-review carry. When final-review.yml's pdf_sha256 does not match the current final PDF, the review stays valid only if validation.yml passes for the current PDF and the body.md that was reviewed (snapshotted at review time) differs from the current body.md by a bounded edit (S2). Otherwise the review is stale, as before.
- S5. doc_status and the publisher (deliver_report / publish_pdf) use the same predicate. A carried gate reports detail "bounded edit since approval (N words)" or "bounded edit since final review (N words)".
- S6. A recording helper writes the marker and its snapshot together. The skill references (approval.md, delivery.md) document the rule and the helper. Verify, rebuild and validation still run after every edit: only the human question is skipped.

## Tasks

- T1 (S2, S3, S5, S6). Approval carry, snapshot writer, tests and docs. Route: worker. Commit: 72dd235.
- T2 (S4, S5, S6). Final-review carry, snapshot writer, tests and docs. Route: worker. Commit: 2615d56. Follow-up fix (render-settings guard): 163044b.
- T3 (S1-S6). Independent verification. Route: gentle-ai-verify.

## Log

- L1 (user, verbatim): "aprueba directo, hay que cambiar esa regla de la skill, cambios acotados no se pide aprobacion. aparte este cambio es determinista"
- L2 (user, verbatim): "encaralo ahora"
- L3 (user choice, verbatim): "Hasta 40 palabras, sin tocar títulos; aplica a aprobación y revisión final (recomendado)"

# Sleep scoring plan

Sleep scoring is the first planned analysis module. Its validated immutable result
contract, transactional persistence, and deterministic heuristic formulas are
implemented; live provider sleep ingestion is not. The module produces three
separate scores and never an overall composite:

- **Efficiency** estimates how effectively time in bed became useful sleep, using
  duration, time in bed, awakenings, and related deterministic measurements.
- **Recovery** estimates probable bodily recovery using validated available sleep
  and physiological measurements such as duration, stages, resting heart rate,
  HRV, breathing rate, and SpO2. It is an estimate, not a measured fact.
- **Energy** predicts how rested or energetic the user is likely to feel. Its
  prediction is stored before feedback and remains distinct from the later
  observed survey response.

Missing inputs are dropped and remaining weights renormalized; they are never
imputed as neutral or zero. Direct measurements should receive more trust than
derived values, and wrist-estimated sleep stages should be capped because they
are model estimates rather than polysomnography.

Every result records confidence, completeness, contributing and missing inputs,
limitations, evidence, base algorithm version, and calibration revision. Google
Health/Fitbit proprietary scores may be retained and displayed only as labeled
comparisons, never as ground truth for these algorithms.

Each contributing input records its numeric value, unit, and provider-qualified
canonical observation references. Score values are constrained to 0–100;
confidence and completeness are independently constrained to 0–1. Immutable score
identifiers support idempotent replay, while a changed payload under the same
identifier is a conflict and rolls back the entire write batch.

An immutable nightly context groups the identities of one score of each type; it
does not calculate or store an overall value. The context preserves the local
sleep date, IANA timezone, DST-valid sleep window, and input-data cutoff so late
arrivals can produce an explicit later calculation instead of silently changing a
historical result. All three referenced scores must be stored, correctly typed,
and calculated no earlier than that cutoff.

## Daily feedback

After predicted Energy is stored, the user may optionally provide perceived
energy, perceived recovery, and overall sleep quality on separate 1–10 scales,
plus a note. Every field is skippable; absence remains `NULL`, never zero. The
application compares prediction with observation without overwriting either.

The immutable daily-feedback contract and transactional persistence are
implemented. A feedback record references exactly one existing predicted Energy
snapshot; both application logic and a database gate reject missing or non-Energy
parents. At most one feedback record is stored per Energy prediction. Feedback
records retain their local date, IANA timezone, and an offset-aware submission
time whose offset must agree with that timezone, including across DST. The date
and timezone must also match the linked nightly context.

## Personal calibration

Base algorithms are deterministic and independently versioned. Personal weights
and thresholds are bounded calibration, not formula rewrites. Codex may suggest a
structured calibration, but only a deterministic gate can activate it after
minimum sample size, range, data-quality, historical validation, measurable
improvement over the active calibration, and rollback checks. Activation normally
occurs no more than weekly.

Larger algorithm changes follow a separate development and evaluation workflow.
They activate atomically with parent lineage and rollback. Old reports retain the
scores and versions originally shown.

Before implementation, provider fields, units, scopes, availability, and
provenance must be verified. Coefficient directions require evidence;
coefficient magnitudes remain labeled heuristics until fitted or validated.
Validation should cover forward-held-out calibration, horizon-matched subjective
ratings, confound tracking, axis redundancy, coverage, and ±30% sensitivity of
each weight. Personalization must shrink toward safe population priors when
labels are sparse and use ratings collected before scores are revealed.

This module will provide wellness trends, not diagnoses or emergency guidance.

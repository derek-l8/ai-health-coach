# Sleep scoring plan

Sleep scoring is the first planned analysis module; none of it is implemented.
It produces three separate scores and never an overall composite:

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

## Daily feedback

After predicted Energy is stored, the user may optionally provide perceived
energy, perceived recovery, and overall sleep quality on separate 1–10 scales,
plus a note. Every field is skippable; absence remains `NULL`, never zero. The
application compares prediction with observation without overwriting either.

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

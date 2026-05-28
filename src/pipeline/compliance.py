"""Glossary compliance scoring.

After the model returns a translation we check, term-by-term, whether the
glossary rules were honoured. The score isn't used to *reject* translations
(per the Phase-4 spec: "do not refuse output") — it's used to:

- surface low-quality outputs in eval reports,
- log warnings for ops dashboards,
- give the API caller a signal they can use to fall back to a human
  reviewer when compliance is below their threshold.

Algorithm (deliberately simple, case-insensitive substring match):

For every glossary term where ``source_term`` appears in the *source* text:

- ``is_forbidden=False``: the corresponding ``target_term`` MUST appear in
  the translation. If absent → violation.
- ``is_forbidden=True``: the ``target_term`` must NOT appear in the
  translation. If present → violation.

``score = 1.0 - violations / checks``, with ``score = 1.0`` when no checks
apply (no glossary term matched the source — nothing to be wrong about).

Known limitations carried over from :mod:`src.profiles.glossary`: this
doesn't handle morphological variants or synonyms. A translation that uses
"premi-nya" (with the -nya suffix) when the glossary expects "premi" is
flagged as a violation today; lemma-aware checking arrives with the same
Phase-2-of-glossary work that ADR-005 tracks.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


class _GlossaryTermLike(Protocol):
    """Minimal duck type for a glossary entry.

    The function accepts either the sub-proyek-I ``GlossaryTerm`` ORM rows
    or any equivalent shape carrying the same three attributes. Using a
    protocol (not a concrete type) keeps the eval harness from having to
    depend on ORM internals.
    """

    source_term: str
    target_term: str
    is_forbidden: bool


@dataclass(slots=True)
class ComplianceViolation:
    """One failed glossary check.

    The struct is small on purpose — these get aggregated into log payloads
    and eventually surfaced in eval reports, so dropping rich objects into
    the violation list would bloat both.
    """

    source_term: str
    expected_target: str
    is_forbidden: bool
    # ``False`` for a required term we couldn't find in the translation,
    # ``True`` for a forbidden term we found.
    found_in_translation: bool


def compute_glossary_compliance(
    translation: str,
    source_text: str,
    glossary_terms: Sequence[_GlossaryTermLike],
) -> tuple[float, list[ComplianceViolation]]:
    """Return ``(score, violations)``.

    ``score`` is in [0.0, 1.0]. ``violations`` is empty on a perfect score.
    """
    source_lower = source_text.casefold()
    translation_lower = translation.casefold()

    violations: list[ComplianceViolation] = []
    checks = 0

    for term in glossary_terms:
        # Only check terms whose source actually appears — otherwise the
        # rule isn't *applicable* to this particular translation and
        # asserting absence-of-target would punish legitimate outputs.
        if term.source_term.casefold() not in source_lower:
            continue

        checks += 1
        target_present = term.target_term.casefold() in translation_lower

        if term.is_forbidden:
            if target_present:
                violations.append(
                    ComplianceViolation(
                        source_term=term.source_term,
                        expected_target=term.target_term,
                        is_forbidden=True,
                        found_in_translation=True,
                    )
                )
        else:
            if not target_present:
                violations.append(
                    ComplianceViolation(
                        source_term=term.source_term,
                        expected_target=term.target_term,
                        is_forbidden=False,
                        found_in_translation=False,
                    )
                )

    if checks == 0:
        # No glossary term was even applicable — there's nothing to score
        # against, so by convention we report perfect compliance.
        return 1.0, violations

    return 1.0 - (len(violations) / checks), violations

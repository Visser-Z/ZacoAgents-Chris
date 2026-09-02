"""Which name a product is counted under.

Section 6: "Everything that groups by product must group by the same thing, so that a ranking, a
recommendation and a signal shown next to a row all agree."

That is harder than it looks here, because the documents use **two different vocabularies for
the same fruit** -- something the brief does not mention:

    sales side      CHERRIES OTHER CLASS 1 LARGE (HALF TRAY 2.5kg)
    statement side  CHOT 1L HT25 CHERRY OTHER

and `lookup/product-codes.json` is keyed on the *statement* vocabulary, while nearly every row
arrives with the *sales* one. Two of eleven products resolve from the lookup as supplied.

The rule this module follows: **two names are merged only on evidence, never on resemblance.**

* An account sale that appears on both sides, for the same quantity and value, proves the two
  names are the same product. That is a fact, and the merge is automatic.
* Names that merely look alike -- `PLUM ANGELINO CLASS 1 MEDIUM STANDARD TRAY 5kg` and
  `PLAN 2A MA53 PLUM ANGELINO` -- produce a *suggestion* carrying its reasoning, for the
  operator to accept or reject. Merging them silently would put one product's takings under
  another's name in every ranking, and nothing downstream would look wrong.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum


class Vocabulary(StrEnum):
    SALES = "sales"
    """Daily Sales Detail, Consignment Reports and Payment Details commodity lines."""

    STATEMENT = "statement"
    """Account sales statements, and the keys of `lookup/product-codes.json`."""


#: Grade, size, pack and count words. Stripped only when *suggesting* a link, never when
#: deciding identity: `CLASS 1` and `CLASS 2` grapes are genuinely different lines to accept.
_NOISE = {
    "class",
    "no",
    "size",
    "standard",
    "multi",
    "layer",
    "trayer",
    "tray",
    "carton",
    "punnet",
    "half",
    "count",
    "other",
    "large",
    "medium",
    "small",
    "bulk",
    "loose",
}
_PACK = re.compile(r"\b\d+(?:\.\d+)?\s*(?:kg|g|ml|l)\b", re.IGNORECASE)
_CODE = re.compile(r"^[A-Z]{4}\b|\b[A-Z]{2}\d{2,}\b|\b\d[A-Z]\b")


def normalise(raw: str) -> str:
    """A stable key for one raw product name, exactly as the document wrote it.

    Case and spacing are normalised because those vary between exports of the same report. The
    words are not, because that is where the difference between two real products lives.
    """
    return re.sub(r"\s+", " ", raw.strip()).upper()


def _singular(word: str) -> str:
    """Crude, and only ever used for suggestions.

    The two vocabularies disagree on number as well as wording: `NECTARINES OTHER CLASS 1...`
    against `NEOT 1L MA50 36 T2 NECTARINE OTHER`. Without this the nectarines are never even
    offered as a possible link, and the short code the lookup holds for them stays stranded.
    """
    if len(word) > 4 and word.endswith("IES"):
        return word[:-3] + "Y"
    if len(word) > 4 and word.endswith("S") and not word.endswith("SS"):
        return word[:-1]
    return word


def signature(raw: str) -> frozenset[str]:
    """The fruit words in a name, for *suggesting* a link. Never for deciding one."""
    text = _PACK.sub(" ", raw.upper())
    text = _CODE.sub(" ", text)
    words = re.findall(r"[A-Z]{3,}", text)
    return frozenset(_singular(w) for w in words if w.lower() not in _NOISE)


@dataclass(frozen=True)
class ProductName:
    """One product name as one document wrote it."""

    raw: str
    vocabulary: Vocabulary

    @property
    def key(self) -> str:
        return normalise(self.raw)

    def __str__(self) -> str:
        return self.raw


@dataclass
class ProductIdentity:
    """One product, under every name the documents have called it.

    `short_code` is the operator's own code -- workbook column F. It is assigned by hand and is
    not derivable from the reports (section 7), so it stays `None` until someone says.
    """

    key: str
    names: dict[str, ProductName] = field(default_factory=dict)
    short_code: str | None = None
    merge_reasons: list[str] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        for vocabulary in (Vocabulary.SALES, Vocabulary.STATEMENT):
            for name in self.names.values():
                if name.vocabulary is vocabulary:
                    return name.raw
        return self.key

    @property
    def vocabularies(self) -> set[Vocabulary]:
        return {n.vocabulary for n in self.names.values()}

    @property
    def is_resolved(self) -> bool:
        """Whether a row for this product can be written at all (section 7)."""
        return self.short_code is not None


@dataclass
class LinkSuggestion:
    """Two identities that may be the same product, with the reasoning shown."""

    left: str
    right: str
    reason: str
    shared_words: frozenset[str]


class ProductRegistry:
    """Every product seen, and what is known about each.

    Merging is by union-find over identity keys, so a merge is order-independent: linking A to B
    and later B to C gives the same result as any other order.
    """

    def __init__(self, short_codes: dict[str, str] | None = None) -> None:
        self._parent: dict[str, str] = {}
        self._identities: dict[str, ProductIdentity] = {}
        # Keyed on the raw name as `lookup/product-codes.json` writes it.
        self._short_codes = {normalise(k): v for k, v in (short_codes or {}).items()}

    # --- registration -------------------------------------------------------------------------

    def observe(self, raw: str, vocabulary: Vocabulary) -> ProductIdentity:
        """Record a product name, creating its identity the first time it is seen."""
        key = normalise(raw)
        if key not in self._parent:
            self._parent[key] = key
            self._identities[key] = ProductIdentity(key=key)
        identity = self._resolve(key)
        identity.names.setdefault(key, ProductName(raw=raw, vocabulary=vocabulary))
        self._apply_short_code(identity)
        return identity

    def link(self, left_raw: str, right_raw: str, reason: str) -> ProductIdentity:
        """Merge two names into one identity, on stated evidence."""
        left = self._resolve(normalise(left_raw))
        right = self._resolve(normalise(right_raw))
        if left.key == right.key:
            return left

        left.names.update(right.names)
        left.merge_reasons.append(reason)
        left.merge_reasons.extend(right.merge_reasons)
        if left.short_code is None:
            left.short_code = right.short_code

        self._parent[right.key] = left.key
        self._identities.pop(right.key, None)
        self._apply_short_code(left)
        return left

    def set_short_code(self, raw: str, code: str) -> ProductIdentity:
        """Record the operator's own code for a product. Remembered from then on."""
        identity = self.observe(raw, Vocabulary.SALES)
        identity.short_code = code
        for name in identity.names:
            self._short_codes[name] = code
        return identity

    # --- reading -------------------------------------------------------------------------------

    def identity_for(self, raw: str) -> ProductIdentity | None:
        key = normalise(raw)
        return self._resolve(key) if key in self._parent else None

    @property
    def identities(self) -> list[ProductIdentity]:
        return sorted(self._identities.values(), key=lambda i: i.display_name)

    @property
    def unresolved(self) -> list[ProductIdentity]:
        """Products with no operator short code. A row cannot be written for these."""
        return [i for i in self.identities if not i.is_resolved]

    def suggestions(self) -> list[LinkSuggestion]:
        """Identities that may be the same product. Never applied automatically.

        Only crosses vocabularies: two names in the same vocabulary that share fruit words are
        usually genuinely different lines (`CLASS 1` against `CLASS 2`), and proposing to merge
        those would be worse than useless.
        """
        found: list[LinkSuggestion] = []
        items = self.identities
        for index, left in enumerate(items):
            for right in items[index + 1 :]:
                if left.vocabularies == right.vocabularies:
                    continue
                shared = self._signature(left) & self._signature(right)
                if not shared:
                    continue
                found.append(
                    LinkSuggestion(
                        left=left.key,
                        right=right.key,
                        reason=(
                            f"{left.display_name!r} and {right.display_name!r} are written in "
                            f"different vocabularies and share {', '.join(sorted(shared))}. "
                            "No account sale links them, so this is a resemblance, not evidence."
                        ),
                        shared_words=shared,
                    )
                )
        return found

    # --- internals ------------------------------------------------------------------------------

    def _resolve(self, key: str) -> ProductIdentity:
        root = key
        while self._parent.get(root, root) != root:
            root = self._parent[root]
        # Path compression, so repeated lookups stay cheap on a long history.
        while self._parent.get(key, key) != key:
            self._parent[key], key = root, self._parent[key]
        return self._identities[root]

    def _apply_short_code(self, identity: ProductIdentity) -> None:
        if identity.short_code is not None:
            return
        for name in identity.names:
            code = self._short_codes.get(name)
            if code is not None:
                identity.short_code = code
                return

    @staticmethod
    def _signature(identity: ProductIdentity) -> frozenset[str]:
        words: set[str] = set()
        for name in identity.names.values():
            words |= signature(name.raw)
        return frozenset(words)

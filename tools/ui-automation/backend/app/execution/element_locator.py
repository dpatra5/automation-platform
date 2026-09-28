"""Find the element a recorded step acts on, however the page has moved on.

A selector says *where* an element was. Apps move things: a wrapper div
appears, a list grows a row, a utility class is renamed, and a path like
``div:nth-of-type(10) > div:nth-of-type(2)`` stops matching even though the
control is still on screen and obvious to anyone looking at it.

So the recorder stores what the element *is* as well - its tag, its role, its
label, its text and a spread of other ways to reach it - and this module walks
those in order until one of them lands on something the tester could actually
have used. It also waits for the element to become operable rather than acting
on the instant it is found: an app that locks an input while it is busy enables
it again a moment later, and a recording keeps no record of the pause the
tester made without thinking about it.

Nothing here changes what a step does. It only decides which element the step
is handed.
"""

import asyncio
import enum
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, NamedTuple, Optional

from app.config import settings
from app.models.models import ActionEnum, SelectorStrategyEnum

logger = logging.getLogger(__name__)


def enum_value(v: Any) -> str:
    """Enum members and plain strings both reach here, depending on the caller."""
    return v.value if isinstance(v, enum.Enum) else str(v)


# Actions whose element has to be one a person could operate right now: on
# screen, and not locked while the app is busy. These get the readiness wait.
NEEDS_READY_ELEMENT = frozenset(
    {
        ActionEnum.click.value,
        ActionEnum.dblclick.value,
        ActionEnum.right_click.value,
        ActionEnum.hover.value,
        ActionEnum.fill.value,
        ActionEnum.type.value,
        ActionEnum.press_key.value,
        ActionEnum.select.value,
        ActionEnum.check.value,
        ActionEnum.uncheck.value,
        ActionEnum.drag.value,
    }
)

# Checks that pass precisely because nothing matches. Finding the element
# another way would answer a different question from the one that was asked.
ABSENCE_ASSERTIONS = frozenset(
    {"not_exists", "hidden", "count_equals", "count_at_least", "count_at_most"}
)


class ElementNotReadyError(RuntimeError):
    """The element was found, on screen, and the app never let go of it.

    Raised instead of handing the step a locator that is certain to fail. That
    saves a second timeout inside Playwright, keeps the failure from being
    retried - retrying a control the app is deliberately holding shut only
    wastes the run's time - and lets the report say what actually happened
    rather than quoting a timeout.
    """


# Said in a step's notes when the recorded selector matched something that no
# longer looks like the recorded element. The runner reads it back: a step that
# acted on the wrong thing is usually why a later one finds the app stuck.
DRIFT_NOTE = "no longer matches anything like"


# How many matches of one candidate are worth looking at. A recorded element
# that now matches more than this is too vague to heal towards - acting on a
# guess is worse than reporting that the step could not be replayed.
MAX_MATCHES_SCANNED = 8

# Ways to reach one element, beyond which the list is noise. A description
# narrowed to where it was recorded counts separately from the same one asked
# of the whole page, so there is room here for both.
MAX_CANDIDATES = 16

POLL_INTERVAL_S = 0.25

# How long to wait in silence before saying, in the run's evidence, that a step
# is still waiting for its element rather than hung, and how often to repeat it.
# A wait for a busy app can run into minutes, and a run that says nothing for
# minutes looks broken.
WAIT_NOTE_AFTER_S = 5.0
WAIT_NOTE_EVERY_S = 15.0

# A scroll is a nudge, not a step: it must not eat into the readiness budget.
NUDGE_TIMEOUT_MS = 1000

# Labels this short are compared exactly. "No" is inside "Not applicable" and
# inside the "Yes No" row that holds it, so a loose comparison would happily
# confirm the wrong one.
EXACT_NAME_UP_TO = 8

# Text this long is looked up loosely; a short label is looked up exactly, for
# the same reason.
EXACT_TEXT_UP_TO = 40

# A selector segment that only counts: `div`, `div:nth-of-type(16)`.
_COUNTING_CSS = re.compile(r"^[a-z][a-z0-9-]*(:nth-(of-type|child)\(\d+\))?$", re.I)
_COUNTING_XPATH = re.compile(r"^([a-z][a-z0-9-]*|\*)(\[\d+\])?$", re.I)

# One counting segment inside a path, wherever it sits.
_NTH_SEGMENT = re.compile(r":nth-(of-type|child)\((\d+)\)")

# An XPath location step that picks a sibling out by number: `div[29]`. A
# predicate that names something - `div[@id='x']` - is deliberately excluded.
_XPATH_POSITION = re.compile(r"([a-z][a-z0-9-]*|\*)\[(\d+)\]", re.I)

# An index this high is counting rows in a list rather than picking out one of
# a handful of wrappers, which is what makes it worth re-reading from the end.
LIST_INDEX_FROM = 4

# Set on a step's fingerprint when its recorded path counts into a list. Not
# something the recorder writes: it is read off the selector at lookup time, so
# recordings made before any of this still get the benefit.
OF_A_GROWING_LIST = "rewind_of_a_growing_list"

# Read back off a candidate match to check it is the element that was recorded
# rather than something that merely answers to the same description.
_DESCRIBE_JS = """el => ({
  tag: el.tagName ? el.tagName.toLowerCase() : '',
  name: ((el.getAttribute && (
      el.getAttribute('aria-label') ||
      el.getAttribute('placeholder') ||
      el.getAttribute('title') ||
      el.getAttribute('alt'))) ||
    el.innerText || el.textContent || '').trim().slice(0, 160)
})"""


@dataclass(frozen=True)
class Candidate:
    """One way of looking an element up, in Playwright's own terms."""

    by: str
    value: str
    #: Only for ``role``: the accessible name that narrows it down.
    name: Optional[str] = None
    #: The part of the page to look inside, if the lookup was narrowed to one.
    within: Optional[str] = None

    def describe(self) -> str:
        said = f"{self.by}={self.value!r}"
        if self.name:
            said = f"{said} named {self.name!r}"
        if self.within:
            said = f"{said} inside {self.within!r}"
        return said

    def inside(self, within: Optional[str]) -> "Candidate":
        """The same lookup, held to the part of the page it was recorded in.

        Only a description is narrowed. A path already says where to start,
        and one written from the same container down would be asked to find
        itself inside itself.
        """
        path = self.by == "xpath" or (
            self.by == "css" and any(mark in self.value for mark in "> ")
        )
        if not within or self.within or path:
            return self
        return Candidate(self.by, self.value, self.name, within)

    def counts_only(self) -> bool:
        """Whether the last step of this path counts rather than names.

        `... > div:nth-of-type(16) > div:nth-of-type(2)` picks the element out
        by where it sat among its siblings. Anchoring the front of the path
        does not help: a list that has grown a row still matches, it just
        matches the neighbour, which is the one way a selector fails without
        looking like it failed.
        """
        if self.by == "css":
            parts = [p for p in re.split(r"[>\s]+", self.value) if p]
            return bool(parts) and bool(_COUNTING_CSS.match(parts[-1]))
        if self.by == "xpath":
            steps = _xpath_steps(self.value)
            return bool(steps) and bool(_COUNTING_XPATH.match(steps[-1][1]))
        return False


class Found(NamedTuple):
    """What one pass over the candidates turned up."""

    element: Any = None
    locator: Any = None
    #: Which candidate found it; 0 is the recorded selector.
    position: int = -1
    #: A match was on screen and switched off, which is worth waiting out.
    locked: bool = False
    #: The match still looks like the element that was recorded.
    agreed: bool = True


_STRATEGY_TO_BY = {
    SelectorStrategyEnum.test_id.value: "test_id",
    SelectorStrategyEnum.role.value: "role",
    SelectorStrategyEnum.text.value: "text",
    SelectorStrategyEnum.xpath.value: "xpath",
    SelectorStrategyEnum.css.value: "css",
}


def build_locator(candidate: Candidate, scope: Any):
    """A Playwright locator for one candidate, or None if it cannot be built.

    `scope` is a Page or a Frame; both expose the same locator API. A selector
    the page's engine rejects must not end the run - the next candidate may
    well work.
    """
    try:
        by = candidate.by
        # Held to the part of the page the step was recorded in, where one was
        # worked out: the same label very often sits somewhere else as well.
        scope = scope.locator(candidate.within) if candidate.within else scope
        if by == "test_id":
            return scope.get_by_test_id(candidate.value)
        if by == "role":
            if candidate.name:
                return scope.get_by_role(candidate.value, name=candidate.name)
            return scope.get_by_role(candidate.value)
        if by == "label":
            return scope.get_by_label(candidate.value)
        if by == "placeholder":
            return scope.get_by_placeholder(candidate.value)
        if by == "alt":
            return scope.get_by_alt_text(candidate.value)
        if by == "title":
            return scope.get_by_title(candidate.value)
        if by == "text":
            # A short label is matched whole: `get_by_text("No")` would
            # otherwise take "Not applicable" as readily as the chip meant.
            if len(candidate.value) <= EXACT_TEXT_UP_TO:
                return scope.get_by_text(candidate.value, exact=True)
            return scope.get_by_text(candidate.value)
        if by == "xpath":
            return scope.locator(f"xpath={candidate.value}")
        return scope.locator(candidate.value)
    except Exception as e:
        logger.debug("Candidate %s could not be built: %s", candidate.describe(), e)
        return None


def fingerprint(step) -> dict:
    """What the recorder noted about the element, or {} for older steps."""
    raw = getattr(step, "element_meta", None)
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def element_label(step) -> str:
    """A human name for the step's element, for logs and error messages."""
    meta = fingerprint(step)
    return str(meta.get("name") or meta.get("text") or "").strip()


def _primary(step) -> Optional[Candidate]:
    if not getattr(step, "selector", None):
        return None
    by = _STRATEGY_TO_BY.get(enum_value(step.selector_strategy), "css")
    return Candidate(by, step.selector)


def _described_candidates(meta: dict):
    """The ways of reaching the element that the recorder wrote down."""
    for raw in meta.get("candidates") or []:
        if isinstance(raw, dict) and raw.get("by") and raw.get("value"):
            name = str(raw["name"]) if raw.get("name") else None
            yield Candidate(str(raw["by"]), str(raw["value"]), name)

    # The label on its own is the last resort, and the one a person would use.
    role, name = meta.get("role"), meta.get("name")
    if role and name:
        yield Candidate("role", str(role), str(name))
    if name:
        yield Candidate("label", str(name))


def _counted_rows(candidate: Optional[Candidate]) -> list[int]:
    """The row numbers a path counts to that are deep enough to be list rows."""
    if candidate is None:
        return []
    if candidate.by == "css":
        return [
            int(m.group(2))
            for m in _NTH_SEGMENT.finditer(candidate.value)
            if int(m.group(2)) >= LIST_INDEX_FROM
        ]
    if candidate.by == "xpath":
        return [
            row for _, row in _xpath_counted(candidate.value) if row >= LIST_INDEX_FROM
        ]
    return []


def _top_level_slashes(value: str) -> list[int]:
    """Where an XPath's location steps actually break.

    A `/` inside a predicate - ``@href='/orders'`` - is part of a string, not a
    step boundary, so splitting on the character alone would cut a path in the
    middle of a label and describe something that does not exist.
    """
    cuts: list[int] = []
    depth = 0
    quote = ""
    for position, char in enumerate(value):
        if quote:
            if char == quote:
                quote = ""
        elif char in "'\"":
            quote = char
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
        elif char == "/" and depth == 0:
            cuts.append(position)
    return cuts


def _xpath_steps(value: str) -> list[tuple[str, str]]:
    """An XPath split into (axis separator, step) pairs, joinable back as-is."""
    steps: list[tuple[str, str]] = []
    sep = ""
    start = 0
    for cut in [*_top_level_slashes(value), len(value)]:
        piece = value[start:cut]
        start = cut + 1
        if piece:
            steps.append((sep, piece))
            sep = "/"
        elif cut < len(value):
            sep += "/"
    return steps


def _xpath_counted(value: str) -> list[tuple[int, int]]:
    """(step position, row number) for every step of an XPath that counts."""
    out: list[tuple[int, int]] = []
    for position, (_, step) in enumerate(_xpath_steps(value)):
        match = _XPATH_POSITION.fullmatch(step)
        if match:
            out.append((position, int(match.group(2))))
    return out


def _xpath_newest(value: str) -> Optional[Candidate]:
    """The XPath with the row it counted to read from the end instead."""
    counted = [pair for pair in _xpath_counted(value) if pair[1] >= LIST_INDEX_FROM]
    if not counted:
        return None
    target = max(counted, key=lambda pair: pair[1])[0]
    steps = _xpath_steps(value)
    tag = _XPATH_POSITION.fullmatch(steps[target][1]).group(1)  # type: ignore[union-attr]
    steps[target] = (steps[target][0], f"{tag}[last()]")
    return Candidate("xpath", "".join(sep + step for sep, step in steps))


def _newest_row(candidate: Optional[Candidate]) -> Optional[Candidate]:
    """The recorded path with the row it counted to read from the end instead.

    A transcript is a list that grows. `div:nth-of-type(29)` is the
    twenty-ninth message, which is the right message only while the run has
    produced exactly as many as the recording did - one extra greeting, one
    question the app decided to skip, and the path points at a message from
    minutes ago that still answers to the same shape. What was true then and
    is true now is that the tester was working on the newest one.
    """
    if candidate is None or not _counted_rows(candidate):
        return None
    if candidate.by == "xpath":
        return _xpath_newest(candidate.value)
    counted = [
        m
        for m in _NTH_SEGMENT.finditer(candidate.value)
        if int(m.group(2)) >= LIST_INDEX_FROM
    ]
    row = max(counted, key=lambda m: int(m.group(2)))
    last = ":last-of-type" if row.group(1) == "of-type" else ":last-child"
    return Candidate(
        "css", candidate.value[: row.start()] + last + candidate.value[row.end() :]
    )


def _container_of(candidate: Optional[Candidate]) -> Optional[str]:
    """The part of a recorded path that names a place rather than a position.

    `div.custom-scroll > div:nth-of-type(2) > div:nth-of-type(29) > div` is a
    row of a transcript, and the transcript is the part worth keeping. The
    same label is very often on the page twice - a chip in the conversation, a
    button in the panel beside it, a dialog left open behind it - and looking
    up "No" across the whole page returns whichever the markup happens to put
    last. This is the scope a person would have written by hand.

    Only the leading segments that name something count: once the path starts
    counting siblings it is describing a position, not a place.
    """
    if candidate is None:
        return None
    if candidate.by == "xpath":
        return _xpath_container(candidate.value)
    if candidate.by != "css":
        return None
    kept: list[str] = []
    for raw in candidate.value.split(">"):
        segment = raw.strip()
        if not segment or _COUNTING_CSS.match(segment):
            break
        kept.append(segment)
    if not any(mark in segment for segment in kept for mark in ".#["):
        return None
    return " > ".join(kept)


def _xpath_container(value: str) -> Optional[str]:
    """The leading steps of an XPath that name a place rather than a position."""
    kept: list[tuple[str, str]] = []
    for sep, step in _xpath_steps(value):
        if _COUNTING_XPATH.match(step):
            break
        kept.append((sep, step))
    if not any("@" in step for _, step in kept):
        return None
    return "".join(sep + step for sep, step in kept) or None


def candidates_for(step) -> list[Candidate]:
    """Every way to reach this step's element, the recorded one first."""
    found: list[Candidate] = []
    seen: set[tuple] = set()

    def add(candidate: Optional[Candidate]) -> None:
        if candidate is None or not candidate.value:
            return
        key = (candidate.by, candidate.value, candidate.name, candidate.within)
        if key not in seen:
            seen.add(key)
            found.append(candidate)

    primary = _primary(step)
    described = list(_described_candidates(fingerprint(step)))
    # Only a path that counts into a list is narrowed. Elsewhere the recorded
    # description is as good as it gets, and a container that has since been
    # renamed would take the one honest lookup away with it.
    within = _container_of(primary) if _counted_rows(primary) else None

    add(primary)
    for candidate in described:
        add(candidate.inside(within))
    for candidate in described:
        add(candidate)

    newest = _newest_row(primary)
    if newest is None:
        return found[:MAX_CANDIDATES]
    # Kept whatever else was on offer: where the same label is on the page
    # several times over, the row the tester was working in decides it.
    return [*found[: MAX_CANDIDATES - 1], newest]


def _norm(text: str) -> str:
    return " ".join((text or "").split()).casefold()


def _names_match(wanted: str, seen: str) -> bool:
    """Whether two labels are close enough to be the same control.

    A long label is compared loosely, so a heading that gained a count or a
    suffix still matches. A short one is compared whole: "No" appears inside
    "Not applicable" and inside the "Yes No" row that contains it, and picking
    either of those is how a run ends up answering a question it was not asked.
    """
    if min(len(wanted), len(seen)) <= EXACT_NAME_UP_TO:
        return wanted == seen
    return wanted in seen or seen in wanted


async def _looks_right(element: Any, meta: dict) -> tuple[bool, bool]:
    """Whether a match agrees with the recorded element on tag and on label."""
    wanted_tag = str(meta.get("tag") or "").lower()
    wanted_name = _norm(str(meta.get("name") or meta.get("text") or ""))
    if not wanted_tag and not wanted_name:
        return True, True
    try:
        seen = await element.evaluate(_DESCRIBE_JS)
    except Exception:
        return True, True
    if not isinstance(seen, dict):
        return True, True

    tag_ok = not wanted_tag or str(seen.get("tag") or "").lower() == wanted_tag
    seen_name = _norm(str(seen.get("name") or ""))
    name_ok = not wanted_name or not seen_name or _names_match(wanted_name, seen_name)
    return tag_ok, name_ok


def _was_last(meta: dict) -> bool:
    """Whether the element was the last of the ones sharing its label.

    A transcript grows. The chip to answer is the newest one on the page, and
    which number that is differs between the recording and the run - that it
    was the newest does not.

    The recorder says so outright when it could count the element's peers. It
    often cannot: a chat chip is a `div` among thousands of divs, too many to
    walk while the tester is clicking. The path it wrote down says the same
    thing less directly - counting to the twenty-ninth row is only ever done
    in a list, and the row the tester was working in was the newest one.
    """
    if meta.get(OF_A_GROWING_LIST):
        return True
    index, of = meta.get("index"), meta.get("of")
    if not isinstance(index, int) or not isinstance(of, int):
        return False
    return of > 1 and index == of - 1


def _scan_order(
    count: int, index_hint: Optional[int], was_last: bool = False
) -> list[int]:
    """Which matches to look at, and in what order.

    The position the element held while recording goes first: with several
    identical controls - one per row - it is the only thing that tells them
    apart. Everything else follows, because a row may since have been added.

    An element recorded as the newest of its kind is read back from the end.
    Which number it was differs between the recording and the run; that it was
    the newest does not, and in a transcript of twenty answered questions it is
    the only thing that separates the chip being asked about from the nineteen
    already dealt with.
    """
    if was_last and count:
        newest = range(count - 1, max(count - MAX_MATCHES_SCANNED, 0) - 1, -1)
        return list(newest)
    order = list(range(min(count, MAX_MATCHES_SCANNED)))
    if index_hint is not None and 0 <= index_hint < count:
        order = [index_hint] + [i for i in order if i != index_hint]
    return order[:MAX_MATCHES_SCANNED]


async def _state(element: Any) -> str:
    """`ready`, `busy` - on screen but switched off - or `gone`.

    The middle one is the whole reason this module waits: the element is there
    and the app is saying 'not yet', which is different from the page having
    moved on and worth a great deal more patience.
    """
    try:
        if not await element.is_visible():
            return "gone"
        return "ready" if await element.is_enabled() else "busy"
    except Exception as e:
        logger.debug("Could not read the state of a match: %s", e)
        return "gone"


async def _is_usable(element: Any, need_ready: bool) -> bool:
    """Whether the step could operate this match right now.

    Only asked of steps that are about to act. A check reads the page as it
    stands - a hidden element is exactly what `hidden` is looking for - and a
    file input is routinely off screen, so those take any match they get.
    """
    return not need_ready or await _state(element) == "ready"


async def _match_quality(element: Any, meta: dict, need_ready: bool) -> tuple[int, str]:
    """How closely a match agrees with the recorded element, and its state."""
    state = await _state(element) if need_ready else "ready"
    tag_ok, name_ok = await _looks_right(element, meta)
    return (2 if tag_ok else 0) + (2 if name_ok else 0), state


def _verdict(score: int, needed: int, state: str, best_score: int) -> str:
    """What a scanned match means for the search: take it, wait, or pass over.

    Waiting is reserved for a match that answers the description in full and
    is simply switched off for the moment - the app is about to release it.
    """
    if score < needed:
        return "pass"
    if state == "ready":
        return "take" if score > best_score else "pass"
    return "wait" if state == "busy" and score == 4 else "pass"


async def _best_verified(
    locator: Any, count: int, meta: dict, need_ready: bool, index_hint: Optional[int]
) -> tuple[Any, bool]:
    """The match that agrees most closely with the recorded element.

    Healing must not quietly act on something that merely answers to the same
    description, so a match is only taken once it has been read back and
    recognised.

    Also reports whether the element it recognised was on screen and switched
    off. That is worth knowing: the run should wait for the app to release the
    right control rather than carry on down the list and act on a lesser one.
    """
    best, best_score, busy = None, 0, False
    # Agreeing on the tag alone is not recognition: every chip in a list is a
    # div. Where the recorder wrote down a label, the label has to match.
    needed = 4 if _norm(str(meta.get("name") or meta.get("text") or "")) else 2
    # The recording says this was the newest of its kind, so the scan runs from
    # the end and the first match it recognises is the one meant. An older chip
    # left enabled belongs to a question answered long ago, and pressing it
    # answers nothing while looking like it worked.
    newest_first = _was_last(meta)
    for position in _scan_order(count, index_hint, newest_first):
        element = locator.first if count == 1 else locator.nth(position)
        score, state = await _match_quality(element, meta, need_ready)
        verdict = _verdict(score, needed, state, best_score)
        if verdict == "take":
            best, best_score = element, score
        elif verdict == "wait":
            busy = True
        if verdict != "pass" and (score == 4 or newest_first):
            break
    return best, busy


async def _first_ready(locator: Any, count: int) -> tuple[Any, bool]:
    """The first match the step could act on, looking past ones it could not.

    A form that is rendered twice - once in a panel the app has hidden, once
    on screen - would otherwise be driven through the copy nobody can see.

    Also reports whether a match was on screen but switched off, which is the
    one failure worth waiting out: the element is there and the app is saying
    'not yet' rather than the page having moved on.
    """
    locked = False
    for position in _scan_order(count, None):
        element = locator.first if count == 1 else locator.nth(position)
        state = await _state(element)
        if state == "busy":
            locked = True
        if state == "ready":
            return element, locked
    return None, locked


async def _agrees(element: Any, meta: dict) -> bool:
    """Whether a match still looks like the element that was recorded.

    Asked of the recorded selector's own match, not just of the fallbacks. A
    path built out of positions - `div:nth-of-type(16) > div > div` - matches
    something on almost any version of a page, so it fails by acting on the
    wrong thing rather than by finding nothing. The comparison is deliberately
    loose (see `_looks_right`): it is there to catch a match that is plainly
    something else, not to insist a label never changes.
    """
    tag_ok, name_ok = await _looks_right(element, meta)
    return tag_ok and name_ok


def _too_many(count: int, meta: dict) -> bool:
    """Whether a description now fits too big a crowd to heal towards.

    Except where the recording says the element was the newest of them: a
    transcript of twenty answered questions holds twenty chips reading "No",
    and the newest is still exactly one of them.
    """
    return count > MAX_MATCHES_SCANNED and not _was_last(meta)


async def _pick(
    locator: Any,
    meta: dict,
    need_ready: bool,
    verify: bool,
    index_hint: Optional[int],
) -> tuple[Any, bool]:
    """The match of `locator` this step should use, and whether one was locked."""
    try:
        count = await locator.count()
    except Exception as e:
        logger.debug("Could not count matches: %s", e)
        return None, False
    if not count:
        return None, False
    if verify:
        # A description that now fits a crowd is too vague to heal towards.
        if _too_many(count, meta):
            return None, False
        return await _best_verified(locator, count, meta, need_ready, index_hint)
    if not need_ready:
        return locator.first, False
    return await _first_ready(locator, count)


def _fallback_allowed(step, action: str) -> bool:
    """Whether this step may be replayed against an element found another way."""
    if action != ActionEnum.assert_.value:
        return True
    return (getattr(step, "assertion_type", None) or "") not in ABSENCE_ASSERTIONS


def _trial_order(pool: list[Candidate], meta: dict) -> list[int]:
    """Which candidate to try first, and which to leave until last.

    The recorded selector normally goes first - it is the one the tester's
    click produced. A path that ends by counting siblings is the exception: it
    says where the element sat rather than what it was, and on a page that has
    since grown a row it points confidently at the neighbour. Where the
    recorder also wrote down a label, that is asked first and the path is kept
    as the fallback; with no label there is nothing to check an answer against,
    so the path stands.
    """
    named = bool(meta.get("name") or meta.get("text"))
    if len(pool) > 1 and named and pool[0].counts_only():
        return [*range(1, len(pool)), 0]
    return list(range(len(pool)))


async def _sweep(
    pool: list[Candidate],
    scope: Any,
    meta: dict,
    need_ready: bool,
    index_hint: Optional[int],
) -> Found:
    """One pass over the candidates: the first usable element any of them finds.

    Whatever is tried first, its match has to look like the element that was
    recorded. A match that does not is kept only as a last resort - the step
    then does what it has always done, and says so - because acting on the
    wrong element succeeds, and the run fails somewhere else entirely.
    """
    locked = False
    drifted = Found()
    for position in _trial_order(pool, meta):
        locator = build_locator(pool[position], scope)
        if locator is None:
            continue
        element, was_locked = await _pick(
            locator,
            meta,
            need_ready,
            verify=position > 0,
            index_hint=index_hint if position > 0 else None,
        )
        locked = locked or was_locked
        if element is None:
            continue
        if position == 0 and len(pool) > 1 and not await _agrees(element, meta):
            drifted = Found(element, locator, 0, locked, agreed=False)
            continue
        return Found(element, locator, position, locked)
    if drifted.element is not None:
        return drifted._replace(locked=locked)
    return Found(locked=locked)


async def _nudge(pool: list[Candidate], scope: Any, meta: dict) -> None:
    """Scroll the element into view once, then leave it alone.

    A long list that renders lazily leaves an empty or disabled placeholder in
    the DOM until the row is scrolled to, and a control below the fold is one
    an app may only wire up when it is reached.

    Whichever candidate has something to show is the one scrolled to. A path
    that counts into a list still matches a row from minutes ago, and
    scrolling there takes the page - and the screenshot taken of it - away
    from the part of the conversation the step is about.
    """
    for position in _trial_order(pool, meta):
        locator = build_locator(pool[position], scope)
        count = await _count(locator)
        if not count:
            continue
        target = locator.nth(count - 1) if _was_last(meta) else locator.first
        try:
            await target.scroll_into_view_if_needed(timeout=NUDGE_TIMEOUT_MS)
        except Exception as e:
            logger.debug("Nudge skipped: %s", e)
        return


def _say(on_note: Optional[Callable[[str], None]], message: str) -> None:
    if on_note is not None:
        on_note(message)


def _due(elapsed: float, announced_at: Optional[float]) -> bool:
    """Whether it is time to say the step is still waiting rather than hung."""
    if elapsed < WAIT_NOTE_AFTER_S:
        return False
    return announced_at is None or elapsed - announced_at >= WAIT_NOTE_EVERY_S


def _waiting_note(
    pool: list[Candidate], locked: bool, elapsed: float, budget_s: float
) -> str:
    reason = (
        "is switched off, waiting for the app to release it"
        if locked
        else "to become usable"
    )
    return (
        f"still waiting: {pool[0].describe()} {reason} "
        f"({int(elapsed)}s so far, giving it {int(budget_s)}s)"
    )


async def _search(
    pool: list[Candidate],
    scope: Any,
    meta: dict,
    need_ready: bool,
    index_hint: Optional[int],
    budget_s: float,
    busy_s: float = 0.0,
    on_note: Optional[Callable[[str], None]] = None,
) -> tuple[Found, bool]:
    """Sweep the candidates until one lands, or the budget runs out.

    Two budgets, because two very different things go wrong. An element that
    matches nothing is a step that has lost its way, and waiting on it only
    delays the news, so `budget_s` keeps that short. An element that is on
    screen with the app holding it switched off is not a fault at all - it is
    a form that will not take input until the work behind it finishes - and a
    tester watching would simply wait. So the moment a locked match is seen
    the deadline moves out to `busy_s`, which is allowed to be minutes.

    Also reports whether any waiting was needed, which is worth saying: it is
    the difference between an app that was slow and one that was wrong.
    """
    started = time.monotonic()
    busy_s = max(budget_s, busy_s)
    waited = nudged = seen_locked = False
    announced_at: Optional[float] = None
    while True:
        found = await _sweep(pool, scope, meta, need_ready, index_hint)
        if found.element is not None:
            return found, waited
        seen_locked = seen_locked or found.locked
        budget = busy_s if seen_locked else budget_s
        elapsed = time.monotonic() - started
        if elapsed >= budget:
            return Found(locked=seen_locked), waited
        waited = True
        if not nudged:
            nudged = True
            await _nudge(pool, scope, meta)
        if _due(elapsed, announced_at):
            announced_at = elapsed
            _say(on_note, _waiting_note(pool, seen_locked, elapsed, budget))
        await asyncio.sleep(POLL_INTERVAL_S)


async def _count(locator: Any) -> int:
    if locator is None:
        return 0
    try:
        return await locator.count()
    except Exception as e:
        logger.debug("Could not count matches: %s", e)
        return 0


async def _stalled(
    pool: list[Candidate], scope: Any, meta: dict, index_hint: Optional[int]
) -> tuple[Any, int]:
    """The first fallback that finds the recorded element, usable or not.

    Asked only once a step is about to fail and its own selector has stopped
    matching anything at all. Failing against the element that is genuinely
    there gives Playwright's message something to describe, and tells the
    tester the lookup was fine and the readiness was not. The match still has
    to be recognisably the recorded element - a description that fits
    something else is no more use here than it was for healing.
    """
    for position, candidate in enumerate(pool):
        if position == 0:
            continue
        locator = build_locator(candidate, scope)
        count = await _count(locator)
        if not count or _too_many(count, meta):
            continue
        element, _ = await _best_verified(locator, count, meta, False, index_hint)
        if element is not None:
            return element, position
    return None, -1


def _report(
    on_note: Optional[Callable[[str], None]],
    pool: list[Candidate],
    found: Found,
    label: str,
    waited: bool,
) -> None:
    """Say in the evidence when the element was not simply where it was left."""
    if on_note is None:
        return
    if not found.agreed:
        on_note(
            f"{pool[0].describe()} {DRIFT_NOTE} {label!r}, and nothing else on the "
            "page matched it either; the step acted on that match anyway"
        )
    elif found.position > 0 and pool[0].counts_only():
        on_note(
            f"{pool[0].describe()} only says where the element sat; found "
            f"{label!r} by {pool[found.position].describe()} instead"
        )
    elif found.position > 0:
        on_note(
            f"{pool[0].describe()} did not lead to a usable element; "
            f"used {pool[found.position].describe()} instead"
        )
    elif waited:
        on_note(f"{pool[found.position].describe()} became ready after a wait")


def _wait_budget(need_ready: bool, budget_s: Optional[float]) -> float:
    """How long this step may wait for its element to become operable.

    A check waits for nothing: it asks about the page as it stands, and waiting
    would change its answer.
    """
    if not need_ready:
        return 0.0
    if budget_s is None:
        return settings.element_ready_timeout_ms / 1000
    return max(budget_s, 0.0)


def _busy_budget(need_ready: bool, busy_budget_s: Optional[float]) -> float:
    """How long this step may wait for an element the app is holding shut."""
    if not need_ready:
        return 0.0
    if busy_budget_s is None:
        return settings.element_busy_timeout_ms / 1000
    return max(busy_budget_s, 0.0)


def _stuck_message(step, pool: list[Candidate], waited_s: float) -> str:
    """Why a step that found its element still could not use it.

    Deliberately says nothing about timeouts. This is the app declining to
    accept input, and the tester reading the report needs to know that, not
    that a number was exceeded.
    """
    label = element_label(step) or pool[0].describe()
    action = enum_value(step.action)
    return (
        f"The run found {label} on screen but the app kept it switched off for "
        f"the whole {int(waited_s)}s it waited, so there was nothing to {action}. "
        "An app disables a control like this while it is busy, so the step "
        "before this one most likely started work that had not finished - a "
        "reply still being written, a save still in flight. Nothing was typed "
        "or clicked, and the page was left exactly as the screenshot shows. "
        "If this app really does need longer, raise ELEMENT_BUSY_TIMEOUT_MS; if "
        "it should have been ready, the step before it is the one to look at."
    )


async def _give_up(
    pool: list[Candidate],
    scope: Any,
    meta: dict,
    index_hint: Optional[int],
    need_ready: bool,
    narrow: bool,
    on_note: Optional[Callable[[str], None]],
) -> Any:
    """What to hand the step when nothing usable was found.

    Normally the recorded selector, so the step fails against the element it
    was written for and Playwright reports it in its own words. When that
    selector has stopped matching anything, a fallback that does still find the
    element is the better thing to fail against: the error then describes the
    control the tester can see rather than a path that leads nowhere.
    """
    recorded = build_locator(pool[0], scope)
    if need_ready and not await _count(recorded):
        element, position = await _stalled(pool, scope, meta, index_hint)
        if element is not None:
            _say(
                on_note,
                f"{pool[0].describe()} found nothing; {pool[position].describe()} "
                "found the element but it never became usable",
            )
            return element

    if recorded is None:
        return None
    return recorded.first if narrow else recorded


def _handed_to(found: Found, narrow: bool) -> Any:
    """The locator the step is given: one element, or the whole match set.

    A check reads the locator itself - `count_equals` asks how many elements
    it matches - so it is handed the recorded selector whole. A check that had
    to be healed on to a description is the exception: `get_by_text` matches
    the paragraph, the block around it and the panel around that, and reading
    the text off all three at once is an error rather than an answer.
    """
    if narrow or found.position > 0:
        return found.element
    return found.locator


async def resolve(
    step,
    scope: Any,
    on_note: Optional[Callable[[str], None]] = None,
    budget_s: Optional[float] = None,
    busy_budget_s: Optional[float] = None,
) -> Any:
    """The element this step acts on, or None when the step needs no element.

    The recorded selector is tried first and, when it lands on something
    usable, is returned straight away - the ordinary case costs one extra
    round trip. Only when it does not does the search widen, and only then is
    time spent waiting.

    `budget_s` caps the wait for an element that cannot be found. Once one is
    found on screen but switched off, `busy_budget_s` takes over: the run is
    then waiting on the app, not looking for something lost, and those deserve
    very different amounts of patience. The runner divides a step's time
    between several attempts and passes each attempt's share; on their own the
    settings are the whole of it.
    """
    candidates = candidates_for(step)
    if not candidates:
        return None

    action = enum_value(step.action)
    meta = fingerprint(step)
    if _counted_rows(_primary(step)):
        meta[OF_A_GROWING_LIST] = True
    need_ready = action in NEEDS_READY_ELEMENT
    # Checks read the locator itself - `count_equals` asks how many elements it
    # matches - so they are handed the locator rather than one match of it.
    narrow = action != ActionEnum.assert_.value
    pool = candidates if _fallback_allowed(step, action) else candidates[:1]
    index_hint = meta.get("index") if isinstance(meta.get("index"), int) else None
    wait_s = _wait_budget(need_ready, budget_s)
    busy_s = _busy_budget(need_ready, busy_budget_s)

    started = time.monotonic()
    found, waited = await _search(
        pool, scope, meta, need_ready, index_hint, wait_s, busy_s, on_note
    )
    if found.element is not None:
        _report(on_note, pool, found, element_label(step) or pool[0].describe(), waited)
        return _handed_to(found, narrow)
    if found.locked:
        # Handing this on would only buy another timeout with a worse message.
        raise ElementNotReadyError(
            _stuck_message(step, pool, time.monotonic() - started)
        )
    return await _give_up(pool, scope, meta, index_hint, need_ready, narrow, on_note)

"""Finding a recorded element again after the page around it has changed."""

import json
import time

import pytest

from app.execution import element_locator
from app.execution.element_locator import resolve
from app.models.models import ActionEnum, SelectorStrategyEnum, Step


class FakeElement:
    """One element as Playwright's locator API sees it."""

    def __init__(self, tag="button", name="", visible=True, enabled=True, enabled_on=0):
        self.tag = tag
        self.name = name
        self.visible = visible
        self._enabled = enabled
        #: Becomes enabled once it has been asked this many times, as an app
        #: that unlocks an input when it stops being busy would.
        self.enabled_on = enabled_on
        self.enabled_asked = 0

    async def is_visible(self):
        return self.visible

    async def is_enabled(self):
        self.enabled_asked += 1
        if self.enabled_on:
            return self.enabled_asked >= self.enabled_on
        return self._enabled

    async def evaluate(self, script):
        return {"tag": self.tag, "name": self.name}


class FakeFinder:
    """The half of Playwright's API that finds elements.

    A page and a locator both offer it, which is what lets a lookup be held to
    one part of the page: `scope.locator(container).get_by_text(...)`.
    """

    def _for(self, key) -> "FakeLocator":
        raise NotImplementedError

    def locator(self, selector):
        return self._for(("css", selector))

    def get_by_test_id(self, value):
        return self._for(("test_id", value))

    def get_by_role(self, role, name=None):
        return self._for(("role", role, name))

    def get_by_label(self, value):
        return self._for(("label", value))

    def get_by_placeholder(self, value):
        return self._for(("placeholder", value))

    def get_by_alt_text(self, value):
        return self._for(("alt", value))

    def get_by_title(self, value):
        return self._for(("title", value))

    def get_by_text(self, value, exact=None):
        return self._for(("text", value))


class FakeLocator(FakeFinder):
    def __init__(self, elements, key=None, owner=None):
        self.elements = elements
        self.key = key
        self.owner = owner

    def _for(self, key):
        if self.owner is None:
            return FakeLocator([])
        return self.owner._for((*(self.key or ()), *key))

    async def count(self):
        return len(self.elements)

    @property
    def first(self):
        if self.elements:
            return self.elements[0]
        # Nothing matched: stand in for the element Playwright would time out
        # on, carrying the lookup it came from so a test can name it.
        missing = FakeElement(visible=False)
        missing.origin = self.key
        return missing

    def nth(self, index):
        return self.elements[index]

    async def scroll_into_view_if_needed(self, timeout=None):
        return None


class FakeScope(FakeFinder):
    """A page whose elements are declared up front, keyed by how to find them."""

    def __init__(self, matches: dict):
        self.matches = matches
        self.asked: list[tuple] = []

    def _for(self, key):
        self.asked.append(key)
        return FakeLocator(self.matches.get(key, []), key, self)


def _meta(**overrides):
    meta = {
        "tag": "textarea",
        "role": "textbox",
        "name": "Type your Answer",
        "candidates": [
            {"by": "css", "value": "textarea#message"},
            {"by": "role", "value": "textbox", "name": "Type your Answer"},
        ],
    }
    meta.update(overrides)
    return json.dumps(meta)


def _step(action=ActionEnum.fill, selector="textarea#message", **kwargs):
    return Step(
        action=action,
        selector=selector,
        selector_strategy=kwargs.pop("selector_strategy", SelectorStrategyEnum.css),
        **kwargs,
    )


@pytest.fixture(autouse=True)
def quick_waits(monkeypatch):
    """A test must not sit out the budgets a real run allows."""
    monkeypatch.setattr(element_locator.settings, "element_ready_timeout_ms", 900)
    monkeypatch.setattr(element_locator.settings, "element_busy_timeout_ms", 1500)
    monkeypatch.setattr(element_locator, "POLL_INTERVAL_S", 0.01)


@pytest.mark.asyncio
async def test_recorded_selector_is_used_when_it_still_works():
    wanted = FakeElement(tag="textarea", name="Type your Answer")
    scope = FakeScope({("css", "textarea#message"): [wanted]})

    found = await resolve(_step(element_meta=_meta()), scope)

    assert found is wanted
    assert scope.asked == [("css", "textarea#message")], "no fallback was needed"


@pytest.mark.asyncio
async def test_waits_for_an_input_the_app_has_locked():
    """The failure that started this: a field enabled a moment after the click."""
    locked = FakeElement(tag="textarea", name="Type your Answer", enabled_on=3)
    scope = FakeScope({("css", "textarea#message"): [locked]})
    notes = []

    found = await resolve(_step(element_meta=_meta()), scope, on_note=notes.append)

    assert found is locked
    assert locked.enabled_asked >= 3, "it was asked again rather than given up on"
    assert notes and "became ready" in notes[0]


@pytest.mark.asyncio
async def test_falls_back_to_the_label_when_the_path_stops_matching():
    """A structural path is the first thing a redesign breaks."""
    moved = FakeElement(tag="div", name="Submit order")
    scope = FakeScope({("role", "button", "Submit order"): [moved]})
    step = _step(
        action=ActionEnum.click,
        selector="div:nth-of-type(10) > div:nth-of-type(2)",
        element_meta=json.dumps(
            {
                "tag": "div",
                "role": "button",
                "name": "Submit order",
                "candidates": [
                    {"by": "role", "value": "button", "name": "Submit order"}
                ],
            }
        ),
    )
    notes = []

    found = await resolve(step, scope, on_note=notes.append)

    assert found is moved
    assert notes and "Submit order" in notes[0]


@pytest.mark.asyncio
async def test_a_fallback_that_finds_something_else_is_refused():
    """Healing must not act on whatever happens to answer to the description."""
    stranger = FakeElement(tag="a", name="Print invoice")
    scope = FakeScope({("role", "button", "Submit order"): [stranger]})
    step = _step(
        action=ActionEnum.click,
        selector="#gone",
        element_meta=json.dumps(
            {
                "tag": "button",
                "role": "button",
                "name": "Submit order",
                "candidates": [
                    {"by": "role", "value": "button", "name": "Submit order"}
                ],
            }
        ),
    )

    found = await resolve(step, scope)

    assert found is not stranger, "nothing about it matched what was recorded"


@pytest.mark.asyncio
async def test_a_hidden_copy_of_the_form_is_stepped_over():
    on_screen = FakeElement(tag="input", name="Search")
    scope = FakeScope(
        {("css", "input.search"): [FakeElement(visible=False), on_screen]}
    )

    found = await resolve(_step(selector="input.search"), scope)

    assert found is on_screen


@pytest.mark.asyncio
async def test_a_check_is_handed_the_locator_not_one_match():
    """`count_equals` asks how many elements match; narrowing would answer 1."""
    matches = [FakeElement(), FakeElement(), FakeElement()]
    scope = FakeScope({("css", ".row"): matches})
    step = _step(
        action=ActionEnum.assert_,
        selector=".row",
        assertion_type="count_equals",
        expected_value="3",
    )

    found = await resolve(step, scope)

    assert await found.count() == 3


@pytest.mark.asyncio
async def test_a_check_for_absence_is_never_healed():
    """Finding the element another way would answer a different question."""
    elsewhere = FakeElement(tag="div", name="Error banner")
    scope = FakeScope({("role", "alert", "Error banner"): [elsewhere]})
    step = _step(
        action=ActionEnum.assert_,
        selector=".banner",
        assertion_type="not_exists",
        element_meta=json.dumps(
            {
                "tag": "div",
                "role": "alert",
                "name": "Error banner",
                "candidates": [
                    {"by": "role", "value": "alert", "name": "Error banner"}
                ],
            }
        ),
    )

    found = await resolve(step, scope)

    assert await found.count() == 0
    assert ("role", "alert", "Error banner") not in scope.asked


@pytest.mark.asyncio
async def test_a_step_with_no_selector_needs_no_element():
    step = Step(
        action=ActionEnum.navigate,
        selector="",
        selector_strategy=SelectorStrategyEnum.css,
        value="https://example.com",
    )
    assert await resolve(step, FakeScope({})) is None


@pytest.mark.asyncio
async def test_the_recorded_selector_is_what_fails_when_nothing_is_found():
    """The error has to be about the element the step was written for."""
    scope = FakeScope({})
    step = _step(action=ActionEnum.click, selector="#gone", element_meta=_meta())

    found = await resolve(step, scope)

    assert scope.asked[0] == ("css", "#gone")
    assert found.origin == ("css", "#gone")


@pytest.mark.asyncio
async def test_it_fails_against_the_element_that_is_actually_there():
    """A dead path plus a live label: the failure is about the control.

    The label found the recorded element and the app is holding it switched
    off. Looking further would only turn up something lesser to act on, so the
    run waits for it and then says what it waited for.
    """
    stuck = FakeElement(tag="textarea", name="Type your Answer", enabled=False)
    scope = FakeScope({("role", "textbox", "Type your Answer"): [stuck]})
    step = _step(selector="#gone", element_meta=_meta())

    with pytest.raises(element_locator.ElementNotReadyError) as raised:
        await resolve(step, scope)

    assert "Type your Answer" in str(raised.value)


@pytest.mark.asyncio
async def test_a_caller_can_shorten_the_wait():
    """The runner splits a step's time across attempts and passes each share."""
    never = FakeElement(tag="textarea", name="Type your Answer", enabled=False)
    scope = FakeScope({("css", "textarea#message"): [never]})
    step = _step()

    started = time.monotonic()
    with pytest.raises(element_locator.ElementNotReadyError):
        await resolve(step, scope, budget_s=0.05, busy_budget_s=0.05)

    assert time.monotonic() - started < 0.5, "the caller's budget won, not the setting"


@pytest.mark.asyncio
async def test_an_element_the_app_holds_shut_is_waited_out_far_longer():
    """A composer locked while an answer streams in is the app working, not a fault.

    The short budget is for an element that cannot be found; one that is on
    screen with the app holding it switched off gets the long one, and the
    step goes through when the app lets go.
    """
    busy = FakeElement(tag="textarea", name="Type your Answer", enabled_on=20)
    scope = FakeScope({("css", "textarea#message"): [busy]})

    found = await resolve(_step(element_meta=_meta()), scope, budget_s=0.02)

    assert found is busy, "the short budget did not cut the wait short"


@pytest.mark.asyncio
async def test_an_element_the_app_never_releases_is_reported_in_plain_words():
    """Handing this to Playwright would only buy a second timeout to quote."""
    never = FakeElement(tag="textarea", name="Type your Answer", enabled=False)
    scope = FakeScope({("css", "textarea#message"): [never]})
    step = _step(element_meta=_meta())
    notes = []

    with pytest.raises(element_locator.ElementNotReadyError) as raised:
        await resolve(step, scope, on_note=notes.append)

    said = str(raised.value)
    assert "Type your Answer" in said, "it names the element the tester saw"
    assert "switched off" in said
    assert "Timeout" not in said, "this is the app saying no, not a clock running out"


@pytest.mark.asyncio
async def test_a_long_wait_keeps_saying_it_is_still_waiting(monkeypatch):
    """Minutes of silence from a run is indistinguishable from a hung one."""
    monkeypatch.setattr(element_locator, "WAIT_NOTE_AFTER_S", 0.02)
    monkeypatch.setattr(element_locator, "WAIT_NOTE_EVERY_S", 0.02)
    never = FakeElement(tag="textarea", name="Type your Answer", enabled=False)
    scope = FakeScope({("css", "textarea#message"): [never]})
    step = _step(element_meta=_meta())
    notes = []

    with pytest.raises(element_locator.ElementNotReadyError):
        await resolve(step, scope, on_note=notes.append)

    assert len(notes) > 1, "it reports progress rather than going quiet"
    assert "still waiting" in notes[0]


@pytest.mark.asyncio
async def test_a_recording_made_before_fingerprints_still_replays():
    wanted = FakeElement()
    scope = FakeScope({("css", ".btn"): [wanted]})

    assert (
        await resolve(_step(action=ActionEnum.click, selector=".btn"), scope) is wanted
    )


def _positional_step(selector="div:nth-of-type(16) > div:nth-of-type(2)"):
    """A click recorded on an answer chip in a chat, with no id to hold on to."""
    return _step(
        action=ActionEnum.click,
        selector=selector,
        element_meta=json.dumps(
            {
                "tag": "div",
                "name": "No",
                "candidates": [
                    {"by": "css", "value": selector},
                    {"by": "text", "value": "No"},
                ],
            }
        ),
    )


@pytest.mark.asyncio
async def test_a_path_that_now_lands_on_a_neighbour_is_not_acted_on():
    """The heart of it: a positional path matches on any page, wrong or right.

    `div:nth-of-type(16) > div` finds a div whatever the page has become, so
    it never fails - it clicks the wrong thing, and the run stalls several
    steps later where the app is still waiting for the answer it never got.
    """
    neighbour = FakeElement(tag="div", name="Is this a repeat issue?")
    wanted = FakeElement(tag="div", name="No")
    step = _positional_step()
    scope = FakeScope({("css", step.selector): [neighbour], ("text", "No"): [wanted]})

    found = await resolve(step, scope)

    assert found is wanted, "it checked what the path had landed on"


@pytest.mark.asyncio
async def test_a_drifted_path_is_still_used_when_nothing_else_matches():
    """Refusing to act would be worse: the description may simply be stale."""
    neighbour = FakeElement(tag="div", name="Is this a repeat issue?")
    step = _positional_step()
    scope = FakeScope({("css", step.selector): [neighbour]})
    notes = []

    found = await resolve(step, scope, on_note=notes.append)

    assert found is neighbour
    assert notes and element_locator.DRIFT_NOTE in notes[-1]
    assert "'No'" in notes[-1], "the note names what the step was looking for"


@pytest.mark.asyncio
async def test_a_selector_with_nothing_to_fall_back_on_is_left_alone():
    """One candidate means the check has no better answer to offer."""
    whatever = FakeElement(tag="div", name="Something else")
    scope = FakeScope({("css", ".only"): [whatever]})
    step = _step(
        action=ActionEnum.click,
        selector=".only",
        element_meta=json.dumps({"tag": "div", "name": "No"}),
    )

    assert await resolve(step, scope) is whatever


@pytest.mark.asyncio
async def test_what_the_element_is_beats_where_it_sat():
    """Both matches look right, so the path being plausible proves nothing.

    A questionnaire keeps every answered question on screen. The second chip
    of the sixteenth block was the right one while recording and is an old,
    answered question now - clicking it succeeds and answers nothing.
    """
    already_answered = FakeElement(tag="div", name="No")
    asked_now = FakeElement(tag="div", name="No")
    step = _positional_step()
    scope = FakeScope(
        {("css", step.selector): [already_answered], ("text", "No"): [asked_now]}
    )
    notes = []

    found = await resolve(step, scope, on_note=notes.append)

    assert found is asked_now
    assert notes and "only says where the element sat" in notes[-1]


@pytest.mark.asyncio
async def test_a_label_that_merely_contains_the_recorded_one_is_refused():
    """Answering 'Not applicable' where 'No' was recorded is not a near miss."""
    not_applicable = FakeElement(tag="div", name="Not applicable")
    recorded = FakeElement(tag="div", name="No")
    step = _positional_step()
    scope = FakeScope(
        {("css", step.selector): [recorded], ("text", "No"): [not_applicable]}
    )

    assert await resolve(step, scope) is recorded


@pytest.mark.asyncio
async def test_anchoring_a_counting_path_does_not_make_it_trustworthy():
    """The path starts somewhere known and still ends by counting siblings."""
    neighbour = FakeElement(tag="div", name="No")
    wanted = FakeElement(tag="div", name="No")
    step = _positional_step(
        selector="div.custom-scroll > div > div:nth-of-type(16) > div:nth-of-type(2)"
    )
    scope = FakeScope({("css", step.selector): [neighbour], ("text", "No"): [wanted]})

    assert await resolve(step, scope) is wanted


@pytest.mark.asyncio
async def test_the_newest_of_several_identical_chips_is_the_one_answered():
    """A transcript grows, so "the third No" means nothing on the next run."""
    answered = [FakeElement(tag="div", name="No") for _ in range(3)]
    asked_now = FakeElement(tag="div", name="No")
    scope = FakeScope({("text", "No"): [*answered, asked_now]})
    step = _step(
        action=ActionEnum.click,
        selector="#gone",
        element_meta=json.dumps(
            {
                "tag": "div",
                "name": "No",
                # It was the last of three while recording; there are four now.
                "index": 2,
                "of": 3,
                "candidates": [{"by": "text", "value": "No"}],
            }
        ),
    )

    assert await resolve(step, scope) is asked_now


@pytest.mark.asyncio
async def test_the_row_the_path_counted_to_is_re_read_from_the_end():
    """A message index only holds while both runs produce the same messages.

    The recorded path counts to the twenty-ninth block of a transcript. One
    extra greeting on this run and that block is an old question - one fewer
    and it is nothing at all. What survives is that the tester was answering
    the newest block.
    """
    recorded = (
        "div.custom-scroll > div:nth-of-type(2) > div:nth-of-type(29) "
        "> div:nth-of-type(2) > div:nth-of-type(2)"
    )
    newest = (
        "div.custom-scroll > div:nth-of-type(2) > div:last-of-type "
        "> div:nth-of-type(2) > div:nth-of-type(2)"
    )
    asked_now = FakeElement(tag="div", name="No")
    step = _positional_step(selector=recorded)
    scope = FakeScope({("css", newest): [asked_now]})

    found = await resolve(step, scope)

    assert found is asked_now
    assert ("css", newest) in scope.asked


@pytest.mark.asyncio
async def test_the_newest_chip_is_found_even_among_a_crowd_of_them():
    """Twenty answered questions hold twenty chips reading "No".

    Refusing to choose between them leaves the step with only the path that
    counts, which is the one thing already known to have moved.
    """
    answered = [FakeElement(tag="div", name="No", enabled=False) for _ in range(19)]
    asked_now = FakeElement(tag="div", name="No")
    scope = FakeScope({("text", "No"): [*answered, asked_now]})
    step = _step(
        action=ActionEnum.click,
        selector="#gone",
        element_meta=json.dumps(
            {
                "tag": "div",
                "name": "No",
                "index": 11,
                "of": 12,
                "candidates": [{"by": "text", "value": "No"}],
            }
        ),
    )

    assert await resolve(step, scope) is asked_now


@pytest.mark.asyncio
async def test_an_older_chip_is_not_pressed_while_the_newest_is_switching_on():
    """The newest chip renders a moment before the app makes it live.

    Taking the nearest usable one instead answers a question that was settled
    long ago, and the run carries on looking as though it worked.
    """
    stale = FakeElement(tag="div", name="No")
    asked_now = FakeElement(tag="div", name="No", enabled_on=3)
    scope = FakeScope({("text", "No"): [stale, asked_now]})
    step = _step(
        action=ActionEnum.click,
        selector="#gone",
        element_meta=json.dumps(
            {
                "tag": "div",
                "name": "No",
                "index": 1,
                "of": 2,
                "candidates": [{"by": "text", "value": "No"}],
            }
        ),
    )

    assert await resolve(step, scope) is asked_now


@pytest.mark.asyncio
async def test_a_path_that_counts_into_a_list_takes_the_newest_match():
    """The recorder often cannot count an element's peers, and says nothing.

    A chat chip is a div among thousands of divs, too many to walk while the
    tester is clicking. The path is the only witness left, and counting to the
    twenty-ninth row is something only ever done in a list.
    """
    answered = [FakeElement(tag="div", name="No", enabled=False) for _ in range(9)]
    asked_now = FakeElement(tag="div", name="No")
    step = _positional_step(
        selector=(
            "div.custom-scroll > div:nth-of-type(2) > div:nth-of-type(29) "
            "> div:nth-of-type(2)"
        )
    )
    scope = FakeScope({("text", "No"): [*answered, asked_now]})

    assert await resolve(step, scope) is asked_now


@pytest.mark.asyncio
async def test_a_check_healed_onto_its_text_reads_only_what_it_recognised():
    """Text matches the line, the block holding it and the panel holding that.

    A check is normally handed its locator whole, because some of them count
    what it matches. Reading the text off three nested elements at once is an
    error rather than an answer, so a healed check gets the one it recognised.
    """
    line = "Here's the generated CAPA Description based on your inputs."
    panel = FakeElement(tag="div", name=line)
    block = FakeElement(tag="div", name=line)
    wanted = FakeElement(tag="strong", name=line)
    step = _step(
        action=ActionEnum.assert_,
        selector="div:nth-of-type(33) > div:nth-of-type(1) > strong:nth-of-type(1)",
        assertion_type="text_contains",
        element_meta=json.dumps(
            {
                "tag": "strong",
                "name": line,
                "candidates": [{"by": "text", "value": line}],
            }
        ),
    )
    scope = FakeScope({("text", line): [panel, block, wanted]})

    assert await resolve(step, scope) is wanted


@pytest.mark.asyncio
async def test_the_same_label_elsewhere_on_the_page_is_not_taken_for_it():
    """ "No" is a chip in the conversation and a button in the panel beside it.

    Asked of the whole page, the label returns whichever of them the markup
    happens to put last - an element the tester never touched, on the other
    side of the screen. The recorded path says which part of the page the
    step was working in, and that is the scope a person would have written.
    """
    chip = FakeElement(tag="div", name="No")
    panel = FakeElement(tag="div", name="No")
    step = _positional_step(
        selector=(
            "div.custom-scroll > div:nth-of-type(2) > div:nth-of-type(29) "
            "> div:nth-of-type(2)"
        )
    )
    scope = FakeScope(
        {
            ("text", "No"): [chip, panel],
            ("css", "div.custom-scroll", "text", "No"): [chip],
        }
    )

    assert await resolve(step, scope) is chip


@pytest.mark.asyncio
async def test_a_container_that_has_been_renamed_does_not_take_the_step_down():
    """Narrowing is an improvement, not a requirement: the page moves on."""
    chip = FakeElement(tag="div", name="No")
    step = _positional_step(
        selector="div.custom-scroll > div:nth-of-type(29) > div:nth-of-type(2)"
    )
    scope = FakeScope({("text", "No"): [chip]})

    assert await resolve(step, scope) is chip


# ---------------------------------------------------------------- xpath steps
#
# The recorder writes XPath, so everything the healing knows about a CSS path -
# that it counts into a list, which part of it names a place - has to be read
# out of an XPath just as well.


def _xpath_step(selector, action=ActionEnum.click, **kwargs):
    return Step(
        action=action,
        selector=selector,
        selector_strategy=SelectorStrategyEnum.xpath,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_a_recorded_xpath_is_used_as_it_stands():
    wanted = FakeElement(tag="button", name="Pay now")
    selector = "//button[@id='pay']"
    scope = FakeScope({("css", f"xpath={selector}"): [wanted]})
    step = _xpath_step(
        selector,
        element_meta=json.dumps({"tag": "button", "name": "Pay now"}),
    )

    found = await resolve(step, scope)

    assert found is wanted
    assert scope.asked == [("css", f"xpath={selector}")], "no fallback was needed"


@pytest.mark.asyncio
async def test_an_xpath_that_only_counts_defers_to_the_recorded_label():
    """`//div[@id='root']/div[2]/button` finds a button on almost any page.

    Which button is another matter. Where the recorder also wrote down a
    label, that is asked first and the path is kept as the fallback.
    """
    wanted = FakeElement(tag="button", name="Pay now")
    step = _xpath_step(
        "//div[@id='root']/div[2]/button",
        element_meta=json.dumps(
            {
                "tag": "button",
                "name": "Pay now",
                "candidates": [{"by": "role", "value": "button", "name": "Pay now"}],
            }
        ),
    )
    scope = FakeScope({("role", "button", "Pay now"): [wanted]})

    assert await resolve(step, scope) is wanted


@pytest.mark.asyncio
async def test_the_xpath_row_that_was_counted_to_is_re_read_from_the_end():
    """The twenty-ninth message is only the right one while the counts agree.

    What survives between the recording and the run is that the tester was
    working on the newest row, so the path is asked again from the end.
    """
    recorded = "//div[@id='chat']/div[2]/div[29]/div[2]"
    newest = "//div[@id='chat']/div[2]/div[last()]/div[2]"
    asked_now = FakeElement(tag="div", name="No")
    step = _xpath_step(
        recorded,
        element_meta=json.dumps(
            {"tag": "div", "name": "No", "candidates": [{"by": "text", "value": "No"}]}
        ),
    )
    scope = FakeScope({("css", f"xpath={newest}"): [asked_now]})

    found = await resolve(step, scope)

    assert found is asked_now
    assert ("css", f"xpath={newest}") in scope.asked


@pytest.mark.asyncio
async def test_an_xpath_says_which_part_of_the_page_the_step_was_working_in():
    """The same label sits in the transcript and in the panel beside it."""
    chip = FakeElement(tag="div", name="No")
    panel = FakeElement(tag="div", name="No")
    step = _xpath_step(
        "//div[@class='custom-scroll']/div[2]/div[29]/div[2]",
        element_meta=json.dumps(
            {"tag": "div", "name": "No", "candidates": [{"by": "text", "value": "No"}]}
        ),
    )
    scope = FakeScope(
        {
            ("text", "No"): [chip, panel],
            ("css", "//div[@class='custom-scroll']", "text", "No"): [chip],
        }
    )

    assert await resolve(step, scope) is chip


def test_a_slash_inside_a_predicate_is_not_a_step_boundary():
    """`@href='/orders'` is a label, not the start of another location step."""
    candidate = element_locator.Candidate("xpath", "//a[@href='/orders']/span[2]")

    assert element_locator._xpath_steps(candidate.value) == [
        ("//", "a[@href='/orders']"),
        ("/", "span[2]"),
    ]
    assert candidate.counts_only() is True

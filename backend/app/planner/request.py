"""MealRequest: what the LLM extracts from "₹1,000, 4 people, two vegetarian, one doesn't eat spicy, a good dinner"
(Phase 5a, D-029). The LLM fills it; code validates it and does everything else.

    {"budget": 1000, "people": 4, "veg_count": 2, "non_spicy_count": 1, "non_spicy_veg_count": null,
     "spice_preference": null, "meal_type": "dinner", "area": null}

Rules:
  · Strict types: a number sent as text ("500"), a boolean or a fraction is refused, never coerced, so a
    misread request can't quietly become a different one. Unknown fields are refused.
  · Missing budget, people or area is not an error: plan_meal answers needs_info and the agent asks for it.
  · Counts must add up: veg and non-spicy counts are at most the group size, and a known overlap
    (non_spicy_veg_count) must be possible for those counts.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

MAX_PEOPLE = 10
MIN_BUDGET, MAX_BUDGET = 1, 20_000
MEAL_TYPES = ("breakfast", "lunch", "dinner", "meal", "snack")
# A stated spice preference is a rule, not a taste (Saif, Session 15, D-036): every person who CAN eat spicy food
# gets a main inside this range, in every plan. Non-spicy people always get spice ≤ 1. The scale is the app's own:
# 0 none, 1 mild, 2 medium, 3 very spicy. "spicy" = 2–3, "medium" = exactly 2, "mild" = 0–1 (so everyone mild).
SPICE_RANGE = {None: (0, 3), "spicy": (2, 3), "medium": (2, 2), "mild": (0, 1)}
ASK_ORDER = ("people", "budget", "area")           # what the agent asks for first when several are missing

Count = Annotated[int, Field(ge=0, le=MAX_PEOPLE, strict=True)]


class MealRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    budget: Annotated[int | None, Field(ge=MIN_BUDGET, le=MAX_BUDGET, description=(
        "The most the user will pay in whole rupees, for the WHOLE bill (items, delivery and GST). "
        "null if the user didn't say."))] = None
    people: Annotated[int | None, Field(ge=1, le=MAX_PEOPLE, description=(
        "How many people will eat. null if the user didn't say."))] = None
    veg_count: Annotated[Count, Field(description="How many of them are vegetarian (no meat, fish or egg).")] = 0
    non_spicy_count: Annotated[Count, Field(description=(
        "How many of them can't eat spicy food. If nobody in the group wants spicy food, this equals people."))] = 0
    non_spicy_veg_count: Annotated[Count | None, Field(description=(
        "Only if the user said WHO the non-spicy people are: how many of the non-spicy people are vegetarian. "
        "null when unclear; the plan then works whoever they are."))] = None
    spice_preference: Annotated[Literal["mild", "medium", "spicy"] | None, Field(description=(
        "The group's taste ('something spicy' → spicy). A preference, not a rule. null if not said."))] = None
    meal_type: Annotated[Literal["breakfast", "lunch", "dinner", "meal", "snack"], Field(description=(
        "snack for 'something light' or a snack; meal if a full meal is meant but no time was given."))] = "meal"
    area: Annotated[str | None, Field(min_length=1, max_length=80, description=(
        "The delivery area as the user said it (e.g. 'Madhapur'). null if not known yet."))] = None

    @model_validator(mode="after")
    def _counts_add_up(self):
        if self.people is not None:
            for name in ("veg_count", "non_spicy_count"):
                if getattr(self, name) > self.people:
                    raise ValueError(f"{name} ({getattr(self, name)}) is more than people ({self.people})")
        k = self.non_spicy_veg_count
        if k is not None:
            if k > min(self.veg_count, self.non_spicy_count):
                raise ValueError("non_spicy_veg_count can't be more than veg_count or non_spicy_count")
            if self.people is not None and k < self.veg_count + self.non_spicy_count - self.people:
                raise ValueError(f"with {self.people} people, {self.veg_count} vegetarian and {self.non_spicy_count} "
                                 f"non-spicy, at least {self.veg_count + self.non_spicy_count - self.people} of the "
                                 "non-spicy people must be vegetarian")
        return self

    def spice_range(self) -> tuple[int, int]:
        """The spice levels a person who can eat spicy food may be given (SPICE_RANGE)."""
        return SPICE_RANGE[self.spice_preference]

    def missing(self) -> list[str]:
        return [f for f in ASK_ORDER if getattr(self, f) is None]

    def overlaps(self) -> range:
        """Every possible number of non-spicy people who are vegetarian. One value when the user said who."""
        if self.non_spicy_veg_count is not None:
            return range(self.non_spicy_veg_count, self.non_spicy_veg_count + 1)
        low = max(0, self.veg_count + self.non_spicy_count - (self.people or 0))
        return range(low, min(self.veg_count, self.non_spicy_count) + 1)


def parse_request(data) -> tuple[MealRequest | None, dict | None]:
    """(request, None) or (None, an invalid_input answer listing every problem in plain words)."""
    if not isinstance(data, dict):
        return None, {"status": "invalid_input", "message": "the meal request must be a JSON object", "problems": []}
    try:
        return MealRequest.model_validate(data), None
    except ValidationError as e:
        problems = []
        for err in e.errors(include_url=False, include_input=False):
            where = ".".join(str(p) for p in err["loc"]) or "request"
            problems.append(f"{where}: {err['msg'].removeprefix('Value error, ')}")
        return None, {"status": "invalid_input", "problems": problems,
                      "message": "The meal request is not valid. Fix these fields (whole numbers, not text) and "
                                 "call again; ask the user if something is unclear."}

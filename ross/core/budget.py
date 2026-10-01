"""Hard budget governor: enforced locally before every model request from a conservative worst case."""
from dataclasses import dataclass
from typing import Optional

from . import pricing


class BudgetExceeded(Exception):
    pass


class GlobalBudgetExhausted(BudgetExceeded):
    """The shared run-wide cap cannot fund the next request. Remaining workloads must not run."""


class RunBudget:
    """Run-wide hard spend cap shared by every session (BASELINE and ROSS) in one evaluation run.

    Each session's Governor consults it before every request, including retries, with the same conservative worst case
    it uses for its own cap. Completed calls charge their estimated cost; failed calls that may have been billed charge
    their worst case. Sessions run sequentially, so admit-then-charge cannot be interleaved by another session.
    """

    def __init__(self, max_usd):
        if max_usd is None or max_usd < 0:
            raise ValueError("max_total_usd must be a non-negative number")
        self.max_usd = float(max_usd)
        self.spent_usd = 0.0
        self.exhausted = False

    @property
    def remaining(self):
        return self.max_usd - self.spent_usd

    def admit(self, worst):
        if worst is None:
            self.exhausted = True
            raise GlobalBudgetExhausted("global run budget: no pricing for this model, a guaranteed run-wide cap is impossible")
        if self.spent_usd + worst > self.max_usd:
            self.exhausted = True
            raise GlobalBudgetExhausted(f"global run budget: next call could cost up to ${worst:.4f}; "
                                        f"${self.remaining:.4f} of ${self.max_usd:.2f} remains")

    def add(self, usd):
        self.spent_usd += usd or 0.0


@dataclass
class Budget:
    max_usd: Optional[float] = None
    max_calls: Optional[int] = None
    max_output_tokens: Optional[int] = None
    max_total_tokens: Optional[int] = None


class Governor:
    def __init__(self, budget, provider, model, rate_override=None, run_budget=None):
        self.b = budget
        self.run = run_budget
        self.rates, self.version = pricing.rates(provider, model, override=rate_override)
        if (budget.max_usd is not None or run_budget is not None) and not self.rates:
            raise BudgetExceeded(f"no pricing for {provider}/{model}: a guaranteed dollar cap is impossible; "
                                 "provide a conservative rate or run without a dollar cap")
        self.spent_usd = 0.0
        self.calls = 0
        self.output = 0
        self.tokens = 0

    def worst_case(self, input_tokens, max_output):
        """Every input token billed at the most expensive input rate (a 1h cache write), plus the full output allowance."""
        if not self.rates:
            return None
        top = max(self.rates["input"], self.rates["cache_write_5m"], self.rates["cache_write_1h"])
        return (input_tokens * top + max_output * self.rates["output"]) / 1e6

    def admit(self, input_tokens, max_output):
        """Return the max_output to request, or raise BudgetExceeded. Called before every request, including retries."""
        b = self.b
        if b.max_calls is not None and self.calls >= b.max_calls:
            raise BudgetExceeded(f"call limit reached ({b.max_calls})")
        if b.max_output_tokens is not None:
            max_output = min(max_output, b.max_output_tokens - self.output)
            if max_output <= 0:
                raise BudgetExceeded(f"output-token limit reached ({b.max_output_tokens})")
        if b.max_total_tokens is not None and self.tokens + input_tokens + max_output > b.max_total_tokens:
            raise BudgetExceeded(f"token limit would be exceeded ({b.max_total_tokens})")
        if b.max_usd is not None:
            worst = self.worst_case(input_tokens, max_output)
            if self.spent_usd + worst > b.max_usd:
                raise BudgetExceeded(f"next call could cost up to ${worst:.4f}; ${b.max_usd - self.spent_usd:.4f} of ${b.max_usd:.2f} remains")
        if self.run is not None:  # both caps must approve: session above, run-wide here
            self.run.admit(self.worst_case(input_tokens, max_output))
        return max_output

    def charge(self, usage):
        """Record a completed call. Returns its estimated cost (rates are a labelled snapshot)."""
        self.calls += 1
        self.output += usage.output
        self.tokens += usage.total
        c = pricing.cost(usage, self.rates) if self.rates else 0.0
        self.spent_usd += c
        if self.run is not None:
            self.run.add(c)
        return c

    def charge_failed_attempt(self, input_tokens, max_output):
        """A failed request may still have been billed: count its worst case so retries cannot bypass the cap."""
        self.calls += 1
        w = self.worst_case(input_tokens, max_output)
        if w:
            self.spent_usd += w
            if self.run is not None:
                self.run.add(w)

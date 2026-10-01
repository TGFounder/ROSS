"""Tool-heavy workload (from the v1.2.0 champion evaluation): 197 tests, one root cause failing 152 with ~87 KB of output,
plus a two-part feature."""


def gen_formatters():
    fns = []
    for i in range(110):
        fns.append(f'''def format_line_{i:03d}(amount_cents, currency="USD", width={10 + i % 7}):
    """Report column formatter {i}: right-aligned money with {i % 3} extra pad."""
    text = money.format_cents(amount_cents, currency)
    return text.rjust(width + {i % 3})
''')
    return "from ledger import money\n\n\n" + "\n\n".join(fns) + "\n\nFORMATTERS = [" + ", ".join(f"format_line_{i:03d}" for i in range(110)) + "]\n"


FILES = {
"README.md": "# ledger\n\nSmall accounting library. `ledger/money.py` (cents arithmetic and formatting), `ledger/accounts.py`,\n`ledger/journal.py` (double-entry), `ledger/reports.py`, `ledger/formatters.py` (report columns),\n`ledger/fx.py` (exchange rates), `ledger/cli.py`. Tests: `python3 -m pytest -q`.\n",
"ledger/__init__.py": "",
"ledger/money.py": '''SYMBOLS = {"USD": "$", "EUR": "€", "INR": "₹", "GBP": "£"}


def round_half_up(value):
    """Round to the nearest whole cent, halves away from zero."""
    return int(value)


def apply_rate(cents, rate):
    return round_half_up(cents * rate)


def format_cents(cents, currency="USD"):
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{SYMBOLS.get(currency, currency + ' ')}{cents // 100}.{cents % 100:02d}"
''',
"ledger/fx.py": '''RATES_TO_USD = {"USD": 1.0, "EUR": 1.08, "INR": 0.012, "GBP": 1.27}


def to_usd(cents, currency):
    raise NotImplementedError("currency conversion not implemented yet")
''',
"ledger/accounts.py": '''from dataclasses import dataclass


@dataclass
class Account:
    code: str
    name: str
    kind: str  # asset, liability, equity, income, expense

    def normal_sign(self):
        return 1 if self.kind in ("asset", "expense") else -1


CHART = {
    "1000": Account("1000", "Cash", "asset"),
    "1200": Account("1200", "Receivables", "asset"),
    "2000": Account("2000", "Payables", "liability"),
    "3000": Account("3000", "Equity", "equity"),
    "4000": Account("4000", "Revenue", "income"),
    "5000": Account("5000", "Expenses", "expense"),
}
''',
"ledger/journal.py": '''from dataclasses import dataclass, field
from typing import List

from ledger.accounts import CHART
from ledger.money import apply_rate


@dataclass
class Posting:
    account: str
    cents: int  # debit positive, credit negative


@dataclass
class Entry:
    memo: str
    postings: List[Posting] = field(default_factory=list)

    def balanced(self):
        return sum(p.cents for p in self.postings) == 0


class Journal:
    def __init__(self):
        self.entries = []

    def post(self, entry):
        if not entry.balanced():
            raise ValueError("unbalanced entry")
        for p in entry.postings:
            if p.account not in CHART:
                raise KeyError(p.account)
        self.entries.append(entry)

    def balance(self, account):
        return sum(p.cents for e in self.entries for p in e.postings if p.account == account)

    def with_tax(self, cents, rate):
        return cents + apply_rate(cents, rate)
''',
"ledger/reports.py": '''from ledger.accounts import CHART
from ledger.money import format_cents


def trial_balance(journal):
    rows = []
    for code, acct in sorted(CHART.items()):
        bal = journal.balance(code)
        if bal:
            rows.append((code, acct.name, bal))
    return rows


def render(journal, currency="USD"):
    return "\\n".join(f"{c} {n:<12} {format_cents(b, currency):>12}" for c, n, b in trial_balance(journal))
''',
"ledger/cli.py": '''import argparse
import json
import sys

from ledger.journal import Entry, Journal, Posting
from ledger.reports import render


def load(path):
    j = Journal()
    for e in json.load(open(path)):
        j.post(Entry(e["memo"], [Posting(p["account"], p["cents"]) for p in e["postings"]]))
    return j


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ledger")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("report")
    r.add_argument("journal")
    args = ap.parse_args(argv)
    if args.cmd == "report":
        print(render(load(args.journal)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
''',
"tests/conftest.py": "import sys, pathlib\nsys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))\n",
"tests/test_money.py": '''import pytest
from ledger.money import apply_rate, format_cents, round_half_up


@pytest.mark.parametrize("value,expected", [(v / 10, int(v / 10 + 0.5)) for v in range(0, 400, 7)])
def test_round_positive(value, expected):
    assert round_half_up(value) == expected


@pytest.mark.parametrize("value,expected", [(-v / 10, -int(v / 10 + 0.5)) for v in range(0, 200, 9)])
def test_round_negative(value, expected):
    assert round_half_up(value) == expected


def test_apply_rate():
    assert apply_rate(1000, 0.185) == 185
    assert apply_rate(999, 0.5) == 500


def test_format():
    assert format_cents(123456) == "$1234.56"
    assert format_cents(-5, "EUR") == "-€0.05"
''',
"tests/test_journal.py": '''import pytest
from ledger.journal import Entry, Journal, Posting


def sale(c):
    return Entry("sale", [Posting("1000", c), Posting("4000", -c)])


def test_post_and_balance():
    j = Journal()
    j.post(sale(500))
    assert j.balance("1000") == 500


def test_unbalanced():
    with pytest.raises(ValueError):
        Journal().post(Entry("x", [Posting("1000", 1)]))


def test_tax():
    assert Journal().with_tax(1001, 0.18) == 1181
''',
"tests/test_formatters.py": '''import pytest
from ledger import formatters


@pytest.mark.parametrize("fn", formatters.FORMATTERS)
def test_formatter_rounds_tax_amount(fn):
    from ledger.money import apply_rate
    assert fn(apply_rate(1001, 0.5)).strip() == "$5.01"
''',
"tests/test_reports.py": '''from ledger.journal import Entry, Journal, Posting
from ledger.reports import render, trial_balance


def test_trial_balance():
    j = Journal()
    j.post(Entry("s", [Posting("1000", 250), Posting("4000", -250)]))
    assert trial_balance(j) == [("1000", "Cash", 250), ("4000", "Revenue", -250)]
    assert "$2.50" in render(j)
''',
}
FILES["ledger/formatters.py"] = gen_formatters()

TASK_A = ("Three things need doing in this library: (1) the test suite is failing; find and fix the root cause. "
          "(2) Implement ledger/fx.py to_usd(cents, currency) using RATES_TO_USD with the library's rounding, and add "
          "Journal.balance_in(account, currency) that returns the account balance converted from USD into the given currency. "
          "(3) Add a `ledger export JOURNAL` CLI subcommand that prints the trial balance as CSV with header code,name,cents. "
          "Add tests for (2) and (3) and make sure the whole suite passes.")
TASK_B = "Continue."

HIDDEN = '''import io, json, contextlib
from ledger.money import round_half_up
from ledger.fx import to_usd
from ledger.journal import Entry, Journal, Posting
from ledger import cli

def test_round():
    assert round_half_up(2.5) == 3 and round_half_up(-2.5) == -3 and round_half_up(2.49) == 2

def test_fx():
    assert to_usd(10000, "EUR") == 10800 and to_usd(100, "USD") == 100 and to_usd(1000, "INR") == 12

def test_balance_in():
    j = Journal(); j.post(Entry("s", [Posting("1000", 10800), Posting("4000", -10800)]))
    assert j.balance_in("1000", "EUR") == 10000

def test_export(tmp_path):
    p = tmp_path / "j.json"
    p.write_text(json.dumps([{"memo": "s", "postings": [{"account": "1000", "cents": 250}, {"account": "4000", "cents": -250}]}]))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cli.main(["export", str(p)])
    rows = [r.strip() for r in buf.getvalue().strip().splitlines()]
    assert rows[0] == "code,name,cents" and rows[1] == "1000,Cash,250" and rows[2] == "4000,Revenue,-250"
'''

SHORT_TASK = "In ledger/money.py, what does format_cents return for negative amounts? Answer in one sentence."

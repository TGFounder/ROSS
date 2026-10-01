"""Build 3 acceptance fixture: `shipq`, a small shipping-quote library (unfamiliar to both conditions).

Session A: suite fails (masked bugs: postcode normalisation, then multi-parcel volumetric weight) + add --json.
Session B: "Continue." -> Phase 2 in ROADMAP.md (remote-area surcharge).
"""
import random

AREAS = ("AB AL B BA BB BD BH BL BN BR BS BT CA CB CF CH CM CO CR CT CV CW DA DD DE DG DH DL DN DT DY E EC EH EN EX "
         "FK FY G GL GU GY HA HD HG HP HR HS HU HX IG IP IV JE KA KT KW KY L LA LD LE LL LN LS LU M ME MK ML N NE NG "
         "NN NP NR NW OL OX PA PE PH PL PO PR RG RH RM S SA SE SG SK SL SM SN SO SP SR SS ST SW SY TA TD TF TN TQ TR "
         "TS TW UB W WA WC WD WF WN WR WS WV YO ZE").split()
REGIONS = ["Scotland North", "Scotland Central", "North East", "North West", "Yorkshire", "Midlands", "Wales",
           "East Anglia", "London", "South East", "South West", "Northern Ireland", "Channel Islands"]


LONDON = {"EC", "WC", "SW", "SE", "NW", "N", "E", "W"}


def gen_zones():
    rnd = random.Random(7)
    rows = []
    for a in AREAS:
        keys = [f"{a}{d}" for d in range(10)] if len(a) == 2 else [f"{a}{d1}{d2}" for d1 in range(1, 10) for d2 in range(10)][:60] + [f"{a}{d}" for d in range(1, 10)]
        for key in keys:
            d = sum(map(int, filter(str.isdigit, key)))
            zone = 1 if a in LONDON else 1 + (sum(map(ord, a)) + d) % 4
            region = REGIONS[(sum(map(ord, a)) + rnd.randrange(3)) % len(REGIONS)]
            rows.append(f'    "{key[:3]}": {zone},  # {region}, {a} district {key[len(a):]}, depot {rnd.randrange(100, 999)}')
    return rows


ZONES = '''"""Postcode zone lookup.

Zones run from 1 (local) to 4 (remote mainland). International destinations use zone 5.
Keys in GB_ZONES are the first three characters of the normalised postcode
(upper case, no spaces), for example "SW1A 1AA" -> "SW1".
"""

INTERNATIONAL = {"IE": 5, "FR": 5, "DE": 5, "NL": 5, "BE": 5}


class UnknownPostcode(KeyError):
    pass


def normalise_postcode(postcode):
    """Return the lookup key for a GB postcode."""
    return postcode.strip().upper()[:4]


def zone_for(country, postcode):
    country = country.upper()
    if country in INTERNATIONAL:
        return INTERNATIONAL[country]
    if country != "GB":
        raise UnknownPostcode(f"no service to {country}")
    key = normalise_postcode(postcode)
    try:
        return GB_ZONES[key]
    except KeyError:
        raise UnknownPostcode(key) from None


GB_ZONES = {
''' + "\n".join(gen_zones()) + "\n}\n"

FILES = {
"README.md": """# shipq

Shipping quotes for UK parcels.

    python3 -m shipq.cli quote --to GB:SW1A1AA --parcel 30x20x10:2.5 [--parcel ...] [--carrier NAME]

Modules: `shipq/units.py` (unit conversion), `shipq/parcel.py`, `shipq/zones.py` (postcode zones, generated
table), `shipq/carriers.py` (carrier tariffs), `shipq/pricing.py` (quotes), `shipq/money.py`, `shipq/cli.py`.
Tests: `python3 -m pytest -q`. Planned work: `ROADMAP.md`.
""",
"ROADMAP.md": """# Roadmap

## Phase 1: correctness and JSON output (in progress)

- Fix failing tests / multi-parcel quotes.
- `shipq quote --json`.

## Phase 2: remote-area surcharge

Carriers charge a per-parcel surcharge for remote postcodes.

- Add `REMOTE_AREAS = {"HS", "IV", "KW", "ZE", "PA"}` and `is_remote(country, postcode)` to `shipq/zones.py`.
  A GB postcode is remote when its area (the leading letters of the normalised postcode) is in `REMOTE_AREAS`.
  Non-GB destinations are never remote.
- Add `remote_surcharge_cents` to each carrier: swiftpost 450, parcelco 600. eurofreight does not serve
  remote areas: quoting it for a remote postcode must raise `NotServiceable` (define it in `shipq/pricing.py`).
- The surcharge is added once per parcel to `price_cents` and also reported as `Quote.surcharge_cents`
  (0 when not remote). Include `surcharge_cents` in the `--json` output.
- When `shipq quote` is run without `--carrier`, carriers that are not serviceable are left out of the output.
- Tests for all of the above.
""",
"shipq/__init__.py": "",
"shipq/money.py": '''def round_half_up(value):
    """Round to the nearest integer, halves away from zero."""
    from decimal import Decimal, ROUND_HALF_UP
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format_cents(cents):
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}\\u00a3{cents // 100}.{cents % 100:02d}"
''',
"shipq/units.py": '''import math

KG_PER = {"kg": 1.0, "g": 0.001, "lb": 0.45359237, "oz": 0.028349523125}
CM_PER = {"cm": 1.0, "mm": 0.1, "in": 2.54}


def to_kg(weight, unit="kg"):
    try:
        return weight * KG_PER[unit]
    except KeyError:
        raise ValueError(f"unknown weight unit {unit!r}") from None


def to_cm(length, unit="cm"):
    try:
        return length * CM_PER[unit]
    except KeyError:
        raise ValueError(f"unknown length unit {unit!r}") from None


def round_up_half_kg(kg):
    """Carriers bill in 0.5 kg steps, always rounding up."""
    return math.ceil(round(kg * 2, 9)) / 2
''',
"shipq/parcel.py": '''from dataclasses import dataclass

from shipq.units import to_cm, to_kg


@dataclass(frozen=True)
class Parcel:
    length: float
    width: float
    height: float
    weight: float
    weight_unit: str = "kg"
    length_unit: str = "cm"

    @property
    def kg(self):
        return to_kg(self.weight, self.weight_unit)

    def volume_cm3(self):
        return to_cm(self.length, self.length_unit) * to_cm(self.width, self.length_unit) * to_cm(self.height, self.length_unit)

    def volumetric_kg(self, divisor):
        return self.volume_cm3() / divisor

    @classmethod
    def parse(cls, spec):
        """'30x20x10:2.5' -> Parcel(30, 20, 10, 2.5) in cm and kg."""
        dims, _, weight = spec.partition(":")
        l, w, h = (float(x) for x in dims.lower().split("x"))
        return cls(l, w, h, float(weight))
''',
"shipq/carriers.py": '''from dataclasses import dataclass, field


@dataclass(frozen=True)
class Carrier:
    name: str
    base_cents: int
    per_kg_cents: int
    dim_divisor: int
    max_kg: float
    zone_multiplier: dict = field(default_factory=dict)


CARRIERS = {
    "swiftpost": Carrier("swiftpost", 395, 120, 5000, 30, {1: 1.0, 2: 1.15, 3: 1.3, 4: 1.6, 5: 2.4}),
    "parcelco": Carrier("parcelco", 450, 95, 4000, 25, {1: 1.0, 2: 1.1, 3: 1.25, 4: 1.5, 5: 2.0}),
    "eurofreight": Carrier("eurofreight", 690, 70, 6000, 40, {1: 1.0, 2: 1.0, 3: 1.2, 4: 1.4, 5: 1.6}),
}


def get(name):
    try:
        return CARRIERS[name]
    except KeyError:
        raise ValueError(f"unknown carrier {name!r}") from None
''',
"shipq/pricing.py": '''from dataclasses import dataclass

from shipq import carriers as carrier_db
from shipq.money import round_half_up
from shipq.units import round_up_half_kg
from shipq.zones import zone_for


class OverweightParcel(ValueError):
    pass


@dataclass(frozen=True)
class Quote:
    carrier: str
    zone: int
    chargeable_kg: float
    price_cents: int


def chargeable_kg(carrier, parcels):
    """Billable weight: per parcel, the larger of actual and volumetric weight, rounded up to 0.5 kg."""
    total = 0.0
    for parcel in parcels:
        if parcel.kg > carrier.max_kg:
            raise OverweightParcel(f"{carrier.name} accepts parcels up to {carrier.max_kg} kg")
        volumetric = parcels[0].volumetric_kg(carrier.dim_divisor)
        total += round_up_half_kg(max(parcel.kg, volumetric))
    return total


def quote(carrier_name, parcels, country, postcode):
    carrier = carrier_db.get(carrier_name)
    zone = zone_for(country, postcode)
    kg = chargeable_kg(carrier, parcels)
    price = len(parcels) * carrier.base_cents + carrier.per_kg_cents * kg * carrier.zone_multiplier[zone]
    return Quote(carrier.name, zone, kg, round_half_up(price))


def quote_all(parcels, country, postcode):
    return sorted((quote(name, parcels, country, postcode) for name in carrier_db.CARRIERS), key=lambda q: q.price_cents)
''',
"shipq/cli.py": '''import argparse
import sys

from shipq.money import format_cents
from shipq.parcel import Parcel
from shipq.pricing import quote, quote_all


def build_parser():
    p = argparse.ArgumentParser(prog="shipq")
    sub = p.add_subparsers(dest="command", required=True)
    q = sub.add_parser("quote", help="quote a shipment")
    q.add_argument("--to", required=True, help="COUNTRY:POSTCODE, e.g. GB:SW1A1AA")
    q.add_argument("--parcel", action="append", required=True, help="LxWxH:KG in cm and kg; repeat per parcel")
    q.add_argument("--carrier", help="quote a single carrier")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    country, _, postcode = args.to.partition(":")
    parcels = [Parcel.parse(s) for s in args.parcel]
    quotes = [quote(args.carrier, parcels, country, postcode)] if args.carrier else quote_all(parcels, country, postcode)
    for q in quotes:
        print(f"{q.carrier:<12} zone {q.zone}  {q.chargeable_kg:>6.1f} kg  {format_cents(q.price_cents):>10}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
''',
"shipq/zones.py": ZONES,
"tests/__init__.py": "",
"tests/test_units.py": '''import pytest

from shipq.units import round_up_half_kg, to_cm, to_kg


@pytest.mark.parametrize("w,unit,kg", [(1, "kg", 1), (500, "g", 0.5), (1, "lb", 0.45359237), (16, "oz", 0.45359237)])
def test_to_kg(w, unit, kg):
    assert to_kg(w, unit) == pytest.approx(kg)


def test_to_cm():
    assert to_cm(10, "in") == pytest.approx(25.4) and to_cm(15, "mm") == pytest.approx(1.5)


@pytest.mark.parametrize("kg,billed", [(0.1, 0.5), (0.5, 0.5), (0.51, 1.0), (2.0, 2.0), (2.01, 2.5), (7.3, 7.5)])
def test_round_up_half_kg(kg, billed):
    assert round_up_half_kg(kg) == billed


def test_bad_units():
    with pytest.raises(ValueError):
        to_kg(1, "stone")
''',
"tests/test_parcel.py": '''import pytest

from shipq.parcel import Parcel


def test_parse():
    assert Parcel.parse("30x20x10:2.5") == Parcel(30, 20, 10, 2.5)


def test_volumetric():
    assert Parcel(50, 40, 30, 1).volumetric_kg(5000) == pytest.approx(12.0)


def test_inches():
    assert Parcel(10, 10, 10, 1, length_unit="in").volume_cm3() == pytest.approx(16387.064)
''',
"tests/test_zones.py": '''import pytest

from shipq.zones import UnknownPostcode, normalise_postcode, zone_for

CASES = [("SW1A 1AA", 1), ("sw1a1aa", 1), ("EH1 1YZ", None), ("M1 1AE", None), ("B33 8TH", None), ("CF10 1EP", None),
         ("BT1 5GS", None), ("IV2 3PR", None), ("ZE1 0AA", None), ("PL4 8AA", None), (" ox1 2jd ", None), ("LS1 4AP", None)]


@pytest.mark.parametrize("postcode,_", CASES)
def test_gb_lookup_is_case_and_space_insensitive(postcode, _):
    assert zone_for("GB", postcode) == zone_for("gb", postcode.replace(" ", "").lower())


@pytest.mark.parametrize("postcode,zone", [c for c in CASES if c[1]])
def test_known_zone(postcode, zone):
    assert zone_for("GB", postcode) == zone


def test_normalise():
    assert normalise_postcode(" sw1a 1aa ") == "SW1"


def test_international():
    assert zone_for("FR", "75001") == 5


def test_unknown():
    with pytest.raises(UnknownPostcode):
        zone_for("US", "10001")
''',
"tests/test_pricing.py": '''import pytest

from shipq.parcel import Parcel
from shipq.pricing import OverweightParcel, chargeable_kg, quote, quote_all
from shipq.carriers import get

SMALL = Parcel(20, 15, 10, 1.2)
BULKY = Parcel(60, 50, 40, 3.0)


@pytest.mark.parametrize("carrier,expected", [("swiftpost", 575), ("parcelco", 593), ("eurofreight", 795)])
def test_single_small_parcel_local(carrier, expected):
    assert quote(carrier, [SMALL], "GB", "SW1A 1AA").price_cents == expected


@pytest.mark.parametrize("carrier,kg", [("swiftpost", 24.0), ("parcelco", 30.0), ("eurofreight", 20.0)])
def test_bulky_uses_volumetric(carrier, kg):
    assert chargeable_kg(get(carrier), [BULKY]) == kg


def test_multi_parcel_each_parcel_uses_its_own_volume():
    assert chargeable_kg(get("swiftpost"), [BULKY, SMALL]) == 25.5


def test_overweight():
    with pytest.raises(OverweightParcel):
        quote("parcelco", [Parcel(10, 10, 10, 26)], "GB", "SW1A 1AA")


def test_international_multiplier():
    assert quote("swiftpost", [SMALL], "FR", "75001").zone == 5


def test_quote_all_sorted():
    prices = [q.price_cents for q in quote_all([SMALL], "GB", "M1 1AE")]
    assert prices == sorted(prices) and len(prices) == 3
''',
"tests/test_cli.py": '''from shipq import cli


def test_quote_table(capsys):
    assert cli.main(["quote", "--to", "GB:SW1A1AA", "--parcel", "20x15x10:1.2", "--carrier", "swiftpost"]) == 0
    out = capsys.readouterr().out
    assert "swiftpost" in out and "\\u00a35.75" in out


def test_quote_all(capsys):
    cli.main(["quote", "--to", "GB:SW1A1AA", "--parcel", "20x15x10:1.2"])
    assert len(capsys.readouterr().out.strip().splitlines()) == 3
''',
}

TASK_A = ("Customers say quotes for multi-parcel shipments look wrong, and the test suite is failing. Find and fix the "
          "root cause, then add a --json flag to `shipq quote` that prints the quotes as a JSON list of objects with "
          "carrier, zone, chargeable_kg and price_cents. Add tests and make sure the whole suite passes. The next piece "
          "of work is in ROADMAP.md; we'll do that in the next session.")
TASK_B = "Continue."

HIDDEN = '''import json
import pytest
from shipq.parcel import Parcel
from shipq import cli, zones, pricing


SMALL = Parcel(20, 15, 10, 1.2)
BULKY = Parcel(60, 50, 40, 3.0)


def _json(capsys, *args):
    assert cli.main(["quote", *args, "--json"]) == 0
    return json.loads(capsys.readouterr().out)


def test_a_postcode_normalisation():
    assert zones.zone_for("GB", " sw1a 1aa ") == 1 and zones.normalise_postcode("EH1 1YZ") == "EH1"


def test_a_multi_parcel_volumetric():
    # small first, bulky second: each parcel uses its own volumetric weight
    assert pricing.chargeable_kg(pricing.carrier_db.get("swiftpost"), [SMALL, BULKY]) == 25.5
    assert pricing.chargeable_kg(pricing.carrier_db.get("swiftpost"), [BULKY, SMALL]) == 25.5


def test_a_json(capsys):
    rows = _json(capsys, "--to", "GB:SW1A1AA", "--parcel", "20x15x10:1.2", "--carrier", "swiftpost")
    assert isinstance(rows, list) and len(rows) == 1
    r = rows[0]
    assert r["carrier"] == "swiftpost" and r["zone"] == 1 and r["chargeable_kg"] == 1.5 and r["price_cents"] == 575


def test_b_is_remote():
    assert zones.is_remote("GB", "HS1 2AB") and zones.is_remote("gb", "ze1 0aa") and zones.is_remote("GB", "PA20 1AA")
    assert not zones.is_remote("GB", "SW1A 1AA") and not zones.is_remote("GB", "PO1 1AA") and not zones.is_remote("FR", "75001")


def test_b_surcharge():
    local = pricing.quote("swiftpost", [SMALL, SMALL], "GB", "SW1A 1AA")
    assert local.surcharge_cents == 0
    remote = pricing.quote("parcelco", [SMALL, SMALL], "GB", "IV2 3PR")
    assert remote.surcharge_cents == 1200
    plain = pricing.quote("parcelco", [SMALL, SMALL], "GB", "IV2 3PR")
    assert plain.price_cents == remote.price_cents


def test_b_surcharge_in_price():
    z = zones.zone_for("GB", "IV2 3PR")
    c = pricing.carrier_db.get("swiftpost")
    base = 2 * c.base_cents + c.per_kg_cents * 3.0 * c.zone_multiplier[z]
    from shipq.money import round_half_up
    assert pricing.quote("swiftpost", [SMALL, SMALL], "GB", "IV2 3PR").price_cents == round_half_up(base) + 900


def test_b_not_serviceable():
    with pytest.raises(pricing.NotServiceable):
        pricing.quote("eurofreight", [SMALL], "GB", "KW1 4AB")


def test_b_cli(capsys):
    rows = _json(capsys, "--to", "GB:HS1 2AB", "--parcel", "20x15x10:1.2")
    assert sorted(r["carrier"] for r in rows) == ["parcelco", "swiftpost"]
    assert all("surcharge_cents" in r for r in rows) and {r["surcharge_cents"] for r in rows} == {450, 600}
'''

SHORT_TASK = "In shipq/money.py, how does format_cents show negative amounts? Answer in one sentence."

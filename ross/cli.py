"""ross orchestrated mode: python3 -m ross run [options] PROMPT"""
import argparse
import os
import sys

from .core.budget import Budget
from .orchestration.loop import Session, summarize
from .orchestration.profile import FLAGS, Profile


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m ross")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run one orchestrated session in the current repository")
    r.add_argument("prompt")
    r.add_argument("--profile", choices=("ross", "baseline"), default="ross")
    r.add_argument("--provider", choices=("anthropic",), default="anthropic")
    r.add_argument("--model", default="claude-sonnet-5-5")
    r.add_argument("--max-usd", type=float, help="hard spend cap, enforced before every request")
    r.add_argument("--max-calls", type=int, default=40)
    r.add_argument("--max-output-tokens", type=int)
    r.add_argument("--disable", default="", help=f"comma-separated ROSS flags to turn off ({', '.join(FLAGS)})")
    r.add_argument("--enable", default="", help="comma-separated ROSS flags to turn on")
    r.add_argument("--json", action="store_true", help="print the run summary as JSON")
    a = ap.parse_args(argv)
    from .providers.anthropic import AnthropicProvider
    provider = AnthropicProvider(a.model)
    split = lambda s: [x for x in s.split(",") if x]
    profile = Profile.baseline() if a.profile == "baseline" else Profile.ross(enable=split(a.enable), disable=split(a.disable))
    budget = Budget(max_usd=a.max_usd, max_calls=a.max_calls, max_output_tokens=a.max_output_tokens)
    res = Session(os.getcwd(), provider, profile, budget, a.prompt).run()
    print(res.final_text)
    print(summarize(res), file=sys.stderr if not a.json else sys.stdout)
    return 0 if res.status == "done" else 1


if __name__ == "__main__":
    sys.exit(main())

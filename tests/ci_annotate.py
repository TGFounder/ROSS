"""Run the unit tests and surface each failure as a GitHub Actions annotation.

Annotations are readable through the public checks API, so CI failures on any
OS can be diagnosed without access to raw job logs. Exit code mirrors the run.
"""
import sys
import unittest


def main():
    suite = unittest.defaultTestLoader.discover("tests", pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    for test, trace in result.failures + result.errors:
        body = (str(test) + "\n" + trace)[-1800:].replace("%", "%25").replace("\r", "").replace("\n", "%0A")
        print(f"::error title=unittest {test.id()}::{body}")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())

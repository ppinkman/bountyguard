import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bountyguard.domain import GuardError
from bountyguard.limits import development_limit
from bountyguard.store import Store


class LimitTests(unittest.TestCase):
    def test_defaults_and_bounded_explicit_override(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(development_limit("funding"), 2)
            self.assertEqual(development_limit("model"), 3)
        with patch.dict(os.environ, {"BOUNTYGUARD_FUNDING_INTENT_LIMIT": "3"}):
            self.assertEqual(development_limit("funding"), 3)
        for value in ("0", "-1", "5", "unlimited"):
            with patch.dict(os.environ, {"BOUNTYGUARD_FUNDING_INTENT_LIMIT": value}):
                with self.assertRaises(ValueError): development_limit("funding")

    def test_override_preserves_usage_and_pending_and_duplicate_guards(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"BOUNTYGUARD_FUNDING_INTENT_LIMIT": "3"}):
            store = Store(Path(folder) / "journal.sqlite3")
            for number in range(3):
                name = str(number)
                row, created = store.operation(name, name, "fund_assigned", {"signer": name})
                self.assertTrue(created)
                same, created = store.operation(name, name, "fund_assigned", {"signer": name})
                self.assertFalse(created)
            with self.assertRaises(GuardError): store.operation("fourth", "4", "fund_assigned", {"signer": "4"})
            with self.assertRaises(GuardError): store.operation("other", "4", "pay", {"signer": "0"})
            with patch.dict(os.environ, {"BOUNTYGUARD_FUNDING_INTENT_LIMIT": "2"}):
                with self.assertRaises(GuardError): store.operation("fourth", "4", "fund_assigned", {"signer": "4"})


if __name__ == "__main__": unittest.main()

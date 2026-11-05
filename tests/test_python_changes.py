from pathlib import Path
import tempfile
import unittest

from bountyguard.domain import GuardError
from bountyguard.python_changes import implementation_changed


class PythonChangeTests(unittest.TestCase):
    def test_docstrings_at_all_supported_levels_do_not_qualify(self):
        before='''"""Old module."""
class Example:
    """Old class."""
    def value(self):
        """Old method."""
        return 1
async def async_value():
    """Old async function."""
    return 2
'''
        self.assertFalse(implementation_changed(before,before.replace('Old','New')))
    def test_adding_only_a_module_docstring_does_not_qualify(self):self.assertFalse(implementation_changed('','"""Documentation only."""'))
    def test_comments_and_formatting_do_not_qualify(self):self.assertFalse(implementation_changed('def f(x):\n    return x + 1\n','# comment\ndef f( x ):\n    return (x+1) # note\n'))
    def test_real_behavior_change_qualifies(self):self.assertTrue(implementation_changed('def f(x):\n    return x+1','def f(x):\n    return x+2'))
    def test_signature_change_qualifies(self):self.assertTrue(implementation_changed('def f(x):\n    return x','def f(x=1):\n    return x'))
    def test_invalid_or_oversized_source_is_not_a_pass(self):
        for value in ['def broken(', 'x'*100001]:
            with self.assertRaises(GuardError):implementation_changed('',value)
    def test_submitted_code_is_not_executed(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'must-not-exist'
            source='from pathlib import Path\nPath('+repr(str(target))+').write_text("executed")'
            self.assertTrue(implementation_changed('',source));self.assertFalse(target.exists())


if __name__=='__main__':unittest.main()

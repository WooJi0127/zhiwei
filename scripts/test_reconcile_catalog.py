import unittest
try:
    from reconcile_catalog import merge_record
except ImportError:
    merge_record = None


class ReconcileTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(merge_record, 'Three-way reconciliation is missing')

    def test_cloud_changes_and_local_corrections_both_survive(self):
        base = {'id':'r', 'image':'old', 'title':'before', 'date':'2026-10-01'}
        local = dict(base, title='corrected')
        cloud = dict(base, image='new', date='2026-10-03')
        self.assertEqual(merge_record('releases',base,local,cloud), dict(cloud,title='corrected'))

    def test_empty_value_does_not_erase_verified_field(self):
        self.assertEqual(merge_record('artists',{'agency':'A'},{'agency':'A'},{'agency':''}), {'agency':'A'})

    def test_unresolved_content_conflict_requires_review(self):
        with self.assertRaisesRegex(ValueError, 'conflict'):
            merge_record('members',{'b':'2000-01-01'},{'b':'2000-01-02'},{'b':'2000-01-03'})

    def test_explicit_source_type_beats_old_computed_type(self):
        base={'rtype':None,'rtype_src':None}
        local={'rtype':'Single','rtype_src':'Single'}
        cloud={'rtype':'Album','rtype_src':None}
        self.assertEqual(merge_record('releases',base,local,cloud),local)


if __name__ == '__main__':
    unittest.main()

from scripts.audit import all_passed, audit_batch


def valid_pair(make_workbook):
    return [('DP_N1.xlsx', make_workbook()),
            ('DP_N2.xlsx', make_workbook(number=2, previous=100, cumulative=200))]


def test_complete_pair_passes(make_workbook):
    batch = audit_batch(valid_pair(make_workbook))
    assert batch.status == 'OK'
    assert len(batch.comparisons) == 1
    assert batch.comparisons[0]['Difference DH'] == 0


def test_missing_previous_never_passes(make_workbook):
    batch = audit_batch([valid_pair(make_workbook)[0],
                         ('DP_N2.xlsx', make_workbook(number=2, previous=None, cumulative=200))])
    assert batch.status != 'OK'
    assert batch.comparisons[0]['Status'] == 'MISSING DATA'


def test_duplicate_never_passes(make_workbook):
    pair = valid_pair(make_workbook)
    batch = audit_batch(pair + [pair[0]])
    assert batch.status != 'OK'
    assert any('Duplicate' in issue for issue in batch.issues)


def test_unidentified_input_not_silently_excluded(make_workbook):
    batch = audit_batch(valid_pair(make_workbook) + [('unknown.xlsx', make_workbook(metadata=False))])
    assert batch.status != 'OK'
    assert len(batch.records) == 3
    assert any('source statement number is missing' in issue for issue in batch.issues)


def test_renamed_file_uses_source_identity(make_workbook):
    pair = valid_pair(make_workbook)
    assert audit_batch([('renamed.xlsx', pair[0][1]), pair[1]]).status == 'OK'


def test_filename_source_conflict_never_passes(make_workbook):
    pair = valid_pair(make_workbook)
    assert audit_batch([('DP_N8.xlsx', pair[0][1]), pair[1]]).status != 'OK'


def test_mixed_projects_never_paired(make_workbook):
    batch = audit_batch([valid_pair(make_workbook)[0],
                         ('DP_N2.xlsx', make_workbook(number=2, project='OTHER', previous=100, cumulative=200))])
    assert batch.status != 'OK'
    assert batch.comparisons == []


def test_invalid_upload_prevents_pass(make_workbook):
    batch = audit_batch(valid_pair(make_workbook) + [('invalid.xlsx', b'broken')])
    assert batch.status != 'OK'
    assert batch.requested == 3
    assert len(batch.records) == 2


def test_large_gap_is_bounded_and_incomplete(make_workbook):
    batch = audit_batch([valid_pair(make_workbook)[0],
                         ('DP_N10000.xlsx', make_workbook(number=10000, previous=100, cumulative=200))])
    assert batch.status != 'OK'
    assert len(batch.issues) < 5
    assert any('Missing intermediate' in issue for issue in batch.issues)


def test_out_of_range_number_does_not_allocate_range(make_workbook):
    batch = audit_batch(valid_pair(make_workbook) + [('DP_N999999999999999999999.xlsx', make_workbook())])
    assert batch.status != 'OK'


def test_interstatement_difference_is_flagged(make_workbook):
    batch = audit_batch([valid_pair(make_workbook)[0],
                         ('DP_N2.xlsx', make_workbook(number=2, previous=90, cumulative=190))])
    assert batch.comparisons[0]['Status'] == 'REVIEW REQUIRED'
    assert batch.status != 'OK'


def test_single_statement_cannot_certify_continuity(make_workbook):
    assert audit_batch(valid_pair(make_workbook)[:1]).status != 'OK'


def test_batch_count_limit(make_workbook):
    assert audit_batch([('DP_N1.xlsx', b'')] * 21).status == 'INVALID INPUT'


def test_unknown_and_empty_statuses_never_pass():
    for statuses in [[], ['REVIEW REQUIRED'], ['CHECK'], ['OK', None], ['OK', 'MISSING DATA']]:
        assert not all_passed(statuses)
    assert all_passed(['OK', 'OK'])

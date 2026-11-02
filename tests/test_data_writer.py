"""TSV writer: format, escaping, atomic save, row-count verification."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dataio.data_writer import DataWriter, NA


@pytest.fixture
def writer(tmp_path):
    return DataWriter(tmp_path, 'test', MagicMock())


def test_tab_separated(writer, tmp_path):
    writer.write_trial({'onset': 1.0, 'trial_type': 'congruent', 'rt': 0.5})
    writer.save_final()
    text = (tmp_path / 'test_events.tsv').read_text()
    assert '\t' in text
    assert ',' not in text.splitlines()[0]


def test_none_becomes_na(writer, tmp_path):
    writer.write_trial({'onset': 1.0, 'rt': None})
    writer.save_final()
    assert NA in (tmp_path / 'test_events.tsv').read_text()


def test_preferred_columns_first(writer, tmp_path):
    writer.write_trial({'word': 'ROUGE', 'onset': 1.0,
                        'trial_type': 'congruent', 'duration': 1.2})
    writer.save_final()
    header = (tmp_path / 'test_events.tsv').read_text().splitlines()[0]
    assert header.split('\t')[:2] == ['onset', 'duration']
    assert set(header.split('\t')) == {'word', 'onset', 'trial_type', 'duration'}


def test_row_count_matches(writer, tmp_path):
    for i in range(50):
        writer.write_trial({'onset': float(i), 'trial_type': 'x'})
    writer.save_final()
    lines = (tmp_path / 'test_events.tsv').read_text().strip().splitlines()
    assert len(lines) == 51          # header + 50


def test_tabs_in_values_are_stripped(writer, tmp_path):
    writer.write_trial({'onset': 1.0, 'note': 'a\tb\nc'})
    writer.save_final()
    lines = (tmp_path / 'test_events.tsv').read_text().strip().splitlines()
    assert len(lines) == 2
    assert len(lines[1].split('\t')) == len(lines[0].split('\t'))


def test_incremental_file_exists_during_run(writer, tmp_path):
    writer.write_trial({'onset': 1.0})
    assert (tmp_path / 'test_events_incremental.tsv').exists()


def test_no_tmp_file_left_behind(writer, tmp_path):
    writer.write_trial({'onset': 1.0})
    writer.save_final()
    assert not list(tmp_path.glob('*.tmp'))
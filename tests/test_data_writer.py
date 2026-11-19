"""TSV writer: format, escaping, atomic save, row-count verification."""

from __future__ import annotations

import csv
import errno
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
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


@pytest.mark.parametrize('suffix', ['events.tsv', 'events_incremental.tsv', 'design.json'])
def test_existing_recording_is_never_overwritten(tmp_path, suffix):
    existing = tmp_path / f'test_{suffix}'
    original = b'previous recording\n'
    existing.write_bytes(original)
    with pytest.raises(FileExistsError):
        DataWriter(tmp_path, 'test', MagicMock())
    assert existing.read_bytes() == original


def test_two_concurrent_launches_only_reserve_once(tmp_path):
    barrier = Barrier(2)

    def launch():
        barrier.wait(timeout=5)
        try:
            return DataWriter(tmp_path, 'test', MagicMock())
        except FileExistsError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        writers = list(pool.map(lambda _: launch(), range(2)))
    winners = [w for w in writers if w is not None]
    assert len(winners) == 1
    winners[0].write_trial({'trial': 1, 'response': 'b'})
    assert winners[0].save_final().exists()
    winners[0].close()


def test_abort_before_first_trial_keeps_reservation(tmp_path):
    writer = DataWriter(tmp_path, 'test', MagicMock())
    writer.close()
    with pytest.raises(FileExistsError):
        DataWriter(tmp_path, 'test', MagicMock())


def test_final_publication_race_preserves_existing_bytes(writer, tmp_path, monkeypatch):
    writer.write_trial({'trial': 1, 'response': 'b'})
    final = tmp_path / 'test_events.tsv'

    def another_process_publishes_first(source, target):
        target.write_bytes(b'existing final recording\n')
        raise FileExistsError('Competing final file')

    monkeypatch.setattr('dataio.data_writer.os.link', another_process_publishes_first)
    assert writer.save_final() is None
    assert final.read_bytes() == b'existing final recording\n'
    assert (tmp_path / 'test_events_incremental.tsv').exists()
    assert (tmp_path / 'test_events.tsv.tmp').exists()


def test_save_on_filesystem_without_hard_links(writer, tmp_path, monkeypatch):
    writer.write_trial({'trial': 1, 'response': 'y'})
    monkeypatch.setattr('dataio.data_writer.os.link',
                        MagicMock(side_effect=OSError(errno.EOPNOTSUPP, 'No hard links')))
    final = writer.save_final()
    assert final is not None
    assert final.read_bytes() == (tmp_path / 'test_events_incremental.tsv').read_bytes()
    assert not list(tmp_path.glob('*.tmp'))


def test_incremental_write_error_is_reported_and_record_can_be_rescued(writer):
    writer.write_trial({'trial': 1, 'response': 'b'})
    writer._writer = MagicMock()
    writer._writer.writerow.side_effect = OSError('Disk write failed')
    with pytest.raises(OSError, match='Disk write failed'):
        writer.write_trial({'trial': 2, 'response': 'y'})
    writer._logger.err.assert_called_once()
    final = writer.save_final()
    with final.open() as stream:
        rows = list(csv.DictReader(stream, delimiter='\t'))
    assert [row['response'] for row in rows] == ['b', 'y']

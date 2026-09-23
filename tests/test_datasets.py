import io
import stat
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from backend import datasets
from backend.datasets import load_dataset, load_official


HEADER = "sender,receiver,amount,timestamp\n"


def csv_frame(rows):
    return load_dataset((HEADER + rows).encode(), "input.csv")


def parquet_bytes(frame):
    stream = io.BytesIO()
    frame.to_parquet(stream, index=False, engine="pyarrow")
    return stream.getvalue()


@pytest.fixture
def official_tables():
    return {
        "transactions.parquet": pd.DataFrame({
            "src": [101, 101], "dst": [202, 202],
            "date": [date(2026, 7, 2), date(2026, 7, 1)], "sum_kzt": [5000.0, 6000.0],
        }),
        "edges.parquet": pd.DataFrame({
            "src": [101], "dst": [202], "sum_kzt": [11000.0], "n_tx": [2], "depth": [1],
        }),
        "nodes.parquet": pd.DataFrame({
            "gid": [101, 202, 303], "depth": [0, 1, 0], "is_seed": [True, False, True],
        }),
    }


def zip_bytes(tables, extras=()):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, frame in tables.items():
            archive.writestr("data/" + filename, parquet_bytes(frame))
        for filename, payload in extras:
            archive.writestr(filename, payload)
    return stream.getvalue()


def test_csv_preserves_ids_and_utc_order_and_stable_ids():
    rows = "0007,9007199254740993,12.5,2026-07-02T03:00:00+03:00\nNA,0007,2,2026-07-01T22:00:00Z\n"
    frame = csv_frame(rows)
    assert frame.sender.tolist() == ["NA", "0007"]
    assert frame.receiver.tolist() == ["0007", "9007199254740993"]
    assert frame.id.tolist() == ["tx-000002", "tx-000001"]
    assert frame.timestamp.iloc[1] == pd.Timestamp("2026-07-02T00:00:00Z")
    assert frame.attrs == {"time_precision": "timestamp", "currency": None, "node_metadata": {}, "source_kind": "csv", "warnings": []}
    pd.testing.assert_frame_equal(frame, csv_frame(rows))


@pytest.mark.parametrize("rows", [
    "A,B,1,2026-07-01\n",
    "A,B,1,2026-07-01\nB,C,2,2026-07-01T12:00:00Z\n",
])
def test_any_date_only_timestamp_disables_intraday_precision(rows):
    frame = csv_frame(rows)
    assert frame.attrs["time_precision"] == "day"
    assert frame.attrs["warnings"]


def test_official_schema_csv_is_day_precision_kzt():
    frame = load_dataset(b"src,dst,date,sum_kzt\n0001,0002,2026-07-01,5000\n", "input.csv")
    assert frame.sender.iloc[0] == "0001"
    assert frame.attrs["currency"] == "KZT"
    assert frame.attrs["time_precision"] == "day"
    assert frame.attrs["source_kind"] == "csv"
    assert "seed" in " ".join(frame.attrs["warnings"])


@pytest.mark.parametrize("row", [
    "A,B,-1,2026-07-01", "A,B,0,2026-07-01", "A,B,NaN,2026-07-01",
    "A,B,inf,2026-07-01", "A,B,1e16,2026-07-01", ",B,1,2026-07-01",
    "A,B,1,2026-02-30", "A,B,1,07/01/2026", "A,B,1,tomorrow",
    "A,B,1,2026-07", "A,B,1,1720000000", "<script>,B,1,2026-07-01",
    "A,B,1,", "A,B,1,2026-07-01,extra", "A,B,1", "",
])
def test_invalid_rows_are_rejected_without_silent_dropping(row):
    with pytest.raises(ValueError):
        csv_frame("OK,FINE,1,2026-07-01\n" + row + "\n")


def test_csv_duplicate_headers_rejected():
    with pytest.raises(ValueError, match="повторяющиеся"):
        load_dataset(b"sender,receiver,amount,timestamp,sender\nA,B,1,2026-07-01,C\n", "input.csv")


def test_subnormal_amounts_are_rejected_before_graph_analysis():
    with pytest.raises(ValueError, match="сумма слишком мала"):
        csv_frame("A,B,1e-320,2026-07-01\n")
    frame = csv_frame("A,B,1e-300,2026-07-01\n")
    assert frame.amount.iloc[0] == 1e-300


def test_ambiguous_dual_schema_cannot_override_official_date_precision():
    with pytest.raises(ValueError, match="неоднозначная схема"):
        load_dataset(b"sender,receiver,amount,timestamp,src,dst,sum_kzt,date\nA,B,1,2026-07-01T12:00:00Z,A,B,1,2026-07-01\n", "input.csv")


def test_standard_parquet_preserves_leading_zero_ids_and_date_precision():
    table = pd.DataFrame({"sender": ["0001"], "receiver": ["0002"], "amount": [1], "timestamp": [date(2026, 7, 1)]})
    frame = load_dataset(parquet_bytes(table), "input.parquet")
    assert frame.sender.iloc[0] == "0001"
    assert frame.receiver.iloc[0] == "0002"
    assert frame.attrs["time_precision"] == "day"


def test_csv_byte_and_row_and_node_caps(monkeypatch):
    monkeypatch.setattr(datasets, "MAX_BYTES", 100)
    with pytest.raises(ValueError, match="50 МБ"):
        load_dataset(b"x" * 101, "input.csv")
    monkeypatch.setattr(datasets, "MAX_ROWS", 1)
    with pytest.raises(ValueError, match="транзакций"):
        csv_frame("A,B,1,2026-07-01\nB,C,2,2026-07-01\n")
    monkeypatch.setattr(datasets, "MAX_NODES", 1)
    with pytest.raises(ValueError, match="узлов"):
        csv_frame("A,B,1,2026-07-01\n")


def test_official_zip_retains_all_seed_metadata_and_consistent_aggregates(official_tables):
    frame = load_dataset(zip_bytes(official_tables), "data.ZIP")
    assert len(frame) == 2
    assert frame.attrs["source_kind"] == "official"
    assert frame.attrs["time_precision"] == "day"
    assert frame.attrs["currency"] == "KZT"
    assert frame.attrs["node_metadata"] == {
        "101": {"is_seed": True, "depth": 0},
        "202": {"is_seed": False, "depth": 1},
        "303": {"is_seed": True, "depth": 0},
    }


def test_single_parquet_has_no_invented_seed_information(official_tables):
    frame = load_dataset(parquet_bytes(official_tables["transactions.parquet"]), "transactions.parquet")
    assert frame.attrs["source_kind"] == "parquet"
    assert frame.attrs["node_metadata"] == {}
    assert frame.attrs["time_precision"] == "day"
    assert frame.amount.sum() == 11000


def test_official_directory_accepts_direct_and_data_subfolder(tmp_path, official_tables):
    directory = tmp_path / "data"
    directory.mkdir()
    for filename, frame in official_tables.items():
        (directory / filename).write_bytes(parquet_bytes(frame))
    direct = load_official(directory)
    nested = load_official(tmp_path)
    pd.testing.assert_frame_equal(direct, nested)
    assert direct.attrs == nested.attrs


@pytest.mark.parametrize("filename,column,value,error", [
    ("edges.parquet", "sum_kzt", 11001.0, "суммой"),
    ("edges.parquet", "n_tx", 1, "числом"),
    ("edges.parquet", "n_tx", 1.5, "целое"),
    ("edges.parquet", "src", 999, "отсутствует"),
    ("edges.parquet", "depth", 0, "от 1 до 4"),
    ("nodes.parquet", "gid", 999, "отсутствуют"),
    ("nodes.parquet", "depth", 1, "не согласован"),
    ("transactions.parquet", "sum_kzt", -1, "положительным"),
])
def test_official_corruption_rejected(official_tables, filename, column, value, error):
    # Explicit object cast also allows malformed floats in normally integral columns.
    official_tables[filename][column] = official_tables[filename][column].astype(object)
    official_tables[filename].loc[0, column] = value
    with pytest.raises(ValueError, match=error):
        load_dataset(zip_bytes(official_tables), "data.zip")


@pytest.mark.parametrize("filename,error", [("edges.parquet", "повторяющиеся пары"), ("nodes.parquet", "повторяющиеся идентификаторы")])
def test_duplicate_edge_and_node_records_rejected(official_tables, filename, error):
    official_tables[filename] = pd.concat([official_tables[filename], official_tables[filename].iloc[:1]], ignore_index=True)
    with pytest.raises(ValueError, match=error):
        load_dataset(zip_bytes(official_tables), "data.zip")


def test_missing_edge_and_nonboolean_seed_rejected(official_tables):
    official_tables["edges.parquet"] = official_tables["edges.parquet"].iloc[:0]
    with pytest.raises(ValueError, match="не совпадают"):
        load_dataset(zip_bytes(official_tables), "data.zip")
    official_tables["nodes.parquet"]["is_seed"] = [1, 0, 1]
    with pytest.raises(ValueError, match="логические"):
        load_dataset(zip_bytes(official_tables), "data.zip")


def test_node_cap_includes_isolated_nodes(official_tables, monkeypatch):
    monkeypatch.setattr(datasets, "MAX_NODES", 2)
    with pytest.raises(ValueError, match="не более 2"):
        load_dataset(zip_bytes(official_tables), "data.zip")


def test_parquet_row_cap_is_checked_before_loading(official_tables, monkeypatch):
    monkeypatch.setattr(datasets, "MAX_ROWS", 1)
    with pytest.raises(ValueError, match="не более 1 строк"):
        load_dataset(parquet_bytes(official_tables["transactions.parquet"]), "transactions.parquet")


def test_float_ids_rejected_in_parquet(official_tables):
    table = official_tables["transactions.parquet"]
    table["src"] = table.src.astype(float)
    with pytest.raises(ValueError, match="целым"):
        load_dataset(parquet_bytes(table), "transactions.parquet")


@pytest.mark.parametrize("unsafe_name", ["../evil.txt", "/evil.txt", "C:/evil.txt", "data\\..\\evil.txt"])
def test_zip_rejects_unsafe_paths_even_for_ignored_members(official_tables, unsafe_name):
    with pytest.raises(ValueError, match="небезопасный путь"):
        load_dataset(zip_bytes(official_tables, [(unsafe_name, b"ignored")]), "data.zip")


def test_zip_rejects_duplicate_expected_names_in_other_folders(official_tables):
    extra = [("other/TRANSACTIONS.PARQUET", parquet_bytes(official_tables["transactions.parquet"]))]
    with pytest.raises(ValueError, match="повторяющийся файл"):
        load_dataset(zip_bytes(official_tables, extra), "data.zip")


def test_zip_requires_all_three_files(official_tables):
    del official_tables["nodes.parquet"]
    with pytest.raises(ValueError, match="три|содержать"):
        load_dataset(zip_bytes(official_tables), "data.zip")


def test_zip_rejects_symlinks_and_excess_members(official_tables, monkeypatch):
    symlink = zipfile.ZipInfo("link")
    symlink.create_system = 3
    symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(ValueError, match="символические"):
        load_dataset(zip_bytes(official_tables, [(symlink, b"/etc/passwd")]), "data.zip")
    monkeypatch.setattr(datasets, "MAX_ZIP_MEMBERS", 2)
    with pytest.raises(ValueError, match="не более 2"):
        load_dataset(zip_bytes(official_tables), "data.zip")


def test_zip_rejects_compressed_bomb_before_reading(monkeypatch):
    monkeypatch.setattr(datasets, "MAX_BYTES", 5000)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("large.txt", b"A" * 10000)
    assert len(stream.getvalue()) < 5000
    with pytest.raises(ValueError, match="распакованный размер"):
        load_dataset(stream.getvalue(), "data.zip")


@pytest.mark.parametrize("filename", ["broken.zip", "broken.parquet", "dataset.pkl"])
def test_corrupt_and_unsupported_formats_have_russian_errors(filename):
    with pytest.raises(ValueError, match="ZIP|Parquet|Поддерживаются"):
        load_dataset(b"not a valid file", filename)


def test_original_official_fixture_when_available():
    directory = Path(__file__).resolve().parents[2] / "merge-inputs" / "data" / "data"
    if not directory.is_dir():
        pytest.skip("Официальный исходный набор не включён в репозиторий.")
    frame = load_official(directory)
    metadata = frame.attrs["node_metadata"]
    assert len(frame) == 4840
    assert frame.duplicated(subset=["sender", "receiver", "amount", "timestamp"]).sum() == 97
    assert frame.amount.sum() == pytest.approx(365890012.01)
    assert len(frame.groupby(["sender", "receiver"])) == 3119
    assert len(metadata) == 2248
    assert sum(node["is_seed"] for node in metadata.values()) == 81
    assert len(set(metadata) - set(frame.sender) - set(frame.receiver)) == 19
    assert frame.timestamp.min() == pd.Timestamp("2026-07-01", tz="UTC")
    assert frame.timestamp.max() == pd.Timestamp("2026-07-31", tz="UTC")
    assert frame.attrs["time_precision"] == "day"

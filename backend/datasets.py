"""Bounded, non-executing imports for transaction CSV and official Parquet data.

The returned frame has sender, receiver, amount, timestamp (UTC), and id columns.
Dataset context is stored directly in ``frame.attrs``. A day-precision timestamp
is only a date container; callers must not infer intraday ordering from it.
"""

import csv
import io
import math
import re
import stat
import zipfile
import zlib
from datetime import date, datetime
from numbers import Integral, Real
from pathlib import Path, PurePosixPath

import numpy as np
import pandas as pd

MAX_ROWS = 20_000
MAX_NODES = 5_000
MAX_BYTES = 50 * 1024 * 1024
MAX_ZIP_MEMBERS = 100
MAX_COLUMNS = 64
MAX_AMOUNT = 1e15
MIN_AMOUNT = float(np.finfo(float).tiny)
OFFICIAL_FILES = ("transactions.parquet", "edges.parquet", "nodes.parquet")
STANDARD_COLUMNS = ("sender", "receiver", "amount", "timestamp")
OFFICIAL_COLUMNS = ("src", "dst", "sum_kzt", "date")
ID_PATTERN = re.compile(r"[\w.\-:@ ]{1,64}")
DAY_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")
TIME_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d{1,9})?)?"
    r"(?:Z|[+-]\d{2}:?\d{2})?"
)
DAY_WARNING = "В данных есть только дата без точного времени: почасовые показатели и FIFO недоступны."


def _check_size(raw: bytes) -> None:
    if not raw:
        raise ValueError("Файл пуст.")
    if len(raw) > MAX_BYTES:
        raise ValueError("Размер входных данных не должен превышать 50 МБ.")


def _check_columns(frame: pd.DataFrame, required, name: str) -> None:
    if len(frame.columns) > MAX_COLUMNS or not frame.columns.is_unique:
        raise ValueError(f"{name}: слишком много столбцов или повторяющиеся названия.")
    missing = set(required) - set(frame.columns)
    if missing:
        raise ValueError(f"{name}: отсутствуют обязательные столбцы: {', '.join(sorted(missing))}.")


def _identifier(value) -> str:
    # Never route identifiers through a floating-point conversion: it can round
    # large gids and would erase leading zeroes in CSV identifiers.
    if isinstance(value, str):
        result = value.strip()
    elif isinstance(value, Integral) and not isinstance(value, (bool, np.bool_)):
        result = str(value)
    else:
        raise ValueError("Идентификатор счёта должен быть строкой или целым числом; дробные и пустые значения запрещены.")
    if not ID_PATTERN.fullmatch(result):
        raise ValueError("Идентификатор счёта: 1–64 букв, цифр, пробелов или символов . - : @ _.")
    return result


def _identifiers(series: pd.Series, name: str) -> pd.Series:
    result = []
    for position, value in enumerate(series, start=1):
        try:
            result.append(_identifier(value))
        except ValueError as exc:
            raise ValueError(f"{name}, строка {position}: {exc}") from exc
    return pd.Series(result, index=series.index, dtype=object)


def _amounts(series: pd.Series, name: str, maximum=MAX_AMOUNT) -> pd.Series:
    if series.map(lambda value: isinstance(value, (bool, np.bool_))).any():
        raise ValueError(f"{name}: логическое значение не является суммой.")
    amounts = pd.to_numeric(series, errors="coerce").astype(float)
    too_small = (amounts > 0) & (amounts < MIN_AMOUNT)
    if too_small.any():
        position = int(np.flatnonzero(too_small.to_numpy())[0]) + 1
        raise ValueError(f"{name}, строка {position}: сумма слишком мала для устойчивого расчёта; минимум {MIN_AMOUNT:.3g}.")
    valid = np.isfinite(amounts) & (amounts > 0) & (amounts <= maximum)
    if not valid.all():
        position = int(np.flatnonzero(~valid.to_numpy())[0]) + 1
        raise ValueError(f"{name}, строка {position}: сумма должна быть конечным положительным числом не более {maximum:g}.")
    return amounts


def _timestamps(series: pd.Series, official_dates: bool):
    values = []
    date_only = []
    for position, value in enumerate(series, start=1):
        if isinstance(value, (datetime, pd.Timestamp)) and not pd.isna(value):
            text = value.isoformat()
            day = official_dates
            if official_dates and (value.tzinfo is not None or any((value.hour, value.minute, value.second, value.microsecond, getattr(value, "nanosecond", 0)))):
                raise ValueError(f"date, строка {position}: ожидается календарная дата без времени.")
        elif isinstance(value, date):
            text, day = value.isoformat(), True
        elif isinstance(value, str):
            text = value.strip()
            day = bool(DAY_PATTERN.fullmatch(text))
            if not day and (official_dates or not TIME_PATTERN.fullmatch(text)):
                raise ValueError(f"Дата/время, строка {position}: используйте YYYY-MM-DD или ISO 8601 с временем.")
        else:
            raise ValueError(f"Дата/время, строка {position}: пустое или неподдерживаемое значение.")
        values.append(text)
        date_only.append(day)
    timestamps = pd.to_datetime(pd.Series(values, index=series.index), errors="coerce", utc=True, format="mixed")
    if timestamps.isna().any():
        raise ValueError("Некорректная дата или время перевода. Используйте ISO 8601; время без зоны считается UTC.")
    # Even one date-only row prevents reliable ordering within a day.
    precision = "day" if any(date_only) else "timestamp"
    warnings = [DAY_WARNING] if precision == "day" else []
    if any(date_only) and not all(date_only):
        warnings.append("Смешаны даты и точное время; для всего набора применяется точность до дня.")
    return timestamps, precision, warnings


def _normalize(frame: pd.DataFrame, source_kind: str) -> pd.DataFrame:
    if not 1 <= len(frame) <= MAX_ROWS:
        raise ValueError(f"Допустимо от 1 до {MAX_ROWS} транзакций.")
    standard_schema = set(STANDARD_COLUMNS).issubset(frame.columns)
    official_schema = set(OFFICIAL_COLUMNS).issubset(frame.columns)
    if standard_schema and official_schema:
        raise ValueError("Транзакции: неоднозначная схема; оставьте стандартные или официальные столбцы.")
    if not standard_schema and not official_schema:
        expected = OFFICIAL_COLUMNS if set(OFFICIAL_COLUMNS) & set(frame.columns) else STANDARD_COLUMNS
        _check_columns(frame, expected, "Транзакции")
    if standard_schema:
        _check_columns(frame, STANDARD_COLUMNS, "Транзакции")
        frame = frame[list(STANDARD_COLUMNS)].copy()
        official_dates = False
    else:
        _check_columns(frame, OFFICIAL_COLUMNS, "Транзакции")
        frame = frame[list(OFFICIAL_COLUMNS)].rename(columns={"src": "sender", "dst": "receiver", "sum_kzt": "amount", "date": "timestamp"}).copy()
        official_dates = True
    for column in ("sender", "receiver"):
        frame[column] = _identifiers(frame[column], column)
    frame["amount"] = _amounts(frame["amount"], "amount")
    frame["timestamp"], precision, warnings = _timestamps(frame["timestamp"], official_dates)
    if len(set(frame.sender) | set(frame.receiver)) > MAX_NODES:
        raise ValueError(f"Допустимо не более {MAX_NODES} узлов.")
    frame["id"] = [f"tx-{i + 1:06d}" for i in range(len(frame))]
    frame = frame[list(STANDARD_COLUMNS) + ["id"]].sort_values(["timestamp", "id"], kind="stable").reset_index(drop=True)
    if official_dates and source_kind != "official":
        warnings.append("Загружены только транзакции: сведения об исходных клиентах (seed) и изолированных узлах отсутствуют.")
    frame.attrs = {
        "time_precision": precision,
        "currency": "KZT" if official_dates else None,
        "node_metadata": {},
        "source_kind": source_kind,
        "warnings": warnings,
    }
    return frame


def _read_csv(raw: bytes) -> pd.DataFrame:
    try:
        decoded = raw.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(decoded), strict=True)
        header = next(reader)
        if len(header) > MAX_COLUMNS or len(header) != len(set(header)):
            raise ValueError("CSV: слишком много столбцов или повторяющиеся названия.")
        for number, row in enumerate(reader, start=1):
            if number > MAX_ROWS:
                raise ValueError(f"Допустимо от 1 до {MAX_ROWS} транзакций.")
            if len(row) != len(header):
                raise ValueError(f"CSV, строка {number + 1}: число значений не совпадает с заголовком.")
        # Reading a bounded extra row lets validation reject, rather than truncate.
        return pd.read_csv(io.StringIO(decoded), dtype=str, keep_default_na=False, skip_blank_lines=False, nrows=MAX_ROWS + 1)
    except (UnicodeError, pd.errors.ParserError, pd.errors.EmptyDataError, StopIteration, csv.Error) as exc:
        raise ValueError("Не удалось прочитать CSV в UTF-8; проверьте заголовок и число столбцов.") from exc


class _ParquetValidationError(ValueError):
    pass


def _read_parquet(raw: bytes, filename: str, row_limit: int) -> pd.DataFrame:
    _check_size(raw)
    try:
        import pyarrow.parquet as pq

        parquet = pq.ParquetFile(io.BytesIO(raw))
        metadata = parquet.metadata
        if metadata.num_rows > row_limit:
            raise _ParquetValidationError(f"{filename}: допустимо не более {row_limit} строк.")
        if metadata.num_columns > MAX_COLUMNS:
            raise _ParquetValidationError(f"{filename}: слишком много столбцов.")
        unpacked_size = sum(metadata.row_group(i).total_byte_size for i in range(metadata.num_row_groups))
        if unpacked_size > MAX_BYTES:
            raise _ParquetValidationError(f"{filename}: распакованные данные превышают 50 МБ.")
        # All accepted schemas are flat scalar tables, never Python objects.
        import pyarrow as pa

        for field in parquet.schema_arrow:
            if pa.types.is_nested(field.type) or isinstance(field.type, pa.ExtensionType):
                raise _ParquetValidationError(f"{filename}: вложенные и расширенные типы данных не поддерживаются.")
        # Ignore pandas metadata: it may describe custom Python extension types.
        return parquet.read(use_pandas_metadata=False).replace_schema_metadata(None).to_pandas(ignore_metadata=True)
    except ImportError as exc:
        raise ValueError("Для чтения Parquet требуется установленный пакет pyarrow.") from exc
    except _ParquetValidationError:
        raise
    except Exception as exc:
        raise ValueError(f"Не удалось прочитать {filename}: повреждённый или неподдерживаемый Parquet.") from exc


def _integer(value, name: str, minimum: int, maximum: int, nullable=False):
    if nullable and pd.isna(value):
        return None
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real) or not math.isfinite(value) or int(value) != value:
        raise ValueError(f"{name}: ожидается целое число.")
    result = int(value)
    if not minimum <= result <= maximum:
        raise ValueError(f"{name}: значение должно быть от {minimum} до {maximum}.")
    return result


def _validate_official(transactions: pd.DataFrame, edges: pd.DataFrame, nodes: pd.DataFrame) -> pd.DataFrame:
    _check_columns(transactions, OFFICIAL_COLUMNS, "transactions.parquet")
    _check_columns(edges, ("src", "dst", "sum_kzt", "n_tx", "depth"), "edges.parquet")
    _check_columns(nodes, ("gid", "depth", "is_seed"), "nodes.parquet")
    frame = _normalize(transactions, "official")
    if not 1 <= len(nodes) <= MAX_NODES:
        raise ValueError(f"nodes.parquet: допустимо от 1 до {MAX_NODES} узлов.")
    node_ids = _identifiers(nodes.gid, "nodes.gid")
    if node_ids.duplicated().any():
        raise ValueError("nodes.parquet: повторяющиеся идентификаторы узлов.")
    node_metadata = {}
    for gid, depth, seed in zip(node_ids, nodes.depth, nodes.is_seed):
        if not isinstance(seed, (bool, np.bool_)):
            raise ValueError("nodes.is_seed: ожидаются только логические значения True/False.")
        depth = _integer(depth, "nodes.depth", 0, 4, nullable=True)
        if depth is not None and bool(seed) != (depth == 0):
            raise ValueError("nodes.parquet: is_seed не согласован с depth (0 = seed).")
        node_metadata[gid] = {"is_seed": bool(seed), "depth": depth}
    endpoint_ids = set(frame.sender) | set(frame.receiver)
    if not endpoint_ids.issubset(node_metadata):
        raise ValueError("nodes.parquet: отсутствуют узлы, упомянутые в транзакциях.")
    edges = edges.copy()
    for column in ("src", "dst"):
        edges[column] = _identifiers(edges[column], f"edges.{column}")
    if edges.duplicated(["src", "dst"]).any():
        raise ValueError("edges.parquet: повторяющиеся пары src/dst.")
    if not (set(edges.src) | set(edges.dst)).issubset(node_metadata):
        raise ValueError("edges.parquet: конец ребра отсутствует в nodes.parquet.")
    edges["sum_kzt"] = _amounts(edges.sum_kzt, "edges.sum_kzt", MAX_AMOUNT * MAX_ROWS)
    edges["n_tx"] = [_integer(value, "edges.n_tx", 1, MAX_ROWS) for value in edges.n_tx]
    for value in edges.depth:
        _integer(value, "edges.depth", 1, 4)
    aggregated = frame.groupby(["sender", "receiver"], sort=False).amount.agg(["sum", "size"])
    supplied = edges.set_index(["src", "dst"])
    if set(aggregated.index) != set(supplied.index):
        raise ValueError("edges.parquet: пары отправитель/получатель не совпадают с транзакциями.")
    supplied = supplied.reindex(aggregated.index)
    if not np.array_equal(supplied.n_tx.to_numpy(), aggregated["size"].to_numpy()):
        raise ValueError("edges.parquet: n_tx не совпадает с числом транзакций по паре.")
    if not np.isclose(supplied.sum_kzt.to_numpy(), aggregated["sum"].to_numpy(), rtol=1e-12, atol=1e-6).all():
        raise ValueError("edges.parquet: sum_kzt не совпадает с суммой транзакций по паре.")
    frame.attrs["node_metadata"] = node_metadata
    return frame


def _official_payloads(payloads: dict[str, bytes]) -> pd.DataFrame:
    if sum(map(len, payloads.values())) > MAX_BYTES:
        raise ValueError("Общий размер данных превышает 50 МБ.")
    tables = {name: _read_parquet(payloads[name], name, MAX_NODES if name == "nodes.parquet" else MAX_ROWS) for name in OFFICIAL_FILES}
    return _validate_official(tables["transactions.parquet"], tables["edges.parquet"], tables["nodes.parquet"])


def _read_zip(raw: bytes) -> pd.DataFrame:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
            if len(members) > MAX_ZIP_MEMBERS:
                raise ValueError(f"ZIP: допустимо не более {MAX_ZIP_MEMBERS} файлов и каталогов.")
            if sum(member.file_size for member in members) > MAX_BYTES:
                raise ValueError("ZIP: общий распакованный размер превышает 50 МБ.")
            expected = {}
            for member in members:
                name = member.filename
                path = PurePosixPath(name)
                if "\\" in name or "\x00" in name or path.is_absolute() or ".." in path.parts or any(":" in part for part in path.parts):
                    raise ValueError("ZIP: запрещён небезопасный путь к файлу.")
                if stat.S_ISLNK(member.external_attr >> 16):
                    raise ValueError("ZIP: символические ссылки не поддерживаются.")
                if member.flag_bits & 1:
                    raise ValueError("ZIP: зашифрованные файлы не поддерживаются.")
                basename = path.name.lower()
                if basename in OFFICIAL_FILES and not member.is_dir():
                    if basename in expected:
                        raise ValueError(f"ZIP: повторяющийся файл {basename}.")
                    expected[basename] = member
            if set(expected) != set(OFFICIAL_FILES):
                raise ValueError("ZIP должен содержать transactions.parquet, edges.parquet и nodes.parquet.")
            payloads = {}
            for name, member in expected.items():
                with archive.open(member) as stream:
                    payload = stream.read(MAX_BYTES + 1)
                _check_size(payload)
                if len(payload) != member.file_size:
                    raise ValueError(f"ZIP: неверный размер файла {name}.")
                payloads[name] = payload
            return _official_payloads(payloads)
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError, EOFError, OSError, zlib.error) as exc:
        raise ValueError("Не удалось прочитать ZIP: архив повреждён или имеет неподдерживаемый формат.") from exc


def load_dataset(raw: bytes, filename: str) -> pd.DataFrame:
    """Validate an uploaded CSV, transaction Parquet, or official ZIP in memory."""
    _check_size(raw)
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        return _normalize(_read_csv(raw), "csv")
    if suffix == ".parquet":
        return _normalize(_read_parquet(raw, filename, MAX_ROWS), "parquet")
    if suffix == ".zip":
        return _read_zip(raw)
    raise ValueError("Поддерживаются CSV, transactions.parquet и ZIP с тремя официальными Parquet-файлами.")


def load_official(directory: Path) -> pd.DataFrame:
    """Read the three local official tables; retain isolated nodes and seed flags."""
    directory = Path(directory)
    if not (directory / "transactions.parquet").is_file() and (directory / "data").is_dir():
        directory = directory / "data"
    paths = {name: directory / name for name in OFFICIAL_FILES}
    if not all(path.is_file() for path in paths.values()):
        raise ValueError("Каталог должен содержать transactions.parquet, edges.parquet и nodes.parquet.")
    if any(path.is_symlink() for path in paths.values()):
        raise ValueError("Символические ссылки на файлы набора не поддерживаются.")
    try:
        if sum(path.stat().st_size for path in paths.values()) > MAX_BYTES:
            raise ValueError("Общий размер данных превышает 50 МБ.")
        payloads = {}
        for name, path in paths.items():
            with path.open("rb") as stream:
                payloads[name] = stream.read(MAX_BYTES + 1)
        return _official_payloads(payloads)
    except OSError as exc:
        raise ValueError("Не удалось прочитать файлы официального набора.") from exc

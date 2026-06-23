from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from difflib import SequenceMatcher
from html import unescape
from pathlib import Path
from typing import Callable
import io
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
import zipfile

try:
    from PIL import Image
except Exception:  # pragma: no cover - optional runtime dependency.
    Image = None

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover - optional runtime dependency.
    PdfReader = None

logging.getLogger("pypdf").setLevel(logging.ERROR)


APP_NAME = "KD_minha_PET 3.0"
CREATOR = "LEONARDO CARDOSO DE MELO TEIXEIRA MENDES"

MAX_TEXT_BYTES = 1_500_000
MAX_ZIP_BYTES = 18_000_000
MAX_PDF_BYTES = 100_000_000
MAX_PDF_TEXT_PAGES = 120
MAX_PDF_OCR_PAGES = 12
PDF_MIN_TEXT_CHARS_BEFORE_OCR = 120
OCR_MAX_IMAGE_DIMENSION = 2200
WINDOWS_SEARCH_TIMEOUT_SECONDS = 45
WINDOWS_SEARCH_MAX_CANDIDATES = 5000
WINDOWS_SEARCH_CANDIDATE_FACTOR = 10

DOCUMENT_TYPE_ALL_KEY = "all"
DOCUMENT_TYPE_LABELS = {
    DOCUMENT_TYPE_ALL_KEY: "Todos os documentos",
    "contestacao": "Contestação",
    "apelacao": "Apelação",
    "contrarrazoes": "Contrarrazões",
    "agravo_instrumento": "Agravo de instrumento",
}
DOCUMENT_TYPE_CHOICES = tuple(DOCUMENT_TYPE_LABELS.values())

DOCUMENT_TYPE_PATTERNS = {
    "contestacao": ("contestacao",),
    "contrarrazoes": ("contrarrazoes", "contra razoes", "contra razao"),
    "agravo_instrumento": ("agravo de instrumento",),
    "apelacao": ("apelacao",),
}

TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".csv",
    ".tsv",
    ".json",
    ".xml",
    ".html",
    ".htm",
    ".rtf",
    ".py",
    ".ps1",
    ".bat",
    ".cmd",
}
DOCX_EXTENSIONS = {".docx", ".docm"}
XLSX_EXTENSIONS = {".xlsx", ".xlsm"}
PDF_EXTENSIONS = {".pdf"}
READABLE_EXTENSIONS = TEXT_EXTENSIONS | DOCX_EXTENSIONS | XLSX_EXTENSIONS | PDF_EXTENSIONS

TECHNICAL_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "build",
    "dist",
    "dist-py314",
    "build-tools",
}

STOP_WORDS = {
    "a",
    "ache",
    "achar",
    "achei",
    "agora",
    "algum",
    "alguma",
    "ao",
    "aos",
    "arquivo",
    "arquivos",
    "as",
    "buscar",
    "busca",
    "com",
    "como",
    "contem",
    "conter",
    "contendo",
    "contenha",
    "da",
    "das",
    "de",
    "dele",
    "dela",
    "do",
    "dos",
    "e",
    "em",
    "encontre",
    "encontrar",
    "estou",
    "esse",
    "essa",
    "este",
    "esta",
    "eu",
    "express",
    "expressao",
    "expressoes",
    "fazer",
    "localizar",
    "me",
    "meu",
    "minha",
    "na",
    "nas",
    "no",
    "nos",
    "o",
    "os",
    "ou",
    "para",
    "pela",
    "pelo",
    "por",
    "precisa",
    "precisando",
    "preciso",
    "procurar",
    "quero",
    "que",
    "se",
    "sobre",
    "um",
    "uma",
}

TYPE_WORDS = {
    "pdf": {".pdf"},
    "word": {".doc", ".docx", ".docm", ".odt", ".rtf"},
    "doc": {".doc", ".docx", ".docm", ".odt", ".rtf"},
    "docx": {".docx", ".docm"},
    "documento": {".doc", ".docx", ".docm", ".odt", ".rtf", ".pdf", ".txt", ".md"},
    "documentos": {".doc", ".docx", ".docm", ".odt", ".rtf", ".pdf", ".txt", ".md"},
    "planilha": {".xls", ".xlsx", ".xlsm", ".csv", ".ods"},
    "planilhas": {".xls", ".xlsx", ".xlsm", ".csv", ".ods"},
    "excel": {".xls", ".xlsx", ".xlsm", ".csv"},
    "xls": {".xls", ".xlsx", ".xlsm"},
    "xlsx": {".xlsx", ".xlsm"},
    "imagem": {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"},
    "imagens": {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"},
    "foto": {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"},
    "fotos": {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"},
    "texto": {".txt", ".md", ".rtf", ".csv"},
    "txt": {".txt"},
}

MONTHS = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}


@dataclass(frozen=True)
class SearchIntent:
    original_query: str
    normalized_query: str
    terms: tuple[str, ...]
    extensions: frozenset[str]
    quoted_phrases: tuple[str, ...] = ()
    date_from: datetime | None = None
    date_to: datetime | None = None
    document_type: str = DOCUMENT_TYPE_ALL_KEY


@dataclass(frozen=True)
class SearchResult:
    path: str
    name: str
    extension: str
    score: float
    modified: float
    size: int
    reason: str
    snippet: str
    document_type: str = ""


@dataclass(frozen=True)
class SearchResponse:
    results: list[SearchResult]
    scanned: int
    skipped: int
    stopped: bool
    intent: SearchIntent
    total_matches: int = 0
    backend: str = "Aplicativo"
    messages: tuple[str, ...] = ()


ProgressCallback = Callable[[int, int, str], None]
LogCallback = Callable[[str], None]


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFD", value or "")
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = value.casefold()
    value = re.sub(r"[_\-./\\:;,+()\[\]{}]+", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def coerce_document_type_key(value: str | None) -> str:
    if not value:
        return DOCUMENT_TYPE_ALL_KEY

    raw = value.strip()
    if raw in DOCUMENT_TYPE_LABELS:
        return raw

    normalized = normalize_text(raw)
    for key, label in DOCUMENT_TYPE_LABELS.items():
        if normalized == normalize_text(label):
            return key

    compact = normalized.replace(" ", "")
    if compact.startswith("todos"):
        return DOCUMENT_TYPE_ALL_KEY
    if compact.startswith("contesta"):
        return "contestacao"
    if compact.startswith("apela"):
        return "apelacao"
    if compact.startswith("contrar") or compact.startswith("contra"):
        return "contrarrazoes"
    if compact.startswith("agravo") or "agravodeinstrumento" in compact:
        return "agravo_instrumento"
    return DOCUMENT_TYPE_ALL_KEY


def _apply_explicit_filters(
    intent: SearchIntent,
    *,
    year_start: int | None = None,
    year_end: int | None = None,
    document_type: str | None = None,
) -> SearchIntent:
    explicit_from, explicit_to = _year_range_to_dates(year_start, year_end)

    date_from = intent.date_from
    if explicit_from is not None:
        date_from = max(dt for dt in (date_from, explicit_from) if dt is not None)

    date_to = intent.date_to
    if explicit_to is not None:
        date_to = min(dt for dt in (date_to, explicit_to) if dt is not None)

    return replace(
        intent,
        date_from=date_from,
        date_to=date_to,
        document_type=coerce_document_type_key(document_type),
    )


def _year_range_to_dates(
    year_start: int | None,
    year_end: int | None,
) -> tuple[datetime | None, datetime | None]:
    if year_start is None and year_end is None:
        return None, None
    if year_start is not None and year_end is not None and year_start > year_end:
        raise ValueError("Ano inicial nao pode ser maior que o ano final.")

    start = datetime(year_start, 1, 1) if year_start is not None else None
    end = datetime(year_end + 1, 1, 1) if year_end is not None else None
    return start, end


def parse_query(query: str) -> SearchIntent:
    normalized = normalize_text(query)
    tokens = normalized.split()
    quoted_phrases = _extract_quoted_phrases(query)

    extensions: set[str] = set()
    type_tokens: set[str] = set()
    for token in tokens:
        mapped = TYPE_WORDS.get(token)
        if mapped:
            extensions.update(mapped)
            type_tokens.add(token)

    date_from, date_to, date_tokens = _parse_date_filters(normalized)
    ignored = STOP_WORDS | type_tokens | date_tokens
    terms = tuple(
        token for token in tokens if token not in ignored and (len(token) > 1 or token.isdigit())
    )

    return SearchIntent(
        original_query=query.strip(),
        normalized_query=normalized,
        terms=terms,
        quoted_phrases=quoted_phrases,
        extensions=frozenset(extensions),
        date_from=date_from,
        date_to=date_to,
    )


def _extract_quoted_phrases(query: str) -> tuple[str, ...]:
    phrases: list[str] = []
    for match in re.finditer(r'"([^"]+)"|“([^”]+)”|‘([^’]+)’', query or ""):
        raw = next((group for group in match.groups() if group), "")
        phrase = normalize_text(raw)
        phrase_terms = [token for token in phrase.split() if token not in STOP_WORDS]
        if len(phrase_terms) >= 2:
            phrases.append(" ".join(phrase_terms))
    return tuple(_dedupe(phrases))


def smart_search(
    query: str,
    root: str | Path,
    *,
    include_content: bool = True,
    pdf_ocr: bool = True,
    skip_technical_dirs: bool = True,
    max_results: int = 500,
    year_start: int | None = None,
    year_end: int | None = None,
    document_type: str | None = None,
    use_windows_search: bool = False,
    progress: ProgressCallback | None = None,
    log: LogCallback | None = None,
    stop_event=None,
) -> SearchResponse:
    root_path = Path(root).expanduser().resolve()
    intent = _apply_explicit_filters(
        parse_query(query),
        year_start=year_start,
        year_end=year_end,
        document_type=document_type,
    )

    if use_windows_search and os.name == "nt":
        try:
            return _smart_search_windows_index(
                intent,
                root_path,
                include_content=include_content,
                pdf_ocr=pdf_ocr,
                skip_technical_dirs=skip_technical_dirs,
                max_results=max_results,
                progress=progress,
                log=log,
                stop_event=stop_event,
            )
        except RuntimeError as exc:
            message = f"Windows Search indisponivel; usando busca interna. Motivo: {exc}"
            if log:
                log(message)
            return _smart_search_local(
                intent,
                root_path,
                include_content=include_content,
                pdf_ocr=pdf_ocr,
                skip_technical_dirs=skip_technical_dirs,
                max_results=max_results,
                progress=progress,
                stop_event=stop_event,
                messages=(message,),
            )

    return _smart_search_local(
        intent,
        root_path,
        include_content=include_content,
        pdf_ocr=pdf_ocr,
        skip_technical_dirs=skip_technical_dirs,
        max_results=max_results,
        progress=progress,
        stop_event=stop_event,
    )


def _smart_search_local(
    intent: SearchIntent,
    root_path: Path,
    *,
    include_content: bool,
    pdf_ocr: bool,
    skip_technical_dirs: bool,
    max_results: int,
    progress: ProgressCallback | None,
    stop_event=None,
    messages: tuple[str, ...] = (),
) -> SearchResponse:
    results: list[SearchResult] = []
    scanned = 0
    skipped = 0
    stopped = False

    def on_walk_error(_error: OSError) -> None:
        nonlocal skipped
        skipped += 1

    for dirpath, dirnames, filenames in os.walk(root_path, topdown=True, onerror=on_walk_error):
        if stop_event is not None and stop_event.is_set():
            stopped = True
            break

        if skip_technical_dirs:
            dirnames[:] = [
                dirname for dirname in dirnames if dirname.casefold() not in TECHNICAL_DIRS
            ]

        for filename in filenames:
            if stop_event is not None and stop_event.is_set():
                stopped = True
                break

            path = Path(dirpath) / filename
            scanned += 1

            try:
                stat = path.stat()
            except OSError:
                skipped += 1
                continue

            result = _evaluate_path_candidate(
                path,
                root_path,
                stat.st_mtime,
                stat.st_size,
                intent,
                include_content=include_content,
                pdf_ocr=pdf_ocr,
                skip_technical_dirs=False,
            )
            if result is not None:
                results.append(result)

            if progress and scanned % 75 == 0:
                progress(scanned, len(results), str(path))

    return _response_from_results(
        results,
        scanned=scanned,
        skipped=skipped,
        stopped=stopped,
        intent=intent,
        max_results=max_results,
        progress=progress,
        backend="Aplicativo",
        messages=messages,
    )


def _smart_search_windows_index(
    intent: SearchIntent,
    root_path: Path,
    *,
    include_content: bool,
    pdf_ocr: bool,
    skip_technical_dirs: bool,
    max_results: int,
    progress: ProgressCallback | None,
    log: LogCallback | None,
    stop_event=None,
) -> SearchResponse:
    max_candidates = min(
        max(max_results * WINDOWS_SEARCH_CANDIDATE_FACTOR, max_results, 100),
        WINDOWS_SEARCH_MAX_CANDIDATES,
    )
    paths = _windows_search_paths(intent, root_path, max_candidates=max_candidates)
    if log:
        log(f"Windows Search retornou {len(paths)} candidatos indexados.")
    if not paths:
        raise RuntimeError("nenhum candidato indexado retornado para esta busca")

    results: list[SearchResult] = []
    scanned = 0
    skipped = 0
    stopped = False
    seen: set[Path] = set()

    for path in paths:
        if stop_event is not None and stop_event.is_set():
            stopped = True
            break

        try:
            resolved = Path(path).expanduser().resolve()
        except OSError:
            skipped += 1
            continue

        if resolved in seen:
            continue
        seen.add(resolved)
        scanned += 1

        try:
            stat = resolved.stat()
        except OSError:
            skipped += 1
            continue

        result = _evaluate_path_candidate(
            resolved,
            root_path,
            stat.st_mtime,
            stat.st_size,
            intent,
            include_content=include_content,
            pdf_ocr=pdf_ocr,
            skip_technical_dirs=skip_technical_dirs,
        )
        if result is not None:
            results.append(result)

        if progress and scanned % 25 == 0:
            progress(scanned, len(results), str(resolved))

    return _response_from_results(
        results,
        scanned=scanned,
        skipped=skipped,
        stopped=stopped,
        intent=intent,
        max_results=max_results,
        progress=progress,
        backend="Windows Search",
    )


def _response_from_results(
    results: list[SearchResult],
    *,
    scanned: int,
    skipped: int,
    stopped: bool,
    intent: SearchIntent,
    max_results: int,
    progress: ProgressCallback | None,
    backend: str,
    messages: tuple[str, ...] = (),
) -> SearchResponse:
    results.sort(key=lambda item: (-item.score, -item.modified, item.name.casefold()))
    total_matches = len(results)
    if max_results and len(results) > max_results:
        results = results[:max_results]

    if progress:
        progress(scanned, total_matches, "")

    return SearchResponse(
        results=results,
        scanned=scanned,
        skipped=skipped,
        stopped=stopped,
        intent=intent,
        total_matches=total_matches,
        backend=backend,
        messages=messages,
    )


def _evaluate_path_candidate(
    path: Path,
    root_path: Path,
    modified: float,
    size: int,
    intent: SearchIntent,
    *,
    include_content: bool,
    pdf_ocr: bool,
    skip_technical_dirs: bool,
) -> SearchResult | None:
    try:
        path.relative_to(root_path)
    except ValueError:
        return None

    if skip_technical_dirs and _is_in_technical_dir(path, root_path):
        return None

    if not _passes_filters(path, modified, intent):
        return None

    document_type_label = ""
    if intent.document_type != DOCUMENT_TYPE_ALL_KEY:
        detected_key, detected_label = detect_document_type(path, size, pdf_ocr=pdf_ocr)
        if detected_key != intent.document_type:
            return None
        document_type_label = detected_label

    result = _evaluate_candidate(path, root_path, modified, size, intent)

    if include_content and _should_read_content(path, size, intent, result.score):
        content = extract_text(path, size, pdf_ocr=pdf_ocr)
        if content:
            result = _evaluate_candidate(path, root_path, modified, size, intent, content)

    if result.score <= 0:
        return None

    if document_type_label:
        result = replace(result, document_type=document_type_label)
    return result


def _is_in_technical_dir(path: Path, root_path: Path) -> bool:
    try:
        parts = path.relative_to(root_path).parts[:-1]
    except ValueError:
        parts = path.parts[:-1]
    return any(part.casefold() in TECHNICAL_DIRS for part in parts)


def _windows_search_paths(
    intent: SearchIntent,
    root_path: Path,
    *,
    max_candidates: int,
) -> list[str]:
    if not intent.original_query.strip():
        return []

    scope = "file:" + root_path.as_posix().rstrip("/")
    payload = {
        "scope": scope,
        "query": intent.original_query,
        "terms": list(intent.terms),
        "max_candidates": max_candidates,
    }

    script = r"""
$ErrorActionPreference = 'Stop'
$payloadText = [Console]::In.ReadToEnd()
$payload = $payloadText | ConvertFrom-Json

function Escape-SqlLiteral([string]$Value) {
    if ($null -eq $Value) { return "" }
    return $Value.Replace("'", "''")
}

function Escape-LikeLiteral([string]$Value) {
    if ($null -eq $Value) { return "" }
    return $Value.Replace("'", "''").Replace("[", "[[]").Replace("%", "[%]").Replace("_", "[_]")
}

$scope = Escape-SqlLiteral ([string]$payload.scope)
$query = Escape-SqlLiteral ([string]$payload.query)
$max = [int]$payload.max_candidates
if ($max -lt 1) { $max = 100 }

$where = New-Object System.Collections.Generic.List[string]
[void]$where.Add("SCOPE='$scope'")

if (-not [string]::IsNullOrWhiteSpace($query)) {
    $searchParts = New-Object System.Collections.Generic.List[string]
    [void]$searchParts.Add("FREETEXT(*, '$query')")

    $nameParts = New-Object System.Collections.Generic.List[string]
    foreach ($term in @($payload.terms)) {
        $termText = Escape-LikeLiteral ([string]$term)
        if (-not [string]::IsNullOrWhiteSpace($termText)) {
            [void]$nameParts.Add("System.ItemNameDisplay LIKE '%$termText%'")
        }
    }

    if ($nameParts.Count -gt 0) {
        [void]$searchParts.Add("(" + ($nameParts -join " AND ") + ")")
    }

    [void]$where.Add("(" + ($searchParts -join " OR ") + ")")
}

$sql = "SELECT TOP $max System.ItemPathDisplay, System.Search.Rank FROM SystemIndex WHERE " +
    ($where -join " AND ") + " ORDER BY System.Search.Rank DESC"

$connection = $null
$recordset = $null
try {
    $connection = New-Object -ComObject ADODB.Connection
    $connection.Open("Provider=Search.CollatorDSO;Extended Properties='Application=Windows';")
    $command = New-Object -ComObject ADODB.Command
    $command.ActiveConnection = $connection
    $command.CommandText = $sql
    $recordset = $command.Execute()

    $rows = New-Object System.Collections.Generic.List[string]
    while (-not $recordset.EOF) {
        $value = $recordset.Fields.Item("System.ItemPathDisplay").Value
        if ($null -ne $value -and -not [string]::IsNullOrWhiteSpace([string]$value)) {
            [void]$rows.Add([string]$value)
        }
        $recordset.MoveNext()
    }

    ConvertTo-Json -InputObject $rows -Compress
}
finally {
    if ($null -ne $recordset) { $recordset.Close() }
    if ($null -ne $connection) { $connection.Close() }
}
"""

    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        script,
    ]
    try:
        completed = subprocess.run(
            command,
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=WINDOWS_SEARCH_TIMEOUT_SECONDS,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(str(exc)) from exc

    if completed.returncode != 0:
        stderr = _compact_text(completed.stderr or completed.stdout)
        raise RuntimeError(stderr or f"codigo de saida {completed.returncode}")

    try:
        payload_out = json.loads(completed.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError("resposta invalida do Windows Search") from exc

    if isinstance(payload_out, str):
        return [payload_out]
    if isinstance(payload_out, list):
        return [str(item) for item in payload_out if item]
    return []


def extract_text(path: Path, file_size: int | None = None, *, pdf_ocr: bool = True) -> str:
    suffix = path.suffix.casefold()
    try:
        if suffix in DOCX_EXTENSIONS:
            return _extract_docx_text(path, file_size)
        if suffix in XLSX_EXTENSIONS:
            return _extract_xlsx_text(path, file_size)
        if suffix in PDF_EXTENSIONS:
            return _extract_pdf_text(path, file_size, use_ocr=pdf_ocr)
        if suffix in TEXT_EXTENSIONS:
            return _extract_plain_text(path, file_size)
    except (OSError, UnicodeError, zipfile.BadZipFile, RuntimeError):
        return ""
    return ""


def extract_document_lead_text(
    path: Path,
    file_size: int | None = None,
    *,
    pdf_ocr: bool = True,
) -> str:
    suffix = path.suffix.casefold()
    try:
        if suffix in PDF_EXTENSIONS:
            return _extract_pdf_first_page_text(path, file_size, use_ocr=pdf_ocr)
        if suffix in DOCX_EXTENSIONS:
            return _extract_docx_text(path, file_size)[:12_000]
        if suffix in TEXT_EXTENSIONS:
            return _extract_plain_text(path, file_size)[:12_000]
        if suffix in XLSX_EXTENSIONS:
            return _extract_xlsx_text(path, file_size)[:12_000]
    except (OSError, UnicodeError, zipfile.BadZipFile, RuntimeError):
        return ""
    return ""


def detect_document_type(
    path: Path,
    file_size: int | None = None,
    *,
    pdf_ocr: bool = True,
) -> tuple[str, str]:
    text = extract_document_lead_text(path, file_size, pdf_ocr=pdf_ocr)
    normalized = normalize_text(text[:12_000])
    if not normalized:
        return DOCUMENT_TYPE_ALL_KEY, ""

    matches: list[tuple[int, int, str]] = []
    priority = {
        "contrarrazoes": 0,
        "agravo_instrumento": 1,
        "contestacao": 2,
        "apelacao": 3,
    }
    for key, patterns in DOCUMENT_TYPE_PATTERNS.items():
        for pattern in patterns:
            index = normalized.find(pattern)
            if index >= 0:
                matches.append((index, priority.get(key, 99), key))
                break

    if not matches:
        return DOCUMENT_TYPE_ALL_KEY, ""

    _, _, key = min(matches)
    return key, DOCUMENT_TYPE_LABELS[key]


def _parse_date_filters(normalized: str) -> tuple[datetime | None, datetime | None, set[str]]:
    today = date.today()
    start_today = datetime.combine(today, time.min)
    tomorrow = start_today + timedelta(days=1)
    tokens_to_ignore: set[str] = set()

    if "hoje" in normalized.split():
        return start_today, tomorrow, {"hoje"}

    if "ontem" in normalized.split():
        yesterday = start_today - timedelta(days=1)
        return yesterday, start_today, {"ontem"}

    match = re.search(r"ultim[oa]s?\s+(\d{1,3})\s+dias", normalized)
    if match:
        days = min(max(int(match.group(1)), 1), 3650)
        return start_today - timedelta(days=days), tomorrow, {"ultimos", "ultimas", "dias"}

    if "semana passada" in normalized:
        this_monday = start_today - timedelta(days=today.weekday())
        return this_monday - timedelta(days=7), this_monday, {"semana", "passada"}

    if "esta semana" in normalized or "semana atual" in normalized:
        this_monday = start_today - timedelta(days=today.weekday())
        return this_monday, tomorrow, {"esta", "semana", "atual"}

    if "mes passado" in normalized:
        first_this_month = start_today.replace(day=1)
        last_month_end = first_this_month
        last_month_start = (first_this_month - timedelta(days=1)).replace(day=1)
        return last_month_start, last_month_end, {"mes", "passado"}

    if "este mes" in normalized or "mes atual" in normalized:
        return start_today.replace(day=1), tomorrow, {"este", "mes", "atual"}

    for month_name, month_number in MONTHS.items():
        if month_name not in normalized.split():
            continue
        year_match = re.search(rf"{month_name}\s+(?:de\s+)?(\d{{4}})", normalized)
        year = int(year_match.group(1)) if year_match else today.year
        start = datetime(year, month_number, 1)
        if month_number == 12:
            end = datetime(year + 1, 1, 1)
        else:
            end = datetime(year, month_number + 1, 1)
        return start, end, {month_name, "de", str(year)}

    return None, None, tokens_to_ignore


def _passes_filters(path: Path, modified: float, intent: SearchIntent) -> bool:
    suffix = path.suffix.casefold()
    if intent.extensions and suffix not in intent.extensions:
        return False

    if intent.date_from or intent.date_to:
        modified_at = datetime.fromtimestamp(modified)
        if intent.date_from and modified_at < intent.date_from:
            return False
        if intent.date_to and modified_at >= intent.date_to:
            return False

    return True


def _evaluate_candidate(
    path: Path,
    root: Path,
    modified: float,
    size: int,
    intent: SearchIntent,
    content: str = "",
) -> SearchResult:
    name = path.name
    extension = path.suffix.casefold()

    try:
        relative_path = str(path.relative_to(root))
    except ValueError:
        relative_path = str(path)

    name_norm = normalize_text(name)
    stem_words = normalize_text(path.stem).split()
    path_norm = normalize_text(relative_path)
    content_norm = normalize_text(content[:120_000]) if content else ""

    score = 0.0
    matched_terms: set[str] = set()
    reasons: list[str] = []
    phrase_matched = False

    if intent.extensions:
        score += 12
        reasons.append("tipo de arquivo")

    if intent.date_from or intent.date_to:
        score += 8
        reasons.append("data")

    if intent.document_type != DOCUMENT_TYPE_ALL_KEY:
        score += 10
        reasons.append("tipo de documento")

    if not intent.terms:
        if intent.extensions or intent.date_from or intent.date_to or intent.document_type != DOCUMENT_TYPE_ALL_KEY:
            snippet = _fallback_snippet(relative_path, content)
            return SearchResult(
                path=str(path),
                name=name,
                extension=extension,
                score=score or 1,
                modified=modified,
                size=size,
                reason=", ".join(reasons) or "filtro",
                snippet=snippet,
            )
        return _empty_result(path, modified, size)

    for quoted_phrase in intent.quoted_phrases:
        phrase_terms = _phrase_terms(quoted_phrase)
        if not phrase_terms:
            continue

        if quoted_phrase in name_norm:
            score += 150
            matched_terms.update(phrase_terms)
            reasons.append("expressao entre aspas no nome")
            phrase_matched = True
            continue

        if quoted_phrase in path_norm:
            score += 130
            matched_terms.update(phrase_terms)
            reasons.append("expressao entre aspas no caminho")
            phrase_matched = True
            continue

        if content_norm and quoted_phrase in content_norm:
            score += 170
            matched_terms.update(phrase_terms)
            reasons.append("expressao entre aspas no conteudo")
            phrase_matched = True
            continue

        if content_norm and _ordered_terms_are_near(content_norm, phrase_terms):
            score += 135
            matched_terms.update(phrase_terms)
            reasons.append("termos da expressao entre aspas proximos no conteudo")
            phrase_matched = True

    phrase = " ".join(intent.terms)
    if phrase and phrase in name_norm:
        score += 44
        reasons.append("frase no nome")
    elif phrase and phrase in path_norm:
        score += 24
        reasons.append("frase no caminho")
    elif phrase and content_norm and phrase in content_norm:
        score += 20
        reasons.append("frase no conteudo")

    for term in intent.terms:
        if term in name_norm:
            score += 24
            matched_terms.add(term)
            reasons.append(f"nome: {term}")
            continue

        if term in path_norm:
            score += 11
            matched_terms.add(term)
            reasons.append(f"pasta: {term}")
            continue

        if _fuzzy_word_match(term, stem_words):
            score += 10
            matched_terms.add(term)
            reasons.append(f"nome parecido: {term}")
            continue

        if content_norm and term in content_norm:
            score += 13
            matched_terms.add(term)
            reasons.append(f"conteudo: {term}")

    coverage = len(matched_terms) / max(len(intent.terms), 1)
    if coverage == 0 and not phrase_matched:
        return _empty_result(path, modified, size)

    if coverage < 0.5 and score < 32 and not phrase_matched:
        return _empty_result(path, modified, size)

    score += coverage * 22
    if coverage == 1:
        score += 16

    score += _recency_bonus(modified)
    snippet = _best_snippet(content, intent.terms) if content else _fallback_snippet(relative_path, "")

    return SearchResult(
        path=str(path),
        name=name,
        extension=extension,
        score=round(score, 2),
        modified=modified,
        size=size,
        reason=", ".join(_dedupe(reasons)) or "correspondencia",
        snippet=snippet,
    )


def _empty_result(path: Path, modified: float, size: int) -> SearchResult:
    return SearchResult(
        path=str(path),
        name=path.name,
        extension=path.suffix.casefold(),
        score=0,
        modified=modified,
        size=size,
        reason="",
        snippet="",
    )


def _should_read_content(path: Path, file_size: int, intent: SearchIntent, current_score: float) -> bool:
    suffix = path.suffix.casefold()
    if suffix not in READABLE_EXTENSIONS:
        return False
    if suffix in TEXT_EXTENSIONS and file_size > MAX_TEXT_BYTES:
        return False
    if suffix in (DOCX_EXTENSIONS | XLSX_EXTENSIONS) and file_size > MAX_ZIP_BYTES:
        return False
    if suffix in PDF_EXTENSIONS and file_size > MAX_PDF_BYTES:
        return False
    return bool(intent.terms) and current_score < 95


def _extract_plain_text(path: Path, file_size: int | None = None) -> str:
    limit = min(file_size or MAX_TEXT_BYTES, MAX_TEXT_BYTES)
    data = path.read_bytes()[:limit]
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        return ""

    if path.suffix.casefold() == ".rtf":
        text = _strip_rtf(text)
    return _compact_text(text)


def _extract_docx_text(path: Path, file_size: int | None = None) -> str:
    if file_size and file_size > MAX_ZIP_BYTES:
        return ""
    pieces: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.startswith("word/") or not name.endswith(".xml"):
                continue
            if not (
                name.endswith("document.xml")
                or "header" in name
                or "footer" in name
                or "footnotes" in name
                or "endnotes" in name
            ):
                continue
            raw = archive.read(name).decode("utf-8", errors="ignore")
            raw = re.sub(r"</w:p>", "\n", raw)
            raw = re.sub(r"<[^>]+>", " ", raw)
            pieces.append(unescape(raw))
    return _compact_text("\n".join(pieces))


def _extract_xlsx_text(path: Path, file_size: int | None = None) -> str:
    if file_size and file_size > MAX_ZIP_BYTES:
        return ""
    pieces: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if name == "xl/sharedStrings.xml" or (
                name.startswith("xl/worksheets/") and name.endswith(".xml")
            ):
                raw = archive.read(name).decode("utf-8", errors="ignore")
                raw = re.sub(r"<[^>]+>", " ", raw)
                pieces.append(unescape(raw))
    return _compact_text("\n".join(pieces))


def _extract_pdf_text(path: Path, file_size: int | None = None, *, use_ocr: bool = True) -> str:
    if file_size and file_size > MAX_PDF_BYTES:
        return ""
    if PdfReader is None:
        return ""

    try:
        reader = PdfReader(str(path), strict=False)
    except Exception:
        return ""

    pieces: list[str] = []
    pages = list(reader.pages[:MAX_PDF_TEXT_PAGES])
    for page in pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text:
            pieces.append(text)

    extracted_text = _compact_text("\n".join(pieces))
    if not use_ocr or len(normalize_text(extracted_text)) >= PDF_MIN_TEXT_CHARS_BEFORE_OCR:
        return extracted_text

    ocr_text = _ocr_pdf_images(reader)
    return _compact_text("\n".join(part for part in (extracted_text, ocr_text) if part))


def _extract_pdf_first_page_text(
    path: Path,
    file_size: int | None = None,
    *,
    use_ocr: bool = True,
) -> str:
    if file_size and file_size > MAX_PDF_BYTES:
        return ""
    if PdfReader is None:
        return ""

    try:
        reader = PdfReader(str(path), strict=False)
    except Exception:
        return ""

    if not reader.pages:
        return ""

    try:
        extracted_text = _compact_text(reader.pages[0].extract_text() or "")
    except Exception:
        extracted_text = ""

    if not use_ocr or len(normalize_text(extracted_text)) >= PDF_MIN_TEXT_CHARS_BEFORE_OCR:
        return extracted_text

    ocr_text = _ocr_pdf_images(reader, max_pages=1)
    return _compact_text("\n".join(part for part in (extracted_text, ocr_text) if part))


def _ocr_pdf_images(reader, *, max_pages: int = MAX_PDF_OCR_PAGES) -> str:
    if Image is None:
        return ""

    image_paths: list[Path] = []
    with tempfile.TemporaryDirectory(prefix="kd_minha_pet_ocr_") as temp_dir:
        temp_path = Path(temp_dir)
        for page_index, page in enumerate(reader.pages[:max_pages], start=1):
            try:
                images = list(page.images)
            except Exception:
                images = []

            for image_index, image_file in enumerate(images, start=1):
                data = getattr(image_file, "data", b"") or b""
                if not data:
                    continue

                output_path = temp_path / f"page_{page_index:03d}_image_{image_index:03d}.png"
                if _save_pdf_image_for_ocr(data, output_path):
                    image_paths.append(output_path)

        if not image_paths:
            return ""

        return _run_windows_ocr(image_paths)


def _save_pdf_image_for_ocr(data: bytes, output_path: Path) -> bool:
    if Image is None:
        return False
    try:
        with Image.open(io.BytesIO(data)) as image:
            image = image.convert("RGB")
            width, height = image.size
            longest_side = max(width, height)
            if longest_side > OCR_MAX_IMAGE_DIMENSION:
                scale = OCR_MAX_IMAGE_DIMENSION / longest_side
                new_size = (max(int(width * scale), 1), max(int(height * scale), 1))
                image = image.resize(new_size)
            image.save(output_path, "PNG")
        return True
    except Exception:
        return False


def _run_windows_ocr(image_paths: list[Path]) -> str:
    script = _resource_path("tools/ocr_windows.ps1")
    if not script.exists():
        return ""

    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-ImagePath",
        *[str(path) for path in image_paths],
    ]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""

    if completed.returncode != 0 or not completed.stdout.strip():
        return ""

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return ""

    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return ""

    texts = [str(item.get("text", "")) for item in payload if isinstance(item, dict)]
    return _compact_text("\n".join(text for text in texts if text))


def _resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative


def _strip_rtf(text: str) -> str:
    text = re.sub(r"\\'[0-9a-fA-F]{2}", " ", text)
    text = re.sub(r"\\[a-zA-Z]+\d* ?", " ", text)
    text = text.replace("{", " ").replace("}", " ")
    return text


def _compact_text(text: str) -> str:
    text = text.replace("\x00", " ")
    return re.sub(r"\s+", " ", text).strip()


def _phrase_terms(phrase: str) -> list[str]:
    return [
        term
        for term in phrase.split()
        if term not in STOP_WORDS and (len(term) > 1 or term.isdigit())
    ]


def _ordered_terms_are_near(content_norm: str, terms: list[str]) -> bool:
    if len(terms) < 2:
        return False

    max_words = max(len(terms) + 12, len(terms) * 4)
    start = content_norm.find(terms[0])
    attempts = 0
    while start >= 0 and attempts < 250:
        attempts += 1
        search_from = start + len(terms[0])
        last_end = search_from

        for term in terms[1:]:
            index = content_norm.find(term, search_from)
            if index < 0:
                return False
            last_end = index + len(term)
            search_from = last_end

        window = content_norm[start:last_end]
        if len(window.split()) <= max_words:
            return True

        start = content_norm.find(terms[0], start + 1)

    return False


def _fuzzy_word_match(term: str, words: list[str]) -> bool:
    if len(term) < 4:
        return False
    for word in words:
        if len(word) < 4:
            continue
        ratio = SequenceMatcher(None, term, word).ratio()
        if ratio >= 0.84:
            return True
    return False


def _recency_bonus(modified: float) -> float:
    age_days = max((datetime.now() - datetime.fromtimestamp(modified)).days, 0)
    if age_days <= 7:
        return 5
    if age_days <= 30:
        return 3
    if age_days <= 180:
        return 1
    return 0


def _best_snippet(content: str, terms: tuple[str, ...]) -> str:
    if not content:
        return ""
    normalized = normalize_text(content)
    index = -1
    for term in terms:
        index = normalized.find(term)
        if index >= 0:
            break
    if index < 0:
        return _compact_text(content[:240])

    start = max(index - 90, 0)
    end = min(index + 260, len(content))
    prefix = "... " if start else ""
    suffix = " ..." if end < len(content) else ""
    return prefix + _compact_text(content[start:end]) + suffix


def _fallback_snippet(relative_path: str, content: str) -> str:
    if content:
        return _compact_text(content[:240])
    return f"Caminho: {relative_path}"


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output[:8]


def human_size(size: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024

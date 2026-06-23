from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

from search_engine import (
    SearchResponse,
    SearchResult,
    human_size,
    smart_search,
)


LM_STUDIO_IDENTIFIER = "kd-minha-pet-ai"
LM_STUDIO_PORT = 1234
LM_STUDIO_BASE_URL = f"http://127.0.0.1:{LM_STUDIO_PORT}/v1"
LM_STUDIO_API_KEY = "lm-studio"
MAX_AI_CANDIDATES = 24
MAX_AI_SEARCH_CANDIDATES = 120

LogCallback = Callable[[str], None]
ProgressCallback = Callable[[int, int, str], None]


class LMStudioError(RuntimeError):
    pass


@dataclass(frozen=True)
class LMStudioSession:
    model_identifier: str
    model_key: str
    display_name: str
    base_url: str = LM_STUDIO_BASE_URL


def prepare_lm_studio(log: LogCallback | None = None) -> LMStudioSession:
    lms_path = find_lms_executable()
    if lms_path is None:
        raise LMStudioError("Nao encontrei o lms.exe do LM Studio.")

    app_path = find_lm_studio_app()
    if app_path is not None:
        _log(log, f"Abrindo LM Studio: {app_path}")
        try:
            subprocess.Popen(
                [str(app_path)],
                cwd=str(app_path.parent),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            _log(log, f"Nao foi possivel abrir a interface do LM Studio: {exc}")
    else:
        _log(log, "Interface do LM Studio nao encontrada; usando a CLI lms.")

    _ensure_server(lms_path, log=log)
    loaded = _loaded_models(lms_path, log=log)
    if loaded:
        session = _session_from_loaded_model(loaded[0])
        api_model = _resolve_api_model_identifier(session.model_identifier)
        if api_model != session.model_identifier:
            session = replace(session, model_identifier=api_model)
        _log(log, f"Modelo ja carregado no LM Studio: {session.display_name}")
        return session

    models = _local_models(lms_path, log=log)
    if not models:
        raise LMStudioError("Nao ha modelos locais disponiveis no LM Studio.")

    selected = _select_last_used_model(models)
    model_key = str(selected.get("modelKey") or selected.get("selectedVariant") or "").strip()
    display_name = str(selected.get("displayName") or model_key).strip()
    if not model_key:
        raise LMStudioError("Nao foi possivel identificar o modelo local a carregar.")

    _log(log, f"Selecionando ultimo modelo do LM Studio: {display_name} ({model_key})")
    _run_lms(
        lms_path,
        [
            "load",
            model_key,
            "--identifier",
            LM_STUDIO_IDENTIFIER,
            "--context-length",
            "8192",
            "-y",
        ],
        timeout=900,
    )

    _wait_for_loaded_model(lms_path, LM_STUDIO_IDENTIFIER, log=log)
    api_model = _resolve_api_model_identifier(LM_STUDIO_IDENTIFIER)
    return LMStudioSession(
        model_identifier=api_model,
        model_key=model_key,
        display_name=display_name,
    )


def lm_studio_semantic_search(
    query: str,
    root: str | Path,
    *,
    session: LMStudioSession,
    include_content: bool,
    pdf_ocr: bool,
    skip_technical_dirs: bool,
    max_results: int,
    year_start: int | None,
    year_end: int | None,
    document_type: str | None,
    use_windows_search: bool,
    progress: ProgressCallback | None = None,
    log: LogCallback | None = None,
    stop_event=None,
) -> SearchResponse:
    expanded_query = expand_natural_language_query(query, session=session, log=log)
    candidate_limit = min(max(max_results * 6, 40), MAX_AI_SEARCH_CANDIDATES)
    _log(log, f"Consulta expandida pelo LM Studio: {expanded_query}")

    response = smart_search(
        expanded_query,
        root,
        include_content=include_content,
        pdf_ocr=pdf_ocr,
        skip_technical_dirs=skip_technical_dirs,
        max_results=candidate_limit,
        year_start=year_start,
        year_end=year_end,
        document_type=document_type,
        use_windows_search=use_windows_search,
        progress=progress,
        log=log,
        stop_event=stop_event,
    )

    if stop_event is not None and stop_event.is_set():
        return replace(
            response,
            backend=f"LM Studio ({session.display_name}) + {response.backend}",
            messages=response.messages + ("Busca em linguagem natural interrompida.",),
        )

    if not response.results:
        return replace(
            response,
            backend=f"LM Studio ({session.display_name}) + {response.backend}",
            messages=response.messages
            + ("LM Studio expandiu a consulta, mas nenhum candidato local foi encontrado.",),
        )

    if any("expressao entre aspas" in result.reason for result in response.results[:max_results]):
        shown = response.results[:max_results]
        if progress:
            progress(response.scanned, response.total_matches, "")
        return SearchResponse(
            results=shown,
            scanned=response.scanned,
            skipped=response.skipped,
            stopped=response.stopped,
            intent=response.intent,
            total_matches=response.total_matches,
            backend=f"LM Studio ({session.display_name}) + {response.backend}",
            messages=response.messages
            + (
                "Expressao entre aspas priorizada pela busca local; reranking por LM Studio dispensado.",
            ),
        )

    reranked = rerank_candidates(
        query,
        response.results[:MAX_AI_CANDIDATES],
        session=session,
        log=log,
    )
    if not reranked:
        shown = response.results[:max_results]
        if progress:
            progress(response.scanned, response.total_matches, "")
        return replace(
            response,
            results=shown,
            backend=f"LM Studio indisponivel no reranking + {response.backend}",
            messages=response.messages
            + ("Reranking por LM Studio falhou; mantida relevancia local.",),
        )

    ranked_results = _merge_ai_ranking(response.results, reranked)
    shown = ranked_results[:max_results]
    if progress:
        progress(response.scanned, response.total_matches or len(ranked_results), "")

    return SearchResponse(
        results=shown,
        scanned=response.scanned,
        skipped=response.skipped,
        stopped=response.stopped,
        intent=response.intent,
        total_matches=response.total_matches or len(ranked_results),
        backend=f"LM Studio ({session.display_name}) + {response.backend}",
        messages=response.messages
        + (
            "Busca em linguagem natural: LM Studio expandiu a consulta e reordenou os candidatos locais.",
        ),
    )


def expand_natural_language_query(
    query: str,
    *,
    session: LMStudioSession,
    log: LogCallback | None = None,
) -> str:
    system = (
        "Voce ajuda a transformar uma pergunta juridica em termos objetivos de busca local. "
        "Responda em uma unica linha, sem JSON, sem markdown e sem explicacao."
    )
    user = (
        "Extraia termos de busca em portugues juridico. Inclua sinonimos curtos, classes "
        "de pecas e expressoes provaveis encontradas em peticoes. Nao invente fatos. "
        "Limite a 220 caracteres.\n\n"
        f"Consulta do usuario: {query}"
    )
    try:
        expanded = _clean_expanded_query(
            _chat_text(session, system, user, max_tokens=900)
        )
    except LMStudioError as exc:
        _log(log, f"Falha ao expandir consulta com LM Studio: {exc}")
        expanded = ""

    pieces = [query]
    if expanded and expanded.casefold() != query.casefold():
        pieces.append(expanded)
    return " ".join(_dedupe_words(" ".join(pieces).split()))


def rerank_candidates(
    query: str,
    candidates: list[SearchResult],
    *,
    session: LMStudioSession,
    log: LogCallback | None = None,
) -> dict[int, tuple[float, str]]:
    rows = []
    for index, result in enumerate(candidates):
        rows.append(
            {
                "id": index,
                "nome": result.name,
                "pasta": Path(result.path).parent.name[:120],
                "tipo": result.document_type or result.extension or "",
                "tamanho": human_size(result.size),
                "motivo_local": result.reason[:180],
                "trecho": (result.snippet or "")[:320],
            }
        )

    system = (
        "Voce reordena resultados de busca juridica. Use apenas os dados fornecidos. "
        "Responda somente JSON valido."
    )
    user = (
        "Pontue a relevancia de cada candidato para a consulta em linguagem natural. "
        "Use escala 0 a 100. Nao altere ids. Seja criterioso.\n\n"
        f"Consulta: {query}\n\n"
        f"Candidatos JSON: {json.dumps(rows, ensure_ascii=False)}\n\n"
        'Formato: {"resultados":[{"id":0,"score":95,"motivo":"..."}]}'
    )
    try:
        payload = _chat_json(session, system, user, max_tokens=1200)
    except LMStudioError as exc:
        _log(log, f"Falha ao reordenar candidatos com LM Studio: {exc}")
        return {}

    ranking: dict[int, tuple[float, str]] = {}
    for item in payload.get("resultados", []):
        if not isinstance(item, dict):
            continue
        try:
            item_id = int(item.get("id"))
            score = float(item.get("score"))
        except (TypeError, ValueError):
            continue
        if item_id < 0 or item_id >= len(candidates):
            continue
        reason = str(item.get("motivo") or "relevancia avaliada pelo LM Studio").strip()
        ranking[item_id] = (max(min(score, 100), 0), reason[:220])

    return ranking


def find_lms_executable() -> Path | None:
    candidates = [
        Path.home() / ".lmstudio" / "bin" / "lms.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "LM Studio" / "resources" / "app" / ".webpack" / "main" / "lms.exe",
    ]
    for raw in os.environ.get("PATH", "").split(os.pathsep):
        if raw:
            candidates.append(Path(raw) / "lms.exe")

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def find_lm_studio_app() -> Path | None:
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "LM Studio" / "LM Studio.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "LM Studio" / "LM Studio.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _ensure_server(lms_path: Path, *, log: LogCallback | None) -> None:
    status = _server_status(lms_path)
    if status.get("running") and int(status.get("port") or 0) == LM_STUDIO_PORT:
        _log(log, f"Servidor LM Studio ativo na porta {LM_STUDIO_PORT}.")
        return

    _log(log, f"Iniciando servidor LM Studio na porta {LM_STUDIO_PORT}.")
    try:
        _run_lms(
            lms_path,
            ["server", "start", "--port", str(LM_STUDIO_PORT), "--bind", "127.0.0.1"],
            timeout=60,
        )
    except LMStudioError as exc:
        if "already" not in str(exc).casefold() and "running" not in str(exc).casefold():
            raise

    deadline = time.time() + 45
    while time.time() < deadline:
        status = _server_status(lms_path)
        if status.get("running"):
            return
        time.sleep(1)
    raise LMStudioError("Servidor local do LM Studio nao iniciou.")


def _server_status(lms_path: Path) -> dict:
    try:
        output = _run_lms(lms_path, ["server", "status", "--json"], timeout=25)
        payload = _json_from_output(output)
        return payload if isinstance(payload, dict) else {}
    except LMStudioError:
        return {}


def _loaded_models(lms_path: Path, *, log: LogCallback | None) -> list[dict]:
    output = _run_lms(lms_path, ["ps", "--json"], timeout=40)
    payload = _json_from_output(output)
    if not isinstance(payload, list):
        return []
    _log(log, f"Modelos carregados no LM Studio: {len(payload)}")
    return [item for item in payload if isinstance(item, dict)]


def _local_models(lms_path: Path, *, log: LogCallback | None) -> list[dict]:
    output = _run_lms(lms_path, ["ls", "--llm", "--json"], timeout=90)
    payload = _json_from_output(output)
    if not isinstance(payload, list):
        return []
    models = [item for item in payload if isinstance(item, dict)]
    _log(log, f"Modelos LLM locais encontrados: {len(models)}")
    return models


def _session_from_loaded_model(item: dict) -> LMStudioSession:
    identifier = _first_text(
        item,
        (
            "identifier",
            "modelIdentifier",
            "modelKey",
            "model",
            "id",
            "path",
        ),
    )
    display_name = _first_text(item, ("displayName", "name", "modelKey", "identifier", "id"))
    if not identifier:
        identifier = display_name
    return LMStudioSession(
        model_identifier=identifier,
        model_key=_first_text(item, ("modelKey", "path", "id")) or identifier,
        display_name=display_name or identifier,
    )


def _select_last_used_model(models: list[dict]) -> dict:
    timestamps = _last_loaded_timestamps()

    def score(model: dict) -> int:
        keys = {
            str(model.get("modelKey") or ""),
            str(model.get("selectedVariant") or ""),
            str(model.get("path") or ""),
            str(model.get("indexedModelIdentifier") or ""),
        }
        return max((timestamps.get(key, 0) for key in keys), default=0)

    best = max(models, key=score)
    if score(best) > 0:
        return best
    return models[0]


def _last_loaded_timestamps() -> dict[str, int]:
    path = Path.home() / ".lmstudio" / ".internal" / "model-data.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}

    entries = payload.get("json") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return {}

    timestamps: dict[str, int] = {}
    for entry in entries:
        if not isinstance(entry, list) or len(entry) != 2:
            continue
        key, data = entry
        if not isinstance(data, dict):
            continue
        timestamp = data.get("lastLoadedTimestamp")
        if isinstance(key, str) and isinstance(timestamp, int):
            timestamps[key] = timestamp
    return timestamps


def _wait_for_loaded_model(lms_path: Path, identifier: str, *, log: LogCallback | None) -> None:
    deadline = time.time() + 900
    last_count = 0
    while time.time() < deadline:
        loaded = _loaded_models(lms_path, log=None)
        last_count = len(loaded)
        for item in loaded:
            values = " ".join(str(value) for value in item.values())
            if identifier in values:
                _log(log, f"Modelo carregado com identificador {identifier}.")
                return
        if loaded:
            _log(log, "Modelo carregado; usando identificador retornado pela API.")
            return
        time.sleep(2)
    raise LMStudioError(f"Modelo nao ficou disponivel no LM Studio. Modelos carregados: {last_count}")


def _resolve_api_model_identifier(preferred: str) -> str:
    try:
        request = urllib.request.Request(
            f"{LM_STUDIO_BASE_URL}/models",
            headers={"Authorization": f"Bearer {LM_STUDIO_API_KEY}"},
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return preferred

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return preferred

    ids = [str(item.get("id")) for item in data if isinstance(item, dict) and item.get("id")]
    if preferred in ids:
        return preferred
    return ids[0] if ids else preferred


def _chat_json(
    session: LMStudioSession,
    system: str,
    user: str,
    *,
    max_tokens: int,
) -> dict:
    payload = {
        "model": session.model_identifier,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.1,
        "max_tokens": max_tokens,
        "stream": False,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "kd_minha_pet_response",
                "schema": {
                    "type": "object",
                    "additionalProperties": True,
                },
            },
        },
    }
    completion = _chat_completion(session, payload)
    try:
        content = completion["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LMStudioError("resposta invalida da API do LM Studio") from exc

    payload = _json_from_output(str(content))
    if not isinstance(payload, dict):
        raise LMStudioError("o modelo nao retornou JSON valido")
    return payload


def _chat_text(
    session: LMStudioSession,
    system: str,
    user: str,
    *,
    max_tokens: int,
) -> str:
    payload = {
        "model": session.model_identifier,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.1,
        "max_tokens": max_tokens,
        "stream": False,
    }
    completion = _chat_completion(session, payload)
    try:
        content = completion["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LMStudioError("resposta invalida da API do LM Studio") from exc
    return str(content).strip()


def _chat_completion(session: LMStudioSession, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{session.base_url}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LM_STUDIO_API_KEY}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise LMStudioError(f"{exc}; {body[:500]}") from exc
    except urllib.error.URLError as exc:
        raise LMStudioError(str(exc)) from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LMStudioError("resposta invalida da API do LM Studio") from exc


def _merge_ai_ranking(
    results: list[SearchResult],
    ranking: dict[int, tuple[float, str]],
) -> list[SearchResult]:
    output: list[SearchResult] = []
    for index, result in enumerate(results):
        if index in ranking:
            ai_score, reason = ranking[index]
            combined = (ai_score * 1.7) + min(result.score, 100) * 0.3
            if "expressao entre aspas" in result.reason:
                combined = max(combined, result.score)
            output.append(
                replace(
                    result,
                    score=round(combined, 2),
                    reason=f"LM Studio: {reason}; local: {result.reason}",
                )
            )
        else:
            output.append(result)
    output.sort(key=lambda item: (-item.score, -item.modified, item.name.casefold()))
    return output


def _run_lms(lms_path: Path, args: list[str], *, timeout: int) -> str:
    command = [str(lms_path), *args]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LMStudioError(str(exc)) from exc

    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    if completed.returncode != 0:
        raise LMStudioError(output.strip() or f"lms retornou codigo {completed.returncode}")
    return output


def _json_from_output(output: str):
    text = output.strip()
    if not text:
        return None

    starts = [index for index in (text.find("{"), text.find("[")) if index >= 0]
    if not starts:
        return None
    start = min(starts)
    end = max(text.rfind("}"), text.rfind("]"))
    if end < start:
        return None
    snippet = text[start : end + 1]
    try:
        return json.loads(snippet)
    except json.JSONDecodeError:
        match = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S | re.I)
        if match:
            return json.loads(match.group(1).strip())
        raise LMStudioError("JSON invalido retornado pelo LM Studio")


def _clean_expanded_query(output: str) -> str:
    text = output.strip()
    if not text:
        return ""

    try:
        payload = _json_from_output(text)
    except LMStudioError:
        payload = None
    if isinstance(payload, dict):
        for key in ("consulta_expandida", "expanded_query", "query", "consulta"):
            value = payload.get(key)
            if value:
                text = str(value)
                break

    match = re.search(
        r"(?:consulta_expandida|expanded_query|consulta|query|termos)\s*[:=]\s*[\"']?(.*)",
        text,
        flags=re.I | re.S,
    )
    if match:
        text = match.group(1)

    text = re.sub(r"```(?:\w+)?", " ", text)
    text = re.sub(r"[\{\}\[\]]", " ", text)
    text = re.sub(r"^[\s\"'`:-]+|[\s\"'`,;:-]+$", "", text.strip())
    text = re.sub(r"\s+", " ", text)
    return text[:260].strip()


def _first_text(item: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = item.get(key)
        if value:
            return str(value)
    return ""


def _dedupe_words(words: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for word in words:
        key = word.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(word)
    return output


def _log(log: LogCallback | None, message: str) -> None:
    if log:
        log(message)

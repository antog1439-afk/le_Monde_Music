import logging
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


def normalize_search_text(value: Any) -> str:
    """Приводит название/исполнителя к форме, пригодной для сравнения."""
    normalized = unicodedata.normalize('NFKD', str(value or '')).casefold()
    normalized = ''.join(char for char in normalized if not unicodedata.combining(char))
    normalized = normalized.replace('ё', 'е')
    return re.sub(r'[^\w]+', ' ', normalized, flags=re.UNICODE).strip()


def calculate_search_relevance(query: str, title: str, artist: str = '') -> float:
    """Оценивает соответствие результата всему запросу, а не только названию."""
    query_normalized = normalize_search_text(query)
    title_normalized = normalize_search_text(title)
    artist_normalized = normalize_search_text(artist)

    if not query_normalized or not title_normalized:
        return 0.0

    query_tokens = set(query_normalized.split())
    candidate_tokens = set(f'{title_normalized} {artist_normalized}'.split())

    matched_tokens = 0
    for query_token in query_tokens:
        if query_token in candidate_tokens:
            matched_tokens += 1
            continue

        # Опечатку допускаем только в достаточно длинном слове, чтобы короткие
        # части запроса не совпадали со случайным исполнителем.
        if len(query_token) >= 4 and any(
            SequenceMatcher(None, query_token, candidate_token).ratio() >= 0.84
            for candidate_token in candidate_tokens
        ):
            matched_tokens += 1

    token_coverage = matched_tokens / len(query_tokens)
    title_artist = f'{title_normalized} {artist_normalized}'.strip()
    artist_title = f'{artist_normalized} {title_normalized}'.strip()
    text_similarity = max(
        SequenceMatcher(None, query_normalized, title_normalized).ratio(),
        SequenceMatcher(None, query_normalized, title_artist).ratio(),
        SequenceMatcher(None, query_normalized, artist_title).ratio(),
    )

    score = token_coverage * 100 + text_similarity * 35
    padded_query = f' {query_normalized} '
    title_in_query = f' {title_normalized} ' in padded_query
    artist_in_query = bool(artist_normalized) and f' {artist_normalized} ' in padded_query

    if query_normalized == title_normalized:
        score += 100
    if query_normalized in {title_artist, artist_title}:
        score += 120
    if title_in_query:
        score += 50
    if artist_in_query:
        score += 40
    if title_in_query and artist_in_query:
        score += 80
    if f' {query_normalized} ' in f' {title_normalized} ':
        score += 60
    if artist_normalized and f' {query_normalized} ' in f' {artist_normalized} ':
        score += 30

    # Чем больше слов запроса проигнорировано, тем сильнее штраф. Например,
    # «Hooligan Drake» не должен вернуть Hooligan другого исполнителя только
    # из-за точного совпадения названия.
    if len(query_tokens) > 1:
        score -= (1 - token_coverage) * 120
        if token_coverage < 0.5:
            score -= 50

    return score


def select_best_search_match(
    query: str,
    candidates: List[Dict[str, Any]],
    *,
    title_field: str,
    artist_field: str,
    minimum_score: float = 80.0,
) -> Optional[Dict[str, Any]]:
    """Возвращает лучший достаточно релевантный результат или None."""
    best_candidate = None
    best_score = 0.0

    for candidate in candidates:
        artist = candidate.get(artist_field, '')
        if isinstance(artist, dict):
            artist = artist.get('name', '')

        score = calculate_search_relevance(
            query,
            candidate.get(title_field, ''),
            artist,
        )
        if score > best_score:
            best_candidate = candidate
            best_score = score

    if best_candidate is None or best_score < minimum_score:
        logger.info(
            'Результаты найдены, но отклонены как нерелевантные '
            '(лучший балл %.1f, минимум %.1f): %s',
            best_score,
            minimum_score,
            query,
        )
        return None

    logger.info('Лучшее совпадение для «%s»: %.1f', query, best_score)
    return best_candidate

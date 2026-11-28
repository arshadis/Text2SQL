"""Lightweight *question-derived* contract for GapGPT SQL planning.

This component describes the requested answer; it never creates SQL, reads the
benchmark, assigns an invented top-k, or supplies a reference answer.  A
trusted catalog, the language of the visitor, and the original question remain
separate inputs. Rules apply equally to previously unseen football questions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re


def _mentioned(q: str, *terms: str) -> bool:
    return any(re.search(pat, q, re.I) for pat in terms)


@dataclass(frozen=True)
class QueryPlan:
    intent: str
    requested_entities: tuple[str, ...]
    requested_measures: tuple[str, ...]
    filters: tuple[str, ...]
    temporal_scope: str
    result_grain: str
    requested_top_n: int | None
    presentation_requirements: tuple[str, ...]
    epistemic_status: str

    def as_prompt(self) -> dict:
        return asdict(self)


def derive_query_plan(question: str) -> QueryPlan:
    """Infer only constraints the user actually expresses.

    This is deliberately incomplete and does not replace the language model.
    Any unrecognized metric remains unspecified rather than guessed. The raw
    visitor question still accompanies the structured hints.
    """
    from .contract import infer_contract
    q = question.casefold()
    entities=[]; measures=[]; filters=[]; presentation=[]
    is_list=_mentioned(q,r'\b(?:list|show|which|who|names?|every|each|all)\b',r'نمایش|فهرست|کدام|چه\s|نام|اسامی|همه|هر\s')
    rank=_mentioned(q,r'\b(?:top|most|highest|lowest|leader|best|rank)\b',r'بیشترین|کمترین|برترین|بهترین|رتبه|صدر')

    vocab = (
        ('team', (r'\b(?:teams?|clubs?|sides?)\b',r'تیم|باشگاه')),
        ('player', (r'\b(?:players?|scorer(?:s)?|goalscorer(?:s)?|goalkeeper(?:s)?|keeper(?:s)?)\b',r'بازیکن|گلزن|دروازه[\s\u200c]*بان')),
        ('match', (r'\b(?:match(?:es)?|fixture(?:s)?|game(?:s)?|derby)\b',r'بازی|دیدار|مسابقه|دربی')),
        ('coach', (r'\b(?:coach(?:es)?|manager(?:s)?|head[ -]?coach(?:es)?)\b',r'مربی|سرمربی')),
        ('referee', (r'\breferees?\b',r'داور')),
        ('stadium', (r'\b(?:stadiums?|venues?)\b',r'ورزشگاه')),
    )
    for key, patterns in vocab:
        if _mentioned(q,*patterns):entities.append(key)
    measure_vocab=(
        ('points',(r'\bpoints?\b',r'امتیاز')),
        ('goal count',(r'\b(?:scor(?:e|es|ed|ing|er|ers)|goals?|goalscorer(?:s)?)\b',r'گل')),
        ('yellow cards',(r'\byellow\s+card(?:s)?\b',r'کارت\s+زرد')),
        ('red cards',(r'\bred\s+card(?:s)?\b',r'کارت\s+قرمز')),
        ('clean sheets',(r'\bclean\s+sheets?\b',r'کلین[\s\u200c]*شیت')),
        ('playing minutes',(r'\bminutes?\s+(?:played|on\s+pitch)\b|\bplayed\s+(?:the\s+)?(?:most\s+)?minutes?\b',r'دقایق\s+بازی|دقیقه\s+بازی')),
        ('distinct formations',(r'\b(?:formations?|tactics?)\b',r'آرایش|سیستم\s+بازی')),
        ('recorded substitutions',(r'\bsubstitutions?\b',r'تعویض')),
        ('VAR decisions',(r'\bVAR\b',r'کمک[\s\u200c]*داور\s+ویدئویی')),
        ('recorded penalties',(r'\bpenalt(?:y|ies)\b',r'پنالتی')),
        ('match count',(r'\b(?:how\s+many|number\s+of)\s+(?:[a-z]+\s+){0,3}(?:matches|fixtures|games)\b',r'تعداد\s+(?:مسابقات|بازی|دیدار)')),
        ('match result',(r'\b(?:final\s+score|result|match\s+score|score\s+of|what\s+was\s+the\s+score)\b',r'نتیجه|نتایج')),
    )
    for key, patterns in measure_vocab:
        if _mentioned(q,*patterns): measures.append(key)
    excluded_own=_mentioned(q,r'\b(?:exclude|excluding|without)\s+own\s+goals?\b',
                           r'\bown\s+goals?\s+(?:excluded|removed|omitted)\b',
                           r'بدون\s+گل\s+به\s+خودی')
    if (_mentioned(q,r'\bown[ -]?goals?\b',r'گل[\s\u200c]*به[\s\u200c]*خودی')
        and is_list and not excluded_own):
        measures=[m for m in measures if m!='goal count']
        measures.append('own-goal event details')
    if 'distinct formations' in measures and not _mentioned(q,r'\b(?:different|distinct|how many|most|count|number)\b',r'تعداد|چند|متفاوت|بیشترین'):
        measures[measures.index('distinct formations')]='formation detail'
    if _mentioned(q,r'\b(?:home|at\s+home|home\s+games?)\b',r'خانگی|میزبان'):
        filters.append('home side only; do not substitute overall-league totals')
    if _mentioned(q,r'\b(?:away|on\s+the\s+road|away\s+games?)\b',r'خارج\s+از\s+خانه|میهمان'):
        filters.append('away side only; do not substitute overall-league totals')
    if _mentioned(q,r'\b(?:actually\s+played|played\s+matches?|completed\s+matches?|finished\s+matches?|matches?\s+(?:(?:have|has)\s+been\s+)?played(?:\s+so\s+far)?)\b',r'بازی[\s\u200c]*(?:های)?\s*(?:برگزار|انجام)\s*شده|مسابقات\s*برگزارشده'):
        filters.append('physically played matches only (not awarded/scheduled)')
    if ('own-goal event details' in measures):
        filters.append('own-goal event; distinguish scorer club from credited club')
    if excluded_own:
        filters.append('exclude own-goal events')
    if _mentioned(q,r'\b(?:change[ds]?|changing|different\s+coaches?|replaced)\b',r'تغییر|عوض\s+شد'):
        filters.append('temporal change: compare repeated observations for the same entity across different events')
    if _mentioned(q,r'\b(?:benefited|credited|benefiting)\b',r'منتفع|سود\s+برد|به\s+نفع'):
        filters.append('credited entity must be obtained from event attribution, not merely fixture sides')
    minute=re.search(r'\b(?:after|later\s+than|beyond)\s+(?:the\s+)?(\d{1,3})(?:st|nd|rd|th)?\s*(?:minute)?\b',q,re.I)
    if minute:
        filters.append(f'event minute strictly > {int(minute.group(1))}; later-than is exclusive')
    if _mentioned(q,r'\b(?:during|in|of)\s+(?:match)?week\s+(\d+)\b',r'هفته[\s\u200c]*(\d+)'):
        filters.append('matchweek constraint must be preserved')
    if _mentioned(q,r'\b(?:all|every|each)\b',r'همه|تمام|هر\s'):
        filters.append('cover all requested records; include zero-event entities only when counting per entity')

    if 'own-goal event details' in measures:
        presentation.extend(('one row per actual goal event, not per club',
                             'named scorer and named credited beneficiary',
                             'match identification and event timing if recorded'))
    if 'match result' in measures and 'match' in entities:
        presentation.extend(('readable identity of both sides', 'both scores', 'completed fixture rather than upcoming NULL score'))
    if 'player' in entities: presentation.append('readable player name; no unrequested internal player_id')
    if 'team' in entities: presentation.append('readable club name; no unrequested internal team_id')
    if 'coach' in entities: presentation.append('readable coach name')
    if 'referee' in entities: presentation.append('readable referee name')
    if any(m!='own-goal event details' and m!='formation detail' and m!='match result' for m in measures):
        presentation.append('project the measured numeric quantity with a descriptive alias')
    if rank: presentation.append('order by the requested metric, with a deterministic tie breaker')

    explicit=infer_contract(question).target_rows
    subjective=_mentioned(q,r'\b(?:best|greatest|better)\b',r'بهترین|بهتر') and not measures
    missing_reference=_mentioned(q,r'\b(?:that\s+(?:game|player|team)|this\s+(?:player|team))\b',r'آن\s+(?:بازی|بازیکن|تیم)|این\s+(?:بازیکن|تیم)')
    status=('clarify_missing_reference' if missing_reference else
            'clarify_subjective_measure' if subjective else 'potentially_answerable')
    temporal=('explicit_time_filter' if minute else 'recorded_snapshot')
    grain=('entity_by_time' if any('temporal change' in f for f in filters) else
           'event' if 'own-goal event details' in measures else
           'entity' if (rank or ('player' in entities and is_list)) else
           'entity_listing' if is_list else 'aggregate_or_detail')
    return QueryPlan('rank' if rank else 'list' if is_list else 'answer',tuple(entities),
                     tuple(measures),tuple(filters),temporal,grain,explicit,
                     tuple(dict.fromkeys(presentation)),status)

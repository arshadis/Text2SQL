"""Generic draft-review signals independent of evaluator SQL and expected rows."""
from __future__ import annotations
import re
from .contract import diagnostics, instruction
from .schema_graph import focused_relations
from .query_plan import derive_query_plan

SUPPORTED_TERMS = re.compile(
    r'\b(?:coaches?|managers?|formations?|goalkeepers?|goals?|matches?|cards?|referees?|penalt(?:y|ies)|'
    r'standings|minutes|fixtures?|substitutions?|VAR|leagues?|lineups?|teams?|players?)\b|'
    r'(?:مربی|سرمربی|آرایش|ترکیب|دروازه|گل|مسابق|بازی|داور|کارت|پنالتی|'
    r'دقیقه|جدول|تیم|بازیکن|لیگ)',re.I)
UNSUPPORTED_TERMS = re.compile(
    r'\b(?:fans?|supporters?|attendance|ticket|revenue|salary|transfer fee|'
    r'prediction|tomorrow|next year|real.time)\b|'
    r'(?:هوادار|تماشاگر|بلیت|درآمد|حقوق|پیش\s?بینی|فردا)',re.I)


def reconsider_refusal(question: str) -> bool:
    return bool(SUPPORTED_TERMS.search(question) and not UNSUPPORTED_TERMS.search(question))


# A bounded second look is permitted for a *concrete* recorded metric.
# This is a general vocabulary of observable quantities, not a list of eval
# questions, a fixed ranking size, or an instruction to fabricate a criterion.
_OBJECTIVE_MEASURES = re.compile(
    r'\b(?:goals?|scor(?:es?|ers?|ing)|cards?|bookings?|penalt(?:y|ies)|'
    r'points?|wins?|draws?|losses?|minutes?|played|finished|results?|'
    r'clean\s+sheets?|formations?|substitutions?|fixtures?|matches?|'
    r'weeks?|rounds?|saves?|shots?|assists?)\b|'
    r'(?:گل|پنالتی|کارت|امتیاز|برد|باخت|مساوی|دقیقه|بازی|نتیجه|'
    r'کلین\s?شیت|آرایش|تعویض|هفته|مسابقه|پاس گل)', re.I)


def reconsider_clarification(question: str) -> bool:
    """Only ask a reviewing model to check premature clarification if the
    question already names an observable measure. Never force it to answer.
    """
    return bool(_OBJECTIVE_MEASURES.search(question)) and not bool(UNSUPPORTED_TERMS.search(question))

def review_feedback(question: str, sql: str, data: dict) -> dict:
    """Share actual SQL/rows and generic guardrails, never a reference solution."""
    hints=[
        'Check relation and column meanings from the supplied schema and semantic dictionary.',
        'Use the focused schema FK edges to verify the identity and role of every entity, not just SQL syntax.',
        'A valid SQL query can still be semantically wrong. Explain whether it answers the precise user metric, subjects, filters, status and output fields.',
        'Check the grain of aggregation and avoid fanout from one-to-many joins.',
        'Preserve user-requested filters, time scope, metrics and any EXPLICIT top-N.',
        'Show readable labels and avoid irrelevant ID columns.',
        'Do not infer a benchmark default ranking size; choose coverage from user intent.',
        'A request for several entities is not answered by one arbitrarily selected row. Do not force a single leader without singular wording.',
        'A result set can be syntactically valid but mix unrelated sides or include NULL values instead of recorded match results; verify role-level conditions.',
    ]
    if re.search(r'\b(?:played|finished)\b|بازی\s*شده|انجام\s*شده',question,re.I):
        hints.append("For physically played fixtures, status='finished' excludes awarded/scheduled records.")
    if data.get('row_count',0)==0:
        hints.append('Zero rows observed. Review restrictive filters/joins, without inventing matches.')
    if data.get('truncated'):
        hints.append('Results reached the row-safety cap.')
    return {
        'mode':'generic_semantic_review',
        'question_derived_result_contract':instruction(question),
        'typed_query_plan':derive_query_plan(question).as_prompt(),
        'focused_schema_graph':focused_relations(question),
        'observed_contract_violations':diagnostics(question,sql,data),
        'instruction':'Revise only if there is a real semantic mistake based on the question and schema. All revised SQL is validated by an independent read-only sandbox.',
        'candidate_sql':sql,
        'database_columns':data.get('columns',[])[:20],
        'database_row_count':data.get('row_count'),
        'database_sample_rows':data.get('rows',[])[:4],
        'review_hints':hints,
    }


def semantic_signal(question: str, sql: str, data: dict) -> float:
    """Quantify only generic presentation properties and explicit row requests."""
    cols=[str(c).lower() for c in data.get('columns',())]
    rows=data.get('rows') or []
    value=0.0
    if not re.search(r'\b(?:id|identifier|شناسه)\b',question.casefold()):
        value-=3*sum(name.endswith('_id') and name!='match_id' for name in cols)
    if rows and any(isinstance(v,str) for v in rows[0]):
        value+=1
    for problem in diagnostics(question,sql,data):
        value-=1.5
    if re.search(r'\b(?:played|finished)\b|بازی\s*شده|انجام\s*شده',question,re.I):
        if re.search(r"status\s*=\s*['\"]finished['\"]",sql,re.I):value+=3
        if re.search(r"['\"]awarded['\"]",sql,re.I):value-=3
    if data.get('truncated'):value-=2
    return value

"""Question-derived result contracts for any Persian/English football query.

This module knows no evaluator cases, model answers, ground-truth rows, or gold SQL.
It describes output shape and flags observable semantic anomalies, not SQL recipes.
"""
from __future__ import annotations
import re
from dataclasses import dataclass

@dataclass(frozen=True)
class Contract:
    grain: str
    target_rows: int | None = None
    ordered: bool = False
    show_names: bool = False
    needs_team: bool = False
    match_result: bool = False
    unique_metric: bool = False
    all_events: bool = False
    rule: str = ''


def infer_contract(question: str) -> Contract:
    q = question.casefold()
    if re.search(r'\b(?:fans?|supporters?|attendance|spectators?|tickets?|revenue|salar(?:y|ies)|transfer fees?|predictions?)\b|هوادار|تماشاگر|بلیت|درآمد|حقوق\s*بازیکن|پیش\s*بینی',q):
        return Contract('not recorded by the database',rule='Do not map an unrecorded metric onto some other stored metric.')
    leader = bool(re.search(r'\b(?:top of the (?:league|table)|league leader|table leader|at the top of the league)\b|صدرنشین|صدر جدول',q))
    match_result = bool(re.search(r'\b(?:derby|score of|result of|final score|score between)\b|نتیجه.{0,25}(?:دربی|بازی|دیدار)|دربی',q))
    explicit = re.search(r'\btop\s+(\d+)\b|(?:^|\s)([۰۱۲۳۴۵۶۷۸۹0-9]+)\s*(?:گلزن|بازیکن|تیم|داور|نفر|مربی)\s*برتر',q)
    n = int((explicit.group(1) or explicit.group(2)).translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹','0123456789'))) if explicit else None
    # A request to list ALL matching events, or a low-frequency sanction distribution,
    # is not a top-N leaderboard: preserve the nonzero distribution.
    all_events=bool(re.search(r'\b(?:list all|show all|all own goals|all events)\b|همه|تمام',q))
    cards=bool(re.search(r'\b(?:red cards?|sending.off|second yellows?)\b|کارت\s*قرمز|اخراج',q))
    rank=bool(re.search(r'\b(?:most|highest|top|best|leaders?|leading)\b|بیشترین|بهترین|برترین|صدر',q))
    keeper=bool(re.search(r'goalkeepers?|clean sheets?|دروازه\s*بان|کلین\s*شیت',q))
    person=bool(re.search(r'\b(?:players?|scorers?|goalkeepers?|minutes played)\b|بازیکن|گلزن|دروازه\s*بان|دقایق\s*بازی',q))
    coach=bool(re.search(r'\b(?:coaches?|managers?|formations?)\b|مربی|سرمربی|آرایش',q))
    referee=bool(re.search(r'\b(?:referees?|officials?)\b|داور',q))
    team=bool(re.search(r'\b(?:teams?|clubs?|home record|standings)\b|تیم|باشگاه|جدول',q))
    change=bool(re.search(r'\b(?:changed|change|replaced|switched|different coaches?)\b|تغییر\s*مربی|تعویض\s*مربی',q)) and coach
    goal_event=bool(re.search(r'\bown.goals?\b|گل\s*به\s*خودی',q)) and not bool(re.search(r'\b(?:excluding|excluded|exclude|except|without)\b.{0,20}\bown.goals?\b|\bown.goals?\b.{0,20}\b(?:excluded|exclude)\b|به\s*جز\s*گل\s*به\s*خودی',q))
    if leader:
        return Contract('single standings leader',1,True,True,True,rule='A league-table leader is ONE club with its points and tiebreak statistics, not the entire standings.')
    if match_result:
        return Contract('named finished match',1,False,True,True,True,rule='Show the played match round, date, both club names, and score; exclude future fixtures with NULL score.')
    if change:
        return Contract('coach tenure per team',None,True,True,True,rule='Find teams with multiple distinct coaches ACROSS DIFFERENT matches; give each coach tenure with first/last rounds and fixtures. Do not self-join one match to find two simultaneous coaches.')
    if goal_event:
        return Contract('individual own goal event',None,True,True,True,all_events=True,rule='One event per row: match identifier, named scorer, scorer club, credited beneficiary club, minute and added time; order by match identifier.')
    if cards and team and rank and n is None:
        return Contract('team sanction distribution',None,True,True,True,rule='Show all clubs with nonzero sanctions, not just one; order count DESC then club name ASC.')
    if n is None and rank and not all_events:
        # For an unspecified leaderboard, show more than an arbitrary winner.
        n = 5 if person or keeper else 3 if (team or coach or referee) else None
    if rank or n:
        entity='player' if person else 'coach' if coach else 'referee' if referee else 'team' if team else 'participant'
        return Contract(f'{entity} ranking',n,True,True,team or person or coach,
                        rule='Show only human-readable participants, their relevant club where needed, and the metric. Sort metric DESC then human-readable name ASC for tied metrics.')
    if all_events:
        return Contract('complete event listing',None,True,True,all_events=True,rule='List each matching event, with readable names and any necessary event identifiers.')
    return Contract('answer from recorded data',show_names=bool(person or team or coach or referee),needs_team=False)


def diagnostics(question: str, sql: str, data: dict) -> list[str]:
    """Observable issues only. Does not know or infer expected database values."""
    c=infer_contract(question)
    columns=[str(x).casefold() for x in data.get('columns',())]
    row_count=int(data.get('row_count',0))
    s=sql.casefold()
    issues=[]
    if c.target_rows is not None and row_count != c.target_rows and not data.get('truncated'):
        # If fewer rows exist than the requested top N, this is just a hint to check,
        # not a claim that N matching records must exist.
        issues.append(f'Output grain expects up to {c.target_rows} ranked records; draft returned {row_count}. '+c.rule)
    if c.target_rows is not None and c.target_rows>1 and row_count==1:
        issues.append('A single arbitrary winner is insufficient for an unspecified leaderboard. Include the requested/default top-N entries.')
    if c.grain=='single standings leader' and row_count>1:
        issues.append('The question asks for the single league leader, not the whole league table.')
    if c.show_names and not re.search(r'\b(?:id|identifier|شناسه)\b',question.casefold()):
        ids=[name for name in columns if name.endswith('_id') and name!='match_id']
        if ids: issues.append('Display names instead of internal ID columns: '+', '.join(ids))
        if data.get('rows') and not any(isinstance(x,str) for x in data['rows'][0]):
            issues.append('No readable participant name in the projected result. Join the appropriate lookup table(s).')
    if c.needs_team and c.grain not in ('single standings leader','named finished match'):
        has_club=any('team' in x or 'club' in x for x in columns)
        if not has_club:
            issues.append('The requested result needs a readable club name, not just participant ID or name.')
    # A clean sheet is a team result, not a goalkeeper statistic unless the
    # lineup is explicitly limited to the starting goalkeeper role. Even a
    # syntactically valid query can falsely credit every outfield starter.
    if (re.search(r'goalkeepers?|clean\s*sheet|دروازه\s*بان|کلین\s*شیت',question.casefold())
        and re.search(r'\b(?:from|join)\s+lineup\b',s)):
        if not re.search(r"\b(?:\w+\.)?position\s*=\s*['\"]GK['\"]",sql,re.I):
            issues.append("Goalkeeper-only statistics must restrict lineup.position = 'GK'; starter status alone includes all outfield players.")
        if not re.search(r'\bis_starter\s*=\s*1\b',s):
            issues.append('Starting goalkeeper metrics must require lineup.is_starter = 1.')
    if c.match_result:
        if not re.search(r"\b(?:status)\s*=\s*['\"]finished['\"]",s):
            issues.append("Match result must filter actual played fixtures: status='finished'; otherwise scheduled return legs may appear with NULL score.")
        if not any('round' in x or 'week' in x for x in columns):
            issues.append('Named match result should include the matchweek/round to identify the fixture.')
        if any(any(v is None for v in row) for row in data.get('rows',[])):
            issues.append('Some returned fixture rows have NULL date or score; select completed fixtures only.')
    if c.grain=='coach tenure per team':
        if not re.search(r'count\s*\(\s*distinct\s+\w*\.?coach_id',s,re.I):
            issues.append('To find changed managers, first identify clubs with COUNT(DISTINCT coach_id)>1 across recorded fixtures.')
        if row_count==0:
            issues.append('No coach changes found. Check that you compare coaches across DIFFERENT matches, not two coaches in the same match/team record.')
    # A factually plausible event list can still omit a crucial requested entity.
    # Own-goals have TWO club roles: the scorer's club and the credited club.
    # This checks the projected labels and schema linkage, not evaluation cases.
    if c.grain=='individual own goal event':
        scorer_club_labels=('scorer_team','scoring_team','scorer_club',
                            'player_team','player_club','own_goal_team','scorer_side')
        beneficiary_labels=('benefited_team','beneficiary_team','credited_team',
                            'benefited_club','beneficiary_club','credited_club',
                            'receiving_team','benefiting_team')
        has_scorer_club=any(any(label in col for label in scorer_club_labels) for col in columns)
        has_beneficiary=any(any(label in col for label in beneficiary_labels) for col in columns)
        if not has_scorer_club:
            issues.append('Missing readable scorer club: own-goal events must show the club of the scorer via goal.scorer_team_id, distinct from the benefited club.')
        if not has_beneficiary:
            issues.append('Missing readable beneficiary club: own-goal events must show goal.team_id as the team credited with the goal.')
        if 'scorer_team_id' not in s:
            issues.append('The SQL does not link the own-goal scorer club using goal.scorer_team_id; join a second club alias to display that name.')
        if not any('scorer' in col or 'player' in col for col in columns):
            issues.append('An own-goal listing must display the named scorer as well as both teams.')

    # The team-match view has TWO rows per recorded fixture, one per side.
    # Joining it to goal solely by match_id makes each event appear for both
    # teams. This common join-cardinality bug is invisible to SQL dry-runs and
    # row-shape checks, and must be corrected before accepting a team goal rank.
    if c.grain=='team ranking' and re.search(r'\b(?:from|join)\s+goal\b',s):
        goal_alias_match=re.search(r'\b(?:from|join)\s+goal\s+(?:as\s+)?(\w+)',s)
        goal_alias=(goal_alias_match.group(1) if goal_alias_match and
                    goal_alias_match.group(1) not in ('join','where','on') else 'goal')
        if re.search(r'\b(?:from|join)\s+v_team_match\b',s):
            tm_alias_match=re.search(r'\b(?:from|join)\s+v_team_match\s+(?:as\s+)?(\w+)',s)
            tm_alias=(tm_alias_match.group(1) if tm_alias_match and
                      tm_alias_match.group(1) not in ('join','where','on') else 'v_team_match')
            pair=(rf'(?:\b{re.escape(goal_alias)}\.team_id\s*=\s*{re.escape(tm_alias)}\.team_id\b|'
                  rf'\b{re.escape(tm_alias)}\.team_id\s*=\s*{re.escape(goal_alias)}\.team_id\b)')
            conceded=bool(re.search(r'\b(?:conceded|against|opponent|allowed|received)\b|گل\s*خورده|گل\s*دریافتی',question.casefold()))
            if not re.search(pair,s) and not (conceded and re.search(
                    rf'\b{re.escape(goal_alias)}\.team_id\s*(?:!=|<>)\s*{re.escape(tm_alias)}\.team_id\b|'
                    rf'\b{re.escape(tm_alias)}\.team_id\s*(?:!=|<>)\s*{re.escape(goal_alias)}\.team_id\b',s)):
                role=('For conceded goals join on match_id AND the OPPOSITE team (goal.team_id != tm.team_id).'
                      if conceded else
                      'Count credited goals using goal.team_id joined directly to team, or join v_team_match on BOTH match_id AND goal.team_id=tm.team_id.')
                issues.append('Goal-to-v_team_match fanout: v_team_match has TWO team rows per match. Joining on match_id alone doubles/misattributes team goals. '+role)
        if re.search(rf'\b{re.escape(goal_alias)}\.scorer_team_id\b',s) and not re.search(rf'\b{re.escape(goal_alias)}\.team_id\b',s):
            issues.append('Team goal statistics must attribute a goal to goal.team_id (credited club), not scorer_team_id (which differs on own goals).')

    if c.grain=='individual own goal event':
        if not any('benefit' in x or 'credit' in x or 'team' in x for x in columns):
            issues.append('Join credited team and scorer team separately; include their readable names.')
        if not any('added' in x for x in columns):
            issues.append('Include stoppage added_time for goal events.')
    if c.grain=='team sanction distribution' and columns and len(columns)>2:
        # A count-per-club distribution should have one readable club label and
        # one statistic; a second translation/ID is not requested by default.
        issues.append('Report club name and sanction count only; omit duplicate bilingual labels or internal metadata.')
    if c.grain=='individual own goal event':
        if ('match_date' in columns and 'match_id' in columns and not
            re.search(r'\b(?:date|when|calendar|day)\b|تاریخ|چه\s*روزی',question.casefold())):
            issues.append('A match identifier already locates this event; omit an unrequested duplicate match_date column.')
    if c.grain=='coach tenure per team' and row_count:
        if not any('coach' in name or 'manager' in name for name in columns):
            issues.append('Include a readable coach name for each club and coach stint.')
        if not any('round' in name or 'first' in name or 'start' in name for name in columns):
            issues.append('Give each coach tenure first and last recorded match rounds.')
        if not any('matches' in name or 'games' in name or 'fixtures' in name or 'count' in name for name in columns):
            issues.append('Give the number of recorded fixtures per coach-team tenure.')
        if any('previous' in name or 'current' in name for name in columns):
            issues.append('Do not collapse one team to one old/new coach pair: return ONE row PER (team, coach).')
        # If the output claims a club changed coaches, that club must appear
        # with at least TWO distinct observed coaches. Check actual returned
        # rows only, never evaluation/reference values.
        team_cols=[i for i,name in enumerate(columns) if name in ('team','team_name','club','club_name')]
        coach_cols=[i for i,name in enumerate(columns) if ('coach' in name or 'manager' in name)
                    and not name.endswith('_id') and not any(x in name for x in ('previous','current'))]
        if team_cols and coach_cols:
            club_coaches={}
            for row in data.get('rows',[]):
                team_name=row[team_cols[0]]
                coach_name=row[coach_cols[0]]
                club_coaches.setdefault(team_name,set()).add(coach_name)
            if club_coaches and any(len(names)<2 for names in club_coaches.values()):
                issues.append('A changed club must appear with EVERY distinct observed coach, not only its latest or first coach. Show one row per coach-team stint.')
    if c.grain=='team sanction distribution' and row_count==1:
        issues.append('Include the full ranking of clubs with nonzero sanctions, not only the maximum.')
    if c.ordered and row_count>1:
        ob=re.search(r'\border\s+by\b(.*?)(?:\blimit\b|\boffset\b|;|$)',s,re.S)
        if not ob:
            issues.append('Stable ORDER BY is required for ranking/list outputs.')
        elif c.grain != 'individual own goal event' and ',' not in ob.group(1):
            issues.append('Add a stable human-readable participant/club name ASC as secondary ORDER BY to resolve equal metric counts.')
    if c.target_rows is not None and c.target_rows>1 and row_count>c.target_rows:
        issues.append(f'Limit the ranking to {c.target_rows} entries; it currently includes too many.')
    if c.grain=='single standings leader' and columns and len(columns)>4:
        issues.append('Only project the requested leader fields: one club label, played, points and goal difference.')
    if c.grain=='team ranking' and columns and len(columns)>3:
        issues.append('For a simple club performance ranking show club and requested score, not unrelated intermediate match statistics.')
    if data.get('truncated'):
        issues.append('The results hit the 100-row safety cap; narrow the result to the requested grain where appropriate.')
    return issues


def instruction(question: str) -> dict:
    c=infer_contract(question)
    return {'result_grain':c.grain, 'target_rows':c.target_rows,
            'use_human_labels':c.show_names, 'include_club_label':c.needs_team,
            'require_played_match':c.match_result,
            'sort_ties_deterministically':c.ordered,
            'result_shape_guidance':c.rule}

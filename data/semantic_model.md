# Football DB — Semantic Model

**Iran Persian Gulf Pro League, season 2026-27 (1405-06)**
Source: varzesh3.com public API, snapshot taken 2026-11-01 (after matchweek 11).
Engine: SQLite. Open it **read-only** (`file:football.db?mode=ro`).

| | |
|---|---|
| Teams | 18 |
| Matches | 306 (34 matchweeks × 9) — 95 finished, 1 awarded, 3 cancelled, 207 scheduled |
| Players | 531 (names in Persian) |
| Lineup rows | 3,945 (starters + bench) |
| Goals / Cards / Subs / Penalties / VAR | 187 / 327 / 855 / 21 / 39 |

---

## Football language → tables

| Fan / analyst says… | Table · column |
|---|---|
| competition, league | `competition` |
| season | `season` (`name` = '2026-27', `name_jalali` = '1405-06') |
| club, team, side | `team` (`name` English, `name_fa` Persian, `city`) |
| fixture, game, match, result, score | `match` |
| matchweek, round, هفته | `match.round` (1–34) |
| home / away, host / guest, میزبان / میهمان | `match.home_team_id` / `match.away_team_id` |
| final score | `match.home_goals`, `match.away_goals` |
| win / draw / loss | `match.result` ('H','D','A') or `v_team_match.outcome` ('W','D','L') |
| referee, داور | `referee` via `match.referee_id` |
| stadium, venue, ورزشگاه | `stadium` via `match.stadium_id` |
| formation, آرایش | `match.home_formation` / `match.away_formation` |
| manager, head coach, سرمربی | `coach` via `match_coach` (per match, per team) |
| lineup, starting XI, bench, ترکیب | `lineup` (`is_starter` 1/0) |
| position | `lineup.position` ('GK','DF','MF','FW'), starters only |
| goal, scorer, گل | `goal` |
| own goal, گل به خودی | `goal.is_own_goal = 1` |
| penalty, پنالتی | `penalty` (all attempts); converted ones also in `goal` with `is_penalty = 1` |
| yellow / red card, sending-off | `card.card_type` ('yellow','second_yellow','red') |
| substitution, تعویض | `substitution` (`player_in_id`, `player_out_id`) |
| VAR | `var_decision` |
| league table, standings, جدول | view `v_standings` |
| minutes played | view `v_player_minutes` (approximate) |

## Tables

### `match`
| column | meaning |
|---|---|
| `match_id` | PK |
| `round` | matchweek number |
| `status` | `finished`, `awarded` (forfeit, 3-0 by disciplinary decision), `cancelled`, `scheduled` |
| `kickoff_utc` | ISO UTC; NULL for unscheduled fixtures |
| `match_date`, `kickoff_local` | Tehran local date/time (UTC+03:30) |
| `match_date_jalali` | Persian calendar date as published, e.g. `1405/06/11` |
| `home_team_id`, `away_team_id` | FK → `team` |
| `home_goals`, `away_goals`, `result` | only set when `status IN ('finished','awarded')` |
| `referee_id`, `stadium_id` | FK; may be NULL for future fixtures |
| `home_formation`, `away_formation` | e.g. `4-2-3-1`; finished matches only |

### `lineup` — PK (`match_id`, `player_id`)
`team_id`, `shirt_number`, `is_starter`, `formation_line` (0 = GK … highest = attack), `position` (derived: line 0 GK, line 1 DF, highest line FW, rest MF; NULL on bench).

### `goal`
| column | meaning |
|---|---|
| `team_id` | team **credited** with the goal (the one whose score went up) |
| `player_id` | scorer |
| `scorer_team_id` | team the scorer plays for — **differs from `team_id` for own goals** |
| `minute`, `added_time` | `90+6` → `minute = 90, added_time = 6` |
| `half` | `first_half` / `second_half` |
| `is_own_goal`, `is_penalty` | 0/1 |

Invariant: for every finished match, `COUNT(goal)` per `team_id` equals `home_goals` / `away_goals`.

### `card`, `substitution`, `penalty`, `var_decision`
All have `match_id`, `team_id`, `minute`, `added_time`, `half` (`card.half` can also be `after_full_time`).
- `penalty.outcome`: `scored`, `saved`, `missed`
- `var_decision.decision`: `goal_disallowed`, `penalty_awarded`, `penalty_cancelled`, `card_changed`. `team_id` is the side the event was recorded under; `player_id` may belong to the other team.

### `match_coach` — PK (`match_id`, `team_id`)
Coach on the touchline for that team in that match. Several teams changed coach mid-season.

### Lookup tables
`competition`, `season`, `team`, `player`, `coach`, `referee`, `stadium` — id + name.

## Views
| view | grain | notes |
|---|---|---|
| `v_team_match` | one row per team per counted match | `venue` home/away, `goals_for`, `goals_against`, `outcome` W/D/L. Includes the awarded match. |
| `v_standings` | one row per team | played, won, drawn, lost, GF, GA, GD, points. Order with `points DESC, goal_diff DESC, goals_for DESC`. |
| `v_match` | one row per match | team and referee names already joined |
| `v_player_minutes` | player × finished match | regulation minutes only; stoppage time ignored |

## Join rules (the usual mistakes)
1. A team appears in a match as **either** home or away. Use `v_team_match`, or `OR`, or `UNION ALL` — never only `home_team_id`.
2. Scorer's club = `goal.scorer_team_id`, not `goal.team_id`. Exclude `is_own_goal = 1` for scorer charts.
3. Do not add `penalty` rows to `goal` rows; converted penalties are already in `goal`.
4. JOIN CARDINALITY WARNING: `v_team_match` contains **two rows per match**.
   Never aggregate `goal` after joining to `v_team_match` on `match_id` alone;
   each goal would be duplicated and attributed to both sides. For team scoring
   counts, prefer `goal.team_id → team.team_id`; if using the view, constrain
   **both** `goal.match_id = v_team_match.match_id` and
   `goal.team_id = v_team_match.team_id`.
5. Join `v_team_match` to `lineup` on **both** `match_id` and `team_id`.
6. Referee and stadium live on `match`, not on event tables.
7. Played matches = `status = 'finished'`. The standings also count `awarded`.
8. A sending-off is `card_type IN ('red','second_yellow')`.

## Known data quirks
- Player and coach names are Persian only; team names exist in both English and Persian.
- 58 substitutes entered the pitch without being listed on the bench (source gap); they appear in `substitution` but not in `lineup`.
- One player id (288406) has no name in the source and is stored as `(نامشخص)`.
- Stadium names are as published; some are short forms (e.g. `تختی`).
- Rounds are not strictly chronological: postponed games keep their original round number.

## SQL generation notes
- SQLite treats `match` as a reserved keyword. When querying its table directly, quote it as `"match"`; use the supplied views if they match the grain of the question.
- Aggregate by unique IDs, then join lookup tables for display names. If rankings tie, order consistently and do not invent a winner.
- Rows describe a fixed snapshot, not live football results. Questions asking about fans/attendance or current unrecorded facts cannot be answered from this schema.
- Number of played games should filter `status='finished'`; standings are different because disciplinary `awarded` results count there.

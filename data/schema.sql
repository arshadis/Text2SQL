CREATE TABLE competition (
    competition_id   INTEGER PRIMARY KEY,
    name             TEXT NOT NULL,
    name_fa          TEXT NOT NULL,
    country          TEXT NOT NULL
);

CREATE TABLE season (
    season_id        INTEGER PRIMARY KEY,
    competition_id   INTEGER NOT NULL REFERENCES competition(competition_id),
    name             TEXT NOT NULL,          -- '2026-27'
    name_jalali      TEXT NOT NULL,          -- '1405-06'
    num_rounds       INTEGER NOT NULL
);

CREATE TABLE team (
    team_id          INTEGER PRIMARY KEY,
    name             TEXT NOT NULL,          -- English name
    name_fa          TEXT NOT NULL,          -- Persian name (as on varzesh3)
    city             TEXT,
    primary_color    TEXT
);

CREATE TABLE player (
    player_id        INTEGER PRIMARY KEY,
    name_fa          TEXT NOT NULL
);

CREATE TABLE coach (
    coach_id         INTEGER PRIMARY KEY,
    name_fa          TEXT NOT NULL
);

CREATE TABLE referee (
    referee_id       INTEGER PRIMARY KEY,
    name_fa          TEXT NOT NULL UNIQUE
);

CREATE TABLE stadium (
    stadium_id       INTEGER PRIMARY KEY,
    name_fa          TEXT NOT NULL UNIQUE
);

CREATE TABLE match (
    match_id          INTEGER PRIMARY KEY,
    season_id         INTEGER NOT NULL REFERENCES season(season_id),
    round             INTEGER NOT NULL,       -- matchweek 1..34
    status            TEXT NOT NULL CHECK (status IN ('scheduled','finished','cancelled','awarded')),
    kickoff_utc       TEXT,                   -- ISO-8601 UTC, NULL if not yet scheduled
    match_date        TEXT,                   -- local (Tehran) date YYYY-MM-DD
    match_date_jalali TEXT,                   -- '1405/06/11'
    kickoff_local     TEXT,                   -- local time HH:MM
    home_team_id      INTEGER NOT NULL REFERENCES team(team_id),
    away_team_id      INTEGER NOT NULL REFERENCES team(team_id),
    home_goals        INTEGER,                -- NULL unless status in ('finished','awarded')
    away_goals        INTEGER,
    result            TEXT CHECK (result IN ('H','D','A')),
    referee_id        INTEGER REFERENCES referee(referee_id),
    stadium_id        INTEGER REFERENCES stadium(stadium_id),
    home_formation    TEXT,
    away_formation    TEXT
);

CREATE TABLE match_coach (
    match_id         INTEGER NOT NULL REFERENCES match(match_id),
    team_id          INTEGER NOT NULL REFERENCES team(team_id),
    coach_id         INTEGER NOT NULL REFERENCES coach(coach_id),
    PRIMARY KEY (match_id, team_id)
);

CREATE TABLE lineup (
    match_id         INTEGER NOT NULL REFERENCES match(match_id),
    team_id          INTEGER NOT NULL REFERENCES team(team_id),
    player_id        INTEGER NOT NULL REFERENCES player(player_id),
    shirt_number     INTEGER,
    is_starter       INTEGER NOT NULL CHECK (is_starter IN (0,1)),   -- 0 = on the bench
    formation_line   INTEGER,                -- 0 = goalkeeper, 1 = defence ... last = attack; NULL for bench
    position         TEXT CHECK (position IN ('GK','DF','MF','FW')),  -- derived from formation_line; NULL for bench
    PRIMARY KEY (match_id, player_id)
);

CREATE TABLE goal (
    goal_id          INTEGER PRIMARY KEY,
    match_id         INTEGER NOT NULL REFERENCES match(match_id),
    team_id          INTEGER NOT NULL REFERENCES team(team_id),   -- team CREDITED with the goal
    player_id        INTEGER REFERENCES player(player_id),        -- scorer
    scorer_team_id   INTEGER NOT NULL REFERENCES team(team_id),   -- team the scorer plays for (differs for own goals)
    minute           INTEGER NOT NULL,       -- regulation minute (45 or 90 during stoppage time)
    added_time       INTEGER NOT NULL DEFAULT 0,  -- stoppage-time minute, e.g. 90+6 -> minute 90, added_time 6
    half             TEXT NOT NULL,
    is_own_goal      INTEGER NOT NULL CHECK (is_own_goal IN (0,1)),
    is_penalty       INTEGER NOT NULL CHECK (is_penalty IN (0,1))
);

CREATE TABLE card (
    card_id          INTEGER PRIMARY KEY,
    match_id         INTEGER NOT NULL REFERENCES match(match_id),
    team_id          INTEGER NOT NULL REFERENCES team(team_id),
    player_id        INTEGER REFERENCES player(player_id),
    card_type        TEXT NOT NULL CHECK (card_type IN ('yellow','second_yellow','red')),
    minute           INTEGER NOT NULL,
    added_time       INTEGER NOT NULL DEFAULT 0,
    half             TEXT NOT NULL
);

CREATE TABLE substitution (
    substitution_id  INTEGER PRIMARY KEY,
    match_id         INTEGER NOT NULL REFERENCES match(match_id),
    team_id          INTEGER NOT NULL REFERENCES team(team_id),
    player_in_id     INTEGER REFERENCES player(player_id),
    player_out_id    INTEGER REFERENCES player(player_id),
    minute           INTEGER NOT NULL,
    added_time       INTEGER NOT NULL DEFAULT 0,
    half             TEXT NOT NULL
);

CREATE TABLE penalty (
    penalty_id       INTEGER PRIMARY KEY,
    match_id         INTEGER NOT NULL REFERENCES match(match_id),
    team_id          INTEGER NOT NULL REFERENCES team(team_id),
    taker_id         INTEGER REFERENCES player(player_id),
    outcome          TEXT NOT NULL CHECK (outcome IN ('scored','saved','missed')),
    minute           INTEGER NOT NULL,
    added_time       INTEGER NOT NULL DEFAULT 0,
    half             TEXT NOT NULL
);

CREATE TABLE var_decision (
    var_id           INTEGER PRIMARY KEY,
    match_id         INTEGER NOT NULL REFERENCES match(match_id),
    team_id          INTEGER NOT NULL REFERENCES team(team_id),   -- side the decision is recorded for
    player_id        INTEGER REFERENCES player(player_id),
    decision         TEXT NOT NULL CHECK (decision IN ('goal_disallowed','penalty_awarded','penalty_cancelled','card_changed')),
    minute           INTEGER NOT NULL,
    added_time       INTEGER NOT NULL DEFAULT 0,
    half             TEXT NOT NULL
);

CREATE INDEX ix_match_round ON match(round);

CREATE INDEX ix_match_home  ON match(home_team_id);

CREATE INDEX ix_match_away  ON match(away_team_id);

CREATE INDEX ix_lineup_player ON lineup(player_id);

CREATE INDEX ix_lineup_team   ON lineup(team_id, match_id);

CREATE INDEX ix_goal_match   ON goal(match_id);

CREATE INDEX ix_goal_player  ON goal(player_id);

CREATE INDEX ix_card_match   ON card(match_id);

CREATE INDEX ix_card_player  ON card(player_id);

CREATE INDEX ix_sub_match    ON substitution(match_id);

CREATE VIEW v_team_match AS
SELECT m.match_id, m.round, m.match_date, m.home_team_id AS team_id, m.away_team_id AS opponent_id,
       'home' AS venue, m.home_goals AS goals_for, m.away_goals AS goals_against,
       CASE WHEN m.home_goals > m.away_goals THEN 'W' WHEN m.home_goals = m.away_goals THEN 'D' ELSE 'L' END AS outcome
FROM match m WHERE m.status IN ('finished','awarded')
UNION ALL
SELECT m.match_id, m.round, m.match_date, m.away_team_id, m.home_team_id,
       'away', m.away_goals, m.home_goals,
       CASE WHEN m.away_goals > m.home_goals THEN 'W' WHEN m.away_goals = m.home_goals THEN 'D' ELSE 'L' END
FROM match m WHERE m.status IN ('finished','awarded');

CREATE VIEW v_standings AS
SELECT t.team_id, t.name AS team, t.name_fa AS team_fa,
       COUNT(*)                                   AS played,
       SUM(tm.outcome = 'W')                      AS won,
       SUM(tm.outcome = 'D')                      AS drawn,
       SUM(tm.outcome = 'L')                      AS lost,
       SUM(tm.goals_for)                          AS goals_for,
       SUM(tm.goals_against)                      AS goals_against,
       SUM(tm.goals_for) - SUM(tm.goals_against)  AS goal_diff,
       SUM(CASE tm.outcome WHEN 'W' THEN 3 WHEN 'D' THEN 1 ELSE 0 END) AS points
FROM v_team_match tm JOIN team t ON t.team_id = tm.team_id
GROUP BY t.team_id;

CREATE VIEW v_match AS
SELECT m.match_id, m.round, m.status, m.match_date, m.kickoff_local,
       h.name AS home_team, a.name AS away_team, m.home_goals, m.away_goals, m.result,
       r.name_fa AS referee, s.name_fa AS stadium
FROM match m
JOIN team h ON h.team_id = m.home_team_id
JOIN team a ON a.team_id = m.away_team_id
LEFT JOIN referee r ON r.referee_id = m.referee_id
LEFT JOIN stadium s ON s.stadium_id = m.stadium_id;

CREATE VIEW v_player_minutes AS
SELECT l.match_id, l.team_id, l.player_id,
       l.is_starter,
       CASE WHEN l.is_starter = 1 THEN 0 ELSE si.minute END AS minute_on,
       COALESCE(so.minute, rc.minute, 90)                    AS minute_off,
       COALESCE(so.minute, rc.minute, 90) - CASE WHEN l.is_starter = 1 THEN 0 ELSE si.minute END AS minutes_played
FROM lineup l
JOIN match m ON m.match_id = l.match_id AND m.status = 'finished'
LEFT JOIN (SELECT match_id, player_in_id AS player_id, MIN(minute) AS minute
           FROM substitution GROUP BY 1, 2) si
       ON si.match_id = l.match_id AND si.player_id = l.player_id
LEFT JOIN (SELECT match_id, player_out_id AS player_id, MIN(minute) AS minute
           FROM substitution GROUP BY 1, 2) so
       ON so.match_id = l.match_id AND so.player_id = l.player_id
LEFT JOIN (SELECT match_id, player_id, MIN(minute) AS minute FROM card
           WHERE card_type IN ('red','second_yellow') GROUP BY match_id, player_id) rc
       ON rc.match_id = l.match_id AND rc.player_id = l.player_id
WHERE l.is_starter = 1 OR si.minute IS NOT NULL;

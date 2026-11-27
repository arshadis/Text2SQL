"""Constant domain definitions, applicable beyond any evaluation questions."""
BASICS = '''SQLite snapshot: Iran Persian Gulf Pro League 2026–27. Do NOT invent data.
Match status: finished = physically played; awarded = administrative result,
      scheduled = future/not played; cancelled = not played. Standings include
      awarded matches; physically played fixture counts do not.
Goal event roles: player_id identifies the scorer; scorer_team_id identifies
      the scorer's club; team_id identifies the credited/benefiting club.
The roles differ for an own goal. Regular scorer totals exclude own goals.
Card types: yellow, second_yellow, red. A sending-off includes second_yellow
      and red; a yellow booking is yellow only.
Team match view: v_team_match is TWO rows per match (one per side), and
      includes goals_for, goals_against, outcome and venue home/away. Join an
      event to that view by BOTH match_id and team_id to prevent fanout.
Goalkeeper clean sheet is a STARTING GK for a team in a played game where
      that SAME team's goals_against equals zero. Join lineup to v_team_match
      using both match_id and team_id; do not infer from a zero score by either side.
Match-coach observations are per (match_id, team_id), enabling reconstruction
      of changes over time by comparing coaches across recorded fixtures.
Formation is stored on the match side: home_formation and away_formation;
      which applies depends on that team's relationship to the fixture.
Names: team.name is English and team.name_fa Persian; player.name_fa,
      referee.name_fa and coach.name_fa are Persian.
Use SQLite-compatible SQL. Quote the table "match" as necessary.
The data snapshot may contain NULLs for future games. Read-only SQL only.
Never send evaluator expected results or gold SQL to the model.'''

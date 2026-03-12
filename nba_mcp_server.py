#!/usr/bin/env python3
import asyncio
import json
import os
from datetime import datetime
from itertools import combinations
from typing import Any
import httpx
from dotenv import load_dotenv
from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio

load_dotenv()

# Initialize MCP server
server = Server("nba-betting-analyzer")

# Configuration - Only need Odds API key
ODDS_API_KEY = os.getenv("ODDS_API_KEY")

class NBADataFetcher:
    """Fetches NBA data without any AI processing"""

    def __init__(self):
        self.odds_api_url = "https://api.the-odds-api.com/v4"

    async def fetch_nba_games(self) -> dict:
        """Fetch today's NBA schedule"""
        today = datetime.now().strftime("%Y-%m-%d")
        url = "https://stats.nba.com/stats/scoreboardV2"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://stats.nba.com/",
            "Accept": "application/json"
        }
        params = {
            "GameDate": today,
            "LeagueID": "00",
            "DayOffset": "0"
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url, headers=headers, params=params)
                data = response.json()

                result_sets = data.get("resultSets", [])
                game_header = next((rs for rs in result_sets if rs.get("name") == "GameHeader"), None)
                line_score = next((rs for rs in result_sets if rs.get("name") == "LineScore"), None)

                if not game_header:
                    return {"error": "No game data available", "games": []}

                gh_headers = game_header.get("headers", [])
                gh_rows = game_header.get("rowSet", [])
                ls_headers = line_score.get("headers", []) if line_score else []
                ls_rows = line_score.get("rowSet", []) if line_score else []

                # Build map of game_id -> [away_team, home_team] (LineScore returns visitor first)
                game_teams: dict[str, list] = {}
                for row in ls_rows:
                    ls_dict = dict(zip(ls_headers, row))
                    game_id = ls_dict.get("GAME_ID")
                    wl = ls_dict.get("TEAM_WINS_LOSSES", "") or ""
                    parts = wl.split("-")
                    wins = int(parts[0]) if len(parts) == 2 and parts[0].isdigit() else None
                    losses = int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else None
                    team = {
                        "name": ls_dict.get("TEAM_NAME"),
                        "city": ls_dict.get("TEAM_CITY_NAME"),
                        "tricode": ls_dict.get("TEAM_ABBREVIATION"),
                        "wins": wins,
                        "losses": losses,
                        "score": ls_dict.get("PTS")
                    }
                    if game_id not in game_teams:
                        game_teams[game_id] = []
                    game_teams[game_id].append(team)

                games = []
                for row in gh_rows:
                    gh_dict = dict(zip(gh_headers, row))
                    game_id = gh_dict.get("GAME_ID")
                    teams = game_teams.get(game_id, [])
                    away_team = teams[0] if len(teams) > 0 else {}
                    home_team = teams[1] if len(teams) > 1 else {}
                    games.append({
                        "game_id": game_id,
                        "game_time": gh_dict.get("GAME_STATUS_TEXT"),
                        "game_status": gh_dict.get("GAME_STATUS_TEXT"),
                        "home_team": home_team,
                        "away_team": away_team,
                    })

                return {
                    "date": today,
                    "total_games": len(games),
                    "games": games
                }

            except Exception as e:
                return {"error": str(e), "games": []}

    async def fetch_nba_stats(self) -> dict:
        """Fetch recent player statistics for players on teams playing today"""
        # First, get today's games to know which teams are playing
        games_data = await self.fetch_nba_games()
        if "error" in games_data and not games_data.get("games"):
            return {"error": f"Could not fetch today's games: {games_data['error']}"}

        # Collect tricodes for all teams playing today
        playing_teams = set()
        for game in games_data.get("games", []):
            home_tricode = game.get("home_team", {}).get("tricode")
            away_tricode = game.get("away_team", {}).get("tricode")
            if home_tricode:
                playing_teams.add(home_tricode)
            if away_tricode:
                playing_teams.add(away_tricode)

        if not playing_teams:
            return {"error": "No games scheduled today", "players": []}

        url = "https://stats.nba.com/stats/leaguedashplayerstats"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://stats.nba.com/",
            "Accept": "application/json"
        }
        params = {
            "LastNGames": "5",
            "LeagueID": "00",
            "MeasureType": "Base",
            "Month": "0",
            "OpponentTeamID": "0",
            "PaceAdjust": "N",
            "PerMode": "PerGame",
            "Period": "0",
            "PlusMinus": "N",
            "Rank": "N",
            "Season": "2025-26",
            "SeasonType": "Regular Season"
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url, headers=headers, params=params)
                data = response.json()

                # Parse the NBA stats API response format
                result_sets = data.get("resultSets", [])
                if not result_sets:
                    return {"error": "No data available"}

                headers_list = result_sets[0].get("headers", [])
                rows = result_sets[0].get("rowSet", [])

                # Filter to only players on teams playing tomorrow
                players = []
                for row in rows:
                    player_dict = dict(zip(headers_list, row))
                    team = player_dict.get("TEAM_ABBREVIATION")
                    if team in playing_teams:
                        players.append({
                            "player_name": player_dict.get("PLAYER_NAME"),
                            "team": team,
                            "games_played": player_dict.get("GP"),
                            "minutes": player_dict.get("MIN"),
                            "points": player_dict.get("PTS"),
                            "rebounds": player_dict.get("REB"),
                            "assists": player_dict.get("AST"),
                            "steals": player_dict.get("STL"),
                            "blocks": player_dict.get("BLK"),
                            "fg_pct": player_dict.get("FG_PCT"),
                            "fg3_pct": player_dict.get("FG3_PCT"),
                            "ft_pct": player_dict.get("FT_PCT")
                        })

                return {
                    "date": games_data.get("date"),
                    "teams_playing_today": sorted(playing_teams),
                    "last_n_games": 5,
                    "total_players": len(players),
                    "players": players
                }

            except Exception as e:
                return {"error": str(e)}

    async def fetch_betting_odds(self) -> dict:
        """Fetch betting odds for today's NBA games only"""
        # Get today's games to know which matchups to filter for
        games_data = await self.fetch_nba_games()
        if "error" in games_data and not games_data.get("games"):
            return {"error": f"Could not fetch today's games: {games_data['error']}"}

        # Build a set of full team names playing today (e.g. "Los Angeles Lakers")
        playing_teams = set()
        for game in games_data.get("games", []):
            for side in ("home_team", "away_team"):
                team = game.get(side, {})
                city = team.get("city", "")
                name = team.get("name", "")
                if city and name:
                    playing_teams.add(f"{city} {name}")

        if not playing_teams:
            return {"error": "No games scheduled today", "games": []}

        url = f"{self.odds_api_url}/sports/basketball_nba/odds"
        params = {
            "apiKey": ODDS_API_KEY,
            "regions": "us",
            "markets": "h2h,spreads,totals",
            "oddsFormat": "american"
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url, params=params)
                data = response.json()

                # Format the odds data, filtering to today's games only
                formatted_games = []
                for game in data:
                    home = game.get("home_team", "")
                    away = game.get("away_team", "")
                    # Only include if both teams are playing today
                    if home not in playing_teams or away not in playing_teams:
                        continue
                    game_info = {
                        "game_id": game.get("id"),
                        "sport": game.get("sport_key"),
                        "commence_time": game.get("commence_time"),
                        "home_team": game.get("home_team"),
                        "away_team": game.get("away_team"),
                        "bookmakers": []
                    }

                    for bookmaker in game.get("bookmakers", []):
                        bookmaker_info = {
                            "name": bookmaker.get("key"),
                            "title": bookmaker.get("title"),
                            "markets": {}
                        }

                        for market in bookmaker.get("markets", []):
                            market_key = market.get("key")
                            bookmaker_info["markets"][market_key] = market.get("outcomes", [])

                        game_info["bookmakers"].append(bookmaker_info)

                    formatted_games.append(game_info)

                return {
                    "total_games": len(formatted_games),
                    "games": formatted_games
                }

            except Exception as e:
                return {"error": str(e), "data": []}

    def _adjusted_edge(
        self,
        team_win_pct: float,
        opponent_win_pct: float,
        implied_prob: float,
        is_home: bool,
        home_boost: float = 0.03,
    ) -> float:
        """
        Compute an edge score that factors in home/away and opponent strength.

        home_boost: flat win% added for home court (NBA home teams win ~60%,
                    so ~+3pp over a neutral-site 50/50 baseline).
        opponent_strength_factor: scales the raw edge by how tough the opponent
                    is. Range 0.5 (opponent wins 0%) to 1.5 (opponent wins 100%).
                    A team beating the odds against a strong opponent gets a
                    higher score than the same edge against a weak opponent.
        """
        if team_win_pct is None or implied_prob is None:
            return 0.0
        adjusted_win_pct = team_win_pct + (home_boost if is_home else 0.0)
        raw_edge = adjusted_win_pct - implied_prob
        opp = opponent_win_pct if opponent_win_pct is not None else 0.5
        opponent_strength_factor = 0.5 + opp  # 0.5–1.5
        return round(raw_edge * opponent_strength_factor, 4)

    def _american_to_implied_prob(self, odds: int) -> float:
        """Convert American odds to implied probability (0-1), removing vig"""
        if odds is None:
            return None
        if odds < 0:
            return abs(odds) / (abs(odds) + 100)
        else:
            return 100 / (odds + 100)

    def _best_line(self, bookmakers: list, market: str, team_name: str) -> dict:
        """Find the best available line for a team across all bookmakers"""
        best = None
        for book in bookmakers:
            outcomes = book.get("markets", {}).get(market, [])
            for outcome in outcomes:
                if outcome.get("name") == team_name:
                    price = outcome.get("price")
                    point = outcome.get("point")
                    if best is None or price > best["price"]:
                        best = {
                            "book": book.get("title"),
                            "price": price,
                            "point": point
                        }
        return best

    def _best_total(self, bookmakers: list, side: str) -> dict:
        """Find best over/under price across bookmakers"""
        best = None
        for book in bookmakers:
            outcomes = book.get("markets", {}).get("totals", [])
            for outcome in outcomes:
                if outcome.get("name") == side:
                    price = outcome.get("price")
                    point = outcome.get("point")
                    if best is None or price > best["price"]:
                        best = {
                            "book": book.get("title"),
                            "price": price,
                            "point": point
                        }
        return best

    def _american_to_decimal(self, odds: int) -> float:
        if odds > 0:
            return odds / 100 + 1
        else:
            return 100 / abs(odds) + 1

    def _decimal_to_american(self, decimal: float) -> int:
        if decimal >= 2.0:
            return round((decimal - 1) * 100)
        elif decimal <= 1.0:
            return -10000  # effectively no-profit / invalid odds
        else:
            return round(-100 / (decimal - 1))

    def _build_parlay(self, prop_candidates: list, target_min=150, target_max=300) -> dict:
        """
        Exhaustively search all combinations of candidates to find the one that:
          1. Falls within [target_min, target_max] combined American odds
          2. Has no duplicate matchups (one leg per game)
          3. Maximizes total edge across all legs

        Falls back to the in-range combo with the best single highest-edge leg
        if no combo hits the target range.
        """
        # De-duplicate: keep best-priced line per matchup+market+side combo
        seen = {}
        for p in prop_candidates:
            key = (p["player"], p["market"], p["side"])
            if key not in seen or p["price"] > seen[key]["price"]:
                seen[key] = p
        deduped = list(seen.values())

        best_combo = None
        best_total_edge = -float("inf")

        max_legs = min(8, len(deduped))
        for r in range(1, max_legs + 1):
            for combo in combinations(deduped, r):
                # One leg per matchup
                matchups = [c["player"] for c in combo]
                if len(matchups) != len(set(matchups)):
                    continue

                # Combined odds
                decimal = 1.0
                for c in combo:
                    decimal *= self._american_to_decimal(c["price"])
                american = self._decimal_to_american(decimal)

                if target_min <= american <= target_max:
                    total_edge = sum(c.get("edge", 0) for c in combo)
                    if total_edge > best_total_edge:
                        best_total_edge = total_edge
                        best_combo = (list(combo), decimal, american)

        if best_combo:
            combo, parlay_decimal, parlay_american = best_combo
            selected = [
                {**c, "leg_decimal": round(self._american_to_decimal(c["price"]), 3)}
                for c in combo
            ]
        else:
            # No combo hits the target — return empty result with a note
            return {
                "legs": [],
                "parlay_odds": "N/A",
                "parlay_american": None,
                "parlay_decimal": None,
                "num_legs": 0,
                "note": (
                    f"No combination of available legs lands in the "
                    f"{'+' if target_min > 0 else ''}{target_min} to "
                    f"{'+' if target_max > 0 else ''}{target_max} range. "
                    "More games on the slate will open up more combinations."
                )
            }

        parlay_american = self._decimal_to_american(parlay_decimal)
        fmt = f"+{parlay_american}" if parlay_american > 0 else str(parlay_american)
        return {
            "legs": selected,
            "parlay_odds": fmt,
            "parlay_american": parlay_american,
            "parlay_decimal": round(parlay_decimal, 2),
            "num_legs": len(selected)
        }

    def _form_score(self, player: dict) -> float:
        """Composite recent-form score weighted like fantasy points"""
        pts = player.get("points") or 0
        reb = player.get("rebounds") or 0
        ast = player.get("assists") or 0
        stl = player.get("steals") or 0
        blk = player.get("blocks") or 0
        return round(pts + (reb * 1.2) + (ast * 1.5) + (stl * 3) + (blk * 3), 2)

    async def analyze_bets(self) -> dict:
        """Synthesize games, player stats, and odds into ranked betting opportunities + parlay"""
        # Fetch all three sources concurrently
        games_data, stats_data, odds_data = await asyncio.gather(
            self.fetch_nba_games(),
            self.fetch_nba_stats(),
            self.fetch_betting_odds()
        )

        # --- Game-level analysis ---
        # Build a lookup: "City Name" -> game record info
        game_record_lookup = {}
        for game in games_data.get("games", []):
            for side in ("home_team", "away_team"):
                team = game.get(side, {})
                full_name = f"{team.get('city', '')} {team.get('name', '')}".strip()
                wins = team.get("wins") or 0
                losses = team.get("losses") or 0
                total = wins + losses
                game_record_lookup[full_name] = {
                    "wins": wins,
                    "losses": losses,
                    "win_pct": round(wins / total, 3) if total > 0 else None
                }

        game_analyses = []
        for odds_game in odds_data.get("games", []):
            home = odds_game.get("home_team")
            away = odds_game.get("away_team")
            bookmakers = odds_game.get("bookmakers", [])

            # Best lines across books
            best_home_ml = self._best_line(bookmakers, "h2h", home)
            best_away_ml = self._best_line(bookmakers, "h2h", away)
            best_home_spread = self._best_line(bookmakers, "spreads", home)
            best_away_spread = self._best_line(bookmakers, "spreads", away)
            best_over = self._best_total(bookmakers, "Over")
            best_under = self._best_total(bookmakers, "Under")

            # Implied probabilities from best moneyline
            home_implied = self._american_to_implied_prob(
                best_home_ml["price"] if best_home_ml else None
            )
            away_implied = self._american_to_implied_prob(
                best_away_ml["price"] if best_away_ml else None
            )

            # Record-based win probability
            home_record = game_record_lookup.get(home, {})
            away_record = game_record_lookup.get(away, {})
            home_win_pct = home_record.get("win_pct")
            away_win_pct = away_record.get("win_pct")

            # Edge: record win% minus implied probability (positive = potential value)
            home_edge = round(home_win_pct - home_implied, 3) if (home_win_pct is not None and home_implied is not None) else None
            away_edge = round(away_win_pct - away_implied, 3) if (away_win_pct is not None and away_implied is not None) else None

            # Pick the side with more edge
            value_side = None
            if home_edge is not None and away_edge is not None:
                if home_edge > 0.03:
                    value_side = {"team": home, "edge": home_edge, "note": "Record outperforms implied odds"}
                elif away_edge > 0.03:
                    value_side = {"team": away, "edge": away_edge, "note": "Record outperforms implied odds"}

            game_analyses.append({
                "matchup": f"{away} @ {home}",
                "commence_time": odds_game.get("commence_time"),
                "home_team": {
                    "name": home,
                    "record": home_record,
                    "implied_win_prob": round(home_implied, 3) if home_implied else None,
                    "edge_vs_implied": home_edge
                },
                "away_team": {
                    "name": away,
                    "record": away_record,
                    "implied_win_prob": round(away_implied, 3) if away_implied else None,
                    "edge_vs_implied": away_edge
                },
                "best_lines": {
                    "moneyline": {"home": best_home_ml, "away": best_away_ml},
                    "spread": {"home": best_home_spread, "away": best_away_spread},
                    "total": {"over": best_over, "under": best_under}
                },
                "value_opportunity": value_side
            })

        # Sort game analyses: games with value opportunities first
        game_analyses.sort(key=lambda g: g["value_opportunity"] is None)

        # --- Player-level analysis ---
        players_with_scores = []
        for player in stats_data.get("players", []):
            score = self._form_score(player)
            players_with_scores.append({**player, "form_score": score})

        # Sort by form score descending
        players_with_scores.sort(key=lambda p: p["form_score"], reverse=True)

        # --- Parlay building from game-level lines ---
        # Limit to top 5 games by combined win% (best records = highest quality matchups)
        def combined_win_pct(game):
            hw = game["home_team"]["record"].get("win_pct") or 0
            aw = game["away_team"]["record"].get("win_pct") or 0
            return hw + aw

        top_games = sorted(game_analyses, key=combined_win_pct, reverse=True)[:5]

        game_candidates = []
        for game in top_games:
            matchup = game["matchup"]
            lines = game.get("best_lines", {})
            home_info = game["home_team"]
            away_info = game["away_team"]
            home_win_pct = home_info["record"].get("win_pct")
            away_win_pct = away_info["record"].get("win_pct")
            home_implied = home_info.get("implied_win_prob")
            away_implied = away_info.get("implied_win_prob")

            home_edge = self._adjusted_edge(home_win_pct, away_win_pct, home_implied, is_home=True)
            away_edge = self._adjusted_edge(away_win_pct, home_win_pct, away_implied, is_home=False)

            for team, edge, side_key, ml_key, sp_key in [
                (home_info["name"], home_edge, "home", "home", "home"),
                (away_info["name"], away_edge, "away", "away", "away"),
            ]:
                if edge > 0.03:
                    ml = lines.get("moneyline", {}).get(ml_key)
                    if ml and ml.get("price") is not None:
                        game_candidates.append({
                            "player": matchup,
                            "market": "moneyline",
                            "side": team,
                            "line": None,
                            "price": ml["price"],
                            "book": ml.get("book"),
                            "edge": edge,
                            "reasoning": (
                                f"{team} ML ({ml['price']:+d}) — "
                                f"adjusted edge {edge:+.3f} "
                                f"({'home' if side_key == 'home' else 'away'}, "
                                f"opp win% {away_win_pct if side_key == 'home' else home_win_pct:.1%})"
                            )
                        })
                    sp = lines.get("spread", {}).get(sp_key)
                    if sp and sp.get("price") is not None:
                        game_candidates.append({
                            "player": matchup,
                            "market": "spread",
                            "side": team,
                            "line": sp.get("point"),
                            "price": sp["price"],
                            "book": sp.get("book"),
                            "edge": edge * 0.8,
                            "reasoning": (
                                f"{team} {sp.get('point'):+g} ({sp['price']:+d}) — "
                                f"adjusted edge {edge:+.3f}"
                            )
                        })

            # Totals: always include best-priced side (over or under)
            over = lines.get("total", {}).get("over")
            under = lines.get("total", {}).get("under")
            if over and over.get("price") is not None:
                game_candidates.append({
                    "player": matchup,
                    "market": "total",
                    "side": "Over",
                    "line": over.get("point"),
                    "price": over["price"],
                    "book": over.get("book"),
                    "edge": 0.01,
                    "reasoning": f"Over {over.get('point')} ({over['price']:+d}) — {matchup}"
                })
            if under and under.get("price") is not None:
                game_candidates.append({
                    "player": matchup,
                    "market": "total",
                    "side": "Under",
                    "line": under.get("point"),
                    "price": under["price"],
                    "book": under.get("book"),
                    "edge": 0.01,
                    "reasoning": f"Under {under.get('point')} ({under['price']:+d}) — {matchup}"
                })

        safer_parlay = self._build_parlay(game_candidates, target_min=-150, target_max=100)
        longshot_parlay = self._build_parlay(game_candidates, target_min=200, target_max=300)

        return {
            "analysis_date": games_data.get("date"),
            "summary": {
                "total_games_analyzed": len(game_analyses),
                "games_with_value": sum(1 for g in game_analyses if g["value_opportunity"]),
                "total_players_analyzed": len(players_with_scores),
                "game_candidates_found": len(game_candidates)
            },
            "game_analyses": game_analyses,
            "parlay_recommendations": {
                "safer_parlay": {
                    "target_odds": "-150 to +100",
                    **safer_parlay
                },
                "longshot_parlay": {
                    "target_odds": "+200 to +300",
                    **longshot_parlay
                }
            },
            "top_players_in_form": players_with_scores[:20]
        }


# Initialize data fetcher
fetcher = NBADataFetcher()

@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available MCP tools"""
    return [
        Tool(
            name="fetch_nba_games",
            description="Fetch today's NBA schedule with team records and game times. Returns structured data about all games scheduled for today.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="fetch_nba_stats",
            description="Fetch recent player statistics (last 5 games) for players on teams playing today. Returns points, rebounds, assists, shooting percentages, and more for all players on today's rosters.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="fetch_betting_odds",
            description="Fetch betting odds from multiple sportsbooks, filtered to only the NBA games scheduled for today. Returns moneyline, spreads, and totals from various bookmakers.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="build_parlay",
            description="Build two recommended parlays from today's games — one targeting -150 to +100 and one targeting +200 to +300. Scores each game line by adjusted edge (home/away + opponent strength) and returns the best legs with reasoning and combined payout.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="analyze_bets",
            description="Synthesize today's NBA games, recent player stats, and betting odds into ranked betting opportunities. Returns implied probabilities, value edges based on team records, best available lines across bookmakers, and top players by recent form score.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls"""
    try:
        if name == "fetch_nba_games":
            result = await fetcher.fetch_nba_games()
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "fetch_nba_stats":
            result = await fetcher.fetch_nba_stats()
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "fetch_betting_odds":
            result = await fetcher.fetch_betting_odds()
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "fetch_player_props":
            # Auto-resolve today's game IDs from betting odds
            odds_data = await fetcher.fetch_betting_odds()
            event_ids = [g["game_id"] for g in odds_data.get("games", []) if g.get("game_id")]
            result = await fetcher.fetch_player_props(event_ids)
            return [TextContent(
                type="text",
                text=json.dumps({"total_props": len(result), "props": result}, indent=2)
            )]

        elif name == "build_parlay":
            # Fetch games + odds concurrently
            games_data, odds_data = await asyncio.gather(
                fetcher.fetch_nba_games(),
                fetcher.fetch_betting_odds()
            )

            # Build record lookup: "City Name" -> win_pct
            game_record_lookup = {}
            for game in games_data.get("games", []):
                for side in ("home_team", "away_team"):
                    team = game.get(side, {})
                    full_name = f"{team.get('city', '')} {team.get('name', '')}".strip()
                    wins = team.get("wins") or 0
                    losses = team.get("losses") or 0
                    total = wins + losses
                    game_record_lookup[full_name] = round(wins / total, 3) if total > 0 else None

            # Sort games by combined win% and take top 5
            all_odds_games = odds_data.get("games", [])
            def game_combined_win_pct(g):
                h = game_record_lookup.get(g.get("home_team")) or 0
                a = game_record_lookup.get(g.get("away_team")) or 0
                return h + a

            top_odds_games = sorted(all_odds_games, key=game_combined_win_pct, reverse=True)[:5]

            game_candidates = []
            for odds_game in top_odds_games:
                home = odds_game.get("home_team")
                away = odds_game.get("away_team")
                matchup = f"{away} @ {home}"
                bookmakers = odds_game.get("bookmakers", [])

                best_home_ml = fetcher._best_line(bookmakers, "h2h", home)
                best_away_ml = fetcher._best_line(bookmakers, "h2h", away)
                best_home_sp = fetcher._best_line(bookmakers, "spreads", home)
                best_away_sp = fetcher._best_line(bookmakers, "spreads", away)
                best_over = fetcher._best_total(bookmakers, "Over")
                best_under = fetcher._best_total(bookmakers, "Under")

                home_implied = fetcher._american_to_implied_prob(best_home_ml["price"] if best_home_ml else None)
                away_implied = fetcher._american_to_implied_prob(best_away_ml["price"] if best_away_ml else None)
                home_win_pct = game_record_lookup.get(home)
                away_win_pct = game_record_lookup.get(away)

                home_edge = fetcher._adjusted_edge(home_win_pct, away_win_pct, home_implied, is_home=True)
                away_edge = fetcher._adjusted_edge(away_win_pct, home_win_pct, away_implied, is_home=False)

                # Moneyline + spread candidates for sides with positive adjusted edge
                for team, edge, ml, sp, location in [
                    (home, home_edge, best_home_ml, best_home_sp, "home"),
                    (away, away_edge, best_away_ml, best_away_sp, "away"),
                ]:
                    if edge > 0.03 and ml and ml.get("price") is not None:
                        game_candidates.append({
                            "player": matchup,
                            "market": "moneyline",
                            "side": team,
                            "line": None,
                            "price": ml["price"],
                            "book": ml.get("book"),
                            "edge": edge,
                            "reasoning": (
                                f"{team} ML ({ml['price']:+d}) — "
                                f"adjusted edge {edge:+.3f} "
                                f"({location}, opp win% {(away_win_pct if location == 'home' else home_win_pct) or 0:.1%})"
                            )
                        })
                    if edge > 0.03 and sp and sp.get("price") is not None:
                        game_candidates.append({
                            "player": matchup,
                            "market": "spread",
                            "side": team,
                            "line": sp.get("point"),
                            "price": sp["price"],
                            "book": sp.get("book"),
                            "edge": edge * 0.8,
                            "reasoning": (
                                f"{team} {sp.get('point'):+g} ({sp['price']:+d}) — "
                                f"adjusted edge {edge:+.3f} ({location})"
                            )
                        })

                # Totals — always include both sides for variety
                for total_side, best in [("Over", best_over), ("Under", best_under)]:
                    if best and best.get("price") is not None:
                        game_candidates.append({
                            "player": matchup,
                            "market": "total",
                            "side": total_side,
                            "line": best.get("point"),
                            "price": best["price"],
                            "book": best.get("book"),
                            "edge": 0.01,
                            "reasoning": (
                                f"{total_side} {best.get('point')} ({best['price']:+d}) — {matchup}"
                            )
                        })

            safer_parlay = fetcher._build_parlay(game_candidates, target_min=-150, target_max=100)
            longshot_parlay = fetcher._build_parlay(game_candidates, target_min=200, target_max=300)
            result = {
                "total_game_candidates": len(game_candidates),
                "safer_parlay": {
                    "target_odds": "-150 to +100",
                    **safer_parlay
                },
                "longshot_parlay": {
                    "target_odds": "+200 to +300",
                    **longshot_parlay
                }
            }
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "analyze_bets":
            result = await fetcher.analyze_bets()
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        else:
            return [TextContent(
                type="text",
                text=f"Unknown tool: {name}"
            )]

    except Exception as e:
        return [TextContent(
            type="text",
            text=f"Error executing {name}: {str(e)}"
        )]

async def main():
    """Run the MCP server"""
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())

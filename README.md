# NBA Betting Analysis MCP Server

A Model Context Protocol (MCP) server that fetches today's NBA games, player stats, and betting odds — then scores and recommends parlays using record-based edge analysis.

---

## Architecture

### `nba_mcp_server.py`
The MCP server. Contains the `NBADataFetcher` class and exposes 5 tools

| Tool | Description |
|---|---|
| `fetch_nba_games` | Today's NBA schedule with team records and game times |
| `fetch_nba_stats` | Last 5 game averages for all players on today's rosters |
| `fetch_betting_odds` | Moneyline, spread, and totals from multiple sportsbooks (filtered to today's games) |
| `build_parlay` | Builds two recommended parlays from today's top 5 games by team record |
| `analyze_bets` | Full report: game breakdowns, value edges, both parlays, and top players in form |

### `daily_report.py`
Calls `analyze_bets` and sends a formatted HTML email to Gmail. Scheduled via launchd to run daily at 12pm.

---

## How Parlay Building Works

### Game Selection
Before building parlays, games are filtered to the **top 5 by combined team win%** (home + away). This keeps the best matchups and limits the search space.

### Edge Scoring
Each game line (moneyline, spread, total) is scored using an adjusted edge formula:

```
adjusted_win_pct  = season win% + 0.03 (home team bonus)
raw_edge          = adjusted_win_pct − implied probability from odds
opponent_factor   = 0.5 + opponent_win_pct   (range 0.5–1.5)
final_edge        = raw_edge × opponent_factor
```

- **Home/away**: home teams get a +3pp boost reflecting the NBA's ~60% historical home win rate
- **Opponent strength**: edge is scaled up when beating the odds against a strong opponent

Moneyline and spread candidates are only included if `edge > 0.03`. Totals (over/under) are always included for parlay variety.

### Exhaustive Search
Rather than greedy selection, the server tries **every valid combination** of up to 4 legs (one leg per game) and picks the combination with the highest total edge that falls within the target odds range.

Two parlays are built from the same candidate pool:

| Parlay | Target Odds |
|---|---|
| Safer parlay | -150 to +100 |
| Longshot parlay | +200 to +300 |

---

## Data Sources

- **NBA Schedule + Records**: NBA Stats API (`stats.nba.com/stats/scoreboardV2`)
- **Player Stats**: NBA Stats API (`stats.nba.com/stats/leaguedashplayerstats`) — last 5 games
- **Betting Odds**: The Odds API — aggregates 20+ sportsbooks, markets: `h2h`, `spreads`, `totals`

---

## Setup

### 1. Install dependencies

```bash
pip install httpx mcp
```

### 2. Add your API key

In `nba_mcp_server.py`:

```python
ODDS_API_KEY = "your-odds-api-key-here"
```

Get a key at [the-odds-api.com](https://the-odds-api.com). Free tier: 500 requests/month.

### 3. Configure Claude Desktop

**Mac**: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "nba-betting": {
      "command": "python3",
      "args": ["/Users/neilgupta/Desktop/NBA-MCP/nba_mcp_server.py"]
    }
  }
}
```

Restart Claude Desktop after saving.

---

## Daily Email Report

`daily_report.py` runs `analyze_bets` and sends an HTML email containing:
- Game-by-game breakdown (record, implied probability, edge, best lines)
- Safer parlay recommendation (-150 to +100)
- Longshot parlay recommendation (+200 to +300)
- Top 20 players in form (ranked by composite form score)

### Gmail setup

In `daily_report.py`:
```python
GMAIL_ADDRESS = "your@gmail.com"
GMAIL_APP_PASSWORD = "your-app-password"
```

Generate an App Password at: Google Account → Security → 2-Step Verification → App Passwords.

### Schedule (launchd)

The report is scheduled via launchd (not cron) so it runs even if the Mac was asleep at 12pm — it fires as soon as the Mac wakes up.

Plist location: `~/Library/LaunchAgents/com.neilgupta.nba-report.plist`

To reload after changes:
```bash
launchctl unload ~/Library/LaunchAgents/com.neilgupta.nba-report.plist
launchctl load ~/Library/LaunchAgents/com.neilgupta.nba-report.plist
```

To run manually:
```bash
python3 /Users/neilgupta/Desktop/NBA-MCP/daily_report.py
```

---

## Player Form Score

Players are ranked by a fantasy-style composite score across their last 5 games:

```
form_score = PTS + (REB × 1.2) + (AST × 1.5) + (STL × 3) + (BLK × 3)
```

This is informational — it does not directly influence parlay picks.

---

## Important Notes

- **No player props**: The Odds API player prop markets require a paid plan. Parlays are built from game-level lines only (moneyline, spread, totals).
- **Today's games only**: All data is filtered to games scheduled for today.
- **Responsible gambling**: This tool is for informational and educational purposes. Not financial advice. Always gamble responsibly.
- **API limits**: The Odds API free tier has monthly limits. Monitor usage at [the-odds-api.com](https://the-odds-api.com).
- **Legal compliance**: Ensure sports betting is legal in your jurisdiction.

---

## Troubleshooting

**No games today**: NBA has off days — check the schedule (season runs October–June).

**Odds API limit reached**: Monthly quota hit. Wait until next month or upgrade your plan.

**Email not sending**: Verify your Gmail App Password and that 2-Step Verification is enabled.

**Parlay returns "N/A"**: No combination of today's top 5 games lands in the target odds range. More games on the slate improves coverage.

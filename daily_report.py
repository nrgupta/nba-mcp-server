#!/usr/bin/env python3
"""Daily NBA betting report — runs analyze_bets and sends to Gmail at 8AM"""

import asyncio
import smtplib
import sys
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

# Allow importing NBADataFetcher from the same directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nba_mcp_server import NBADataFetcher

GMAIL_ADDRESS = "neilg2001@gmail.com"
GMAIL_APP_PASSWORD = "dtqc caiq iddq igml"


def fmt_odds(price) -> str:
    if price is None:
        return "N/A"
    return f"+{price}" if price > 0 else str(price)


def fmt_pct(val) -> str:
    if val is None:
        return "N/A"
    return f"{val:.1%}"


def fmt_edge(val) -> str:
    if val is None:
        return "N/A"
    color = "#2e7d32" if val > 0 else "#c62828"
    return f'<span style="color:{color};font-weight:bold;">{val:+.1%}</span>'


def build_html(data: dict) -> str:
    date = data.get("analysis_date", datetime.now().strftime("%Y-%m-%d"))
    summary = data.get("summary", {})
    game_analyses = data.get("game_analyses", [])
    top_players = data.get("top_players_in_form", [])

    html = f"""
    <html><body style="font-family:Arial,sans-serif;max-width:720px;margin:auto;color:#222;">
    <h2 style="color:#1a73e8;">🏀 NBA Betting Report &mdash; {date}</h2>
    <p style="color:#555;">
      <b>{summary.get('total_games_analyzed', 0)}</b> games &nbsp;&bull;&nbsp;
      <b>{summary.get('games_with_value', 0)}</b> value opportunities &nbsp;&bull;&nbsp;
      <b>{summary.get('total_players_analyzed', 0)}</b> players tracked
    </p>
    <hr style="border:none;border-top:1px solid #ddd;">
    <h3 style="color:#1a73e8;">Game Analysis</h3>
    """

    if not game_analyses:
        html += "<p>No games with active pre-game odds today.</p>"

    for game in game_analyses:
        value = game.get("value_opportunity")
        border_color = "#4caf50" if value else "#ddd"
        home = game["home_team"]
        away = game["away_team"]
        lines = game.get("best_lines", {})
        ml = lines.get("moneyline", {})
        spread = lines.get("spread", {})
        total = lines.get("total", {})

        home_ml = ml.get("home") or {}
        away_ml = ml.get("away") or {}
        home_sp = spread.get("home") or {}
        away_sp = spread.get("away") or {}
        over = total.get("over") or {}
        under = total.get("under") or {}

        value_banner = ""
        if value:
            value_banner = f"""
            <p style="background:#e8f5e9;border-left:4px solid #4caf50;padding:8px 12px;margin:0 0 12px 0;border-radius:4px;">
              ✅ <b>Value opportunity:</b> {value['team']} &mdash; edge {value['edge']:+.1%} &mdash; {value['note']}
            </p>"""

        html += f"""
        <div style="border:1px solid {border_color};border-radius:8px;padding:16px;margin-bottom:20px;">
          <h4 style="margin:0 0 12px 0;">
            {game['matchup']}
            <span style="font-size:13px;color:#888;font-weight:normal;margin-left:8px;">{game.get('commence_time','')}</span>
          </h4>
          {value_banner}
          <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:12px;">
            <tr style="background:#f0f4ff;">
              <th style="padding:6px 8px;text-align:left;">Team</th>
              <th style="padding:6px;text-align:center;">Record</th>
              <th style="padding:6px;text-align:center;">Win% (record)</th>
              <th style="padding:6px;text-align:center;">Implied Prob</th>
              <th style="padding:6px;text-align:center;">Edge</th>
            </tr>
            <tr>
              <td style="padding:6px 8px;">{home['name']}</td>
              <td style="text-align:center;">{home['record'].get('wins','?')}-{home['record'].get('losses','?')}</td>
              <td style="text-align:center;">{fmt_pct(home['record'].get('win_pct'))}</td>
              <td style="text-align:center;">{fmt_pct(home.get('implied_win_prob'))}</td>
              <td style="text-align:center;">{fmt_edge(home.get('edge_vs_implied'))}</td>
            </tr>
            <tr style="background:#fafafa;">
              <td style="padding:6px 8px;">{away['name']}</td>
              <td style="text-align:center;">{away['record'].get('wins','?')}-{away['record'].get('losses','?')}</td>
              <td style="text-align:center;">{fmt_pct(away['record'].get('win_pct'))}</td>
              <td style="text-align:center;">{fmt_pct(away.get('implied_win_prob'))}</td>
              <td style="text-align:center;">{fmt_edge(away.get('edge_vs_implied'))}</td>
            </tr>
          </table>
          <p style="font-size:13px;color:#444;margin:0;line-height:1.8;">
            <b>Moneyline:</b>
              {home['name']} <b>{fmt_odds(home_ml.get('price'))}</b> ({home_ml.get('book','')}) &nbsp;&bull;&nbsp;
              {away['name']} <b>{fmt_odds(away_ml.get('price'))}</b> ({away_ml.get('book','')})<br>
            <b>Spread:</b>
              {home['name']} <b>{home_sp.get('point','N/A')}</b> @ {fmt_odds(home_sp.get('price'))} ({home_sp.get('book','')}) &nbsp;&bull;&nbsp;
              {away['name']} <b>{away_sp.get('point','N/A')}</b> @ {fmt_odds(away_sp.get('price'))} ({away_sp.get('book','')})<br>
            <b>Total:</b>
              Over <b>{over.get('point','N/A')}</b> @ {fmt_odds(over.get('price'))} ({over.get('book','')}) &nbsp;&bull;&nbsp;
              Under <b>{under.get('point','N/A')}</b> @ {fmt_odds(under.get('price'))} ({under.get('book','')})
          </p>
        </div>
        """

    # Parlay recommendations
    parlays = data.get("parlay_recommendations", {})
    safer_parlay = parlays.get("safer_parlay", {})
    longshot_parlay = parlays.get("longshot_parlay", {})

    MARKET_LABEL = {
        "moneyline": "Moneyline",
        "spread": "Spread",
        "total": "Game Total",
    }

    def build_parlay_html(parlay: dict, title: str, color: str, bg: str) -> str:
        legs = parlay.get("legs", [])
        parlay_odds = parlay.get("parlay_odds", "N/A")
        parlay_note = parlay.get("note", "")
        target_odds = parlay.get("target_odds", "")
        out = f"""
    <h3 style="color:{color};">{title}
      <span style="font-size:13px;font-weight:normal;color:#888;">target {target_odds}</span>
    </h3>
    <div style="border:2px solid {color};border-radius:8px;padding:16px;margin-bottom:20px;background:{bg};">
      <p style="margin:0 0 12px 0;font-size:15px;">
        <b>{parlay.get('num_legs', 0)}-leg parlay &mdash; Combined odds:
        <span style="color:{color};font-size:18px;">{parlay_odds}</span></b>
        &nbsp;({parlay.get('parlay_decimal','?')}x payout)
      </p>
        """
        if parlay_note:
            out += f'<p style="color:#e65100;font-size:12px;margin:0 0 10px 0;">⚠️ {parlay_note}</p>'
        for i, leg in enumerate(legs, 1):
            market_label = MARKET_LABEL.get(leg.get("market", ""), leg.get("market", ""))
            reasoning = leg.get("reasoning", "")
            price = leg.get("price")
            out += f"""
      <div style="border-top:1px solid #ddd;padding:8px 0;">
        <b>Leg {i}:</b> {leg.get('player','')} &mdash;
        <b>{leg.get('side','')} {leg.get('line') or ''} {market_label}</b>
        @ <b>{fmt_odds(price)}</b> ({leg.get('book','')})<br>
        <span style="font-size:12px;color:#555;">{reasoning}</span>
      </div>"""
        if not legs:
            out += '<p style="color:#888;">No combination of legs lands in this range with today\'s slate.</p>'
        out += "</div>"
        return out

    html += build_parlay_html(safer_parlay,  "Safer Parlay",   "#1a73e8", "#f0f4ff")
    html += build_parlay_html(longshot_parlay, "Longshot Parlay", "#6a1b9a", "#f3e5f5")

    # Player form table
    html += """
    <h3 style="color:#1a73e8;">Top Players in Form (Last 5 Games)</h3>
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      <tr style="background:#1a73e8;color:white;">
        <th style="padding:7px 4px;">#</th>
        <th style="padding:7px 8px;text-align:left;">Player</th>
        <th style="padding:7px 4px;">Team</th>
        <th style="padding:7px 4px;">PTS</th>
        <th style="padding:7px 4px;">REB</th>
        <th style="padding:7px 4px;">AST</th>
        <th style="padding:7px 4px;">STL</th>
        <th style="padding:7px 4px;">BLK</th>
        <th style="padding:7px 4px;">FG%</th>
        <th style="padding:7px 4px;">Score</th>
      </tr>
    """

    for i, p in enumerate(top_players, 1):
        bg = "#f5f5f5" if i % 2 == 0 else "white"
        fg_pct = p.get("fg_pct")
        fg_str = f"{fg_pct:.0%}" if fg_pct is not None else "N/A"
        html += f"""
      <tr style="background:{bg};">
        <td style="padding:5px 4px;text-align:center;color:#888;">{i}</td>
        <td style="padding:5px 8px;">{p.get('player_name','')}</td>
        <td style="text-align:center;">{p.get('team','')}</td>
        <td style="text-align:center;">{p.get('points','')}</td>
        <td style="text-align:center;">{p.get('rebounds','')}</td>
        <td style="text-align:center;">{p.get('assists','')}</td>
        <td style="text-align:center;">{p.get('steals','')}</td>
        <td style="text-align:center;">{p.get('blocks','')}</td>
        <td style="text-align:center;">{fg_str}</td>
        <td style="text-align:center;font-weight:bold;">{p.get('form_score','')}</td>
      </tr>"""

    html += """
    </table>
    <hr style="border:none;border-top:1px solid #ddd;margin-top:24px;">
    <p style="font-size:11px;color:#aaa;">Generated by NBA MCP Server &mdash; For informational purposes only. Not financial advice.</p>
    </body></html>
    """
    return html


def send_email(html_body: str, date: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🏀 NBA Betting Report — {date}"
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = GMAIL_ADDRESS
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, GMAIL_ADDRESS, msg.as_string())

    print(f"[{datetime.now()}] Email sent to {GMAIL_ADDRESS}")


async def main():
    print(f"[{datetime.now()}] Fetching NBA betting analysis...")
    fetcher = NBADataFetcher()
    data = await fetcher.analyze_bets()
    date = data.get("analysis_date", datetime.now().strftime("%Y-%m-%d"))
    html = build_html(data)
    send_email(html, date)


if __name__ == "__main__":
    asyncio.run(main())

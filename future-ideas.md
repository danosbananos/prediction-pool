# Prediction Pool — Future Ideas

Ideas for future versions, collected during initial planning. Not in scope for v1.

---

## Enhanced Match Data ✅ DONE
- ~~Collect data and images on specific fights and participants~~
- ~~Pull fight history for each fighter (record, weight class, recent results)~~
- ~~Show fighter stats alongside prediction interface~~
- Auto-fetched from Wikipedia/Wikidata on match creation
- Manual override available in settings
- Display current odds on each fight → see **Odds & Scoring** below

## Odds & Scoring ✅ DONE
- ~~Fetch betting odds from external sources (hybrid: auto + manual fallback)~~
- ~~Display decimal (European) odds on each match card~~
- ~~New scoring: **score = odds × multiplier** (replaces old fixed-point system)~~
- ~~Rename "points" to "multiplier" throughout the app~~
- Auto-fetch via The Odds API (set `ODDS_API_KEY` env var), manual entry fallback
- CSV upload for bulk-importing matches with odds and fighter data

## Automatic Result Collection
- After each fight is over, automatically fetch and enter the result
- Sources: official Glory results page, sports APIs, or web scraping
- Push notification or live update when a result comes in

## AI-Generated Avatars
- Allow users to upload a photo of themselves
- Use Claude's image capabilities to generate a fun, kickboxing-themed avatar
- Display avatars on the leaderboard and throughout the app
- Could replace the PIN-based auth with an avatar-picker system

## Native Mobile Apps
- Wrap the web app in a native shell (React Native, Flutter, or PWA)
- iOS App Store + Google Play Store distribution
- Push notifications for pool updates, fight results, standings changes

## Enhanced Authentication
- Avatar-picker auth (choose your icon from a grid)
- Pattern swipe unlock
- Optional OAuth (Google, Apple) for users who want it
- "Remember me" on device

## Pool Features
- Pool-level passcode for access control
- Draw/no-contest support with configurable point rules
- Multiple pools per tournament
- Pool templates (pre-fill common match formats)
- Pool chat / trash talk section

## Social Features
- Historical leaderboard across multiple tournaments
- "Win streak" badges and achievements
- Share results to social media
- Invite friends via WhatsApp/iMessage deep links

## Bugfixes & Improvements
- Add a favicon
- Fix "None" appearing before fighter names
- Fix flags not displaying at fighter names (possibly related to the "None" issue)
- Review the fetch fighter data feature — currently not producing results
- Investigate deployment without re-creating the database (likely cause of lost pool data on last deploy)

## Data & Analytics
- Prediction accuracy stats per user over time
- Most/least predictable fighters
- Upset tracker (when underdogs win)
- Head-to-head record between friends across pools

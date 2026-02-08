# Prediction Pool — Future Ideas

Ideas for future versions, collected during initial planning. Not in scope for v1.

---

## Enhanced Match Data
- Collect data and images on specific fights and participants
- Pull fight history for each fighter (record, weight class, recent results)
- Display current odds on each fight (from public sources)
- Show fighter stats alongside prediction interface

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
- Public pool directory: browse and view all pools (read-only for non-participants)
- Creator-only editing: pool creator can lock editing so only they can modify the pool (default behavior)
- Next-round placeholder fights: add fights where fighters are "winner of fight X vs Y", with odds to be filled in later once the winners are known

## Social Features
- Historical leaderboard across multiple tournaments
- "Win streak" badges and achievements
- Share results to social media
- Invite friends via WhatsApp/iMessage deep links

## Data & Analytics
- Prediction accuracy stats per user over time
- Most/least predictable fighters
- Upset tracker (when underdogs win)
- Head-to-head record between friends across pools

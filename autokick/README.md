# AutoKick

Automatically kicks members who never receive any of one or more designated "verified" roles (e.g. `Member`) within a configurable number of days after joining.

Built for servers that use a ticket-based approval/verification flow (e.g. [AAA3A's Tickets cog](https://github.com/AAA3A-AAA3A/AAA3A-cogs)) where staff manually grant a role once someone is approved. AutoKick doesn't hook into the ticket system directly — it just watches for the presence of the role, so it works with any verification method that ends in "give the user a role."

## How it works

Every 30 minutes (and on-demand via `checknow`), the cog fetches the **live member list directly from Discord's API** (not the gateway cache, to avoid missing inactive/older members) and checks each non-bot member:

- Do they have any of the configured verified roles? → skip.
- Have they been in the server for fewer than the configured number of days? → skip.
- Otherwise → optionally DM them a notice, then kick, then log it to your configured log channel.

**Note on rejoins:** the check is based on Discord's `joined_at` timestamp, which resets whenever a member leaves and rejoins. If someone rejoins, they get a fresh grace period starting from the rejoin date — the cog does not currently track original first-seen dates independently of Discord's own timestamp.

## Requirements

- **Server Members Intent** must be enabled for your bot in the [Discord Developer Portal](https://discord.com/developers/applications) (Bot page → Privileged Gateway Intents). Without this, member fetching will fail.
- The bot needs the **Kick Members** permission.
- The bot's role must sit **above** the roles of any members it needs to kick, in Server Settings → Roles.

## Configuration

All commands are under `[p]autokick` and require the **Kick Members** permission (or admin) to run.

| Command | Description |
|---|---|
| `[p]autokick role add <role>` | Add a role that marks a member as verified. Members with *any* verified role are skipped. |
| `[p]autokick role remove <role>` | Remove a role from the verified roles list. |
| `[p]autokick role list` | List the currently configured verified roles. |
| `[p]autokick days <number>` | Days a member has to get verified before being kicked (default: 3). |
| `[p]autokick toggle <true/false>` | Enable or disable auto-kicking. |
| `[p]autokick logchannel [channel]` | Set (or clear, if omitted) a channel for kick logs. |
| `[p]autokick dmtoggle <true/false>` | Enable/disable DM'ing members before they're kicked. |
| `[p]autokick dmmessage [message]` | Set (or reset, if omitted) the DM text. Supports `{guild}` and `{days}` placeholders. |
| `[p]autokick status` | Show current configuration for this server. |
| `[p]autokick checknow` | Run a check immediately instead of waiting for the next scheduled loop. |
| `[p]autokick checkuser <member>` | Debug: show what AutoKick sees for one specific member (join date, role status, kick eligibility). |

### Example setup

```
[p]autokick role add @Member
[p]autokick role add @Trusted
[p]autokick days 3
[p]autokick logchannel #mod-log
[p]autokick dmtoggle true
[p]autokick toggle true
```

## ⚠️ Before enabling on an existing server

Turning the cog on doesn't "start the clock from today" — it immediately sweeps **every current member** who already fails the check (no role + joined more than N days ago), including any long-standing unverified accounts. If your server has a backlog of old unverified members, they'll all be caught in the first pass.

Before flipping `toggle true` on a live server, it's worth running `[p]autokick checknow` with a log channel set first, or spot-checking a few members with `[p]autokick checkuser`, so you know what you're about to kick.

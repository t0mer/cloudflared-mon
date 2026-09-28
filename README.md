# cloudflared-mon

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docker Pulls](https://img.shields.io/docker/pulls/techblog/cloudflared-mon)](https://hub.docker.com/r/techblog/cloudflared-mon)

Cloudflared-Mon is a small Python service that monitors the health of your [Cloudflare Tunnels](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) (`cloudflared`). It polls the Cloudflare API on a fixed interval and sends a notification through [Apprise](https://github.com/caronc/apprise) (Telegram, Discord, Slack, email, Home Assistant, and many more) whenever a tunnel's status changes, for example from `healthy` to `down`.

## Table of Contents

- [Features](#features)
- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Notifications](#notifications)
- [Security notes](#security-notes)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [Components and frameworks](#components-and-frameworks)
- [Contributing](#contributing)
- [License](#license)

## Features

- Monitors the non-deleted Cloudflare Tunnels in a Cloudflare account (first page of the API result only, see [Limitations](#limitations)).
- Checks tunnel status on a configurable interval (default: every 60 seconds).
- Sends a notification when a tunnel's status changes (e.g. `healthy` → `degraded`, `down` → `healthy`), with a ✅ icon when the new status is `healthy` and ❌ otherwise.
- Supports any notification service Apprise supports; several targets can be configured at once.
- Persists the last known state of each tunnel in a local SQLite database, so restarts don't trigger duplicate alerts.
- Authenticates with a scoped, read-only Cloudflare API token (Bearer auth).
- Multi-arch Docker image: `linux/amd64`, `linux/arm64`, `linux/arm/v7`.

## How it works

```mermaid
flowchart LR
    S[Scheduler<br/>every CHECK_INTERVALS s] --> A[GET /accounts/:id/cfd_tunnel?is_deleted=false]
    A --> C{Tunnel known?}
    C -- no --> I[Store current status<br/>in SQLite, no alert]
    C -- yes --> D{Status changed?}
    D -- no --> N[Do nothing]
    D -- yes --> P[Send Apprise notification<br/>and update SQLite]
```

1. Every `CHECK_INTERVALS` seconds the service calls the Cloudflare API endpoint
   [`GET /accounts/{account_id}/cfd_tunnel?is_deleted=false`](https://developers.cloudflare.com/api/resources/zero_trust/subresources/tunnels/methods/list/)
   with your API token.
2. The first time a tunnel is seen, its current status is saved to the SQLite database (`/app/db/cf.db`) without sending a notification.
3. On later checks, the current status is compared with the stored one. If it differs, a notification is sent to every configured Apprise target and the stored status is updated.

The first check runs one interval after startup, not immediately. The service has no web UI and does not listen on any port.

### Limitations

- The tunnel list is requested once per check without pagination, so only the first page returned by the Cloudflare API is monitored (the API's default page size applies). Accounts with more tunnels than fit on one page are only partially monitored.
- Newly created tunnels are recorded silently, and deleted tunnels are ignored; only status changes of known tunnels trigger notifications.

Notification format:

- **Title:** `Tunnel status changed`
- **Body:** `✅ The tunnel <tunnel name> Status changed from <old status> to <new status> ✅` (❌ instead of ✅ when the new status is not `healthy`)

## Requirements

- Docker (or Python 3 for running from source).
- A Cloudflare account with one or more Cloudflare Tunnels.
- Your Cloudflare **Account ID**. It is part of the dashboard URL (`https://dash.cloudflare.com/<account_id>`), see [Find account and zone IDs](https://developers.cloudflare.com/fundamentals/setup/find-account-and-zone-ids/).
- A Cloudflare **API token** that can read your tunnels. The only API call the service makes is the account-level tunnel list, so a token with the **Account → Cloudflare Tunnel → Read** permission is enough. See [Create an API token](https://developers.cloudflare.com/fundamentals/api/get-started/create-token/) and [API token permissions](https://developers.cloudflare.com/fundamentals/api/reference/permissions/).
- At least one Apprise notification URL (optional, but without one no alerts are sent).

## Installation

### Docker Compose

The image is published on Docker Hub as [`techblog/cloudflared-mon`](https://hub.docker.com/r/techblog/cloudflared-mon) for `linux/amd64`, `linux/arm64` and `linux/arm/v7`.

```yaml
services:
  cloudflared-mon:
    image: techblog/cloudflared-mon:latest
    container_name: cloudflared-mon
    restart: always
    environment:
      - CHECK_INTERVALS=60
      - NOTIFIERS=tgram://bottoken/ChatID
      - CF_TOKEN=your-cloudflare-api-token
      - CF_ACCOUNT_ID=your-cloudflare-account-id
    volumes:
      - ./cloudflared-mon/db:/app/db
```

```bash
docker compose up -d
docker compose logs -f cloudflared-mon
```

The repository also contains a [`docker-compose.yaml`](docker-compose.yaml) template. It is blank and **does not work as shipped**: its line `CHECK_INTERVALS= #In seconds, ...` is parsed as an empty value (the `#` part is a YAML comment), which crashes the service at startup. Fill in every value (or remove the `CHECK_INTERVALS` line) before using it. Its service is named `cfmon`, so use `docker compose logs -f cfmon` with that file.

### Docker

```bash
docker run -d --name cloudflared-mon --restart always \
  -e CF_TOKEN=your-cloudflare-api-token \
  -e CF_ACCOUNT_ID=your-cloudflare-account-id \
  -e NOTIFIERS="tgram://bottoken/ChatID" \
  -e CHECK_INTERVALS=60 \
  -v "$(pwd)/cloudflared-mon/db:/app/db" \
  techblog/cloudflared-mon:latest
```

### Volumes

| Container path | Purpose |
| -------------- | ------- |
| `/app/db` | SQLite database (`cf.db`) holding the last known status of each tunnel. Mount it to keep the state across updates and restarts. |

## Configuration

All configuration is done with environment variables.

| Variable | Required | Default (Docker image) | Description |
| -------- | -------- | ---------------------- | ----------- |
| `CF_TOKEN` | Yes | _(empty)_ | Cloudflare API token, sent as `Authorization: Bearer <token>`. Use a read-only token (see [Requirements](#requirements)). |
| `CF_ACCOUNT_ID` | Yes | _(empty)_ | Cloudflare Account ID whose tunnels are monitored. |
| `NOTIFIERS` | No | _(empty)_ | One or more [Apprise URLs](https://github.com/caronc/apprise/wiki), separated by spaces. When empty, status changes are only tracked, no notifications are sent. |
| `CHECK_INTERVALS` | No | `60` | Time in seconds between checks. Must be an integer. |
| `CF_EMAIL` | No | _(empty)_ | Legacy setting. It is defined in the image but **not used** by the current code (authentication uses the API token only). |

> **Note:** The defaults above come from the Dockerfile. When running from source there are no defaults: `CF_TOKEN`, `CF_ACCOUNT_ID`, `NOTIFIERS` and `CHECK_INTERVALS` must all be set (use `NOTIFIERS=""` for no notifications), otherwise the service crashes at startup.

## Notifications

Notifications are sent with [Apprise](https://github.com/caronc/apprise). Set `NOTIFIERS` to one or more Apprise URLs separated by spaces, for example:

```bash
NOTIFIERS="tgram://bottoken/ChatID discord://webhook_id/webhook_token"
```

### Example: Telegram

To get Telegram alerts, create a Telegram bot and use the Apprise URL `tgram://<bot_token>/<chat_id>`.

Open [Telegram](https://web.telegram.org/), sign in to your account or create a new one.

Enter @BotFather in the search tab and choose this bot (official Telegram bots have a blue checkmark beside their name).

[![@BotFather](https://github.com/t0mer/voicy/blob/main/screenshots/scr1-min.png?raw=true "@BotFather")](https://github.com/t0mer/voicy/blob/main/screenshots/scr1-min.png?raw=true "@BotFather")

Click "Start" to activate the BotFather bot.

[![@start](https://github.com/t0mer/voicy/blob/main/screenshots/scr2-min.png?raw=true "@start")](https://github.com/t0mer/voicy/blob/main/screenshots/scr2-min.png?raw=true "@start")

In response, you receive a list of commands to manage bots.
Choose or type the `/newbot` command and send it.

[![@newbot](https://github.com/t0mer/voicy/blob/main/screenshots/scr3-min.png?raw=true "@newbot")](https://github.com/t0mer/voicy/blob/main/screenshots/scr3-min.png?raw=true "@newbot")

Choose a name for your bot (your subscribers will see it in the conversation) and a username (the bot can be found by its username in searches). The username must be unique and end with the word "bot".

[![@username](https://github.com/t0mer/voicy/blob/main/screenshots/scr4-min.png?raw=true "@username")](https://github.com/t0mer/voicy/blob/main/screenshots/scr4-min.png?raw=true "@username")

After you choose a suitable name, the bot is created. You will receive a message with a link to your bot `t.me/<bot_username>`, the bot token, recommendations to set up a profile picture and description, and a list of commands to manage your new bot.

[![@bot_username](https://github.com/t0mer/voicy/blob/main/screenshots/scr5-min.png?raw=true "@bot_username")](https://github.com/t0mer/voicy/blob/main/screenshots/scr5-min.png?raw=true "@bot_username")

Send a message to your new bot, then use the bot token and your chat ID in the Apprise URL. See the [Apprise Telegram wiki page](https://github.com/caronc/apprise/wiki/Notify_telegram) for details on finding the chat ID.

### Supported notification services

This section lists popular services supported by Apprise. [Check out the Apprise wiki for the full list and details on each service](https://github.com/caronc/apprise/wiki).

> **Note:** The image runs Python 3.6 (Ubuntu 18.04), so pip installs the newest Apprise release that still supports Python 3.6, not the latest release, so the exact set of services and URL formats depends on the installed Apprise version. Some services below may have been renamed or retired upstream; always check the Apprise wiki.

The table below lists the services and some example service URLs. Click on any of the services to get more details on how to configure it.

| Notification Service | Service ID | Default Port | Example Syntax |
| -------------------- | ---------- | ------------ | -------------- |
| [Apprise API](https://github.com/caronc/apprise/wiki/Notify_apprise_api)  | apprise:// or apprises:// | (TCP) 80 or 443 | apprise://hostname/Token
| [AWS SES](https://github.com/caronc/apprise/wiki/Notify_ses)  | ses://   | (TCP) 443   | ses://user@domain/AccessKeyID/AccessSecretKey/RegionName<br/>ses://user@domain/AccessKeyID/AccessSecretKey/RegionName/email1/email2/emailN
| [Boxcar](https://github.com/caronc/apprise/wiki/Notify_boxcar)  | boxcar://   | (TCP) 443   | boxcar://hostname<br />boxcar://hostname/@tag<br/>boxcar://hostname/device_token<br />boxcar://hostname/device_token1/device_token2/device_tokenN<br />boxcar://hostname/@tag/@tag2/device_token
| [Discord](https://github.com/caronc/apprise/wiki/Notify_discord)  | discord://   | (TCP) 443   | discord://webhook_id/webhook_token<br />discord://avatar@webhook_id/webhook_token
| [Emby](https://github.com/caronc/apprise/wiki/Notify_emby)  | emby:// or embys:// | (TCP) 8096 | emby://user@hostname/<br />emby://user:password@hostname
| [Enigma2](https://github.com/caronc/apprise/wiki/Notify_enigma2)  | enigma2:// or enigma2s:// | (TCP) 80 or 443 | enigma2://hostname
| [Faast](https://github.com/caronc/apprise/wiki/Notify_faast) | faast://    | (TCP) 443    | faast://authorizationtoken
| [FCM](https://github.com/caronc/apprise/wiki/Notify_fcm) | fcm://    | (TCP) 443    | fcm://project@apikey/DEVICE_ID<br />fcm://project@apikey/#TOPIC<br/>fcm://project@apikey/DEVICE_ID1/#topic1/#topic2/DEVICE_ID2/
| [Flock](https://github.com/caronc/apprise/wiki/Notify_flock) | flock://    | (TCP) 443    | flock://token<br/>flock://botname@token<br/>flock://app_token/u:userid<br/>flock://app_token/g:channel_id<br/>flock://app_token/u:userid/g:channel_id
| [Gitter](https://github.com/caronc/apprise/wiki/Notify_gitter) | gitter://    | (TCP) 443    | gitter://token/room<br/>gitter://token/room1/room2/roomN
| [Google Chat](https://github.com/caronc/apprise/wiki/Notify_googlechat) | gchat://    | (TCP) 443    | gchat://workspace/key/token
| [Gotify](https://github.com/caronc/apprise/wiki/Notify_gotify) | gotify:// or gotifys://   | (TCP) 80 or 443    | gotify://hostname/token<br />gotifys://hostname/token?priority=high
| [Growl](https://github.com/caronc/apprise/wiki/Notify_growl)  | growl://   | (UDP) 23053   | growl://hostname<br />growl://hostname:portno<br />growl://password@hostname<br />growl://password@hostname:port<br />**Note**: you can also use the get parameter _version_ which can allow the growl request to behave using the older v1.x protocol. An example would look like: growl://hostname?version=1
| [Home Assistant](https://github.com/caronc/apprise/wiki/Notify_homeassistant)       | hassio:// or hassios://   | (TCP) 8123 or 443 | hassio://hostname/accesstoken<br />hassio://user@hostname/accesstoken<br />hassio://user:password@hostname:port/accesstoken<br />hassio://hostname/optional/path/accesstoken
| [IFTTT](https://github.com/caronc/apprise/wiki/Notify_ifttt) | ifttt://    | (TCP) 443    | ifttt://webhooksID/Event<br />ifttt://webhooksID/Event1/Event2/EventN<br/>ifttt://webhooksID/Event1/?+Key=Value<br/>ifttt://webhooksID/Event1/?-Key=value1
| [Join](https://github.com/caronc/apprise/wiki/Notify_join) | join://   | (TCP) 443    | join://apikey/device<br />join://apikey/device1/device2/deviceN/<br />join://apikey/group<br />join://apikey/groupA/groupB/groupN<br />join://apikey/DeviceA/groupA/groupN/DeviceN/
| [KODI](https://github.com/caronc/apprise/wiki/Notify_kodi) | kodi:// or kodis://    | (TCP) 8080 or 443   | kodi://hostname<br />kodi://user@hostname<br />kodi://user:password@hostname:port
| [Kumulos](https://github.com/caronc/apprise/wiki/Notify_kumulos) | kumulos:// | (TCP) 443 | kumulos://apikey/serverkey
| [LaMetric Time](https://github.com/caronc/apprise/wiki/Notify_lametric) | lametric:// | (TCP) 443 | lametric://apikey@device_ipaddr<br/>lametric://apikey@hostname:port<br/>lametric://client_id@client_secret
| [Mailgun](https://github.com/caronc/apprise/wiki/Notify_mailgun) | mailgun:// | (TCP) 443 | mailgun://user@hostname/apikey<br />mailgun://user@hostname/apikey/email<br />mailgun://user@hostname/apikey/email1/email2/emailN<br />mailgun://user@hostname/apikey/?name="From%20User"
| [Matrix](https://github.com/caronc/apprise/wiki/Notify_matrix) | matrix:// or matrixs://  | (TCP) 80 or 443 | matrix://hostname<br />matrix://user@hostname<br />matrixs://user:pass@hostname:port/#room_alias<br />matrixs://user:pass@hostname:port/!room_id<br />matrixs://user:pass@hostname:port/#room_alias/!room_id/#room2<br />matrixs://token@hostname:port/?webhook=matrix<br />matrix://user:token@hostname/?webhook=slack&format=markdown
| [Mattermost](https://github.com/caronc/apprise/wiki/Notify_mattermost) | mmost:// or mmosts:// | (TCP) 8065 | mmost://hostname/authkey<br />mmost://hostname:80/authkey<br />mmost://user@hostname:80/authkey<br />mmost://hostname/authkey?channel=channel<br />mmosts://hostname/authkey<br />mmosts://user@hostname/authkey<br />
| [Microsoft Teams](https://github.com/caronc/apprise/wiki/Notify_msteams) | msteams://  | (TCP) 443   | msteams://TokenA/TokenB/TokenC/
| [MQTT](https://github.com/caronc/apprise/wiki/Notify_mqtt) | mqtt://  or mqtts:// | (TCP) 1883 or 8883   | mqtt://hostname/topic<br />mqtt://user@hostname/topic<br />mqtts://user:pass@hostname:9883/topic
| [Nextcloud](https://github.com/caronc/apprise/wiki/Notify_nextcloud) | ncloud:// or nclouds:// | (TCP) 80 or 443 | ncloud://adminuser:pass@host/User<br/>nclouds://adminuser:pass@host/User1/User2/UserN
| [NextcloudTalk](https://github.com/caronc/apprise/wiki/Notify_nextcloudtalk) | nctalk:// or nctalks:// | (TCP) 80 or 443 | nctalk://user:pass@host/RoomId<br/>nctalks://user:pass@host/RoomId1/RoomId2/RoomIdN
| [Notica](https://github.com/caronc/apprise/wiki/Notify_notica) | notica://  | (TCP) 443   | notica://Token/
| [Notifico](https://github.com/caronc/apprise/wiki/Notify_notifico) | notifico://  | (TCP) 443   | notifico://ProjectID/MessageHook/
| [Office 365](https://github.com/caronc/apprise/wiki/Notify_office365) | o365://  | (TCP) 443   | o365://TenantID:AccountEmail/ClientID/ClientSecret<br />o365://TenantID:AccountEmail/ClientID/ClientSecret/TargetEmail<br />o365://TenantID:AccountEmail/ClientID/ClientSecret/TargetEmail1/TargetEmail2/TargetEmailN
| [OneSignal](https://github.com/caronc/apprise/wiki/Notify_onesignal) | onesignal:// | (TCP) 443 | onesignal://AppID@APIKey/PlayerID<br/>onesignal://TemplateID:AppID@APIKey/UserID<br/>onesignal://AppID@APIKey/#IncludeSegment<br/>onesignal://AppID@APIKey/Email
| [Opsgenie](https://github.com/caronc/apprise/wiki/Notify_opsgenie) | opsgenie:// | (TCP) 443 | opsgenie://APIKey<br/>opsgenie://APIKey/UserID<br/>opsgenie://APIKey/#Team<br/>opsgenie://APIKey/\*Schedule<br/>opsgenie://APIKey/^Escalation
| [ParsePlatform](https://github.com/caronc/apprise/wiki/Notify_parseplatform) | parsep:// or parseps:// | (TCP) 80 or 443 | parsep://AppID:MasterKey@Hostname<br/>parseps://AppID:MasterKey@Hostname
| [PopcornNotify](https://github.com/caronc/apprise/wiki/Notify_popcornnotify) | popcorn://  | (TCP) 443   | popcorn://ApiKey/ToPhoneNo<br/>popcorn://ApiKey/ToPhoneNo1/ToPhoneNo2/ToPhoneNoN/<br/>popcorn://ApiKey/ToEmail<br/>popcorn://ApiKey/ToEmail1/ToEmail2/ToEmailN/<br/>popcorn://ApiKey/ToPhoneNo1/ToEmail1/ToPhoneNoN/ToEmailN
| [Prowl](https://github.com/caronc/apprise/wiki/Notify_prowl) | prowl://   | (TCP) 443    | prowl://apikey<br />prowl://apikey/providerkey
| [PushBullet](https://github.com/caronc/apprise/wiki/Notify_pushbullet) | pbul://    | (TCP) 443    | pbul://accesstoken<br />pbul://accesstoken/#channel<br/>pbul://accesstoken/A_DEVICE_ID<br />pbul://accesstoken/email@address.com<br />pbul://accesstoken/#channel/#channel2/email@address.net/DEVICE
| [Pushjet](https://github.com/caronc/apprise/wiki/Notify_pushjet) | pjet:// or pjets:// | (TCP) 80 or 443 | pjet://hostname/secret<br />pjet://hostname:port/secret<br />pjets://secret@hostname/secret<br />pjets://hostname:port/secret
| [Push (Techulus)](https://github.com/caronc/apprise/wiki/Notify_techulus) | push://    | (TCP) 443    | push://apikey/
| [Pushed](https://github.com/caronc/apprise/wiki/Notify_pushed) | pushed://    | (TCP) 443    | pushed://appkey/appsecret/<br/>pushed://appkey/appsecret/#ChannelAlias<br/>pushed://appkey/appsecret/#ChannelAlias1/#ChannelAlias2/#ChannelAliasN<br/>pushed://appkey/appsecret/@UserPushedID<br/>pushed://appkey/appsecret/@UserPushedID1/@UserPushedID2/@UserPushedIDN
| [Pushover](https://github.com/caronc/apprise/wiki/Notify_pushover)  | pover://   | (TCP) 443   | pover://user@token<br />pover://user@token/DEVICE<br />pover://user@token/DEVICE1/DEVICE2/DEVICEN<br />**Note**: you must specify both your user_id and token
| [PushSafer](https://github.com/caronc/apprise/wiki/Notify_pushsafer)  | psafer:// or psafers://  | (TCP) 80 or 443  | psafer://privatekey<br />psafers://privatekey/DEVICE<br />psafer://privatekey/DEVICE1/DEVICE2/DEVICEN
| [Reddit](https://github.com/caronc/apprise/wiki/Notify_reddit) | reddit:// | (TCP) 443   | reddit://user:password@app_id/app_secret/subreddit<br />reddit://user:password@app_id/app_secret/sub1/sub2/subN
| [Rocket.Chat](https://github.com/caronc/apprise/wiki/Notify_rocketchat) | rocket:// or rockets://  | (TCP) 80 or 443   | rocket://user:password@hostname/RoomID/Channel<br />rockets://user:password@hostname:443/#Channel1/#Channel1/RoomID<br />rocket://user:password@hostname/#Channel<br />rocket://webhook@hostname<br />rockets://webhook@hostname/@User/#Channel
| [Ryver](https://github.com/caronc/apprise/wiki/Notify_ryver) | ryver://  | (TCP) 443   | ryver://Organization/Token<br />ryver://botname@Organization/Token
| [SendGrid](https://github.com/caronc/apprise/wiki/Notify_sendgrid) | sendgrid://  | (TCP) 443   | sendgrid://APIToken:FromEmail/<br />sendgrid://APIToken:FromEmail/ToEmail<br />sendgrid://APIToken:FromEmail/ToEmail1/ToEmail2/ToEmailN/
| [ServerChan](https://github.com/caronc/apprise/wiki/Notify_serverchan) | serverchan://   | (TCP) 443    | serverchan://token/
| [SimplePush](https://github.com/caronc/apprise/wiki/Notify_simplepush) | spush://   | (TCP) 443    | spush://apikey<br />spush://salt:password@apikey<br />spush://apikey?event=Apprise
| [Slack](https://github.com/caronc/apprise/wiki/Notify_slack) | slack://  | (TCP) 443   | slack://TokenA/TokenB/TokenC/<br />slack://TokenA/TokenB/TokenC/Channel<br />slack://botname@TokenA/TokenB/TokenC/Channel<br />slack://user@TokenA/TokenB/TokenC/Channel1/Channel2/ChannelN
| [SMTP2Go](https://github.com/caronc/apprise/wiki/Notify_smtp2go) | smtp2go:// | (TCP) 443 | smtp2go://user@hostname/apikey<br />smtp2go://user@hostname/apikey/email<br />smtp2go://user@hostname/apikey/email1/email2/emailN<br />smtp2go://user@hostname/apikey/?name="From%20User"
| [Streamlabs](https://github.com/caronc/apprise/wiki/Notify_streamlabs) | strmlabs:// | (TCP) 443 | strmlabs://AccessToken/<br/>strmlabs://AccessToken/?name=name&identifier=identifier&amount=0&currency=USD
| [SparkPost](https://github.com/caronc/apprise/wiki/Notify_sparkpost) | sparkpost:// | (TCP) 443 | sparkpost://user@hostname/apikey<br />sparkpost://user@hostname/apikey/email<br />sparkpost://user@hostname/apikey/email1/email2/emailN<br />sparkpost://user@hostname/apikey/?name="From%20User"
| [Spontit](https://github.com/caronc/apprise/wiki/Notify_spontit) | spontit://  | (TCP) 443   | spontit://UserID@APIKey/<br />spontit://UserID@APIKey/Channel<br />spontit://UserID@APIKey/Channel1/Channel2/ChannelN
| [Syslog](https://github.com/caronc/apprise/wiki/Notify_syslog) | syslog://  | (UDP) 514 (_if hostname specified_) | syslog://<br />syslog://Facility<br />syslog://hostname<br />syslog://hostname/Facility
| [Telegram](https://github.com/caronc/apprise/wiki/Notify_telegram) | tgram://  | (TCP) 443   | tgram://bottoken/ChatID<br />tgram://bottoken/ChatID1/ChatID2/ChatIDN
| [Twitter](https://github.com/caronc/apprise/wiki/Notify_twitter) | twitter://  | (TCP) 443   | twitter://CKey/CSecret/AKey/ASecret<br/>twitter://user@CKey/CSecret/AKey/ASecret<br/>twitter://CKey/CSecret/AKey/ASecret/User1/User2/User2<br/>twitter://CKey/CSecret/AKey/ASecret?mode=tweet
| [Twist](https://github.com/caronc/apprise/wiki/Notify_twist) | twist://  | (TCP) 443   | twist://password:login<br/>twist://password:login/#channel<br/>twist://password:login/#team:channel<br/>twist://password:login/#team:channel1/channel2/#team3:channel
| [XBMC](https://github.com/caronc/apprise/wiki/Notify_xbmc) | xbmc:// or xbmcs://    | (TCP) 8080 or 443   | xbmc://hostname<br />xbmc://user@hostname<br />xbmc://user:password@hostname:port
| [XMPP](https://github.com/caronc/apprise/wiki/Notify_xmpp) | xmpp:// or xmpps://    | (TCP) 5222 or 5223   | xmpp://user:password@hostname<br />xmpps://user:password@hostname:port?jid=user@hostname/resource<br/>xmpps://user:password@hostname/target@myhost, target2@myhost/resource
| [Webex Teams (Cisco)](https://github.com/caronc/apprise/wiki/Notify_wxteams) | wxteams://  | (TCP) 443   | wxteams://Token
| [Zulip Chat](https://github.com/caronc/apprise/wiki/Notify_zulip) | zulip://  | (TCP) 443   | zulip://botname@Organization/Token<br />zulip://botname@Organization/Token/Stream<br />zulip://botname@Organization/Token/Email

## Security notes

- Use a **read-only** API token scoped to the single account you want to monitor (**Account → Cloudflare Tunnel → Read**). The service never modifies anything in Cloudflare.
- The API token and Apprise URLs (which often embed credentials) are passed as plain environment variables. Keep your `docker-compose.yaml` or `.env` file out of version control and restrict access to the host.
- The service exposes no ports, so no inbound access is needed; it only makes outbound connections to the Cloudflare API (HTTPS) and to your notification services (whatever protocol each Apprise URL uses).

## Troubleshooting

- **`Error login to cloudflare api with status code ...` in the logs:** the Cloudflare API rejected the request. Check that `CF_TOKEN` is valid, has the Cloudflare Tunnel read permission, and that `CF_ACCOUNT_ID` is correct.
- **`Error login to cloudflare api with status code ...` on every check right after setup:** in Docker, `CF_TOKEN` and `CF_ACCOUNT_ID` default to empty strings, so a missing value does not stop the container; the API request just fails on every interval. Set both.
- **The service exits right after start:** `CHECK_INTERVALS` must be an integer. Setting it to an empty value (`CHECK_INTERVALS=`) overrides the image default and crashes the service, so either set a number or remove the line.
- **No notification after starting the container:** this is expected. The first check only records each tunnel's current status; notifications are sent only when a status changes afterwards. The first check also runs one interval after startup.
- **No notifications at all:** check that `NOTIFIERS` is set and that each Apprise URL is valid. Test a URL with the [Apprise CLI](https://github.com/caronc/apprise#command-line-usage) (`apprise -vv -b "test" "<url>"`).
- **Duplicate "changed" alerts after an update:** make sure `/app/db` is mounted to persistent storage, otherwise the state is lost when the container is recreated.

## Development

Project layout:

```
app/app.py              # Monitor: polling, state comparison, Apprise notifications
app/sqliteconnector.py  # SQLite storage for the last known tunnel status
requirements.txt        # Python dependencies
Dockerfile              # Container image
docker-compose.yaml     # Example Compose file
VERSION                 # Image version used by the Docker Hub workflow
```

Run from source with Python 3.8 or newer (`requirements.txt` requires `urllib3>=2.2.2`). The database path `db/cf.db` is relative to the working directory:

```bash
pip install -r requirements.txt
cd app
mkdir -p db
CF_TOKEN=... CF_ACCOUNT_ID=... NOTIFIERS="..." CHECK_INTERVALS=60 python3 app.py
```

Build the image locally:

```bash
docker build -t cloudflared-mon .
```

> **Note:** A local image build currently fails. The Dockerfile uses `ubuntu:18.04` (Python 3.6), while `requirements.txt` requires `urllib3>=2.2.2`, which needs Python 3.8+. The published Docker Hub images predate that requirement.

Two manually triggered GitHub Actions workflows build multi-arch images (`linux/amd64`, `linux/arm64`, `linux/arm/v7`): [`docker-image.yml`](.github/workflows/docker-image.yml) pushes `techblog/cloudflared-mon:latest` and `:<VERSION>` to Docker Hub, and [`publish-ghcr.yml`](.github/workflows/publish-ghcr.yml) pushes to `ghcr.io/t0mer/cloudflared-mon`. <!-- TODO: verify - no public GHCR image found at the time of writing -->

## Components and frameworks

* [Apprise](https://pypi.org/project/apprise/) for notifications.
* [Requests](https://pypi.org/project/requests/) for Cloudflare API calls.
* [schedule](https://pypi.org/project/schedule/) for scheduling tunnel checks.
* [Loguru](https://pypi.org/project/loguru/) for logging.

## Contributing

Issues and pull requests are welcome at [github.com/t0mer/cloudflared-mon](https://github.com/t0mer/cloudflared-mon).

## License

This project is licensed under the [MIT License](LICENSE).

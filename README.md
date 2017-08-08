# Lighthouse API client

This project provides a ready to go implementation of the [Lighthouse API Client](https://github.com/thiagolcmelo/oglhclient) as a Slack Bot, and a Docker image for bootstrapping the Slack Bot in minutes.

## Authentication

The **Lighthouse API Client** expects to find the following environment variables:

- **(required)** `OGLH_API_USER` a valid Lighthouse user
- **(required)** `OGLH_API_PASS` a valid Lighthouse user's password
- **(required)** `OGLH_API_URL` the Lighthouse API url without `/api/v1`

## Lighthouse Slack Bot

It expects to find the following environment variables:

- **(required)** `SLACK_BOT_TOKEN` which is provided by Slack at the moment of [creating a bot](https://api.slack.com/bot-users).
- **(required)** `SLACK_BOT_NAME` is the name given to the Slack bot.
- **(required)** `SLACK_BOT_DEFAULT_CHANNEL` a default Slack channel name used for warnings.
- **(optional)** `SLACK_BOT_DEFAULT_LOG_CHANNEL` a Slack channel name for logs, if it is not provided, logs will be printed to a file only, but logs classified as high priority like warnings and errors will be printed to the `SLACK_BOT_DEFAULT_CHANNEL` when `SLACK_BOT_DEFAULT_LOG_CHANNEL` is not set.

The **Lighhouse** Slack bot can be triggered as simple as:

```python
>>> from oglhslack import OgLhSlackBot
>>> slack_bot = OgLhSlackBot()
>>> slack_bot.listen()
```

Or, straight from the terminal:

```bash
$ python oglh_bot.py
```

## Channels conventions

### Administration commands

Commands that make changes in Lighthouse are not allowed in normal channels or in private messages.

In order to execute such commands, it is required that the Slack administrator creates a channel named **ohlh-admin**. This channel is supposed to be locked for not invited members and that only authorized users get those invites.

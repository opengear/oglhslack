# Lighthouse/Slack Integration

This project provides an application of the [Lighthouse API Client](https://github.com/opengear/oglhclient) as a Slack Bot.
There is also a [Docker image](https://hub.docker.com/r/opengeardev/oglhslack) for launching the Slack Bot application in minutes.

## Authentication

The **Lighthouse API Client** expects to find the following environment variables:

- **(required)** `OGLH_API_USER` a valid Lighthouse user
- **(required)** `OGLH_API_PASS` a valid Lighthouse user's password
- **(required)** `OGLH_API_URL` the Lighthouse API URL without `/api/v3.4`

## Lighthouse Slack Bot

It expects to find the following environment variables:

- **(required)** `SLACK_BOT_TOKEN` provided by Slack at the moment of [creating a bot](https://api.slack.com/bot-users)
- **(required)** `SLACK_BOT_NAME` the name given to the Slack Bot
- **(required)** `SLACK_BOT_DEFAULT_CHANNEL` a default Slack channel for warnings (see below)
- **(optional)** `SLACK_BOT_DEFAULT_LOG_CHANNEL` a Slack channel used for logs; if not provided, logs will be printed to a file only, but logs classified as high priority like warnings and errors will also be sent to the `SLACK_BOT_DEFAULT_CHANNEL`
- **(optional)** `SLACK_BOT_ADMIN_CHANNEL` the name for the administrator channel; if not provided, it is assumed to be **oglhadmin**

The **Lighthouse Slack Bot** can be triggered as shown below:

```python
>>> from oglhslack import OgLhSlackBot
>>> slack_bot = OgLhSlackBot()
>>> slack_bot.listen()
```

Or, straight from the terminal:

```bash
$ ./oglhslack.py
```

## Commands

It is possible to interact with the Slack Bot using direct messages or from private or public channels. When commands are not issued in direct messages, they must be prefixed with `@mybot`, where `mybot` is the bot's name in Slack.

### Built in commands

There is a small set of commands which can be found in the bot's help. They are pretty straightforward in what they do and can be listed in Slack with the following command:

```
@mybot help
```

Some commands have **(admin only)** on theirs descriptions, indicating that they can only be performed from the `administrator channel`.

### API client commands

This commands follow the [Lighthouse API Client](https://github.com/opengear/oglhclient) conventions.

For listing objects like `nodes` it is possible to perform:

```
@mybot list nodes
```

For listing `tags` belonging to a `node` with id *my-node-name*:

```
@mybot list tags from node my-node-name
```

For listing `smartgroups`:

```
@mybot list smartgroups from nodes
```

For getting information regarding to a specific `node`:

```
@mybot find node my-node-name
```

For getting `system` information:

```
@mybot get hostname from system
```

It follows the logic as described below:

Listing objects of a given type, like **nodes**, **ports**, and so on:
> **list** *objects*

Listing objects of a given type, belonging to a parent object, like **system**:
> **list** *objects* **from** *parent-object*

Listing objects of a given type, belonging to a parent object specified by its id:
> **list** *objects* **from** *parent-object* *parent-name*

Finding specific objects by their ids:
> **find** *object* *object-name*

Finding specific objects by their ids, when belonging to parent objects (possibly also specified by id):
> **find** *object* *object-name* **from** *parent-object*
> **find** *object* *object-name* **from** *parent-object* *parent-name*

Getting objects when **list** and **find** do not apply:
> **get** *object* **from** *parent-object*

## Channels conventions

### Administration channel

Commands that make changes in Lighthouse are not allowed in normal channels or in private messages.

In order to execute such commands, it is required that the Slack administrator creates a channel named **oglhadmin**, or with the name specified in the `SLACK_BOT_ADMIN_CHANNEL` environment variable. This channel is supposed to be open for authorized members only.

## Docker image

The Docker image for the Opengear Lighthouse Slack Bot is available at [Docker Hub](https://hub.docker.com/r/opengeardev/oglhslack).

It requires a file containing the environment variables that looks like:

```
SLACK_BOT_TOKEN=xoxb-************-************************
SLACK_BOT_NAME=mybotname
SLACK_BOT_DEFAULT_CHANNEL=myDefaultChannel
SLACK_BOT_DEFAULT_LOG_CHANNEL=myDefaultLogChannel
SLACK_BOT_ADMIN_CHANNEL=oglhadmin
OGLH_API_USER=myOgLhUser
OGLH_API_PASS=myOgLhPassword
OGLH_API_URL=https://oglh-octo.opengear.com
```

For launching a Lighthouse Slack Bot Docker container just run:

```bash
$ sudo docker run --env-file /path/to/my/env.list opengeardev/oglhslack
```

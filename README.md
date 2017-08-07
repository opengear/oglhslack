# Lighthouse API client

This project provides a client library for accessing the Lighthouse API, available for **Python 2.7** and **Python 2.6**.

It also provides a ready to go implementation of the API client as a Slack Bot, and a Docker image for bootstrapping the Slack Bot in minutes.

## Lighthouse API Client library

The client is tightly tied to the RESTfull API [RAML specification](http://ftp.opengear.com/download/api/lighthouse/og-rest-api-specification-v1.raml), which is very well exposed [here](http://ftp.opengear.com/download/api/lighthouse/og-rest-api-specification-v1.html).

### Authentication

The **Lighthouse API Client** expects to find the following environment variables:

- **(required)** `OGLH_API_USER` a valid Lighthouse user
- **(required)** `OGLH_API_PASS` a valid Lighthouse user's password
- **(required)** `OGLH_API_URL` the Lighthouse API url without `/api/v1`

### Conventions

All the methods follow the convention specified as follows. A call for an *url* like:

```
GET /system/global_enrollment_token HTTP/1.0
```

would be performed through the client as:

```python
>>> from oglh_client import LighthouseApi
>>> api = LighthouseApi()
>>> client = api.get_client()
>>> client.system.global_enrollment_token.get()
```

Basically, all `/` must be replaced by `.` followed by an action:

#### GET: `find()`
Used when asking for a specific object

Example:

```
GET /nodes/smartgroups/myGrouId HTTP/1.0
```

Becomes:

```python
smartgroup = client.nodes.smartgroups.find(id='myGrouId')
```

or

```python
smartgroup = client.nodes.smartgroups.find('myGrouId')
```

In case of a child object like in `/nodes/{id}/tags/{tag_value_id}`, with a possible call like:

```
GET /nodes/nodes-13/tags/London HTTP/1.0
```

The python call should be:


```python
tag = client.nodes.tags.find(id='myTagId', parent_id='myNodeId')
```

Also possible to make:

```python
tag = client.nodes.tags.find(id='myTagId', node_id='myNodeId')
```

Always paying attention to the simple plural formatting removal:

- **nodes**: *node*
- **properties**: *property*

#### GET: `list()`
Used when asking for a list of objects

Example:

```
GET /nodes/smartgroups HTTP/1.0
```

Becomes:

```python
smartgroups = client.nodes.smartgroups.list()
```

parameters may apply like `page`, `per_page`, and so on:

```python
smartgroups = client.nodes.smartgroups.list(page=1,per_page=5)
```

#### GET: `get()`
Only used when the two previous do not apply, like:

```
GET /system/webui_session_timeout HTTP/1.0
```

Becomes:

```python
timeout = client.system.webui_session_timeout.get()
```


#### POST: `create()`
As the name suggests, it is used to create objects, for instance:

```
POST /tags/node_tags HTTP/1.0
Content-Type: application/json

{"node_tag": {"name": "Location","values": [{"value": "USA.NewYork"},{"value": "UK.London"}]}}
```

could be performed as:

```python
result = client.tags.node_tags.create(data={"username":"root","password":"default"})
```

#### PUT: `update()`
It is used to update a given object, like:

```
PUT /tags/node_tags/nodes_tags-1 HTTP/1.0
Content-Type: application/json

{"node_tag": {"name": "Location","values": [{"id": "tags_node_tags_values_90","value": "USA.NewYork"}]}}
```

could be performed as:

```python
data = {
  "node_tag": {
    "name": "Location",
    "values": [
      {
        "id": "tags_node_tags_values_90",
        "value": "USA.NewYork"
      }
    ]
  }
}
result = client.tags.node_tags.update(tag_value_id='nodes_tags-1', data=data)
```

#### DELETE: `delete()`

It is used for deleting an object by its `id`, for instance:

```
DELETE /tags/node_tags/nodes_tags-1 HTTP/1.0
```

could be performed as:

```python
result = client.tags.node_tags.delete(tag_value_id='nodes_tags-1')
```

## Lighthouse Slack Bot

The Slack Bot is a playful example of how to use the **Lighthouse API Client library**.

It expects to find the following environment variables:

- **(required)** `SLACK_BOT_TOKEN` which is provided by Slack at the moment of [creating a bot](https://api.slack.com/bot-users).
- **(required)** `SLACK_BOT_NAME` is the name given to the Slack bot.
- **(required)** `SLACK_BOT_DEFAULT_CHANNEL` a default Slack channel name used for warnings.
- **(optional)** `SLACK_BOT_DEFAULT_LOG_CHANNEL` a Slack channel name for logs, if it is not provided, logs will be printed to a file only, but logs classified as high priority like warnings and errors will be printed to the `SLACK_BOT_DEFAULT_CHANNEL` when `SLACK_BOT_DEFAULT_LOG_CHANNEL` is not set.

The **Lighhouse** Slack bot can be triggered as simple as:

```python
>>> from oglh_bot import OgLhSlackBot
>>> slack_bot = OgLhSlackBot()
>>> slack_bot.listen()
```

Or, straight from the terminal:

```bash
$ python oglh_bot.py
```
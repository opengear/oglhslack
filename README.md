# Lighthouse API client

This project provides a client library for accessing the Lighthouse API, available for **Python 2.7** and **Python 2.6**.

It also provides a ready to go implementation of the API client as a Slack Bot, and a Docker image for bootstrapping the Slack Bot in minutes.

## Lighthouse API Client library

The client is tightly tied to the RESTfull API [RAML specification](http://ftp.opengear.com/download/api/lighthouse/og-rest-api-specification-v1.raml).

### Authentication

The **Lighthouse API Client** expects to find the following environment variables:

- `OGLH_API_USER` a valid Lighthouse user
- `OGLH_API_PASS` a valid Lighthouse user's password

### Conventions

All the methods follow the convention specified as follows. A call for an *url* like:

```
GET /system/global_enrollment_token
```

would be performed through the client as:

```python
>>> from oglh_client import LighthouseApi
>>> api = LighthouseApi()
>>> client = api.get_client()
>>> client.system.global_enrollment_token.get()
```

Basically, all `/` must be replaced by `.` followed by an action:

#### **GET**: `find()`
Used when asking for a specific object

Example:

```
GET /nodes/smartgroups/{groupId}
```

Becomes:

```python
smartgroup = client.nodes.smartgroups.find(groupId='myGrouId')
```

#### **GET**: `list()`
Used when asking for a list of objects

Example:

```
GET /nodes/smartgroups
```

Becomes:

```python
smartgroups = client.nodes.smartgroups.list()
```

parameters may apply like `page`, `per_page`, and so on:

```python
smartgroups = client.nodes.smartgroups.list(page=1,per_page=5)
```

#### **GET**: `get()`
Only used when the two prevous do not apply, like:

```
GET /system/webui_session_timeout
```

Becomes:

```python
timeout = client.system.webui_session_timeout.get()
```


#### **POST**: `create()`
As the name suggests, it is used to create objects, for instance:

```
POST /sessions HTTP/1.0
Content-Type: application/json

username=root&password=default
```

could be performed as:

```python
session = client.sessions.create(data={"username":"root","password":"default"})
```

#### **PUT**: `update()`



#### **DELETE**: `delete()`





## Lighthouse Slack Bot

--/--

## Lighthouse Slack Bot (Docker image)

--/--

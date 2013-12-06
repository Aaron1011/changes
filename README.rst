Changes
-------

Changes is a dashboard to view information about your code. Specifically, it focuses on aggregating quality metrics and history, such as results from a build server.

Supported build platforms include:

- `Koality <http://koalitycode.com>`_
- `Jenkins <http://jenkins-ci.org>`_ (not actually implemented yet)

Supported code review platforms include:

- `Phabricator <http://phabricator.com>`_

Requirements
============

- Node.js
	- Bower (npm install -g bower)
- Postgresql
- Python 2.7
	- virtualenv
	- pip

Setup
=====

Create the database:

::

	$ createdb -E utf-8 changes

Setup the default configuration:

::

	# ~/.changes/changes.conf.py
	BASE_URI = 'http://localhost:5000'
	SERVER_NAME = 'localhost:5000'

	REPO_ROOT = '/tmp'

Create a Python environment:

::

	$ mkvirtualenv changes

Bootstrap your environment:

::

	$ make


.. note:: You can run ``make resetdb`` to drop and re-create a clean database.


Webserver
=========

Run the webserver:

::

	bin/web


Background Workers
==================

Workers are managed via Celery:

::


	bin/worker -B


NGINX Configuration
===================

::


	    location / {
	        proxy_pass              http://changes_server;
	        proxy_set_header        Host $host;
	        proxy_set_header        X-Real-IP $remote_addr;
	        proxy_set_header        X-Forwarded-For $proxy_add_x_forwarded_for;
	        proxy_set_header        X-Forwarded-Proto $scheme;
	        proxy_connect_timeout   150;
	        proxy_send_timeout      100;
	        proxy_read_timeout      100;
	        proxy_buffers           4 32k;
	        proxy_buffering	        off;
	        client_max_body_size    8m;
	        client_body_buffer_size 128k;

	    }

API
===

The general API workflow (utilizing something like Jenkins + Koality looks like this):

- A diff (code review request) is created in Phabricator
  - Send request to create change
  - Store change ID with diff ID
  - Send request to create build with initial patch
- A diff is updated in Phabricator
  - Use change ID that's bound with diff ID
  - Send request to create a new build on the existing change

The build process ideally works like this:

- A backend (Koality in our example) run's tests asynchronously
- Changes aggregates the results continuously (we dont wait for the final result)
- When an initial failure is detected, hooks are fired
  - Email notifications may be sent at this time
- When the build is complete, hooks are fired
  - Results are reported back to Phabricator


List Changes
~~~~~~~~~~~

::

	GET /api/0/changes/


Change Details
~~~~~~~~~~~~~

::

	GET /api/0/changes/:change_id/


Create Change
~~~~~~~~~~~~~

::

	POST /api/0/changes/

**Params**

project:
	the project slug

label:
	a label for this change

(optional) key:
	a unique identifier for this change (e.g. D1234)

(optional) sha:
	the committed revision's sha

(optional) author:
	the author of this change (e.g. "David Cramer <dcramer@example.com>")


**Response**

::

	{
		"build": {
			"id": "a857d7dc0d9843cfa568cfbd0b0de91c"
		}
	}


List Builds
~~~~~~~~~~~

::

	GET /api/0/changes/:change_id/builds/


Create Build
~~~~~~~~~~~~

Create's a new build. A ``change`` or ``project`` is required to create a build.

::

	POST /api/0/builds/

**Params**

sha:
	the base revision sha to build on

(optional) change:
	the change ID

(optional) change:
	the project ID

(optional) author:
	the author of this build (e.g. "David Cramer <dcramer@example.com>")

(optional) patch:
	git unified diff format

(optional) patch[label]:
	a human readable label for this patch
	**must be specified if patch is present**

(optional) patch[url]:
	a url which describes this patch

**Response**

::

	{
		"build": {
			"id": "a857d7dc0d9843cfa568cfbd0b0de91c"
		}
	}


Architecture
============

An attempt to explain how some things map from their counterparts to the data models within Changes.

Phabricator
-----------

Revision (e.g. DXXXX):
	Change
Diff (a change within a revision):
	Patch

Koality
-------

Change
	Build
Stage
	Each stage is grouped by stage[type] as single Phase, and created as many Steps.


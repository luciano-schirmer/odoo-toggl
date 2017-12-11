Odoo + Toggl Integration
========================

Script to integrate Odoo with Toggl service (time tracking).

---

## Requirements

The script is written in Python language and requires the following packages:

- requests
- python-dateutil

### Environment variables

Please, add the following to `~/.bash_profile` (on macOS).

    # Odoo connection
    export ODOO_URL="url"
    export ODOO_DB="db"
    export ODOO_USERNAME="email"
    export ODOO_PASSWORD="password"

    # Toggl
    export TOGGL_API_TOKEN="token"
    export TOGGL_WORKSPACE="workspace"
    export TOGGL_USER_AGENT="user <email>"

## Description

The script executes the following actions:

1. Connect to Odoo.
2. Authenticate with Toggl API and get list of projects.
3. Add Odoo tasks as Toggl projects if they don't exist yet.
4. Find the last date with task work entry in Odoo.
5. Process each day since then.

Process is as follows:

1. Verify if all time entries have an associated project.
2. Request all time entries and verify if they don't exceed the maximum page
   size. Paged requests are not implemented, so the limit is around 50 entries
   per day, which is more than enough.
3. Insert each time entry in Odoo as a task work (analytic account entry).

A cron job example is provided in the `cron.daily` directory. Please verify the
location of the files and then save the file under the `/etc/cron.daily` directory.

It can also be implemented as an AWS Lambda function executed daily.


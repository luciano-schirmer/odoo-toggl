Odoo + Toggl Integration
========================

Script to integrate Odoo (actually OpenERP 6.1) with Toggl service (time
tracking).

---

## Requirements

The script is written in Python language and requires the following packages:

- json
- [openerplib](https://github.com/openerp/openerp-client-lib)
- requests
- datetime
- dateutil

Before executing, check the definitions in the beginning of the file.

## Description

The script executes the following actions:

1. Ask for Odoo username and password.
2. Connect to Odoo.
3. Authenticate with Toggl API and get list of projects.
4. Add Odoo tasks as Toggl projects if they don't exist yet.
5. Find the last date with task work entry in Odoo.
6. Process each day since then.

Process is as follows:

1. Request Toggl time entries to verify if they fulfill a 24-hours day.
2. Verify if all time entries have an associated project.
3. Request all time entries and verify if they don't exceed the maximum page
   size. Paged requests are not implemented, so the limit is around 50 entries
   per day, which is more than enough.
4. Insert each time entry in Odoo as a task work.

A cron job example is provided in the `cron.daily` directory. Please change the
Odoo password and check location of the files and then save the file under the
`/etc/cron.daily` directory.


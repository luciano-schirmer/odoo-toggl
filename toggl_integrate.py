#!/usr/bin/python
# -*- coding: utf-8 -*-
import json
import sys
import getpass
import openerplib
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime
from datetime import timedelta
from dateutil import tz
import dateutil.parser
import argparse

# Definitions
ODOO_HOSTNAME = '192.168.1.4'  # Odoo hostname
ODOO_DATABASE = 'prod'  # Odoo database name
ODOO_USER = 'odoo_user'  # Odoo user name
ODOO_TIMEZONE = 'America/Sao_Paulo'  # Timezone
TOGGL_API_TOKEN = ''  # please complete with Toggl API token
TOGGL_API_URL = 'https://www.toggl.com/api/v8/'
TOGGL_REPORTS_URL = 'https://toggl.com/reports/api/v2/'
TOGGL_WORKSPACE = 'Company'  # Toggl workspace to process
TOGGL_USER_AGENT = 'User name <email@address>'  # This is required by Toggl

# Parse arguments
parser = argparse.ArgumentParser(description='Integrate Odoo with Toggl.')
parser.add_argument('-u', '--username', action='store', help='Odoo username')
parser.add_argument('-p', '--password', action='store', help='Odoo password')
parser.add_argument('-o', '--one', action='store_true',
                    help='Process only one day and exit')
args = parser.parse_args()

# Get Odoo user name and password
if args.username:
    odoo_username = args.username
else:
    odoo_username = raw_input('Odoo User: ')
if args.password:
    odoo_password = args.password
else:
    odoo_password = getpass.getpass('Odoo Password: ')
if not (args.username and args.password):
    print

# Connect to Odoo
connection = openerplib.get_connection(hostname=ODOO_HOSTNAME,
                                       database=ODOO_DATABASE,
                                       login=odoo_username,
                                       password=odoo_password)

# Toggl authentication via HTTP Basic Auth
url = TOGGL_API_URL + 'me'
response = requests.get(url, auth=HTTPBasicAuth(TOGGL_API_TOKEN, 'api_token'))
if response.status_code != 200:
    sys.exit('Login failed. Check your API key.')
response = response.json()
# print json.dumps(response, sort_keys=True, indent=4, separators=(',', ': '))

# Workspace id
try:
    wid = [item['id'] for item in response['data']['workspaces']
           if item['admin'] == True and item['name'] == TOGGL_WORKSPACE][0]
except IndexError:
    sys.exit('Workspace not found!')

# Get projects from Toggl
url = TOGGL_API_URL + 'workspaces/' + str(wid) + '/projects'
response = requests.get(url, auth=HTTPBasicAuth(TOGGL_API_TOKEN, 'api_token'))
if response.status_code != 200:
    sys.exit('Request failed!')
response = response.json()
projects = [{'id': item['id'], 'name': item['name'],
             'active': item['active'], 'archive': True}
            for item in response]

# Add Oddo tasks as Toggl projects and create dictionary with ids to use later.
task_model = connection.get_model('project.task')
open_tasks = task_model.search([('state', '=', 'open')])
open_tasks_dict = dict()
for task in open_tasks:
    task_info = task_model.read(task, ['id', 'name'])
    open_tasks_dict[task_info['name']] = task_info['id']
    found = False
    for project in projects:
        if project['name'] == task_info['name']:
            found = True
            project['archive'] = False
            break
    if not found:
        print "Creating project '{0}'".format(
                task_info['name'].encode('utf-8'))
        url = TOGGL_API_URL + 'projects'
        data = {'project': {
            'name': task_info['name'],
            'wid': wid,
            'color': '13'
        }}
        response = requests.post(
            url, data=json.dumps(data),
            auth=HTTPBasicAuth(TOGGL_API_TOKEN, 'api_token'))
        if response.status_code != 200:
            sys.exit('Request failed!')

# Find user id
user_model = connection.get_model('res.users')
user_ids = user_model.search([('login', '=', ODOO_USER)])
user_info = user_model.read(user_ids[0], ['id', 'name'])
user_id = user_info['id']

# Find last date with task work entry in Odoo
work_model = connection.get_model('project.task.work')
works = work_model.search([('user_id', '=', user_id)], limit=1,
                          order='date DESC')
work_info = work_model.read(works[0], ['date'])

# Convert UTC time to local time
tz_utc = tz.gettz('UTC')
tz_local = tz.gettz(ODOO_TIMEZONE)
utc = datetime.strptime(work_info['date'], '%Y-%m-%d %H:%M:%S')
utc = utc.replace(tzinfo=tz_utc)
local = utc.astimezone(tz_local)
print 'Last task work entry was ' + local.strftime('%Y-%m-%d %H:%M')

# Calculate start date to get data from Toggl
since = local.replace(hour=0, minute=0, second=0, microsecond=0) + \
        timedelta(days=1)
until = datetime.now().replace(
        tzinfo=tz_local, hour=0, minute=0, second=0, microsecond=0) + \
            timedelta(days=-1)


# Prepare Toggl requests
api_url = TOGGL_API_URL + 'time_entries'
url = TOGGL_REPORTS_URL + 'details'
params = {
    'user_agent': TOGGL_USER_AGENT,
    'workspace_id': wid,
    'order_field': 'date',
    'order_desc': 'off',
    'rounding': 'off',
    'display_hours': 'minutes',
    'page': '1'
}

# Iterate each day
cur_date = since
while cur_date <= until:

    # Informative message
    print 'Processing Toggl time entries from {0}...'.format(
            cur_date.strftime('%Y-%m-%d'))

    # Request to verify if time entries fulfill a 24-hours day
    api_params = {
        'start_date': cur_date.replace(
            hour=0, minute=0, second=0, microsecond=0).isoformat(),
        'end_date': cur_date.replace(
            hour=23, minute=59, second=59, microsecond=0).isoformat()
    }
    response = requests.get(api_url, params=api_params,
                            auth=HTTPBasicAuth(TOGGL_API_TOKEN, 'api_token'))
    if response.status_code != 200:
        sys.exit('Request failed!' + str(response.status_code))
    response = response.json()
    total_duration = 0
    for item in response:
        total_duration += item['duration']
    if total_duration != 86400:
        sys.exit('Total duration is ' + str(total_duration) +
                 '. Must be 86400!')

    # Filter current date
    filter_date = cur_date.strftime('%Y-%m-%d')
    params['since'] = filter_date
    params['until'] = filter_date

    # Request to verify if all time entries have an associated project
    params['project_ids'] = '0'
    response = requests.get(url, params=params,
                            auth=HTTPBasicAuth(TOGGL_API_TOKEN, 'api_token'))
    if response.status_code != 200:
        sys.exit('Request failed!' + str(response.status_code))
    response = response.json()
    if len(response['data']) > 0:
        sys.exit('There are ' + str(len(response)) +
                 ' entries with no associated project!')

    # Request time entries
    params['project_ids'] = None
    response = requests.get(url, params=params,
                            auth=HTTPBasicAuth(TOGGL_API_TOKEN, 'api_token'))
    if response.status_code != 200:
        sys.exit('Request failed!' + str(response.status_code))
    response = response.json()

    # Totals
    total_count = response['total_count']
    per_page = response['per_page']
    if total_count > per_page:
        sys.exit('Total count is ' + str(total_count) +
                 '. Per page is ' + str(per_page) +
                 '. Paged reports not supported by this application!')

    # Process time entries
    for item in response['data']:

        # Print information about time entry
        seconds = timedelta(seconds=item['dur']/1000)
        start = dateutil.parser.parse(item['start'])
        end = dateutil.parser.parse(item['end'])
        print '[{0}] {1} - {2} (from {3} to {4})'.format(
                item['project'].encode('utf-8'),
                item['description'].encode('utf-8'), str(seconds),
                start.strftime('%H:%M'), end.strftime('%H:%M'))

        # Insert task work entry in Odoo
        start_utc = start.astimezone(dateutil.tz.tzutc())
        work_model = connection.get_model('project.task.work')
        work_id = work_model.create({
            'name': item['description'],
            'date': start_utc.isoformat(),
            'task_id': open_tasks_dict[item['project']],
            'hours': float(item['dur']) / 1000 / 3600,
            'user_id': user_id
            })

    # Next day
    cur_date += timedelta(days=1)
    if args.one:
        break

# Archive Toggl projects which refer to closed (done) Odoo tasks
for project in projects:
    if project['archive']:
        print "Archiving project '{0}'".format(project['name'].encode('utf-8'))
        url = TOGGL_API_URL + 'projects/' + str(project['id'])
        data = {'project': {'active': False}}
        response = requests.put(
            url, data=json.dumps(data),
            auth=HTTPBasicAuth(TOGGL_API_TOKEN, 'api_token'))
        if response.status_code != 200:
            sys.exit('Request failed!')

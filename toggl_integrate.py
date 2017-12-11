#!venv/bin/python
# -*- coding: utf-8 -*-
import os
import sys
import getpass
import argparse
import xmlrpclib
import json
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime, timedelta
import dateutil.parser

# Rounding (minutes)
ROUNDING_MINUTES = 15

# Odoo definitions
odoo_url = os.getenv('ODOO_URL', '')
odoo_db = os.getenv('ODOO_DB', '')
odoo_username = os.getenv('ODOO_USERNAME', '')
odoo_password = os.getenv('ODOO_PASSWORD', '')

# Toggl definitions
TOGGL_API_URL = 'https://www.toggl.com/api/v8/'
TOGGL_REPORTS_URL = 'https://toggl.com/reports/api/v2/'
toggl_api_token = os.getenv('TOGGL_API_TOKEN', '')
toggl_workspace = os.getenv('TOGGL_WORKSPACE', '')
toggl_user_agent = os.getenv('TOGGL_USER_AGENT', '')

# Parse arguments
parser = argparse.ArgumentParser(description='Integrate Odoo with Toggl.')
#parser.add_argument('-u', '--username', action='store', help='Odoo username')
#parser.add_argument('-p', '--password', action='store', help='Odoo password')
parser.add_argument('-o', '--one', action='store_true',
                    help='Process only one day and exit')
parser.add_argument('-p', '--projects_only', action='store_true',
                    help='Process only projects and no time entries')
args = parser.parse_args()

## Get Odoo user name and password
#if args.username:
#    odoo_username = args.username
#else:
#    odoo_username = raw_input('Odoo User: ')
#if args.password:
#    odoo_password = args.password
#else:
#    odoo_password = getpass.getpass('Odoo Password: ')
#if not (args.username and args.password):
#    print()

# Access Odoo
print('Connecting to Odoo...')
common = xmlrpclib.ServerProxy('{}/xmlrpc/2/common'.format(odoo_url))
uid = common.authenticate(odoo_db, odoo_username, odoo_password, {})
models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(odoo_url))

# Toggl authentication via HTTP Basic Auth
auth_url = TOGGL_API_URL + 'me'
response = requests.get(auth_url, auth=HTTPBasicAuth(toggl_api_token, 'api_token'))
if response.status_code != 200:
    sys.exit('Login failed. Check your API key.')
response = response.json()
# print json.dumps(response, sort_keys=True, indent=4, separators=(',', ': '))

# Workspace id
try:
    wid = [item['id'] for item in response['data']['workspaces']
           if item['admin'] == True and item['name'] == toggl_workspace][0]
except IndexError:
    sys.exit('Workspace not found!')

# Get projects from Toggl
workspaces_url = TOGGL_API_URL + 'workspaces/' + str(wid) + '/projects'
response = requests.get(
        workspaces_url, auth=HTTPBasicAuth(toggl_api_token, 'api_token'))
if response.status_code != 200:
    sys.exit('Request failed!')
response = response.json()
projects = [{'id': item['id'], 'name': item['name'],
             'active': item['active'], 'archive': True}
            for item in response]

# Find user id
[odoo_user] = models.execute_kw(odoo_db, uid, odoo_password, 'res.users',
        'search_read', [[['login', '=', odoo_username]]],
        {'fields': ['id', 'name'], 'limit': 1})

# Add Oddo tasks as Toggl projects and create dictionary with ids to use later.
ids = models.execute_kw(odoo_db, uid, odoo_password, 'project.task', 'search',
        [[['active', '=', True], ['user_id', '=', odoo_user['id']]]], {'order': 'name'})
if len(ids) > 0:
    open_tasks_dict = dict()
    # Other fields include: kanban_state, stage_id
    open_tasks = models.execute_kw(odoo_db, uid, odoo_password, 'project.task',
            'read', [ids], {'fields': ['id', 'name', 'project_id']})
    for task in open_tasks:
        # print('{} - {}'.format(task['id'], task['name'].encode('utf-8')))
        open_tasks_dict[task['name']] = (task['id'], task['project_id'])
        found = False
        for project in projects:
            if project['name'] == task['name']:
                found = True
                project['archive'] = False
                break
        if not found:
            print "Creating project '{0}'".format(task['name'].encode('utf-8'))
            projects_url = TOGGL_API_URL + 'projects'
            data = {'project': {
                'name': task['name'],
                'wid': wid,
                'color': '13'
            }}
            response = requests.post(
                projects_url, data=json.dumps(data),
                auth=HTTPBasicAuth(toggl_api_token, 'api_token'))
            if response.status_code != 200:
                sys.exit('Request failed!')

# Find last date with task work entry in Odoo
[work] = models.execute_kw(odoo_db, uid, odoo_password, 'account.analytic.line',
        'search_read', [[['user_id', '=', odoo_user['id']],
            ['is_timesheet', '=', True]]],
        {'fields': ['date'], 'limit': 1, 'order': 'date DESC'})
print('Last task work entry was ' + work['date'])

# Calculate start date to get data from Toggl
last_work_date = datetime.strptime(work['date'], '%Y-%m-%d')
since = last_work_date + timedelta(days=1)
until = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + \
                timedelta(days=-1)
print('Since ' + since.strftime('%Y-%m-%d'))
print('Until ' + until.strftime('%Y-%m-%d'))

# Prepare Toggl requests
# time_entries_url = TOGGL_API_URL + 'time_entries'
reports_url = TOGGL_REPORTS_URL + 'details'
params = {
    'user_agent': toggl_user_agent,
    'workspace_id': wid,
    'order_field': 'date',
    'order_desc': 'off',
    'rounding': 'off',
    'display_hours': 'minutes',
    'page': '1'
}

# Iterate each day
cur_date = since
while (cur_date <= until) and not args.projects_only:

    # Informative message
    print 'Processing Toggl time entries from {0}...'.format(
            cur_date.strftime('%Y-%m-%d'))

    # Filter current date
    filter_date = cur_date.strftime('%Y-%m-%d')
    params['since'] = filter_date
    params['until'] = filter_date

    # Request to verify if all time entries have an associated project
    params['project_ids'] = '0'
    response = requests.get(reports_url, params=params,
                            auth=HTTPBasicAuth(toggl_api_token, 'api_token'))
    if response.status_code != 200:
        sys.exit('Request failed!' + str(response.status_code))
    response = response.json()
    if len(response['data']) > 0:
        sys.exit('There are ' + str(len(response)) +
                 ' entries with no associated project!')

    # Request time entries
    params['project_ids'] = None
    response = requests.get(reports_url, params=params,
                            auth=HTTPBasicAuth(toggl_api_token, 'api_token'))
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
        rounding = ROUNDING_MINUTES * 60.0
        seconds = timedelta(seconds=round(item['dur']/1000/rounding) * rounding)
        start = dateutil.parser.parse(item['start'])
        end = dateutil.parser.parse(item['end'])
        print '[{0}] {1} - {2} (from {3} to {4})'.format(
                item['project'].encode('utf-8'),
                item['description'].encode('utf-8'), str(seconds),
                start.strftime('%H:%M'), end.strftime('%H:%M'))

        # Insert task work entry in Odoo
        work_id = models.execute_kw(odoo_db, uid, odoo_password,
                'account.analytic.line', 'create', [{
                    'name': item['description'],
                    'date': start.strftime('%Y-%m-%d'),
                    'task_id': open_tasks_dict[item['project']][0],
                    'project_id': open_tasks_dict[item['project']][1][0],
                    'unit_amount': seconds.seconds / 3600.0,
                    'is_timesheet': True,
                    'user_id': odoo_user['id']
                    }])

    # Next day
    cur_date += timedelta(days=1)
    if args.one:
        break

# Archive Toggl projects which refer to archived Odoo tasks
for project in projects:
    if project['archive']:
        print "Archiving project '{0}'".format(project['name'].encode('utf-8'))
        projects_url = TOGGL_API_URL + 'projects/' + str(project['id'])
        data = {'project': {'active': False}}
        response = requests.put(
            projects_url, data=json.dumps(data),
            auth=HTTPBasicAuth(toggl_api_token, 'api_token'))
        if response.status_code != 200:
            sys.exit('Request failed!')

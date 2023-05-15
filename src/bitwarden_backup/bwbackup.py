# SPDX-License-Identifier: MIT
import click
from datetime import datetime
import os
import json
import random
import shutil
import subprocess
import sys

#	Requires:
#		bw		From Bitwarden CLI

@click.command()
@click.argument('output_dir', required=True)
@click.argument('bw_userid', envvar='BW_USERID', type=str, required=True)
@click.option('-p', '--bw_password', default=None, hide_input=True, envvar='BW_PASSWORD', prompt=True, help='Bitwarden master password, defaults to $BW_PASSWORD, or prompts', required=True)
@click.version_option()
def bw_backup(output_dir, bw_userid, bw_password):
	"""Back up a Bitwarden account.
	
	OUTPUT_DIR: Backup output directory  [required]
	
	BW_USERID: Bitwarden userid, defaults to $BW_USERID  [required]
	"""

	run_cmd(['bw', 'logout'], fail_ok=True)

	output_dir = os.path.join(output_dir, f'bwbackup_{datetime.now().isoformat(timespec="seconds").replace(":",".")}')
	print(f'Backing up to {output_dir}.')

	export_file = os.path.join(output_dir, 'export.json')
	folder_file = os.path.join(output_dir, 'folders.json')
	items_file = os.path.join(output_dir, 'items.json')
	attachments_dir = os.path.join(output_dir, 'attachments')
	attachments_file = os.path.join(output_dir, 'attachments.txt')
	organizations_dir = os.path.join(output_dir, 'organizations')
	organizations_file = os.path.join(output_dir, 'organizations.json')
	password_file = os.path.join(output_dir, 'master_password.txt')

	shutil.rmtree(output_dir, ignore_errors=True)
	os.mkdir(output_dir)
	os.mkdir(attachments_dir)
	os.mkdir(organizations_dir)

	# We'll pass the Master Password to the Bitwarden CLI via a random environment variable,
	# to make it harder to steal.  We'll also wipe that variable as soon as we're logged in.
	password_env = f'BW_{random.randint(1,100000)}'
	try:
		# Store the userid and master password in the master_password.txt file.
		with open(password_file, 'w') as pwf:
			pwf.write(f'user: {bw_userid}\n')
			pwf.write(f'password: {bw_password}\n')
		# Log in and get a session-id, and then wipe the master password out of memory.
		os.environ[password_env] = bw_password
		result = run_cmd(['bw', 'login', '--passwordenv', password_env, '--raw', bw_userid], capture_output=True, text=True, fail_ok=True)
		bw_password = ''
		os.environ[password_env] = ''
		if result.returncode != 0:
			raise Exception(f'Login failed:\n{result.stdout}\n{result.stderr}')
		print('You are logged in!')
		os.environ['BW_SESSION'] = result.stdout
	except Exception as err:
		print(err)
		run_cmd(['bw', 'logout'], fail_ok=True)
		os.environ['BW_SESSION'] = ''
		return 1
	finally:
		bw_password = ''
		os.environ[password_env] = ''
	try:
		# Back up the Bitwarden vault.
		run_cmd(['bw', 'sync'])
		run_cmd(['bw', 'export', '--format', 'json', '--output', export_file])
		run_cmd(['bw', 'list', 'folders', '>', folder_file])
		with open(folder_file, 'r') as ff:
			folders = json.load(ff)
		print(f'Backed up {len(folders)} folders to {folder_file}.')
		del folders

		run_cmd(['bw', 'list', 'items', '>', items_file])
		with open(items_file, 'r') as ff:
			items = json.load(ff)
		print(f'Backed up {len(items)} items.')
 
		# Attachments require purchasing a Premium subscription, so this code is untested.
		total_attachments = 0
		with open(attachments_file, 'w') as attf:
			for item in items:
				if 'attachments' in item:
					for attachment in item['attachments']:
						attachment_id = attachment['id']
						attachment_filename = attachment['fileName']
						attf.write(f'item_id: {item["id"]} attachment_id: {attachment_id} filename: {attachment_filename}\n')
						run_cmd(['bw', 'get', 'attachment', attachment_id, '--item_id', item['id'], '--output', 
							os.path.join(attachments_dir, item['id'], attachment_filename)])
					print(f'Backed up {len(item["attachments"])} attachments for item {item["id"]}.')
					total_attachments = total_attachments + len(item["attachments"])
		print(f'Backed up {total_attachments} attachments to {attachments_dir}.')

		run_cmd(['bw', 'list', 'organizations', '>', organizations_file])
		with open(organizations_file, 'r') as ff:
			organizations = json.load(ff)
		organization_ids = []
		for organization_id in [item['organizationId'] for item in items if item['organizationId']]:
			if organization_id not in organization_ids:
				organization_ids.append(organization_id)
		for organization_id in organization_ids:
			organization_name = organizations[organization_id]['name']
			run_cmd(['bw', 'export', '--organization_id', organization_id, '--format', 'json', '--output',  
				os.path.join(organizations_dir, f'{organization_id}_{organization_name}')])
		print(f'Backed up {len(organization_ids)} organizations to {organizations_dir}.')
		return 0
	except Exception as err:
		print(err)
		return 1
	finally:
		run_cmd(['bw', 'logout'], fail_ok=True)
		os.environ['BW_SESSION'] = ''

def run_cmd(command, fail_ok=False, **kwargs):
	""" Run a command, displaying it first. """

	print(' '.join(command))
	result = subprocess.run(command, shell=True, **kwargs)
	if not fail_ok and result.returncode != 0:
		raise Exception(f'Command execution failed: {result.stdout}\n{result.stderr}')
	if not kwargs.get('capture_output', False):
		print('\n') # bw cli doesn't finish it's lines
	return result

if __name__ == '__main__':
	rc = bw_backup()
	sys.exit(rc)

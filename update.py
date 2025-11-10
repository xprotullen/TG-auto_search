import os
import shutil
from os import path as opath, getenv, rename
from subprocess import run as srun
from dotenv import load_dotenv
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AutoUpdater")

load_dotenv('config.env', override=True)

UPSTREAM_REPO = getenv('UPSTREAM_REPO', "")
UPSTREAM_BRANCH = getenv('UPSTREAM_BRANCH', "main")

if UPSTREAM_REPO:
    config_backup = 'config.env.tmp'
    
    try:
        # Backup config.env
        if opath.exists('config.env'):
            rename('config.env', config_backup)
        
        # Remove .git for clean update
        if opath.exists('.git'):
            try:
                shutil.rmtree('.git')
            except Exception as e:
                logger.error(f"Failed to remove .git: {e}")
        
        git_commands = (
            f"git init -q && "
            f"git config --global user.email 'thunder@update.local' && "
            f"git config --global user.name 'Thunder' && "
            f"git add . && "
            f"git commit -sm update -q && "
            f"git remote add origin {UPSTREAM_REPO} && "
            f"git fetch origin -q && "
            f"git reset --hard origin/{UPSTREAM_BRANCH} -q"
        )
        
        result = srun(git_commands, shell=True)
        
        if result.returncode == 0:
            logger.info('✅ Successfully updated with latest commit from UPSTREAM_REPO')
        else:
            logger.error('❌ Update failed! Check UPSTREAM_REPO or branch name.')
            
    finally:
        # Restore config.env
        if opath.exists(config_backup):
            rename(config_backup, 'config.env')

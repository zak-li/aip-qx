#!/usr/bin/env python3
"""
Deployment script to upload the frontend `dist` directory to the remote VM via SFTP.
"""
import os
import posixpath
import sys

import paramiko

HOST = os.environ.get("DEPLOY_HOST", "")
USERNAME = os.environ.get("DEPLOY_USER", "")
PASSWORD = os.environ.get("DEPLOY_PASSWORD", "")
if not HOST or not USERNAME or not PASSWORD:
    print("Set DEPLOY_HOST, DEPLOY_USER, DEPLOY_PASSWORD environment variables.")
    raise SystemExit(1)

LOCAL_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "../frontend/src"))
REMOTE_DEST = f"/home/{USERNAME}/rwa-platform/frontend/src"

def create_remote_dir_if_missing(sftp, remote_path):
    try:
        sftp.stat(remote_path)
    except OSError:
        # Parent might not exist, but let's just assume we can mkdir
        try:
            sftp.mkdir(remote_path)
            print(f"Created remote directory: {remote_path}")
        except Exception as e:
            print(f"Failed to create {remote_path}: {e}")

def deploy_frontend():
    if not os.path.exists(LOCAL_SRC):
        print(f"Error: {LOCAL_SRC} does not exist.")
        sys.exit(1)

    print(f"Connecting to {HOST} as {USERNAME}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # noqa: S507 - dev tooling against a known VM
    
    try:
        ssh.connect(HOST, username=USERNAME, password=PASSWORD, timeout=10)
        sftp = ssh.open_sftp()
        
        # Ensure remote base directory exists
        try:
            sftp.stat("/home/zakaria/rwa-platform")
        except OSError:
            sftp.mkdir("/home/zakaria/rwa-platform")
            
        try:
            sftp.stat("/home/zakaria/rwa-platform/frontend")
        except OSError:
            sftp.mkdir("/home/zakaria/rwa-platform/frontend")
            
        create_remote_dir_if_missing(sftp, REMOTE_DEST)
        
        print("Uploading files...")
        for root, _dirs, files in os.walk(LOCAL_SRC):
            # Convert local path to remote path
            rel_path = os.path.relpath(root, LOCAL_SRC)
            if rel_path == ".":
                remote_dir = REMOTE_DEST
            else:
                remote_dir = posixpath.join(REMOTE_DEST, rel_path.replace(os.sep, '/'))
                
            create_remote_dir_if_missing(sftp, remote_dir)
            
            for f in files:
                local_file = os.path.join(root, f)
                remote_file = posixpath.join(remote_dir, f)
                print(f"  Uploading: {local_file} -> {remote_file}")
                sftp.put(local_file, remote_file)
                
        print("Frontend deployment completed successfully!")
        
    except Exception as e:
        print(f"Deployment failed: {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    deploy_frontend()

import os
import paramiko
import sys

def run_ssh_commands():
    host = os.environ.get("DEPLOY_HOST", "")
    user = os.environ.get("DEPLOY_USER", "")
    password = os.environ.get("DEPLOY_PASSWORD", "")
    if not host or not user or not password:
        print("Set DEPLOY_HOST, DEPLOY_USER, DEPLOY_PASSWORD environment variables.")
        sys.exit(1)

    sudo_pass = os.environ.get("DEPLOY_SUDO_PASSWORD", password)
    commands = [
        f"echo '{sudo_pass}' | sudo -S docker pull neo4j:5.23.0",
        f"echo '{sudo_pass}' | sudo -S docker pull hashicorp/vault:1.15.1",
        f"echo '{sudo_pass}' | sudo -S docker compose -f /home/{user}/rwa-platform/docker/docker-compose.yaml up -d neo4j vault",
    ]
    
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(hostname=host, username=user, password=password, timeout=10)
        for cmd in commands:
            print(f"> {cmd}")
            stdin, stdout, stderr = client.exec_command(cmd)
            stdout.channel.recv_exit_status()
            out = stdout.read().decode('utf-8', errors='ignore').strip()
            print(f"[OUT]\n{out}")
    except Exception as e:
        print(f"Connection failed: {e}")
        sys.exit(1)
    finally:
        client.close()

if __name__ == "__main__":
    run_ssh_commands()

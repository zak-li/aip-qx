import paramiko
import sys

def run_ssh_commands():
    host = '10.10.10.150'
    user = 'zakaria'
    password = 'zakaria'
    
    commands = [
        "echo 'zakaria' | sudo -S docker pull neo4j:5.23.0",
        "echo 'zakaria' | sudo -S docker pull hashicorp/vault:1.15.1",
        "echo 'zakaria' | sudo -S docker compose -f /home/zakaria/rwa-platform/docker/docker-compose.yaml up -d neo4j vault"
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

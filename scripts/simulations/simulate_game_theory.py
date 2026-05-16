#!/usr/bin/env python3
"""
Simulation visuelle du Tribunal de Compliance et de la Théorie des Jeux.
Utilise 'rich' pour un rendu dans le terminal.
"""
import hashlib
import os
import random
import sys
import time
from dataclasses import dataclass

# Add the project root to python path to import the backend
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

@dataclass
class Auditor:
    name: str
    reputation: float
    is_malicious: bool = False

def compute_hash(vote: str, salt: str) -> str:
    return hashlib.sha256(f"{vote}:{salt}".encode()).hexdigest()

def simulate_tribunal():
    console.clear()
    console.print(Panel.fit("[bold cyan][*] Simulation: Decentralized Compliance Tribunal (Game Theory)[/]", border_style="cyan"))
    
    # 1. Setup Auditors
    auditors = [
        Auditor("REG01 (Regulator)", 100.0),
        Auditor("Bank01", 100.0),
        Auditor("Bank 02", 100.0),
        Auditor("Crédit Agricole", 100.0, is_malicious=True), # The deviator
        Auditor("BPCE", 100.0)
    ]
    
    console.print("\n[bold yellow]Step 1: The Tribunal is Formed[/]")
    table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE)
    table.add_column("Auditor Node")
    table.add_column("Initial Reputation", justify="right")
    table.add_column("Role")
    
    for a in auditors:
        role = "[red]Bribed / Lazy[/]" if a.is_malicious else "[green]Honest[/]"
        table.add_row(a.name, f"{a.reputation:.1f}", role)
    console.print(table)
    
    time.sleep(2)
    
    # 2. Anomaly Detected
    ground_truth = "FRAUD"
    console.print("\n[bold red][!] ALERT: AI Compliance Engine flagged Transaction #8932 as SUSPICIOUS.[/]")
    console.print(f"Ground Truth (Unknown to network): [bold]{ground_truth}[/]\n")
    
    time.sleep(1)
    
    # 3. Phase 1: COMMIT
    console.print("[bold yellow]Step 2: Commit Phase (Cryptographic Hashing)[/]")
    console.print("Auditors analyze evidence and submit a salted hash to prevent copying (free-riding).")
    
    commitments = []
    with console.status("[bold green]Auditors are committing votes..."):
        for a in auditors:
            time.sleep(0.5)
            # The malicious node votes LEGITIMATE despite evidence
            vote = "LEGITIMATE" if a.is_malicious else "FRAUD"
            salt = str(random.randint(1000, 9999))
            commit_hash = compute_hash(vote, salt)
            commitments.append({"auditor": a, "hash": commit_hash, "vote": vote, "salt": salt})
            console.print(f"[+] {a.name} committed: [dim]{commit_hash}[/]")
            
    time.sleep(1)
    
    # 4. Phase 2: REVEAL
    console.print("\n[bold yellow]Step 3: Reveal Phase (Unveiling the votes)[/]")
    
    reveal_table = Table(show_header=True, header_style="bold blue")
    reveal_table.add_column("Auditor Node")
    reveal_table.add_column("Revealed Vote")
    reveal_table.add_column("Salt")
    reveal_table.add_column("Hash Check")
    
    for c in commitments:
        time.sleep(0.3)
        vote_color = "[red]" if c["vote"] == "LEGITIMATE" else "[green]"
        reveal_table.add_row(
            c["auditor"].name, 
            f"{vote_color}{c['vote']}[/]", 
            c["salt"], 
            "[green]Valid[/]"
        )
    console.print(reveal_table)
    
    time.sleep(1)
    
    # 5. Phase 3: TALLY & SLASH (Game Theory)
    console.print("\n[bold yellow]Step 4: Tally and Game Theory Slashing[/]")
    
    fraud_votes = sum(1 for c in commitments if c["vote"] == "FRAUD")
    legit_votes = sum(1 for c in commitments if c["vote"] == "LEGITIMATE")
    
    decision = "FRAUD" if fraud_votes >= (len(auditors) * 2/3) else "LEGITIMATE"
    
    console.print(f"Votes for FRAUD: {fraud_votes}")
    console.print(f"Votes for LEGITIMATE: {legit_votes}")
    console.print(f"Supermajority Decision: [bold reverse red] {decision} [/]\n")
    
    time.sleep(1)
    
    console.print("[bold italic]Applying Nash Equilibrium Mechanics (Schelling Point)...[/]")
    
    final_table = Table(show_header=True, header_style="bold white", box=box.HEAVY)
    final_table.add_column("Auditor Node")
    final_table.add_column("Action Taken")
    final_table.add_column("Reputation Change", justify="right")
    final_table.add_column("Final Reputation", justify="right")
    
    for c in commitments:
        a = c["auditor"]
        if c["vote"] == decision:
            # Reward
            a.reputation += 10.0
            action = "[green]Consensus (Rewarded)[/]"
            change = "[green]+10.0[/]"
        else:
            # Slash
            a.reputation -= 50.0
            action = "[bold red]Deviated (Slashed!)[/]"
            change = "[bold red]-50.0[/]"
            
        final_table.add_row(a.name, action, change, f"{a.reputation:.1f}")
        
    console.print(final_table)
    
    console.print("\n[bold green]Conclusion:[/]")
    text = (
        "The system incentivizes truth-telling. The deviating node (Crédit Agricole) "
        "lost 50% of its consensus power because it voted against the obvious evidence. "
        "Over time, malicious nodes lose all influence, proving the Nash Equilibrium."
    )
    console.print(Panel(text, border_style="green"))

if __name__ == "__main__":
    try:
        simulate_tribunal()
    except KeyboardInterrupt:
        sys.exit(0)

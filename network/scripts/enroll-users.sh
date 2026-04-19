#!/bin/bash
set -e

echo "Les identités sont générées par cryptogen."
echo "Wallets disponibles dans ~/rwa-platform/network/wallet/"

ls ~/rwa-platform/network/wallet/ 2>/dev/null || echo "Dossier wallet vide - lancer generate_wallets.py"

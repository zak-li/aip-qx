#!/bin/bash
set -e

echo "Installation des dépendances LaTeX pour la génération d'Audits certifiés..."
sudo apt-get update
sudo apt-get install -y texlive-latex-extra texlive-fonts-recommended texlive-lang-french
echo "✓ Installation LaTeX terminée."

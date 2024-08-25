#!/usr/bin/env python3

export PATH=$PATH:/Users/juliebelzanne/.local/bin/poetry

# Chemin vers le répertoire du projet
PROJECT_DIR="/Users/juliebelzanne/Documents/Hush_Crasher/steam_data/newgame-newtweet"
SCRIPT_DIR="$PROJECT_DIR/socialmedia_dev"
LOG_FILE="$SCRIPT_DIR/smdev_update_log.log"

# Activation de l'environnement virtuel Poetry
cd "$PROJECT_DIR"

# Changement du répertoire de travail vers socialmedia_dev
cd "$SCRIPT_DIR"

# Exécution du script Python
poetry run python update-smdev.py >> "$LOG_FILE" 2>&1

# Ajouter une ligne vide et un séparateur dans le fichier de log pour plus de lisibilité
echo "" >> "$LOG_FILE"
echo "----------------------------------------" >> "$LOG_FILE"
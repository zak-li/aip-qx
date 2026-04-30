import { Component, EventEmitter, Output } from '@angular/core';
import { CommonModule } from '@angular/common';

const SUGGESTIONS = [
  "Quelle est la valeur totale des actifs sous gestion?",
  "Montre-moi les transactions récentes sur Hyperledger Fabric",
  "Génère un rapport de conformité pour le trimestre",
  "Liste les organisations enregistrées sur la blockchain",
  "Analyse le risque du portefeuille d'actifs immobiliers",
  "Affiche l'état des validateurs du réseau",
  "Quels actifs ont des problèmes de conformité en attente?",
  "Génère un diagramme de flux des transactions",
  "Compare les performances des actifs ce mois-ci",
  "Montre les métriques du circuit breaker",
  "Liste les événements d'audit récents",
  "Quel est le statut des émissions ZKP en cours?",
  "Affiche un graphique de la valeur des actifs par type",
  "Quelles organisations ont des accès en attente?",
  "Résume l'activité blockchain des 24 dernières heures"
];

@Component({
  selector: 'app-suggestions',
  standalone: false,
  template: `
    <div class="sug-panel" [class.open]="open">
      <div class="sug-list">
        <div class="sug-item"
          *ngFor="let s of suggestions; let i = index"
          [class.focused]="i === focused"
          (click)="select(s)"
          (mouseenter)="focused = i">
          {{ s }}
        </div>
      </div>
    </div>
  `
})
export class SuggestionsComponent {
  @Output() selected = new EventEmitter<string>();
  open = false;
  focused = -1;
  suggestions = SUGGESTIONS;

  toggle() { this.open = !this.open; if (!this.open) this.focused = -1; }
  close() { this.open = false; this.focused = -1; }

  select(s: string) {
    this.selected.emit(s);
    this.close();
  }
}

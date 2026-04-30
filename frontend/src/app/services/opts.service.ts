import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

export interface Opts {
  temperature: number;
  topP: number;
  maxTokens: number;
  presencePenalty: number;
  frequencyPenalty: number;
  style: string;
  ragEnabled: boolean;
  stream: boolean;
}

const DEFAULTS: Opts = {
  temperature: 0.7, topP: 0.9, maxTokens: 2048,
  presencePenalty: 0, frequencyPenalty: 0,
  style: 'precise', ragEnabled: true, stream: true
};

@Injectable({ providedIn: 'root' })
export class OptsService {
  opts$ = new BehaviorSubject<Opts>({ ...DEFAULTS });

  update(patch: Partial<Opts>) {
    this.opts$.next({ ...this.opts$.value, ...patch });
  }

  reset() {
    this.opts$.next({ ...DEFAULTS });
  }

  get snapshot(): Opts {
    return this.opts$.value;
  }
}

import { create } from 'zustand';

export const useOptsStore = create((set) => ({
  temperature:  0.4,
  maxTokens:    4096,
  topP:         0.95,
  freqPenalty:  0.0,
  presPenalty:  0.0,
  useRag:       true,
  nResults:     5,
  ctxDepth:     10,
  stylePreset:  'auto',

  set(patch) { set(patch); },
}));

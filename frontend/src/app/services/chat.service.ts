import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';
import { environment } from '../../environments/environment';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  raw?: string;
  stream?: boolean;
  responseTime?: number;
  promptTokens?: number;
  completionTokens?: number;
}

@Injectable({ providedIn: 'root' })
export class ChatService {
  private base = environment.apiBase;
  messages$ = new BehaviorSubject<Message[]>([]);
  busy$ = new BehaviorSubject(false);

  clearMessages() {
    this.messages$.next([]);
  }

  async send(text: string, opts: any) {
    if (this.busy$.value) return;
    const userMsg: Message = { id: crypto.randomUUID(), role: 'user', content: text };
    this.messages$.next([...this.messages$.value, userMsg]);
    this.busy$.next(true);

    const assistantId = crypto.randomUUID();
    const asstMsg: Message = { id: assistantId, role: 'assistant', content: '', stream: opts.stream };
    this.messages$.next([...this.messages$.value, asstMsg]);

    try {
      const csrf = this.getCsrf();
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (csrf) headers['X-CSRF-Token'] = csrf;

      const t0 = Date.now();
      const res = await fetch(`${this.base}/agent/chat`, {
        method: 'POST',
        credentials: 'include',
        headers,
        body: JSON.stringify({ message: text, ...opts })
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      if (opts.stream && res.body) {
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          this.updateAssistant(assistantId, buf, true);
        }
        const elapsed = ((Date.now() - t0) / 1000).toFixed(2);
        this.updateAssistant(assistantId, buf, false, parseFloat(elapsed));
      } else {
        const data = await res.json();
        this.updateAssistant(assistantId, data.response ?? data.message ?? JSON.stringify(data), false,
          undefined, data.prompt_tokens, data.completion_tokens);
      }
    } catch (err: any) {
      this.updateAssistant(assistantId, `Error: ${err.message}`, false);
    } finally {
      this.busy$.next(false);
    }
  }

  private updateAssistant(id: string, content: string, streaming: boolean,
    responseTime?: number, promptTokens?: number, completionTokens?: number) {
    const msgs = this.messages$.value.map(m =>
      m.id === id ? { ...m, content, stream: streaming, responseTime, promptTokens, completionTokens } : m
    );
    this.messages$.next(msgs);
  }

  private getCsrf(): string | null {
    const match = document.cookie.match(/(?:^|;\s*)rwa_csrf=([^;]*)/);
    return match ? decodeURIComponent(match[1]) : null;
  }
}

import { Component, Input, OnChanges, SimpleChanges, AfterViewChecked, ElementRef, ViewChild } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { Message } from '../../services/chat.service';

interface ParsedMessage {
  id: string;
  role: string;
  content: string;
  raw?: string;
  stream?: boolean;
  responseTime?: number;
  promptTokens?: number;
  completionTokens?: number;
  blocks?: Block[];
}

interface Block {
  type: 'html' | 'chart' | 'mermaid';
  html?: SafeHtml;
  spec?: any;
  code?: string;
}

@Component({
  selector: 'app-message-list',
  standalone: false,
  template: `
    <div class="chat-scroll" #scrollEl>
      <app-welcome *ngIf="messages.length === 0"></app-welcome>
      <div class="msg-group" *ngFor="let msg of parsed">
        <div class="msg-label" [class.user-label]="msg.role === 'user'">
          {{ msg.role === 'user' ? 'YOU' : 'AGENT' }}
        </div>
        <ng-container *ngIf="msg.role === 'user'">
          <div class="user-msg">{{ msg.content }}</div>
        </ng-container>
        <ng-container *ngIf="msg.role === 'assistant'">
          <ng-container *ngIf="msg.stream; else rendered">
            <div class="stream-raw">{{ msg.content }}<span class="cursor"></span></div>
          </ng-container>
          <ng-template #rendered>
            <div class="ai-msg">
              <ng-container *ngFor="let block of msg.blocks">
                <div *ngIf="block.type === 'html'" [innerHTML]="block.html"></div>
                <app-chart-block *ngIf="block.type === 'chart'" [spec]="block.spec"></app-chart-block>
                <app-mermaid-block *ngIf="block.type === 'mermaid'" [code]="block.code!"></app-mermaid-block>
              </ng-container>
            </div>
          </ng-template>
          <app-msg-meta
            [responseTime]="msg.responseTime"
            [promptTokens]="msg.promptTokens"
            [completionTokens]="msg.completionTokens">
          </app-msg-meta>
        </ng-container>
      </div>
    </div>
  `
})
export class MessageListComponent implements OnChanges, AfterViewChecked {
  @Input() messages: Message[] = [];
  @ViewChild('scrollEl') scrollEl!: ElementRef<HTMLDivElement>;
  parsed: ParsedMessage[] = [];
  private shouldScroll = false;

  constructor(private sanitizer: DomSanitizer) {}

  ngOnChanges(changes: SimpleChanges) {
    if (changes['messages']) {
      this.parsed = this.messages.map(m => ({
        ...m,
        blocks: m.role === 'assistant' && !m.stream ? this.parseBlocks(m.content) : undefined
      }));
      this.shouldScroll = true;
    }
  }

  ngAfterViewChecked() {
    if (this.shouldScroll && this.scrollEl) {
      const el = this.scrollEl.nativeElement;
      el.scrollTop = el.scrollHeight;
      this.shouldScroll = false;
    }
  }

  private parseBlocks(content: string): Block[] {
    const blocks: Block[] = [];
    const chartRe = /```json:chart\n([\s\S]*?)```/g;
    const mermaidRe = /```mermaid\n([\s\S]*?)```/g;
    let last = 0;
    const parts: { start: number; end: number; type: 'chart' | 'mermaid'; data: string }[] = [];

    let m;
    while ((m = chartRe.exec(content)) !== null)
      parts.push({ start: m.index, end: m.index + m[0].length, type: 'chart', data: m[1] });
    chartRe.lastIndex = 0;
    while ((m = mermaidRe.exec(content)) !== null)
      parts.push({ start: m.index, end: m.index + m[0].length, type: 'mermaid', data: m[1] });

    parts.sort((a, b) => a.start - b.start);

    for (const part of parts) {
      if (part.start > last) {
        const html = DOMPurify.sanitize(marked.parse(content.slice(last, part.start)) as string);
        blocks.push({ type: 'html', html: this.sanitizer.bypassSecurityTrustHtml(html) });
      }
      if (part.type === 'chart') {
        try { blocks.push({ type: 'chart', spec: JSON.parse(part.data) }); } catch {}
      } else {
        blocks.push({ type: 'mermaid', code: part.data });
      }
      last = part.end;
    }

    if (last < content.length) {
      const html = DOMPurify.sanitize(marked.parse(content.slice(last)) as string);
      blocks.push({ type: 'html', html: this.sanitizer.bypassSecurityTrustHtml(html) });
    }

    return blocks.length ? blocks : [{ type: 'html', html: this.sanitizer.bypassSecurityTrustHtml(DOMPurify.sanitize(marked.parse(content) as string)) }];
  }
}

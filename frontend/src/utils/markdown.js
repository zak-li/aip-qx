import { marked } from 'marked';
import DOMPurify from 'dompurify';

marked.use({ gfm: true, breaks: true, mangle: false, headerIds: false });

const ALLOWED_TAGS = [
  'h1','h2','h3','h4','p','ul','ol','li','table','thead','tbody','tr','th','td',
  'pre','code','em','strong','blockquote','br','hr','span','div','a',
];
const ALLOWED_ATTR = ['href', 'class', 'target', 'rel'];

export function renderMarkdown(raw) {
  const dirty = marked.parse(raw || '');
  return DOMPurify.sanitize(dirty, { ALLOWED_TAGS, ALLOWED_ATTR });
}

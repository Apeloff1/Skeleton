import { type LearningFile } from '../../product/gameLearningClient';

const MAX_ENTRY_CHARS = 2 * 1024 * 1024;
const MAX_DOCUMENT_CHARS = 4 * 1024 * 1024;
const PREVIEW_POLICY = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; media-src data: blob:; connect-src 'none'; frame-src 'none'; object-src 'none'; form-action 'none'; base-uri 'none'";

/** Prepare an opaque-origin browser preview of the emitted successor files. */
export function successorPreviewDocument(files: LearningFile[]): string | null {
  const map = new Map(files.map(file => [file.path, file.content]));
  const entry = map.get('game/successor/index.html');
  if (!entry || entry.length > MAX_ENTRY_CHARS) return null;
  const result = entry.replace(/<script\b([^>]*?)\bsrc=["']([^"']+)["']([^>]*)>\s*<\/script\s*>/gi, (_match, _before, source: string) => {
    const path = 'game/successor/' + source.replace(/^\.\//, '');
    if (source.includes('..') || /^[a-z]+:|^\//i.test(source) || !map.has(path)) return '';
    return '<script>' + map.get(path)!.replace(/<\/script/gi, '<\\/script') + '</script>';
  });
  // The browser must encounter the policy before *any* untrusted markup. An
  // entry may put executable tags before <head>, or include a fake <head> in
  // a comment or script. Author-supplied policies can only tighten this one.
  const document = `<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${PREVIEW_POLICY}">${result}`;
  return document.length <= MAX_DOCUMENT_CHARS ? document : null;
}

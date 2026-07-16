import { useRef, useEffect, useCallback } from "react";
import { Bold, Italic, Underline, Link as LinkIcon, List, ListOrdered, Undo2, Redo2, Type } from "lucide-react";

/**
 * Minimal contentEditable HTML rich-text editor with a compact toolbar.
 * Uses `document.execCommand` — deprecated but still works everywhere and
 * needs zero dependencies. The parent controls state via `value` (only used
 * for the initial render + reset) and `onChange(html)`.
 *
 * Reset is signalled by changing `resetKey` (parent bumps this after send).
 */
export default function RichTextEditor({ value = "", onChange, resetKey = 0, testid = "rte" }) {
  const ref = useRef(null);

  // Reset editor content when parent bumps `resetKey`. We intentionally do
  // NOT depend on `value` — otherwise every keystroke would rewrite innerHTML
  // and move the caret back to the start.
  const lastReset = useRef(resetKey);
  useEffect(() => {
    if (!ref.current) return;
    // First mount OR resetKey changed → hard-sync from parent value.
    if (lastReset.current !== resetKey || ref.current.innerHTML === "") {
      ref.current.innerHTML = value || "";
      lastReset.current = resetKey;
    }
  }, [resetKey, value]);

  const exec = useCallback((cmd, arg) => {
    ref.current?.focus();
    document.execCommand(cmd, false, arg);
    onChange?.(ref.current?.innerHTML || "");
  }, [onChange]);

  const onInput = useCallback(() => {
    onChange?.(ref.current?.innerHTML || "");
  }, [onChange]);

  const insertLink = useCallback(() => {
    const raw = window.prompt("Enter URL (https://…)");
    if (!raw) return;
    const url = raw.trim();
    // Defence in depth — only permit http(s)/mailto/tel schemes. execCommand
    // itself blocks `javascript:` in modern browsers, but belt-and-braces.
    if (!/^(https?:|mailto:|tel:)/i.test(url)) {
      window.alert("Only https://, http://, mailto: or tel: links are allowed.");
      return;
    }
    exec("createLink", url);
  }, [exec]);

  const clearFormat = useCallback(() => exec("removeFormat"), [exec]);

  const btn = "inline-flex items-center justify-center w-8 h-8 rounded-md text-[#1a1a1f]/70 hover:bg-[#f6f4ef] hover:text-[#232369] transition-colors";
  return (
    <div
      className="rounded-md border border-[#1a1a1f]/15 bg-white overflow-hidden focus-within:border-[#232369]/60 focus-within:ring-2 focus-within:ring-[#232369]/15"
      data-testid={testid}
    >
      <div className="flex flex-wrap items-center gap-0.5 px-1.5 py-1 border-b border-[#1a1a1f]/10 bg-[#faf9f5]">
        <button type="button" title="Bold"       className={btn} onClick={() => exec("bold")}       data-testid={`${testid}-bold`}><Bold size={14} /></button>
        <button type="button" title="Italic"     className={btn} onClick={() => exec("italic")}     data-testid={`${testid}-italic`}><Italic size={14} /></button>
        <button type="button" title="Underline"  className={btn} onClick={() => exec("underline")}  data-testid={`${testid}-underline`}><Underline size={14} /></button>
        <span className="w-px h-4 bg-[#1a1a1f]/10 mx-1" />
        <button type="button" title="Bullet list"  className={btn} onClick={() => exec("insertUnorderedList")} data-testid={`${testid}-ul`}><List size={14} /></button>
        <button type="button" title="Numbered list" className={btn} onClick={() => exec("insertOrderedList")}  data-testid={`${testid}-ol`}><ListOrdered size={14} /></button>
        <span className="w-px h-4 bg-[#1a1a1f]/10 mx-1" />
        <button type="button" title="Link"        className={btn} onClick={insertLink}   data-testid={`${testid}-link`}><LinkIcon size={14} /></button>
        <button type="button" title="Clear formatting" className={btn} onClick={clearFormat} data-testid={`${testid}-clear`}><Type size={14} /></button>
        <span className="w-px h-4 bg-[#1a1a1f]/10 mx-1" />
        <button type="button" title="Undo" className={btn} onClick={() => exec("undo")} data-testid={`${testid}-undo`}><Undo2 size={14} /></button>
        <button type="button" title="Redo" className={btn} onClick={() => exec("redo")} data-testid={`${testid}-redo`}><Redo2 size={14} /></button>
      </div>
      <div
        ref={ref}
        contentEditable
        suppressContentEditableWarning
        onInput={onInput}
        onBlur={onInput}
        data-testid={`${testid}-area`}
        className="min-h-[220px] max-h-[420px] overflow-y-auto px-3 py-2 text-sm text-[#1a1a1f] focus:outline-none [&_a]:text-[#232369] [&_a]:underline [&_ul]:list-disc [&_ul]:pl-6 [&_ol]:list-decimal [&_ol]:pl-6"
        // Placeholder trick via CSS: styled below via .rte-empty when empty.
      />
    </div>
  );
}

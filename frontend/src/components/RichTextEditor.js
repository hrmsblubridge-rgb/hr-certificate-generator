import { useRef, useEffect, useCallback, useState } from "react";
import {
  Bold, Italic, Underline, Strikethrough, Link as LinkIcon, List, ListOrdered,
  Undo2, Redo2, Eraser, AlignLeft, AlignCenter, AlignRight, AlignJustify,
  IndentIncrease, IndentDecrease, Quote, Minus, Palette,
} from "lucide-react";

/**
 * contentEditable HTML rich-text editor with a full toolbar:
 *   B / I / U / S  ·  H1 H2 H3 ¶  ·  bullets / numbered / indent / outdent
 *   ·  align L C R J  ·  quote / hr  ·  link  ·  color  ·  clear  ·  undo/redo
 *
 * Uses `document.execCommand` (deprecated but works everywhere with zero deps).
 * Parent controls state via `value` (initial + reset) and `onChange(html)`.
 * Reset is signalled by bumping `resetKey`.
 */
export default function RichTextEditor({ value = "", onChange, resetKey = 0, testid = "rte" }) {
  const ref = useRef(null);
  const [showColor, setShowColor] = useState(false);

  // Reset editor content when parent bumps `resetKey`. Intentionally NOT
  // depending on `value` — otherwise every keystroke would rewrite innerHTML
  // and move the caret back to the start.
  const lastReset = useRef(resetKey);
  useEffect(() => {
    if (!ref.current) return;
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
    // Defence in depth — only permit http(s)/mailto/tel schemes.
    if (!/^(https?:|mailto:|tel:)/i.test(url)) {
      window.alert("Only https://, http://, mailto: or tel: links are allowed.");
      return;
    }
    exec("createLink", url);
  }, [exec]);

  const setBlock = useCallback((tag) => {
    // browsers accept both 'h1' and '<h1>' but wrapping in `<>` is more reliable.
    exec("formatBlock", `<${tag}>`);
  }, [exec]);

  const btn = "inline-flex items-center justify-center w-8 h-8 rounded-md text-[#1a1a1f]/70 hover:bg-[#f6f4ef] hover:text-[#232369] transition-colors";
  const sep = <span className="w-px h-4 bg-[#1a1a1f]/10 mx-1" />;
  const colorSwatches = [
    "#1a1a1f", "#232369", "#7a4119", "#1e6f59",
    "#b91c1c", "#c2410c", "#a16207", "#6b21a8", "#0369a1",
  ];

  return (
    <div
      className="rounded-md border border-[#1a1a1f]/15 bg-white overflow-hidden focus-within:border-[#232369]/60 focus-within:ring-2 focus-within:ring-[#232369]/15"
      data-testid={testid}
    >
      <div className="flex flex-wrap items-center gap-0.5 px-1.5 py-1 border-b border-[#1a1a1f]/10 bg-[#faf9f5]">
        {/* Block format dropdown */}
        <select
          data-testid={`${testid}-block`}
          onChange={(e) => { if (e.target.value) { setBlock(e.target.value); e.target.value = ""; } }}
          defaultValue=""
          className="h-8 text-[12px] font-medium text-[#1a1a1f]/75 bg-transparent border border-transparent hover:border-[#1a1a1f]/15 rounded-md px-1.5 focus:outline-none focus:border-[#232369]/40"
          title="Paragraph style"
        >
          <option value="" disabled>Paragraph</option>
          <option value="p">Normal</option>
          <option value="h1">Heading 1</option>
          <option value="h2">Heading 2</option>
          <option value="h3">Heading 3</option>
          <option value="pre">Code block</option>
        </select>
        {sep}

        {/* Inline styles */}
        <button type="button" title="Bold (Ctrl+B)"        className={btn} onClick={() => exec("bold")}          data-testid={`${testid}-bold`}><Bold size={14} /></button>
        <button type="button" title="Italic (Ctrl+I)"      className={btn} onClick={() => exec("italic")}        data-testid={`${testid}-italic`}><Italic size={14} /></button>
        <button type="button" title="Underline (Ctrl+U)"   className={btn} onClick={() => exec("underline")}     data-testid={`${testid}-underline`}><Underline size={14} /></button>
        <button type="button" title="Strikethrough"        className={btn} onClick={() => exec("strikeThrough")} data-testid={`${testid}-strike`}><Strikethrough size={14} /></button>

        {/* Text color popover */}
        <div className="relative">
          <button
            type="button" title="Text colour" className={btn}
            onClick={() => setShowColor((v) => !v)}
            data-testid={`${testid}-color-toggle`}
          ><Palette size={14} /></button>
          {showColor && (
            <div
              className="absolute z-30 top-full left-0 mt-1 p-2 bg-white rounded-md shadow-lg border border-[#1a1a1f]/10 grid grid-cols-5 gap-1"
              data-testid={`${testid}-color-picker`}
              onMouseLeave={() => setShowColor(false)}
            >
              {colorSwatches.map((c) => (
                <button
                  key={c} type="button" title={c}
                  onClick={() => { exec("foreColor", c); setShowColor(false); }}
                  className="w-5 h-5 rounded-full border border-[#1a1a1f]/15 hover:scale-110 transition-transform"
                  style={{ background: c }}
                  data-testid={`${testid}-color-${c}`}
                />
              ))}
              <button
                type="button" title="Reset colour"
                onClick={() => { exec("foreColor", "#1a1a1f"); setShowColor(false); }}
                className="w-5 h-5 rounded-full border border-dashed border-[#1a1a1f]/40 grid place-items-center text-[8px] text-[#1a1a1f]/60 col-span-5 mt-0.5"
              >
                reset
              </button>
            </div>
          )}
        </div>
        {sep}

        {/* Alignment */}
        <button type="button" title="Align left"    className={btn} onClick={() => exec("justifyLeft")}   data-testid={`${testid}-align-left`}><AlignLeft size={14} /></button>
        <button type="button" title="Align centre"  className={btn} onClick={() => exec("justifyCenter")} data-testid={`${testid}-align-center`}><AlignCenter size={14} /></button>
        <button type="button" title="Align right"   className={btn} onClick={() => exec("justifyRight")}  data-testid={`${testid}-align-right`}><AlignRight size={14} /></button>
        <button type="button" title="Justify"       className={btn} onClick={() => exec("justifyFull")}   data-testid={`${testid}-align-justify`}><AlignJustify size={14} /></button>
        {sep}

        {/* Lists + indent */}
        <button type="button" title="Bullet list"    className={btn} onClick={() => exec("insertUnorderedList")} data-testid={`${testid}-ul`}><List size={14} /></button>
        <button type="button" title="Numbered list"  className={btn} onClick={() => exec("insertOrderedList")}   data-testid={`${testid}-ol`}><ListOrdered size={14} /></button>
        <button type="button" title="Decrease indent" className={btn} onClick={() => exec("outdent")} data-testid={`${testid}-outdent`}><IndentDecrease size={14} /></button>
        <button type="button" title="Increase indent" className={btn} onClick={() => exec("indent")}  data-testid={`${testid}-indent`}><IndentIncrease size={14} /></button>
        {sep}

        {/* Blocks + link */}
        <button type="button" title="Blockquote"       className={btn} onClick={() => setBlock("blockquote")} data-testid={`${testid}-quote`}><Quote size={14} /></button>
        <button type="button" title="Horizontal rule"  className={btn} onClick={() => exec("insertHorizontalRule")} data-testid={`${testid}-hr`}><Minus size={14} /></button>
        <button type="button" title="Link"             className={btn} onClick={insertLink} data-testid={`${testid}-link`}><LinkIcon size={14} /></button>
        <button type="button" title="Clear formatting" className={btn} onClick={() => exec("removeFormat")} data-testid={`${testid}-clear`}><Eraser size={14} /></button>
        {sep}

        {/* History */}
        <button type="button" title="Undo (Ctrl+Z)" className={btn} onClick={() => exec("undo")} data-testid={`${testid}-undo`}><Undo2 size={14} /></button>
        <button type="button" title="Redo (Ctrl+Y)" className={btn} onClick={() => exec("redo")} data-testid={`${testid}-redo`}><Redo2 size={14} /></button>
      </div>
      <div
        ref={ref}
        contentEditable
        suppressContentEditableWarning
        onInput={onInput}
        onBlur={onInput}
        data-testid={`${testid}-area`}
        className="rte-area min-h-[240px] max-h-[440px] overflow-y-auto px-3 py-2 text-sm text-[#1a1a1f] focus:outline-none
                   [&_a]:text-[#232369] [&_a]:underline
                   [&_ul]:list-disc [&_ul]:pl-6
                   [&_ol]:list-decimal [&_ol]:pl-6
                   [&_h1]:text-xl [&_h1]:font-semibold [&_h1]:mt-2 [&_h1]:mb-1
                   [&_h2]:text-lg [&_h2]:font-semibold [&_h2]:mt-2 [&_h2]:mb-1
                   [&_h3]:text-base [&_h3]:font-semibold [&_h3]:mt-2 [&_h3]:mb-1
                   [&_blockquote]:border-l-4 [&_blockquote]:border-[#1a1a1f]/15 [&_blockquote]:pl-3 [&_blockquote]:italic [&_blockquote]:text-[#1a1a1f]/70
                   [&_pre]:bg-[#f6f4ef] [&_pre]:rounded [&_pre]:px-2 [&_pre]:py-1 [&_pre]:font-mono [&_pre]:text-[12px]
                   [&_hr]:my-3 [&_hr]:border-[#1a1a1f]/15"
      />
    </div>
  );
}
